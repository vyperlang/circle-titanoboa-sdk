"""
BatchFacilitatorClient - calls Circle's Gateway API for verify/settle/supported.

Matches server/index.mjs:1-119 from @circlefin/x402-batching v1.0.1.

Structurally compatible with x402's FacilitatorClient protocol (duck-typed).
If the x402 package is installed, this client can be used directly with
x402ResourceServer without any adapter.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from circlekit.constants import GATEWAY_API_TESTNET_URL


def _to_dict(obj: Any) -> Dict[str, Any]:
    """Normalize a payload to dict.

    Accepts plain dicts, Pydantic models (.model_dump), or any mapping.
    """
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump(by_alias=True)
    return dict(obj)


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
    network: Optional[str] = None


@dataclass
class SupportedKind:
    """A supported payment kind (network + scheme)."""
    x402_version: int
    scheme: str
    network: str
    extra: Optional[Dict[str, Any]] = None


@dataclass
class SupportedResponse:
    """Response from the supported endpoint.

    Compatible with x402's SupportedResponse (has .kinds attribute).
    """
    kinds: List[SupportedKind] = field(default_factory=list)
    extensions: List[str] = field(default_factory=list)
    signers: Dict[str, List[str]] = field(default_factory=dict)


class BatchFacilitatorClient:
    """
    Client for Circle's Gateway facilitator API.

    Handles payment verification and settlement by calling the
    Gateway API endpoints.

    Structurally satisfies x402's FacilitatorClient protocol:
      - verify(payload, requirements) -> VerifyResponse  (async)
      - settle(payload, requirements) -> SettleResponse  (async)
      - get_supported() -> SupportedResponse             (sync)
      - aclose() / async context manager
    """

    def __init__(self, url: Optional[str] = None):
        self._url = (url or GATEWAY_API_TESTNET_URL).rstrip("/")
        self._http = httpx.AsyncClient(timeout=30.0)

    async def verify(
        self,
        payment_payload: Any,
        payment_requirements: Any,
    ) -> VerifyResponse:
        """
        Verify a payment payload against the Gateway API.

        Args:
            payment_payload: The decoded payment payload (dict or Pydantic model)
            payment_requirements: The payment requirements (dict or Pydantic model)

        Returns:
            VerifyResponse with is_valid flag
        """
        payload_dict = _to_dict(payment_payload)
        requirements_dict = _to_dict(payment_requirements)

        response = await self._http.post(
            f"{self._url}/v1/x402/verify",
            json={
                "paymentPayload": payload_dict,
                "paymentRequirements": requirements_dict,
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
        payment_payload: Any,
        payment_requirements: Any,
    ) -> SettleResponse:
        """
        Submit a payment for settlement via the Gateway API.

        Args:
            payment_payload: The decoded payment payload (dict or Pydantic model)
            payment_requirements: The payment requirements (dict or Pydantic model)

        Returns:
            SettleResponse with transaction hash if successful

        Raises:
            ValueError: If settlement fails
        """
        payload_dict = _to_dict(payment_payload)
        requirements_dict = _to_dict(payment_requirements)

        response = await self._http.post(
            f"{self._url}/v1/x402/settle",
            json={
                "paymentPayload": payload_dict,
                "paymentRequirements": requirements_dict,
            },
        )

        if response.status_code == 200:
            data = response.json()
            return SettleResponse(
                success=data.get("success", True),
                transaction=data.get("transaction"),
                error_reason=data.get("errorReason"),
                payer=data.get("payer"),
                network=requirements_dict.get("network"),
            )

        error_msg = response.text
        try:
            error_data = response.json()
            error_msg = error_data.get("error", error_msg)
        except Exception:
            pass
        raise ValueError(f"Settlement failed: {error_msg}")

    def get_supported(self) -> SupportedResponse:
        """
        Get supported chains/tokens from the Gateway API.

        Note: This method is sync (not async). x402's initialize() calls
        get_supported() synchronously during server startup, so the
        FacilitatorClient protocol requires it to be sync. This is a
        breaking change from the previous async version — callers that
        used ``await client.get_supported()`` should remove the ``await``.

        Returns:
            SupportedResponse with kinds list
        """
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{self._url}/v1/x402/supported")

        if response.status_code == 200:
            data = response.json()
            return _parse_supported_response(data)
        return SupportedResponse()

    async def close(self):
        """Close the HTTP client."""
        await self._http.aclose()

    async def aclose(self):
        """Close the HTTP client (x402 protocol naming)."""
        await self.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False


def _parse_supported_response(data: Any) -> SupportedResponse:
    """Parse the Gateway API /supported response into SupportedResponse.

    The Gateway API returns a dict like:
        {"eip155:8453": ["exact"], "eip155:84532": ["exact"]}
    or a structured response with "kinds" already present.
    """
    # If it already has a "kinds" key, parse it directly
    if isinstance(data, dict) and "kinds" in data:
        kinds = []
        for kind_data in data["kinds"]:
            kinds.append(SupportedKind(
                x402_version=kind_data.get("x402Version", 2),
                scheme=kind_data.get("scheme", "exact"),
                network=kind_data.get("network", ""),
                extra=kind_data.get("extra"),
            ))
        return SupportedResponse(
            kinds=kinds,
            extensions=data.get("extensions", []),
            signers=data.get("signers", {}),
        )

    # Otherwise assume it's a flat dict: {network: [schemes]}
    if isinstance(data, dict):
        kinds = []
        for network, schemes in data.items():
            if isinstance(schemes, list):
                for scheme in schemes:
                    kinds.append(SupportedKind(
                        x402_version=2,
                        scheme=scheme,
                        network=network,
                    ))
        return SupportedResponse(kinds=kinds)

    return SupportedResponse()
