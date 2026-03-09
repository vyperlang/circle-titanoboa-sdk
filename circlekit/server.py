"""
Server-side middleware for accepting Circle Gateway payments.

Framework-agnostic: exposes a process_request() method that takes
generic inputs and returns generic outputs. No framework imports.

Usage:
    gateway = create_gateway_middleware(seller_address='0x...', chain='arcTestnet')

    # In any framework:
    result = await gateway.process_request(
        payment_header=request.headers.get("PAYMENT-SIGNATURE"),
        path="/api/analyze",
        price="$0.01",
    )

    if isinstance(result, dict):
        # 402: return body + result["headers"] (contains PAYMENT-REQUIRED)
        ...
    else:
        # PaymentInfo: return data + result.response_headers (contains PAYMENT-RESPONSE)
        ...
"""

from dataclasses import dataclass, field
from typing import Any

from circlekit.boa_utils import parse_usdc
from circlekit.constants import (
    CHAIN_CONFIGS,
    CIRCLE_BATCHING_NAME,
    CIRCLE_BATCHING_SCHEME,
    CIRCLE_BATCHING_VERSION,
    DEFAULT_MAX_TIMEOUT_SECONDS,
    X402_VERSION,
    ChainConfig,
    get_gateway_api_url,
)
from circlekit.facilitator import BatchFacilitatorClient, SettleResponse, VerifyResponse
from circlekit.x402 import (
    PAYMENT_REQUIRED_HEADER,
    PAYMENT_RESPONSE_HEADER,
    PaymentInfo,
    decode_payment_header,
    encode_payment_required,
    encode_payment_response,
)


@dataclass
class GatewayMiddlewareConfig:
    """Configuration for Gateway middleware."""

    seller_address: str
    networks: list[str] = field(default_factory=list)
    description: str = "Paid resource"
    chain: str = "arcTestnet"
    facilitator_url: str | None = None


class GatewayMiddleware:
    """
    Framework-agnostic middleware for accepting Gateway payments.

    Uses BatchFacilitatorClient for real cryptographic verification
    and settlement via the Gateway API.
    """

    def __init__(self, config: GatewayMiddlewareConfig):
        self._config = config
        self._chain_config = CHAIN_CONFIGS.get(config.chain, CHAIN_CONFIGS["arcTestnet"])
        self._gateway_api = get_gateway_api_url(self._chain_config.is_testnet)
        facilitator_url = config.facilitator_url or self._gateway_api
        self._facilitator = BatchFacilitatorClient(url=facilitator_url)

        # Build accepted chains map: "eip155:{chain_id}" -> ChainConfig
        # If config.networks is non-empty, resolve each to ChainConfig;
        # otherwise, default to just the primary chain.
        self._accepted_chains: dict[str, ChainConfig] = {}
        if config.networks:
            for net_name in config.networks:
                cc = CHAIN_CONFIGS.get(net_name)
                if cc is None:
                    raise ValueError(
                        f"Unknown network: {net_name}. Supported: {', '.join(CHAIN_CONFIGS.keys())}"
                    )
                self._accepted_chains[f"eip155:{cc.chain_id}"] = cc
        else:
            self._accepted_chains[f"eip155:{self._chain_config.chain_id}"] = self._chain_config

    def _decode_and_resolve(
        self,
        payment_header: str,
        price: str,
    ) -> tuple[dict[str, Any], dict[str, Any], str]:
        """Decode a payment header and build server-side requirements.

        Returns:
            (header_data, server_requirements, network) on success.

        Raises:
            ValueError: On malformed header or unsupported network.
        """
        amount = parse_usdc(price)

        header_data = decode_payment_header(payment_header)
        if not isinstance(header_data, dict):
            raise ValueError("Payment header must decode to a JSON object")

        accepted = header_data.get("accepted") or {}
        if not isinstance(accepted, dict):
            raise ValueError("Invalid payment header: 'accepted' must be an object")
        network = accepted.get("network", f"eip155:{self._chain_config.chain_id}")

        if network not in self._accepted_chains:
            raise ValueError(f"Network {network} is not accepted by this server")

        matched_chain = self._accepted_chains[network]

        server_requirements = {
            "scheme": CIRCLE_BATCHING_SCHEME,
            "network": network,
            "asset": matched_chain.usdc_address,
            "amount": str(amount),
            "payTo": self._config.seller_address,
            "maxTimeoutSeconds": DEFAULT_MAX_TIMEOUT_SECONDS,
            "extra": {
                "name": CIRCLE_BATCHING_NAME,
                "version": CIRCLE_BATCHING_VERSION,
                "verifyingContract": matched_chain.gateway_address,
            },
        }

        return header_data, server_requirements, network

    def require(self, price: str, path: str) -> dict[str, Any]:
        """
        Build a 402 Payment Required response.

        Args:
            price: Price in USD (e.g., "$0.01")
            path: Request path (e.g., "/api/analyze")

        Returns:
            Dict with status, headers, and body for a 402 response.
        """
        amount = parse_usdc(price)
        body = self._build_402_response(str(amount), path)
        return {
            "status": 402,
            "headers": {PAYMENT_REQUIRED_HEADER: encode_payment_required(body)},
            "body": body,
        }

    async def verify(self, payment_header: str, price: str) -> VerifyResponse:
        """
        Verify a payment header against the Gateway API.

        Args:
            payment_header: Value of Payment-Signature header
            price: Price in USD (e.g., "$0.01")

        Returns:
            VerifyResponse with is_valid flag

        Raises:
            ValueError: On malformed header or unsupported network.
        """
        header_data, server_requirements, _network = self._decode_and_resolve(
            payment_header,
            price,
        )
        return await self._facilitator.verify(
            payload=header_data,
            requirements=server_requirements,
        )

    def _build_payment_info(
        self,
        header_data: dict[str, Any],
        settle_result: SettleResponse,
        network: str,
        price: str,
    ) -> PaymentInfo:
        """Build a PaymentInfo from a successful settle result."""
        amount = parse_usdc(price)
        payload = header_data.get("payload", header_data)
        authorization = payload.get("authorization", {})
        payer = authorization.get("from", "")
        value = str(authorization.get("value", amount))

        response_headers = {
            PAYMENT_RESPONSE_HEADER: encode_payment_response(
                {
                    "success": settle_result.success,
                    "transaction": settle_result.transaction or "",
                    "payer": payer,
                    "network": network,
                }
            )
        }

        return PaymentInfo(
            verified=True,
            payer=payer,
            amount=value,
            network=network,
            transaction=settle_result.transaction,
            response_headers=response_headers,
        )

    async def settle(self, payment_header: str, price: str) -> PaymentInfo:
        """
        Settle a verified payment via the Gateway API.

        Args:
            payment_header: Value of Payment-Signature header
            price: Price in USD (e.g., "$0.01")

        Returns:
            PaymentInfo with transaction hash and response headers.

        Raises:
            ValueError: On malformed header, unsupported network, or settlement failure.
        """
        header_data, server_requirements, network = self._decode_and_resolve(
            payment_header,
            price,
        )

        settle_result = await self._facilitator.settle(
            payload=header_data,
            requirements=server_requirements,
        )

        if not settle_result.success:
            raise ValueError(f"Payment settlement failed: {settle_result.error_reason}")

        return self._build_payment_info(header_data, settle_result, network, price)

    async def process_request(
        self,
        payment_header: str | None,
        path: str,
        price: str,
    ) -> dict[str, Any] | PaymentInfo:
        """
        Process a request that may require payment.

        Convenience method that combines require(), verify(), and settle().

        Returns either:
          - A dict {"status": 402, "body": {...}} if payment needed/failed
          - A PaymentInfo on success

        Args:
            payment_header: Value of Payment-Signature header, or None
            path: Request path (e.g., "/api/analyze")
            price: Price in USD (e.g., "$0.01")
        """
        if not payment_header:
            return self.require(price, path)

        try:
            header_data, server_requirements, network = self._decode_and_resolve(
                payment_header,
                price,
            )
        except Exception as e:
            return {
                "status": 402,
                "body": {"error": f"Invalid payment header: {e}"},
            }

        # Verify via Gateway API
        try:
            verify_result = await self._facilitator.verify(
                payload=header_data,
                requirements=server_requirements,
            )
        except Exception as e:
            return {
                "status": 402,
                "body": {"error": f"Payment verification failed: {e}"},
            }

        if not verify_result.is_valid:
            return {
                "status": 402,
                "body": {"error": "Invalid payment signature"},
            }

        # Settle via Gateway API; block access on failure
        try:
            settle_result = await self._facilitator.settle(
                payload=header_data,
                requirements=server_requirements,
            )
        except Exception as e:
            return {
                "status": 402,
                "body": {"error": f"Payment settlement failed: {e}"},
            }

        if not settle_result.success:
            return {
                "status": 402,
                "body": {
                    "error": "Payment settlement failed",
                    "reason": settle_result.error_reason,
                },
            }

        return self._build_payment_info(header_data, settle_result, network, price)

    def _build_402_response(self, amount: str, path: str) -> dict[str, Any]:
        """Build a 402 response body with one accepts entry per accepted network."""
        accepts = []
        for network_id, cc in self._accepted_chains.items():
            accepts.append(
                {
                    "scheme": CIRCLE_BATCHING_SCHEME,
                    "network": network_id,
                    "asset": cc.usdc_address,
                    "amount": amount,
                    "payTo": self._config.seller_address,
                    "maxTimeoutSeconds": DEFAULT_MAX_TIMEOUT_SECONDS,
                    "extra": {
                        "name": CIRCLE_BATCHING_NAME,
                        "version": CIRCLE_BATCHING_VERSION,
                        "verifyingContract": cc.gateway_address,
                    },
                }
            )

        return {
            "x402Version": X402_VERSION,
            "resource": {
                "url": path,
                "description": self._config.description,
                "mimeType": "application/json",
            },
            "accepts": accepts,
        }

    async def close(self):
        """Close the facilitator HTTP client."""
        await self._facilitator.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False


def create_gateway_middleware(
    seller_address: str,
    networks: list[str] | None = None,
    description: str = "Paid resource",
    chain: str = "arcTestnet",
    *,
    facilitator_url: str | None = None,
) -> GatewayMiddleware:
    """
    Create middleware for accepting Gateway payments.

    Args:
        seller_address: Your wallet address to receive payments
        networks: List of networks to accept (default: just the primary chain)
        description: Resource description for 402 responses
        chain: Primary chain for configuration
        facilitator_url: Custom facilitator URL (default: Circle Gateway API)

    Returns:
        GatewayMiddleware instance

    Example:
        gateway = create_gateway_middleware(
            seller_address='0x1234...',
            chain='arcTestnet',
        )

        # In your framework handler:
        result = await gateway.process_request(
            payment_header=request.headers.get("Payment-Signature"),
            path=request.path,
            price="$0.01",
        )
    """
    config = GatewayMiddlewareConfig(
        seller_address=seller_address,
        networks=networks or [],
        description=description,
        chain=chain,
        facilitator_url=facilitator_url,
    )
    return GatewayMiddleware(config)
