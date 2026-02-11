"""
x402 protocol implementation for Circle Gateway batching.

This module handles:
- Parsing 402 Payment Required responses
- Creating payment signatures
- Building Payment-Signature headers
- Verifying payment requirements

The x402 protocol uses HTTP 402 status codes to negotiate payments:
1. Client requests resource -> Server returns 402 with payment requirements
2. Client signs payment intent -> Sends request with Payment-Signature header
3. Server verifies signature -> Returns resource
"""

import base64
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from circlekit.constants import (
    CIRCLE_BATCHING_NAME,
    CIRCLE_BATCHING_VERSION,
    CIRCLE_BATCHING_SCHEME,
    X402_VERSION,
    USDC_DECIMALS,
)
from circlekit.boa_utils import generate_nonce
from circlekit.signer import Signer


@dataclass
class PaymentRequirements:
    """
    Payment requirements from a 402 response.

    This represents what the seller wants:
    - scheme: Payment scheme (e.g., 'exact')
    - network: Chain identifier (e.g., 'eip155:5042002')
    - asset: Token address (USDC)
    - amount: Required payment in base units
    - pay_to: Seller's address
    - max_timeout_seconds: Maximum signature validity
    - extra: Additional data (verifyingContract, name, version)
    """
    scheme: str
    network: str
    asset: str
    amount: str
    pay_to: str
    max_timeout_seconds: int = 345600  # 4 days default
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_gateway_batched(self) -> bool:
        """Check if this is a Circle Gateway batched payment."""
        return (
            self.extra.get("name") == CIRCLE_BATCHING_NAME
            and self.extra.get("version") == CIRCLE_BATCHING_VERSION
        )

    @property
    def verifying_contract(self) -> Optional[str]:
        """Get the Gateway Wallet contract address."""
        vc = self.extra.get("verifyingContract")
        if isinstance(vc, str):
            return vc
        return None

    @property
    def chain_id(self) -> int:
        """Extract chain ID from network string (eip155:CHAIN_ID)."""
        if self.network.startswith("eip155:"):
            return int(self.network.split(":")[1])
        return int(self.network)

    @property
    def amount_formatted(self) -> str:
        """Format the amount as human-readable USDC."""
        return f"${int(self.amount) / 10**USDC_DECIMALS:.6f}"


@dataclass
class X402Response:
    """
    Parsed 402 Payment Required response.

    Contains the x402 version and list of accepted payment methods.
    """
    x402_version: int
    resource: Dict[str, Any]
    accepts: List[PaymentRequirements]

    def get_gateway_option(self) -> Optional[PaymentRequirements]:
        """Get the Circle Gateway batched payment option if available."""
        for option in self.accepts:
            if option.is_gateway_batched:
                return option
        return None

    def supports_gateway(self) -> bool:
        """Check if any payment option supports Gateway batching."""
        return self.get_gateway_option() is not None


@dataclass
class PaymentPayload:
    """
    Signed payment payload to include in request header.

    Matches TS client/index.mjs:809-815 structure:
    {x402Version, payload: {authorization, signature}, resource, accepted}
    """
    x402_version: int
    signature: str
    authorization: Dict[str, Any]

    def to_header(self, accepted: PaymentRequirements, resource: Dict[str, Any]) -> str:
        """
        Encode as base64 for Payment-Signature header.

        Format matches TS SDK: {x402Version, payload: {authorization, signature}, resource, accepted}
        """
        header_data = {
            "x402Version": self.x402_version,
            "payload": {
                "authorization": self.authorization,
                "signature": self.signature,
            },
            "resource": resource,
            "accepted": {
                "scheme": accepted.scheme,
                "network": accepted.network,
                "asset": accepted.asset,
                "amount": accepted.amount,
                "payTo": accepted.pay_to,
                "maxTimeoutSeconds": accepted.max_timeout_seconds,
                "extra": accepted.extra,
            },
        }
        return base64.b64encode(json.dumps(header_data).encode()).decode()


@dataclass
class PaymentInfo:
    """
    Payment information attached to request after verification.

    Available in server handlers after successful payment.
    """
    verified: bool
    payer: str
    amount: str
    network: str
    transaction: Optional[str] = None

    @property
    def amount_formatted(self) -> str:
        """Format the amount as human-readable USDC."""
        return f"${int(self.amount) / 10**USDC_DECIMALS:.6f}"


def parse_402_response(response_body: Union[str, bytes, Dict]) -> X402Response:
    """
    Parse a 402 Payment Required response body.

    Args:
        response_body: Raw response body (JSON string, bytes, or dict)

    Returns:
        X402Response with parsed payment requirements

    Raises:
        ValueError: If response is not valid x402 format
    """
    if isinstance(response_body, bytes):
        response_body = response_body.decode()
    if isinstance(response_body, str):
        data = json.loads(response_body)
    else:
        data = response_body

    # Validate x402 structure
    if "x402Version" not in data:
        raise ValueError("Response missing x402Version field")
    if "accepts" not in data:
        raise ValueError("Response missing accepts field")

    # Parse accepts array
    accepts = []
    for opt in data["accepts"]:
        requirements = PaymentRequirements(
            scheme=opt.get("scheme", CIRCLE_BATCHING_SCHEME),
            network=opt.get("network", ""),
            asset=opt.get("asset", ""),
            amount=str(opt.get("amount", "0")),
            pay_to=opt.get("payTo", ""),
            max_timeout_seconds=opt.get("maxTimeoutSeconds", 345600),
            extra=opt.get("extra", {}),
        )
        accepts.append(requirements)

    return X402Response(
        x402_version=data["x402Version"],
        resource=data.get("resource", {}),
        accepts=accepts,
    )


class BatchEvmScheme:
    """
    Matches client/index.mjs:44-131 BatchEvmScheme.

    Creates payment payloads using the GatewayWalletBatched EIP-712 domain.
    """

    def __init__(self, signer: Signer):
        self._signer = signer

    def create_payment_payload(
        self,
        x402_version: int,
        requirements: PaymentRequirements,
    ) -> PaymentPayload:
        """
        Create a signed payment payload for x402.

        Signs an EIP-712 TransferWithAuthorization message using the
        GatewayWalletBatched domain (not USDC domain).

        Args:
            x402_version: The x402 protocol version from the 402 response
            requirements: Payment requirements from 402 response

        Returns:
            PaymentPayload with signature, authorization, and x402Version
        """
        current_time = int(time.time())
        # Per client/index.mjs:80-82
        valid_after = current_time - 600  # 10 min clock skew buffer
        valid_before = current_time + requirements.max_timeout_seconds

        nonce = generate_nonce()

        # Authorization values are STRINGS in the JSON payload
        # (per client/index.mjs:116-123), only BigInt for EIP-712 signing
        authorization = {
            "from": self._signer.address,
            "to": requirements.pay_to,
            "value": str(int(requirements.amount)),
            "validAfter": str(valid_after),
            "validBefore": str(valid_before),
            "nonce": "0x" + nonce.hex(),
        }

        # EIP-712 domain is GatewayWalletBatched (per client/index.mjs:858-864)
        # NOT USDC domain
        domain = {
            "name": CIRCLE_BATCHING_NAME,
            "version": CIRCLE_BATCHING_VERSION,
            "chainId": requirements.chain_id,
            "verifyingContract": requirements.extra["verifyingContract"],
        }

        types = {
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ]
        }

        # For EIP-712 signing, use int values (per client/index.mjs:906-913)
        signing_message = {
            "from": self._signer.address,
            "to": requirements.pay_to,
            "value": int(requirements.amount),
            "validAfter": valid_after,
            "validBefore": valid_before,
            "nonce": "0x" + nonce.hex(),
        }

        signature = self._signer.sign_typed_data(
            domain=domain,
            types=types,
            primary_type="TransferWithAuthorization",
            message=signing_message,
        )

        return PaymentPayload(
            x402_version=x402_version,
            signature=signature,
            authorization=authorization,
        )


def create_payment_payload(
    signer: Signer,
    requirements: PaymentRequirements,
    x402_version: int = X402_VERSION,
) -> PaymentPayload:
    """
    Create a signed payment payload for x402.

    Convenience wrapper around BatchEvmScheme.

    Args:
        signer: Signer instance (implements Signer protocol)
        requirements: Payment requirements from 402 response
        x402_version: x402 protocol version (default: current)

    Returns:
        PaymentPayload with signature, authorization, and x402Version
    """
    scheme = BatchEvmScheme(signer)
    return scheme.create_payment_payload(x402_version, requirements)


def create_payment_header(
    signer: Signer,
    requirements: PaymentRequirements,
    resource: Optional[Dict[str, Any]] = None,
    x402_version: int = X402_VERSION,
) -> str:
    """
    Create the Payment-Signature header value for x402.

    This is the main function for creating payment signatures.

    Args:
        signer: Signer instance
        requirements: Payment requirements from 402 response
        resource: Resource dict from 402 response
        x402_version: x402 protocol version

    Returns:
        Base64-encoded Payment-Signature header value
    """
    payload = create_payment_payload(signer, requirements, x402_version)
    return payload.to_header(requirements, resource or {})


def decode_payment_header(header: str) -> Dict[str, Any]:
    """
    Decode a Payment-Signature header value.

    Args:
        header: Base64-encoded header value

    Returns:
        Decoded payload dict
    """
    decoded = base64.b64decode(header).decode()
    return json.loads(decoded)


def is_batch_payment(requirements: Union[Dict, PaymentRequirements]) -> bool:
    """
    Check if payment requirements are for Gateway batching.

    Checks both name AND version (per index.mjs:7-13).

    Args:
        requirements: Payment requirements (dict or PaymentRequirements)

    Returns:
        True if this is a Circle Gateway batched payment
    """
    if isinstance(requirements, PaymentRequirements):
        return requirements.is_gateway_batched

    extra = requirements.get("extra", {})
    return (
        extra.get("name") == CIRCLE_BATCHING_NAME
        and extra.get("version") == CIRCLE_BATCHING_VERSION
    )


def get_verifying_contract(requirements: Union[Dict, PaymentRequirements]) -> Optional[str]:
    """
    Extract the GatewayWallet contract address from payment requirements.

    Verifies that verifyingContract is a string (per index.mjs:19-23).

    Args:
        requirements: Payment requirements (dict or PaymentRequirements)

    Returns:
        GatewayWallet contract address, or None if not valid
    """
    if isinstance(requirements, PaymentRequirements):
        return requirements.verifying_contract

    extra = requirements.get("extra", {})
    vc = extra.get("verifyingContract")
    if isinstance(vc, str):
        return vc
    return None


def build_402_response(
    seller_address: str,
    amount: str,
    chain_id: int,
    usdc_address: str,
    gateway_address: str,
    description: str = "Paid resource",
) -> Dict[str, Any]:
    """
    Build a 402 response body for a seller.

    This is used by server middleware to construct proper 402 responses.

    Args:
        seller_address: Address to receive payment
        amount: Amount in USDC base units (string)
        chain_id: Chain ID
        usdc_address: USDC contract address
        gateway_address: Gateway Wallet contract address
        description: Resource description

    Returns:
        Dict suitable for JSON response
    """
    return {
        "x402Version": X402_VERSION,
        "resource": {
            "url": "",  # Will be filled by middleware
            "description": description,
            "mimeType": "application/json",
        },
        "accepts": [
            {
                "scheme": CIRCLE_BATCHING_SCHEME,
                "network": f"eip155:{chain_id}",
                "asset": usdc_address,
                "amount": amount,
                "payTo": seller_address,
                "maxTimeoutSeconds": 345600,
                "extra": {
                    "name": CIRCLE_BATCHING_NAME,
                    "version": CIRCLE_BATCHING_VERSION,
                    "verifyingContract": gateway_address,
                },
            }
        ],
    }
