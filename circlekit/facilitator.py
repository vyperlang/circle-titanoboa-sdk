"""
BatchFacilitatorClient - calls Circle's Gateway API for verify/settle/supported.

Matches server/index.mjs:1-119 from @circlefin/x402-batching v1.0.1.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from circlekit.constants import GATEWAY_API_TESTNET_URL


@dataclass
class VerifyResponse:
    """Response from the verify endpoint."""
    is_valid: bool
    payer: Optional[str] = None
    invalid_reason: Optional[str] = None


@dataclass
class SettleResponse:
    """Response from the settle endpoint."""
    success: bool = False
    transaction: Optional[str] = None
    error_reason: Optional[str] = None
    payer: Optional[str] = None


@dataclass
class SupportedResponse:
    """Response from the supported endpoint."""
    supported: bool
    chains: Optional[Dict[str, Any]] = None


class BatchFacilitatorClient:
    """
    Client for Circle's Gateway facilitator API.

    Handles payment verification and settlement by calling the
    Gateway API endpoints.
    """

    def __init__(self, url: Optional[str] = None):
        self._url = (url or GATEWAY_API_TESTNET_URL).rstrip("/")
        self._http = httpx.AsyncClient(timeout=30.0)

    async def verify(
        self,
        payment_payload: Dict[str, Any],
        payment_requirements: Dict[str, Any],
    ) -> VerifyResponse:
        """
        Verify a payment payload against the Gateway API.

        Args:
            payment_payload: The decoded payment payload from the header
            payment_requirements: The payment requirements to verify against

        Returns:
            VerifyResponse with is_valid flag
        """
        response = await self._http.post(
            f"{self._url}/v1/x402/verify",
            json={
                "paymentPayload": payment_payload,
                "paymentRequirements": payment_requirements,
            },
        )

        if response.status_code == 200:
            data = response.json()
            return VerifyResponse(
                is_valid=data.get("isValid", False),
                payer=data.get("payer"),
                invalid_reason=data.get("invalidReason"),
            )
        return VerifyResponse(is_valid=False)

    async def settle(
        self,
        payment_payload: Dict[str, Any],
        payment_requirements: Dict[str, Any],
    ) -> SettleResponse:
        """
        Submit a payment for settlement via the Gateway API.

        Args:
            payment_payload: The decoded payment payload
            payment_requirements: The payment requirements

        Returns:
            SettleResponse with transaction hash if successful

        Raises:
            ValueError: If settlement fails
        """
        response = await self._http.post(
            f"{self._url}/v1/x402/settle",
            json={
                "paymentPayload": payment_payload,
                "paymentRequirements": payment_requirements,
            },
        )

        if response.status_code == 200:
            data = response.json()
            return SettleResponse(
                success=data.get("success", True),
                transaction=data.get("transaction"),
                error_reason=data.get("errorReason"),
                payer=data.get("payer"),
            )

        error_msg = response.text
        try:
            error_data = response.json()
            error_msg = error_data.get("error", error_msg)
        except Exception:
            pass
        raise ValueError(f"Settlement failed: {error_msg}")

    async def get_supported(self) -> SupportedResponse:
        """
        Get supported chains/tokens from the Gateway API.

        Returns:
            SupportedResponse with support info
        """
        response = await self._http.get(f"{self._url}/v1/x402/supported")

        if response.status_code == 200:
            data = response.json()
            return SupportedResponse(supported=True, chains=data)
        return SupportedResponse(supported=False)

    async def close(self):
        """Close the HTTP client."""
        await self._http.aclose()
