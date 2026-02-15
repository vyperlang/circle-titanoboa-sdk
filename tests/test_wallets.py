"""
Tests for circlekit.wallets — CircleWalletSigner adapter.

All tests mock the Circle SDK — no live API calls.

Run with: uv run pytest tests/test_wallets.py -v
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from circlekit.signer import Signer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_WALLET_ID = "test-wallet-id-123"
FAKE_ADDRESS = "0x1234567890abcdef1234567890abcdef12345678"
FAKE_API_KEY = "TEST_API_KEY_abc123"
FAKE_ENTITY_SECRET = "a" * 64  # 32-byte hex string

SAMPLE_DOMAIN = {
    "name": "CircleBatching",
    "version": "1",
    "chainId": 5042002,
    "verifyingContract": "0x0000000000000000000000000000000000000001",
}

SAMPLE_TYPES = {
    "Transfer": [
        {"name": "to", "type": "address"},
        {"name": "amount", "type": "uint256"},
    ],
}


# A stand-in for SignTypedDataRequest that captures constructor kwargs
class _FakeSignTypedDataRequest:
    def __init__(self, *, walletId=None, data=None, **kwargs):
        self.wallet_id = walletId
        self.data = data
        self.entity_secret_ciphertext = kwargs.get("entitySecretCiphertext", "#REFILL_PLACEHOLDER")


@pytest.fixture()
def circle_mocks():
    """Patch all Circle SDK symbols in circlekit.wallets for the duration of a test."""
    with (
        patch("circlekit.wallets.HAS_CIRCLE_WALLETS", True),
        patch("circlekit.wallets.init_developer_controlled_wallets_client") as mock_init,
        patch("circlekit.wallets.SigningApi") as mock_signing_cls,
        patch("circlekit.wallets.WalletsApi") as mock_wallets_cls,
        patch("circlekit.wallets.SignTypedDataRequest", _FakeSignTypedDataRequest),
    ):
        mock_init.return_value = MagicMock()
        mock_signing_api = MagicMock()
        mock_signing_cls.return_value = mock_signing_api
        mock_wallets_api = MagicMock()
        mock_wallets_cls.return_value = mock_wallets_api

        yield {
            "init": mock_init,
            "signing_api": mock_signing_api,
            "wallets_api": mock_wallets_api,
        }


def _make_signer(circle_mocks, wallet_address=FAKE_ADDRESS):
    """Create a CircleWalletSigner inside an active circle_mocks context."""
    from circlekit.wallets import CircleWalletSigner

    signer = CircleWalletSigner(
        wallet_id=FAKE_WALLET_ID,
        wallet_address=wallet_address,
        api_key=FAKE_API_KEY,
        entity_secret=FAKE_ENTITY_SECRET,
    )
    return signer


def _mock_sign_response(mock_signing_api, signature):
    """Configure mock signing API to return given signature."""
    mock_response = MagicMock()
    mock_response.data.signature = signature
    mock_signing_api.sign_typed_data.return_value = mock_response


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestCircleWalletSignerProtocol:
    """Verify CircleWalletSigner satisfies the Signer protocol."""

    def test_satisfies_signer_protocol(self, circle_mocks):
        signer = _make_signer(circle_mocks)
        assert isinstance(signer, Signer)

    def test_address_property(self, circle_mocks):
        signer = _make_signer(circle_mocks)
        assert signer.address == FAKE_ADDRESS

    def test_sign_typed_data_calls_circle_api(self, circle_mocks):
        signer = _make_signer(circle_mocks)
        mock_signing_api = circle_mocks["signing_api"]

        sig_hex = "ab" * 65
        _mock_sign_response(mock_signing_api, "0x" + sig_hex)

        result = signer.sign_typed_data(
            domain=SAMPLE_DOMAIN,
            types=SAMPLE_TYPES,
            primary_type="Transfer",
            message={"to": "0xdead", "amount": 100},
        )

        # Verify the API was called with the request as positional arg
        mock_signing_api.sign_typed_data.assert_called_once()
        call_args = mock_signing_api.sign_typed_data.call_args
        request = call_args.args[0]

        # walletId is inside the request, not a separate param
        assert request.wallet_id == FAKE_WALLET_ID

        # Verify the EIP-712 payload
        data = json.loads(request.data)
        assert data["primaryType"] == "Transfer"
        assert "EIP712Domain" in data["types"]
        assert data["domain"] == SAMPLE_DOMAIN

        assert result == "0x" + sig_hex

    def test_sign_typed_data_does_not_set_ciphertext(self, circle_mocks):
        """SDK's @auto_fill decorator handles entitySecretCiphertext, we shouldn't set it."""
        signer = _make_signer(circle_mocks)
        mock_signing_api = circle_mocks["signing_api"]

        _mock_sign_response(mock_signing_api, "0x" + "00" * 65)

        signer.sign_typed_data(
            domain=SAMPLE_DOMAIN,
            types=SAMPLE_TYPES,
            primary_type="Transfer",
            message={"to": "0xdead", "amount": 1},
        )

        request = mock_signing_api.sign_typed_data.call_args.args[0]
        # Should be the placeholder that the SDK's @auto_fill decorator replaces
        assert request.entity_secret_ciphertext == "#REFILL_PLACEHOLDER"

    def test_sign_typed_data_returns_0x_prefixed(self, circle_mocks):
        signer = _make_signer(circle_mocks)
        mock_signing_api = circle_mocks["signing_api"]

        sig_hex = "cd" * 65
        _mock_sign_response(mock_signing_api, "0x" + sig_hex)

        result = signer.sign_typed_data(
            domain=SAMPLE_DOMAIN,
            types=SAMPLE_TYPES,
            primary_type="Transfer",
            message={"to": "0xdead", "amount": 1},
        )

        assert result.startswith("0x")

    def test_sign_typed_data_adds_prefix_when_missing(self, circle_mocks):
        signer = _make_signer(circle_mocks)
        mock_signing_api = circle_mocks["signing_api"]

        # Circle returns bare hex without 0x prefix
        sig_hex = "ef" * 65
        _mock_sign_response(mock_signing_api, sig_hex)  # no 0x

        result = signer.sign_typed_data(
            domain=SAMPLE_DOMAIN,
            types=SAMPLE_TYPES,
            primary_type="Transfer",
            message={"to": "0xdead", "amount": 1},
        )

        assert result == "0x" + sig_hex

    def test_eip712_domain_construction(self, circle_mocks):
        """Verify EIP712Domain type is built from domain keys present."""
        signer = _make_signer(circle_mocks)
        mock_signing_api = circle_mocks["signing_api"]

        _mock_sign_response(mock_signing_api, "0x" + "00" * 65)

        # Domain with only name and chainId
        partial_domain = {"name": "Test", "chainId": 1}

        signer.sign_typed_data(
            domain=partial_domain,
            types=SAMPLE_TYPES,
            primary_type="Transfer",
            message={"to": "0xdead", "amount": 1},
        )

        request = mock_signing_api.sign_typed_data.call_args.args[0]
        data = json.loads(request.data)
        domain_fields = {f["name"] for f in data["types"]["EIP712Domain"]}
        assert domain_fields == {"name", "chainId"}


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestCircleWalletSignerInit:
    """Test constructor behavior."""

    def test_requires_circle_sdk_installed(self):
        with patch("circlekit.wallets.HAS_CIRCLE_WALLETS", False):
            from circlekit.wallets import CircleWalletSigner

            with pytest.raises(ImportError, match="circle-developer-controlled-wallets"):
                CircleWalletSigner(
                    wallet_id=FAKE_WALLET_ID,
                    wallet_address=FAKE_ADDRESS,
                    api_key=FAKE_API_KEY,
                    entity_secret=FAKE_ENTITY_SECRET,
                )

    def test_fetches_address_from_api(self, circle_mocks):
        """When wallet_address is not provided, fetch via WalletsApi.get_wallet."""
        mock_wallets_api = circle_mocks["wallets_api"]

        # SDK returns WalletResponse with .data.wallet.address structure
        wallet_obj = SimpleNamespace(address=FAKE_ADDRESS)
        wallet_data = SimpleNamespace(wallet=wallet_obj)
        response = SimpleNamespace(data=wallet_data)
        mock_wallets_api.get_wallet.return_value = response

        from circlekit.wallets import CircleWalletSigner

        signer = CircleWalletSigner(
            wallet_id=FAKE_WALLET_ID,
            api_key=FAKE_API_KEY,
            entity_secret=FAKE_ENTITY_SECRET,
        )

        mock_wallets_api.get_wallet.assert_called_once_with(id=FAKE_WALLET_ID)
        assert signer.address == FAKE_ADDRESS

    def test_uses_provided_address(self, circle_mocks):
        """When wallet_address is provided, skip the API call."""
        signer = _make_signer(circle_mocks, wallet_address=FAKE_ADDRESS)
        circle_mocks["wallets_api"].get_wallet.assert_not_called()
        assert signer.address == FAKE_ADDRESS

    def test_env_var_fallback(self):
        """Credentials fall back to CIRCLE_API_KEY and CIRCLE_ENTITY_SECRET env vars."""
        env = {
            "CIRCLE_API_KEY": "env-api-key",
            "CIRCLE_ENTITY_SECRET": "b" * 64,
        }
        with (
            patch("circlekit.wallets.HAS_CIRCLE_WALLETS", True),
            patch.dict("os.environ", env),
            patch("circlekit.wallets.init_developer_controlled_wallets_client") as mock_init,
            patch("circlekit.wallets.SigningApi"),
            patch("circlekit.wallets.WalletsApi"),
        ):
            mock_init.return_value = MagicMock()

            from circlekit.wallets import CircleWalletSigner

            signer = CircleWalletSigner(
                wallet_id=FAKE_WALLET_ID,
                wallet_address=FAKE_ADDRESS,
            )

            mock_init.assert_called_once_with(
                api_key="env-api-key",
                entity_secret="b" * 64,
            )
            assert signer.address == FAKE_ADDRESS

    def test_raises_without_api_key(self):
        with (
            patch("circlekit.wallets.HAS_CIRCLE_WALLETS", True),
            patch.dict("os.environ", {}, clear=True),
            patch("circlekit.wallets.init_developer_controlled_wallets_client"),
            patch("circlekit.wallets.SigningApi"),
            patch("circlekit.wallets.WalletsApi"),
        ):
            from circlekit.wallets import CircleWalletSigner

            with pytest.raises(ValueError, match="api_key"):
                CircleWalletSigner(
                    wallet_id=FAKE_WALLET_ID,
                    wallet_address=FAKE_ADDRESS,
                    entity_secret=FAKE_ENTITY_SECRET,
                )

    def test_raises_without_entity_secret(self):
        with (
            patch("circlekit.wallets.HAS_CIRCLE_WALLETS", True),
            patch.dict("os.environ", {}, clear=True),
            patch("circlekit.wallets.init_developer_controlled_wallets_client"),
            patch("circlekit.wallets.SigningApi"),
            patch("circlekit.wallets.WalletsApi"),
        ):
            from circlekit.wallets import CircleWalletSigner

            with pytest.raises(ValueError, match="entity_secret"):
                CircleWalletSigner(
                    wallet_id=FAKE_WALLET_ID,
                    wallet_address=FAKE_ADDRESS,
                    api_key=FAKE_API_KEY,
                )

    def test_repr(self, circle_mocks):
        signer = _make_signer(circle_mocks)
        r = repr(signer)
        assert "CircleWalletSigner" in r
        assert FAKE_WALLET_ID in r
        assert FAKE_ADDRESS in r


# ---------------------------------------------------------------------------
# Integration with GatewayClient
# ---------------------------------------------------------------------------


class TestCircleWalletSignerWithGatewayClient:
    """Verify CircleWalletSigner can be used with GatewayClient."""

    def test_works_as_gateway_client_signer(self, circle_mocks):
        signer = _make_signer(circle_mocks)

        from circlekit import GatewayClient

        client = GatewayClient(chain="arcTestnet", signer=signer)
        assert client.address == FAKE_ADDRESS
