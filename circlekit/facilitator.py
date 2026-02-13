"""
BatchFacilitatorClient - calls Circle's Gateway API for verify/settle/supported.

Structurally compatible with x402's FacilitatorClient protocol (duck-typed).
If the x402 package is installed, this client can be used directly with
x402ResourceServer without any adapter.
"""

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

import asyncio

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

    Args:
        url: Gateway API base URL (default: testnet)
        create_auth_headers: Optional async callable that returns per-endpoint
            auth headers. Should return a dict with optional keys ``verify``,
            ``settle``, and ``supported``, each mapping to a dict of headers.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        create_auth_headers: Optional[Callable[[], Awaitable[Dict[str, Dict[str, str]]]]] = None,
    ):
        self._url = (url or GATEWAY_API_TESTNET_URL).rstrip("/")
        self._http = httpx.AsyncClient(timeout=30.0)
        self._create_auth_headers = create_auth_headers

    async def _get_auth_headers(self, endpoint: str) -> Dict[str, str]:
        """Get auth headers for a specific endpoint."""
        if self._create_auth_headers is None:
            return {}
        auth = await self._create_auth_headers()
        return auth.get(endpoint, {})

    def _get_auth_headers_sync(self, endpoint: str) -> Dict[str, str]:
        """Get auth headers synchronously (for sync methods like get_supported).

        When called from an async context (running event loop), delegates to
        a background thread to avoid ``asyncio.run()`` conflicts.
        """
        if self._create_auth_headers is None:
            return {}
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            auth = asyncio.run(self._create_auth_headers())
        else:
            # Inside an async context — run in a thread to avoid nested loop.
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=1) as pool:
                auth = pool.submit(asyncio.run, self._create_auth_headers()).result()
        return auth.get(endpoint, {})

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

        Raises:
            ValueError: If the API response is malformed
        """
        payload_dict = _to_dict(payment_payload)
        requirements_dict = _to_dict(payment_requirements)

        headers = await self._get_auth_headers("verify")
        response = await self._http.post(
            f"{self._url}/v1/x402/verify",
            headers=headers,
            json={
                "paymentPayload": payload_dict,
                "paymentRequirements": requirements_dict,
            },
        )

        data = response.json()
        if isinstance(data, dict) and "isValid" in data:
            return VerifyResponse(
                is_valid=data.get("isValid", False),
                payer=data.get("payer"),
                invalid_reason=data.get("invalidReason"),
            )
        raise ValueError(
            f"Gateway verify failed ({response.status_code}): {data}"
        )

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
            ValueError: If the API response is malformed or missing expected fields
        """
        payload_dict = _to_dict(payment_payload)
        requirements_dict = _to_dict(payment_requirements)

        headers = await self._get_auth_headers("settle")
        response = await self._http.post(
            f"{self._url}/v1/x402/settle",
            headers=headers,
            json={
                "paymentPayload": payload_dict,
                "paymentRequirements": requirements_dict,
            },
        )

        data = response.json()
        if isinstance(data, dict) and "success" in data:
            return SettleResponse(
                success=data["success"],
                transaction=data.get("transaction"),
                error_reason=data.get("errorReason"),
                payer=data.get("payer"),
                network=requirements_dict.get("network"),
            )
        raise ValueError(
            f"Gateway settle failed ({response.status_code}): {data}"
        )

    def get_supported(self) -> SupportedResponse:
        """
        Get supported chains/tokens from the Gateway API.

        Note: This method is sync (not async). x402's initialize() calls
        get_supported() synchronously during server startup, so the
        FacilitatorClient protocol requires it to be sync.

        Returns:
            SupportedResponse with kinds list

        Raises:
            ValueError: If the API returns a non-OK response
        """
        headers = self._get_auth_headers_sync("supported")
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{self._url}/v1/x402/supported", headers=headers)

        if not (200 <= response.status_code < 300):
            error_text = response.text
            raise ValueError(
                f"Gateway getSupported failed ({response.status_code}): {error_text}"
            )
        data = response.json()
        return _parse_supported_response(data)

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
