"""
x402 Protocol implementation for Circle Gateway.

This module handles:
- Parsing 402 Payment Required responses
- Creating payment signatures
- Building Payment-Signature headers
- Verifying payment requirements

The x402 protocol uses HTTP 402 status codes to negotiate payments:
1. Client requests resource → Server returns 402 with payment requirements
2. Client signs payment intent → Sends request with Payment-Signature header
3. Server verifies signature → Returns resource
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
    MIN_SIGNATURE_VALIDITY_SECONDS,
    USDC_DECIMALS,
    USDC_TOKEN_NAME,
    USDC_TOKEN_VERSION,
    EIP712_DOMAIN_TYPE,
    TRANSFER_WITH_AUTHORIZATION_TYPE,
)
from circlekit.boa_utils import generate_nonce, sign_typed_data


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
        return self.extra.get("name") == CIRCLE_BATCHING_NAME
    
    @property
    def verifying_contract(self) -> Optional[str]:
        """Get the Gateway Wallet contract address."""
        return self.extra.get("verifyingContract")
    
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
    
    Contains the signed TransferWithAuthorization for USDC.
    """
    signature: str
    authorization: Dict[str, Any]
    
    def to_header(self, accepted: PaymentRequirements) -> str:
        """
        Encode as base64 for Payment-Signature header.
        
        Format: base64(JSON({...payload, accepted: requirements}))
        """
        payload = {
            "signature": self.signature,
            "authorization": self.authorization,
            "accepted": {
                "scheme": accepted.scheme,
                "network": accepted.network,
                "asset": accepted.asset,
                "amount": accepted.amount,
                "payTo": accepted.pay_to,
                "maxTimeoutSeconds": accepted.max_timeout_seconds,
                "extra": accepted.extra,
            }
        }
        return base64.b64encode(json.dumps(payload).encode()).decode()


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


def create_payment_payload(
    private_key: str,
    payer_address: str,
    requirements: PaymentRequirements,
) -> PaymentPayload:
    """
    Create a signed payment payload for x402.
    
    Signs an EIP-712 TransferWithAuthorization message that allows
    the Gateway to transfer USDC from the payer to the seller.
    
    Args:
        private_key: Payer's private key
        payer_address: Payer's wallet address
        requirements: Payment requirements from 402 response
        
    Returns:
        PaymentPayload with signature and authorization data
    """
    # Get current timestamp and calculate validity window
    current_time = int(time.time())
    valid_after = current_time
    valid_before = current_time + MIN_SIGNATURE_VALIDITY_SECONDS
    
    # Generate random nonce
    nonce = generate_nonce()
    
    # Build the authorization message
    authorization = {
        "from": payer_address,
        "to": requirements.pay_to,
        "value": int(requirements.amount),
        "validAfter": valid_after,
        "validBefore": valid_before,
        "nonce": "0x" + nonce.hex(),
    }
    
    # Build EIP-712 domain for USDC
    domain = {
        "name": USDC_TOKEN_NAME,
        "version": USDC_TOKEN_VERSION,
        "chainId": requirements.chain_id,
        "verifyingContract": requirements.asset,  # USDC address
    }
    
    # Define message types
    message_types = {
        "TransferWithAuthorization": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
        ]
    }
    
    # Sign the typed data
    signature = sign_typed_data(
        private_key=private_key,
        domain_data=domain,
        message_types=message_types,
        message_data=authorization,
        primary_type="TransferWithAuthorization",
    )
    
    return PaymentPayload(
        signature=signature,
        authorization=authorization,
    )


def create_payment_header(
    private_key: str,
    payer_address: str,
    requirements: PaymentRequirements,
) -> str:
    """
    Create the Payment-Signature header value for x402.
    
    This is the main function for creating payment signatures.
    
    Args:
        private_key: Payer's private key
        payer_address: Payer's wallet address  
        requirements: Payment requirements from 402 response
        
    Returns:
        Base64-encoded Payment-Signature header value
    """
    payload = create_payment_payload(private_key, payer_address, requirements)
    return payload.to_header(requirements)


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
    
    Args:
        requirements: Payment requirements (dict or PaymentRequirements)
        
    Returns:
        True if this is a Circle Gateway batched payment
    """
    if isinstance(requirements, PaymentRequirements):
        return requirements.is_gateway_batched
    
    extra = requirements.get("extra", {})
    return extra.get("name") == CIRCLE_BATCHING_NAME


def get_verifying_contract(requirements: Union[Dict, PaymentRequirements]) -> Optional[str]:
    """
    Extract the GatewayWallet contract address from payment requirements.
    
    This is the contract that will execute the batched settlement.
    
    Args:
        requirements: Payment requirements (dict or PaymentRequirements)
        
    Returns:
        GatewayWallet contract address, or None if not a batch payment
    """
    if isinstance(requirements, PaymentRequirements):
        return requirements.verifying_contract
    
    extra = requirements.get("extra", {})
    return extra.get("verifyingContract")


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
                "maxTimeoutSeconds": MIN_SIGNATURE_VALIDITY_SECONDS,
                "extra": {
                    "name": CIRCLE_BATCHING_NAME,
                    "version": CIRCLE_BATCHING_VERSION,
                    "verifyingContract": gateway_address,
                },
            }
        ],
    }
