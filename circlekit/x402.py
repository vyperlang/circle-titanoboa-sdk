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
import warnings
from dataclasses import dataclass, field
from typing import Any

from circlekit.boa_utils import generate_nonce
from circlekit.constants import (
    CIRCLE_BATCHING_NAME,
    CIRCLE_BATCHING_SCHEME,
    CIRCLE_BATCHING_VERSION,
    DEFAULT_MAX_TIMEOUT_SECONDS,
    USDC_DECIMALS,
    X402_VERSION,
)
from circlekit.signer import Signer

# x402 v2 header names
PAYMENT_REQUIRED_HEADER = "PAYMENT-REQUIRED"
PAYMENT_SIGNATURE_HEADER = "Payment-Signature"
PAYMENT_RESPONSE_HEADER = "PAYMENT-RESPONSE"


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
    max_timeout_seconds: int = DEFAULT_MAX_TIMEOUT_SECONDS
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_gateway_batched(self) -> bool:
        """Check if this is a Circle Gateway batched payment."""
        return (
            self.extra.get("name") == CIRCLE_BATCHING_NAME
            and self.extra.get("version") == CIRCLE_BATCHING_VERSION
        )

    @property
    def verifying_contract(self) -> str | None:
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
        return f"{int(self.amount) / 10**USDC_DECIMALS:.6f}"


@dataclass
class X402Response:
    """
    Parsed 402 Payment Required response.

    Contains the x402 version and list of accepted payment methods.
    """

    x402_version: int
    resource: dict[str, Any]
    accepts: list[PaymentRequirements]

    def get_gateway_option(self) -> PaymentRequirements | None:
        """Get the Circle Gateway batched payment option if available."""
        for option in self.accepts:
            if option.is_gateway_batched:
                return option
        return None

    def supports_gateway(self) -> bool:
        """Check if any payment option supports Gateway batching.

        .. deprecated::
            Use ``get_gateway_option() is not None`` instead.
        """
        warnings.warn(
            "supports_gateway() is deprecated, use get_gateway_option() is not None",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.get_gateway_option() is not None


@dataclass
class PaymentPayload:
    """
    Signed payment payload to include in request header.

    Structure: {x402Version, payload: {authorization, signature}, resource, accepted}
    """

    x402_version: int
    signature: str
    authorization: dict[str, Any]

    def to_header(self, accepted: PaymentRequirements, resource: dict[str, Any]) -> str:
        """
        Encode as base64 for Payment-Signature header.

        Format: {x402Version, payload: {authorization, signature}, resource, accepted}
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
    transaction: str | None = None
    response_headers: dict[str, str] = field(default_factory=dict)

    @property
    def amount_formatted(self) -> str:
        """Format the amount as human-readable USDC.

        .. deprecated::
            Use ``format_usdc(int(info.amount))`` instead.
        """
        warnings.warn(
            "PaymentInfo.amount_formatted is deprecated, use format_usdc(int(info.amount)) instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return f"{int(self.amount) / 10**USDC_DECIMALS:.6f}"


def _parse_x402_dict(data: dict) -> X402Response:
    """
    Parse a dict into an X402Response.

    Shared logic for both body-based and header-based parsing.

    Args:
        data: Parsed dict with x402Version and accepts fields

    Returns:
        X402Response with parsed payment requirements

    Raises:
        ValueError: If data is not valid x402 format
    """
    if "x402Version" not in data:
        raise ValueError("Response missing x402Version field")
    if "accepts" not in data:
        raise ValueError("Response missing accepts field")

    accepts = []
    for opt in data["accepts"]:
        requirements = PaymentRequirements(
            scheme=opt.get("scheme", CIRCLE_BATCHING_SCHEME),
            network=opt.get("network", ""),
            asset=opt.get("asset", ""),
            amount=str(opt.get("amount", "0")),
            pay_to=opt.get("payTo", ""),
            max_timeout_seconds=opt.get("maxTimeoutSeconds", DEFAULT_MAX_TIMEOUT_SECONDS),
            extra=opt.get("extra", {}),
        )
        accepts.append(requirements)

    return X402Response(
        x402_version=data["x402Version"],
        resource=data.get("resource", {}),
        accepts=accepts,
    )


def parse_402_response(response_body: str | bytes | dict) -> X402Response:
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
    data = json.loads(response_body) if isinstance(response_body, str) else response_body

    return _parse_x402_dict(data)


def get_payment_required(
    header: str | None,
    body: str | bytes | dict | None = None,
) -> X402Response:
    """
    Extract payment requirements from a 402 response.

    Handles both v2 (header) and v1 (body) formats:
    - If PAYMENT-REQUIRED header is present, decode it (strict; raises on malformed).
    - If header is absent, parse body but only accept x402Version == 1.
    - Otherwise raise ValueError.

    Args:
        header: Value of the PAYMENT-REQUIRED header, or None
        body: Response body (for v1 compatibility)

    Returns:
        X402Response with parsed payment requirements

    Raises:
        ValueError: If no valid payment required info found
    """
    if header:
        return decode_payment_required(header)

    if body is not None:
        if isinstance(body, bytes):
            body = body.decode()
        data = json.loads(body) if isinstance(body, str) else body

        if isinstance(data, dict) and data.get("x402Version") == 1:
            return _parse_x402_dict(data)

    raise ValueError(
        "Invalid payment required response: no PAYMENT-REQUIRED header and body is not a valid v1 x402 response"
    )


def encode_payment_required(data: dict) -> str:
    """
    Encode payment requirements as a base64 string for the PAYMENT-REQUIRED header.

    Args:
        data: Payment requirements dict (x402Version, accepts, resource, etc.)

    Returns:
        Base64-encoded JSON string
    """
    return base64.b64encode(json.dumps(data).encode()).decode()


def decode_payment_required(header: str) -> X402Response:
    """
    Decode a PAYMENT-REQUIRED header value into an X402Response.

    Args:
        header: Base64-encoded header value

    Returns:
        X402Response with parsed payment requirements

    Raises:
        ValueError: If header is not valid x402 format
    """
    decoded = base64.b64decode(header).decode()
    data = json.loads(decoded)
    return _parse_x402_dict(data)


def encode_payment_response(settle_info: dict) -> str:
    """
    Encode settlement info as a base64 string for the PAYMENT-RESPONSE header.

    Args:
        settle_info: Settlement info dict (success, transaction, payer, network)

    Returns:
        Base64-encoded JSON string
    """
    return base64.b64encode(json.dumps(settle_info).encode()).decode()


def decode_payment_response(header: str) -> dict[str, Any]:
    """
    Decode a PAYMENT-RESPONSE header value.

    Args:
        header: Base64-encoded header value

    Returns:
        Decoded settlement receipt dict
    """
    decoded = base64.b64decode(header).decode()
    result: dict[str, Any] = json.loads(decoded)
    return result


class BatchEvmScheme:
    """
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
        valid_after = current_time - 600  # 10 min clock skew buffer
        valid_before = current_time + requirements.max_timeout_seconds

        nonce = generate_nonce()

        # Authorization values are STRINGS in the JSON payload, only int for EIP-712 signing
        authorization = {
            "from": self._signer.address,
            "to": requirements.pay_to,
            "value": str(int(requirements.amount)),
            "validAfter": str(valid_after),
            "validBefore": str(valid_before),
            "nonce": "0x" + nonce.hex(),
        }

        # EIP-712 domain is GatewayWalletBatched, NOT USDC domain
        verifying_contract = requirements.extra.get("verifyingContract")
        if not verifying_contract:
            raise ValueError("Payment requirements missing 'verifyingContract' in extra field")

        domain = {
            "name": CIRCLE_BATCHING_NAME,
            "version": CIRCLE_BATCHING_VERSION,
            "chainId": requirements.chain_id,
            "verifyingContract": verifying_contract,
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

        # For EIP-712 signing, use int values
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
    resource: dict[str, Any] | None = None,
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


def decode_payment_header(header: str) -> dict[str, Any]:
    """
    Decode a Payment-Signature header value.

    Args:
        header: Base64-encoded header value

    Returns:
        Decoded payload dict
    """
    decoded = base64.b64decode(header).decode()
    result: dict[str, Any] = json.loads(decoded)
    return result


def is_batch_payment(requirements: dict | PaymentRequirements) -> bool:
    """
    Check if payment requirements are for Gateway batching.

    Checks both name AND version.

    Args:
        requirements: Payment requirements (dict or PaymentRequirements)

    Returns:
        True if this is a Circle Gateway batched payment
    """
    if isinstance(requirements, PaymentRequirements):
        return requirements.is_gateway_batched

    extra = requirements.get("extra", {})
    return bool(
        extra.get("name") == CIRCLE_BATCHING_NAME
        and extra.get("version") == CIRCLE_BATCHING_VERSION
    )


def get_verifying_contract(requirements: dict | PaymentRequirements) -> str | None:
    """
    Extract the GatewayWallet contract address from payment requirements.

    Verifies that verifyingContract is a string.

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
) -> dict[str, Any]:
    """
    Build a 402 response body for a seller.

    .. deprecated::
        Use :func:`create_gateway_middleware` and its ``require()`` method instead.

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
    warnings.warn(
        "build_402_response() is deprecated, use create_gateway_middleware().require() instead",
        DeprecationWarning,
        stacklevel=2,
    )
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
                "maxTimeoutSeconds": DEFAULT_MAX_TIMEOUT_SECONDS,
                "extra": {
                    "name": CIRCLE_BATCHING_NAME,
                    "version": CIRCLE_BATCHING_VERSION,
                    "verifyingContract": gateway_address,
                },
            }
        ],
    }
