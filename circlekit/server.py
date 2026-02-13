"""
Server-side middleware for accepting Circle Gateway payments.

Framework-agnostic — exposes a process_request() method that takes
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
        # 402 — return body + result["headers"] (contains PAYMENT-REQUIRED)
        ...
    else:
        # PaymentInfo — return data + result.response_headers (contains PAYMENT-RESPONSE)
        ...
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from circlekit.constants import (
    CHAIN_CONFIGS,
    ChainConfig,
    get_gateway_api_url,
)
from circlekit.boa_utils import parse_usdc
from circlekit.facilitator import BatchFacilitatorClient, VerifyResponse
from circlekit.x402 import (
    decode_payment_header,
    encode_payment_required,
    encode_payment_response,
    PaymentInfo,
    PAYMENT_REQUIRED_HEADER,
    PAYMENT_RESPONSE_HEADER,
)


@dataclass
class GatewayMiddlewareConfig:
    """Configuration for Gateway middleware."""
    seller_address: str
    networks: List[str] = field(default_factory=list)
    description: str = "Paid resource"
    chain: str = "arcTestnet"


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
        self._facilitator = BatchFacilitatorClient(url=self._gateway_api)

        # Build accepted chains map: "eip155:{chain_id}" -> ChainConfig
        # If config.networks is non-empty, resolve each to ChainConfig;
        # otherwise, default to just the primary chain.
        self._accepted_chains: Dict[str, ChainConfig] = {}
        if config.networks:
            for net_name in config.networks:
                cc = CHAIN_CONFIGS.get(net_name)
                if cc is None:
                    raise ValueError(
                        f"Unknown network: {net_name}. "
                        f"Supported: {', '.join(CHAIN_CONFIGS.keys())}"
                    )
                self._accepted_chains[f"eip155:{cc.chain_id}"] = cc
        else:
            self._accepted_chains[f"eip155:{self._chain_config.chain_id}"] = self._chain_config

    def _decode_and_resolve(
        self,
        payment_header: str,
        price: str,
    ) -> tuple:
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
            "scheme": "exact",
            "network": network,
            "asset": matched_chain.usdc_address,
            "amount": str(amount),
            "payTo": self._config.seller_address,
            "maxTimeoutSeconds": 345600,
            "extra": {
                "name": "GatewayWalletBatched",
                "version": "1",
                "verifyingContract": matched_chain.gateway_address,
            },
        }

        return header_data, server_requirements, network

    def require(self, price: str, path: str) -> Dict[str, Any]:
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
            payment_header, price,
        )
        return await self._facilitator.verify(
            payment_payload=header_data,
            payment_requirements=server_requirements,
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
            payment_header, price,
        )
        amount = parse_usdc(price)

        settle_result = await self._facilitator.settle(
            payment_payload=header_data,
            payment_requirements=server_requirements,
        )

        if not settle_result.success:
            raise ValueError(
                f"Payment settlement failed: {settle_result.error_reason}"
            )

        payload = header_data.get("payload", header_data)
        authorization = payload.get("authorization", {})
        payer = authorization.get("from", "")
        value = str(authorization.get("value", amount))

        response_headers = {
            PAYMENT_RESPONSE_HEADER: encode_payment_response({
                "success": settle_result.success,
                "transaction": settle_result.transaction or "",
                "payer": payer,
                "network": network,
            })
        }

        return PaymentInfo(
            verified=True,
            payer=payer,
            amount=value,
            network=network,
            transaction=settle_result.transaction,
            response_headers=response_headers,
        )

    async def process_request(
        self,
        payment_header: Optional[str],
        path: str,
        price: str,
    ) -> Union[Dict[str, Any], PaymentInfo]:
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
                payment_header, price,
            )
        except (ValueError, Exception) as e:
            return {
                "status": 402,
                "body": {"error": f"Invalid payment header: {e}"},
            }

        # Verify via Gateway API
        try:
            verify_result = await self._facilitator.verify(
                payment_payload=header_data,
                payment_requirements=server_requirements,
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

        # Settle via Gateway API — block access on failure
        try:
            settle_result = await self._facilitator.settle(
                payment_payload=header_data,
                payment_requirements=server_requirements,
            )
        except Exception as e:
            return {
                "status": 402,
                "body": {"error": f"Payment settlement failed: {e}"},
            }

        if not settle_result.success:
            return {
                "status": 402,
                "body": {"error": "Payment settlement failed", "reason": settle_result.error_reason},
            }

        amount = parse_usdc(price)
        payload = header_data.get("payload", header_data)
        authorization = payload.get("authorization", {})
        payer = authorization.get("from", "")
        value = str(authorization.get("value", amount))

        response_headers = {
            PAYMENT_RESPONSE_HEADER: encode_payment_response({
                "success": settle_result.success,
                "transaction": settle_result.transaction or "",
                "payer": payer,
                "network": network,
            })
        }

        return PaymentInfo(
            verified=True,
            payer=payer,
            amount=value,
            network=network,
            transaction=settle_result.transaction,
            response_headers=response_headers,
        )

    def _build_402_response(self, amount: str, path: str) -> Dict[str, Any]:
        """Build a 402 response body with one accepts entry per accepted network."""
        from circlekit.constants import CIRCLE_BATCHING_NAME, CIRCLE_BATCHING_VERSION, CIRCLE_BATCHING_SCHEME, X402_VERSION

        accepts = []
        for network_id, cc in self._accepted_chains.items():
            accepts.append({
                "scheme": CIRCLE_BATCHING_SCHEME,
                "network": network_id,
                "asset": cc.usdc_address,
                "amount": amount,
                "payTo": self._config.seller_address,
                "maxTimeoutSeconds": 345600,
                "extra": {
                    "name": CIRCLE_BATCHING_NAME,
                    "version": CIRCLE_BATCHING_VERSION,
                    "verifyingContract": cc.gateway_address,
                },
            })

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


def create_gateway_middleware(
    seller_address: str,
    networks: Optional[List[str]] = None,
    description: str = "Paid resource",
    chain: str = "arcTestnet",
) -> GatewayMiddleware:
    """
    Create middleware for accepting Gateway payments.

    Args:
        seller_address: Your wallet address to receive payments
        networks: List of networks to accept (default: just the primary chain)
        description: Resource description for 402 responses
        chain: Primary chain for configuration

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
    )
    return GatewayMiddleware(config)
