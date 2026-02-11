"""
Tests for x402 package integration.

Tests that BatchFacilitatorClient is structurally compatible with x402's
FacilitatorClient protocol and that create_resource_server works.

Run with: .venv/bin/pytest tests/test_x402_integration.py -v
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# ============================================================================
# TEST: _to_dict helper
# ============================================================================


class TestToDict:
    """Test the _to_dict normalization helper."""

    def test_dict_passthrough(self):
        from circlekit.facilitator import _to_dict
        d = {"foo": "bar"}
        assert _to_dict(d) is d

    def test_pydantic_model(self):
        from circlekit.facilitator import _to_dict

        class FakeModel:
            def model_dump(self, by_alias=False):
                return {"fooBar": "baz"} if by_alias else {"foo_bar": "baz"}

        result = _to_dict(FakeModel())
        assert result == {"fooBar": "baz"}

    def test_mapping_fallback(self):
        from circlekit.facilitator import _to_dict
        from collections import OrderedDict
        od = OrderedDict([("a", 1), ("b", 2)])
        result = _to_dict(od)
        # OrderedDict is a dict subclass, so it's returned as-is
        assert result is od


# ============================================================================
# TEST: BatchFacilitatorClient protocol compatibility
# ============================================================================


class TestBatchFacilitatorProtocol:
    """Test that BatchFacilitatorClient matches x402's FacilitatorClient protocol."""

    def test_has_verify_method(self):
        from circlekit.facilitator import BatchFacilitatorClient
        import inspect
        client = BatchFacilitatorClient()
        assert hasattr(client, "verify")
        assert inspect.iscoroutinefunction(client.verify)

    def test_has_settle_method(self):
        from circlekit.facilitator import BatchFacilitatorClient
        import inspect
        client = BatchFacilitatorClient()
        assert hasattr(client, "settle")
        assert inspect.iscoroutinefunction(client.settle)

    def test_has_get_supported_method(self):
        from circlekit.facilitator import BatchFacilitatorClient
        import inspect
        client = BatchFacilitatorClient()
        assert hasattr(client, "get_supported")
        # get_supported must be sync (x402's initialize() calls it synchronously)
        assert not inspect.iscoroutinefunction(client.get_supported)

    def test_has_aclose_method(self):
        from circlekit.facilitator import BatchFacilitatorClient
        import inspect
        client = BatchFacilitatorClient()
        assert hasattr(client, "aclose")
        assert inspect.iscoroutinefunction(client.aclose)

    def test_has_close_method(self):
        from circlekit.facilitator import BatchFacilitatorClient
        import inspect
        client = BatchFacilitatorClient()
        assert hasattr(client, "close")
        assert inspect.iscoroutinefunction(client.close)


class TestProtocolStructuralMatch:
    """Test structural compatibility with x402's FacilitatorClient protocol."""

    def test_x402_protocol_isinstance(self):
        """BatchFacilitatorClient satisfies x402's FacilitatorClient protocol."""
        try:
            from x402.server import FacilitatorClient
        except ImportError:
            pytest.skip("x402 package not installed")

        from circlekit.facilitator import BatchFacilitatorClient
        # Protocol check — structural typing
        # We can't use isinstance with Protocol unless it's @runtime_checkable,
        # so just verify the methods exist with correct signatures
        client = BatchFacilitatorClient()
        assert hasattr(client, "verify")
        assert hasattr(client, "settle")
        assert hasattr(client, "get_supported")


# ============================================================================
# TEST: verify/settle with typed objects (Pydantic models)
# ============================================================================


class TestVerifySettleWithTypedObjects:
    """Test that verify/settle accept Pydantic model arguments (not just dicts)."""

    @pytest.mark.asyncio
    async def test_verify_with_pydantic_model(self):
        from circlekit.facilitator import BatchFacilitatorClient

        class FakePayload:
            def model_dump(self, by_alias=False):
                return {"x402Version": 2, "payload": {}, "accepted": {}}

        class FakeRequirements:
            def model_dump(self, by_alias=False):
                return {"scheme": "exact", "network": "eip155:8453"}

        client = BatchFacilitatorClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"isValid": True, "payer": "0xABC"}

        with patch.object(client._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await client.verify(FakePayload(), FakeRequirements())

        assert result.is_valid is True
        assert result.payer == "0xABC"
        # Verify the posted JSON used the model_dump output
        call_kwargs = mock_post.call_args
        json_body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "paymentPayload" in json_body
        await client.close()

    @pytest.mark.asyncio
    async def test_settle_with_pydantic_model(self):
        from circlekit.facilitator import BatchFacilitatorClient

        class FakePayload:
            def model_dump(self, by_alias=False):
                return {"x402Version": 2, "payload": {}, "accepted": {}}

        class FakeRequirements:
            def model_dump(self, by_alias=False):
                return {"scheme": "exact", "network": "eip155:8453"}

        client = BatchFacilitatorClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "transaction": "0xTXHASH",
            "payer": "0xABC",
        }

        with patch.object(client._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await client.settle(FakePayload(), FakeRequirements())

        assert result.success is True
        assert result.transaction == "0xTXHASH"
        assert result.network == "eip155:8453"
        await client.close()

    @pytest.mark.asyncio
    async def test_verify_with_dict(self):
        """Existing dict-based usage still works."""
        from circlekit.facilitator import BatchFacilitatorClient

        client = BatchFacilitatorClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"isValid": True}

        with patch.object(client._http, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await client.verify({"payload": {}}, {"scheme": "exact"})

        assert result.is_valid is True
        await client.close()


# ============================================================================
# TEST: get_supported returns SupportedResponse with .kinds
# ============================================================================


class TestGetSupported:
    """Test get_supported returns proper SupportedResponse."""

    def test_get_supported_returns_supported_response(self):
        from circlekit.facilitator import BatchFacilitatorClient, SupportedResponse

        client = BatchFacilitatorClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "eip155:8453": ["exact"],
            "eip155:84532": ["exact"],
        }

        with patch("httpx.Client") as MockClient:
            mock_client_instance = MagicMock()
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            mock_client_instance.get.return_value = mock_response
            MockClient.return_value = mock_client_instance

            result = client.get_supported()

        assert isinstance(result, SupportedResponse)
        assert hasattr(result, "kinds")
        assert len(result.kinds) == 2
        networks = {k.network for k in result.kinds}
        assert "eip155:8453" in networks
        assert "eip155:84532" in networks
        for kind in result.kinds:
            assert kind.scheme == "exact"
            assert kind.x402_version == 2

    def test_get_supported_with_structured_response(self):
        """Test when API returns x402-style structured response."""
        from circlekit.facilitator import BatchFacilitatorClient

        client = BatchFacilitatorClient()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "kinds": [
                {"x402Version": 2, "scheme": "exact", "network": "eip155:8453"},
                {"x402Version": 2, "scheme": "exact", "network": "eip155:84532"},
            ],
            "extensions": ["bazaar"],
            "signers": {"eip155": ["0xSIGNER"]},
        }

        with patch("httpx.Client") as MockClient:
            mock_client_instance = MagicMock()
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            mock_client_instance.get.return_value = mock_response
            MockClient.return_value = mock_client_instance

            result = client.get_supported()

        assert len(result.kinds) == 2
        assert result.extensions == ["bazaar"]
        assert result.signers == {"eip155": ["0xSIGNER"]}

    def test_get_supported_empty_on_failure(self):
        from circlekit.facilitator import BatchFacilitatorClient

        client = BatchFacilitatorClient()
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("httpx.Client") as MockClient:
            mock_client_instance = MagicMock()
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            mock_client_instance.get.return_value = mock_response
            MockClient.return_value = mock_client_instance

            result = client.get_supported()

        assert len(result.kinds) == 0

    def test_get_supported_is_sync(self):
        """get_supported must be sync — x402's initialize() calls it synchronously."""
        import inspect
        from circlekit.facilitator import BatchFacilitatorClient
        client = BatchFacilitatorClient()
        assert not inspect.iscoroutinefunction(client.get_supported)


# ============================================================================
# TEST: VerifyResponse / SettleResponse field compatibility
# ============================================================================


class TestResponseFieldCompatibility:
    """Test that our response dataclasses have the fields x402 expects."""

    def test_verify_response_fields(self):
        from circlekit.facilitator import VerifyResponse
        r = VerifyResponse(is_valid=True, payer="0xABC", invalid_reason=None)
        assert r.is_valid is True
        assert r.payer == "0xABC"
        assert r.invalid_reason is None

    def test_settle_response_fields(self):
        from circlekit.facilitator import SettleResponse
        r = SettleResponse(
            success=True,
            transaction="0xTX",
            network="eip155:8453",
            payer="0xABC",
        )
        assert r.success is True
        assert r.transaction == "0xTX"
        assert r.network == "eip155:8453"
        assert r.payer == "0xABC"
        assert r.error_reason is None

    def test_settle_response_has_network_field(self):
        """x402's SettleResponse requires a network field."""
        from circlekit.facilitator import SettleResponse
        r = SettleResponse()
        assert hasattr(r, "network")


# ============================================================================
# TEST: Context manager protocol
# ============================================================================


class TestContextManager:
    """Test async context manager support."""

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        from circlekit.facilitator import BatchFacilitatorClient

        async with BatchFacilitatorClient() as client:
            assert isinstance(client, BatchFacilitatorClient)
        # After exiting, the client should be closed
        # (we can't easily verify the internal state, but no error means success)

    @pytest.mark.asyncio
    async def test_aclose(self):
        from circlekit.facilitator import BatchFacilitatorClient

        client = BatchFacilitatorClient()
        await client.aclose()
        # Should not raise

    @pytest.mark.asyncio
    async def test_close(self):
        from circlekit.facilitator import BatchFacilitatorClient

        client = BatchFacilitatorClient()
        await client.close()
        # Should not raise


# ============================================================================
# TEST: create_resource_server
# ============================================================================


class TestCreateResourceServer:
    """Test the create_resource_server convenience function."""

    def test_create_resource_server_import(self):
        """create_resource_server is importable from circlekit."""
        from circlekit import create_resource_server
        assert callable(create_resource_server)

    def test_create_resource_server_from_module(self):
        """create_resource_server is importable from x402_integration."""
        from circlekit.x402_integration import create_resource_server
        assert callable(create_resource_server)

    def test_create_resource_server_returns_x402_server(self):
        """create_resource_server returns an x402ResourceServer instance."""
        try:
            from x402.server import x402ResourceServer
        except ImportError:
            pytest.skip("x402 package not installed")

        from circlekit.x402_integration import create_resource_server

        server = create_resource_server(is_testnet=True)
        assert isinstance(server, x402ResourceServer)

    def test_create_resource_server_custom_url(self):
        """create_resource_server accepts a custom URL."""
        try:
            from x402.server import x402ResourceServer
        except ImportError:
            pytest.skip("x402 package not installed")

        from circlekit.x402_integration import create_resource_server

        server = create_resource_server(url="https://custom.gateway.example.com")
        assert isinstance(server, x402ResourceServer)

    def test_create_resource_server_testnet_vs_mainnet(self):
        """create_resource_server uses correct URL for testnet/mainnet."""
        try:
            import x402  # noqa: F401
        except ImportError:
            pytest.skip("x402 package not installed")

        from circlekit.x402_integration import create_resource_server
        from circlekit.constants import GATEWAY_API_TESTNET_URL, GATEWAY_API_BASE_URL

        with patch("circlekit.facilitator.BatchFacilitatorClient") as MockClient:
            create_resource_server(is_testnet=True)
            MockClient.assert_called_with(url=GATEWAY_API_TESTNET_URL)

        with patch("circlekit.facilitator.BatchFacilitatorClient") as MockClient:
            create_resource_server(is_testnet=False)
            MockClient.assert_called_with(url=GATEWAY_API_BASE_URL)


class TestX402ResourceServerInitialize:
    """Test that x402ResourceServer.initialize() works with our client.

    This exercises the real code path: initialize() calls
    client.get_supported() (sync), iterates .kinds, and maps
    network/scheme to the facilitator client.
    """

    def test_initialize_with_mocked_supported(self):
        """x402ResourceServer.initialize() succeeds with our client's get_supported."""
        try:
            from x402.server import x402ResourceServer
        except ImportError:
            pytest.skip("x402 package not installed")

        from circlekit.facilitator import BatchFacilitatorClient, SupportedResponse, SupportedKind

        client = BatchFacilitatorClient()

        # Mock get_supported to return kinds without hitting the network
        supported = SupportedResponse(kinds=[
            SupportedKind(x402_version=2, scheme="exact", network="eip155:84532"),
            SupportedKind(x402_version=2, scheme="exact", network="eip155:8453"),
        ])
        with patch.object(client, "get_supported", return_value=supported):
            server = x402ResourceServer(client)
            server.initialize()

        # After initialize, the server should have mapped our client to those networks
        assert server._initialized is True
        assert "eip155:84532" in server._facilitator_clients_map
        assert "eip155:8453" in server._facilitator_clients_map
        assert server._facilitator_clients_map["eip155:84532"]["exact"] is client
        assert server._facilitator_clients_map["eip155:8453"]["exact"] is client

    def test_initialize_with_empty_supported(self):
        """x402ResourceServer.initialize() handles empty supported response."""
        try:
            from x402.server import x402ResourceServer
        except ImportError:
            pytest.skip("x402 package not installed")

        from circlekit.facilitator import BatchFacilitatorClient, SupportedResponse

        client = BatchFacilitatorClient()

        with patch.object(client, "get_supported", return_value=SupportedResponse()):
            server = x402ResourceServer(client)
            server.initialize()

        assert server._initialized is True
        assert len(server._facilitator_clients_map) == 0

    def test_initialize_with_http_mocked(self):
        """Full integration: get_supported makes HTTP call, parses response,
        and x402ResourceServer.initialize() consumes the result."""
        try:
            from x402.server import x402ResourceServer
        except ImportError:
            pytest.skip("x402 package not installed")

        from circlekit.facilitator import BatchFacilitatorClient

        client = BatchFacilitatorClient(url="https://gateway-api-testnet.circle.com")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "eip155:5042002": ["exact"],
        }

        with patch("httpx.Client") as MockHttpxClient:
            mock_instance = MagicMock()
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_instance.get.return_value = mock_response
            MockHttpxClient.return_value = mock_instance

            server = x402ResourceServer(client)
            server.initialize()

        assert server._initialized is True
        assert "eip155:5042002" in server._facilitator_clients_map
        assert server._facilitator_clients_map["eip155:5042002"]["exact"] is client


class TestCreateResourceServerImportError:
    """Test graceful ImportError when x402 is not installed."""

    def test_import_error_message(self):
        """create_resource_server raises ImportError with helpful message."""
        from circlekit.x402_integration import create_resource_server

        with patch.dict("sys.modules", {"x402": None, "x402.server": None}):
            with pytest.raises(ImportError, match="x402 package required"):
                create_resource_server()
