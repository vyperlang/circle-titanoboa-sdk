"""
Tests for circlekit.wallets: CircleWalletSigner and CircleTxExecutor adapters.

All tests mock the Circle SDK. No live API calls.

Run with: uv run pytest tests/test_wallets.py -v
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from circlekit.signer import Signer
from circlekit.tx_executor import TxExecutor

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


class _FakeContractExecutionRequest:
    """Stand-in for CreateContractExecutionTransactionForDeveloperRequest."""

    def __init__(self, **kwargs):
        self.wallet_id = kwargs.get("walletId")
        self.contract_address = kwargs.get("contractAddress")
        self.abi_function_signature = kwargs.get("abiFunctionSignature")
        self.abi_parameters = kwargs.get("abiParameters", [])
        self.fee_level = kwargs.get("feeLevel")


class _FakeAbiParametersInner:
    """Stand-in for AbiParametersInner. Stores a plain value (str/int/bool/list)."""

    def __init__(self, value):
        self.actual_instance = value

    def __eq__(self, other):
        if isinstance(other, _FakeAbiParametersInner):
            return self.actual_instance == other.actual_instance
        return NotImplemented

    def __repr__(self):
        return f"AbiParametersInner({self.actual_instance!r})"


class _FakeFeeLevel:
    """Stand-in for FeeLevel enum."""

    def __init__(self, value):
        self.value = value


@pytest.fixture()
def circle_mocks():
    """Patch all Circle SDK symbols in circlekit.wallets for the duration of a test."""
    with (
        patch("circlekit.wallets.HAS_CIRCLE_WALLETS", True),
        patch("circlekit.wallets.init_developer_controlled_wallets_client") as mock_init,
        patch("circlekit.wallets.SigningApi") as mock_signing_cls,
        patch("circlekit.wallets.WalletsApi") as mock_wallets_cls,
        patch("circlekit.wallets.TransactionsApi") as mock_transactions_cls,
        patch("circlekit.wallets.SignTypedDataRequest", _FakeSignTypedDataRequest),
        patch(
            "circlekit.wallets.CreateContractExecutionTransactionForDeveloperRequest",
            _FakeContractExecutionRequest,
        ),
        patch("circlekit.wallets.AbiParametersInner", _FakeAbiParametersInner),
        patch("circlekit.wallets.FeeLevel", _FakeFeeLevel),
    ):
        mock_init.return_value = MagicMock()
        mock_signing_api = MagicMock()
        mock_signing_cls.return_value = mock_signing_api
        mock_wallets_api = MagicMock()
        mock_wallets_cls.return_value = mock_wallets_api
        mock_transactions_api = MagicMock()
        mock_transactions_cls.return_value = mock_transactions_api

        yield {
            "init": mock_init,
            "signing_api": mock_signing_api,
            "wallets_api": mock_wallets_api,
            "transactions_api": mock_transactions_api,
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

    def test_fetches_address_from_api_actual_instance_wrapper(self, circle_mocks):
        """Supports oneOf wrapper shape where wallet address is in actual_instance."""
        mock_wallets_api = circle_mocks["wallets_api"]

        wallet_obj = SimpleNamespace(actual_instance=SimpleNamespace(address=FAKE_ADDRESS))
        response = SimpleNamespace(data=SimpleNamespace(wallet=wallet_obj))
        mock_wallets_api.get_wallet.return_value = response

        from circlekit.wallets import CircleWalletSigner

        signer = CircleWalletSigner(
            wallet_id=FAKE_WALLET_ID,
            api_key=FAKE_API_KEY,
            entity_secret=FAKE_ENTITY_SECRET,
        )

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


# ===========================================================================
# CircleTxExecutor tests
# ===========================================================================

FAKE_TX_ID = "tx-id-abc123"
FAKE_TX_HASH = "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"


def _make_executor(circle_mocks, wallet_address=FAKE_ADDRESS, **kwargs):
    """Create a CircleTxExecutor inside an active circle_mocks context."""
    from circlekit.wallets import CircleTxExecutor

    executor = CircleTxExecutor(
        wallet_id=FAKE_WALLET_ID,
        wallet_address=wallet_address,
        api_key=FAKE_API_KEY,
        entity_secret=FAKE_ENTITY_SECRET,
        **kwargs,
    )
    return executor


def _mock_submit_response(mock_transactions_api, tx_id=FAKE_TX_ID):
    """Configure mock TransactionsApi to return a submit response with given tx ID."""
    response = MagicMock()
    response.data.transaction.id = tx_id
    mock_transactions_api.create_developer_transaction_contract_execution.return_value = response


def _mock_submit_response_flat_data(mock_transactions_api, tx_id=FAKE_TX_ID):
    """Configure mock submit response using newer SDK shape: response.data.id."""
    response = MagicMock()
    response.data.id = tx_id
    response.data.transaction = None
    mock_transactions_api.create_developer_transaction_contract_execution.return_value = response


def _mock_poll_response(mock_transactions_api, state, tx_hash=FAKE_TX_HASH, error_reason=None):
    """Configure mock TransactionsApi.get_transaction to return given state."""
    response = MagicMock()
    response.data.transaction.state = state
    response.data.transaction.tx_hash = tx_hash
    response.data.transaction.error_reason = error_reason
    mock_transactions_api.get_transaction.return_value = response


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestCircleTxExecutorProtocol:
    """Verify CircleTxExecutor satisfies the TxExecutor protocol."""

    def test_satisfies_tx_executor_protocol(self, circle_mocks):
        executor = _make_executor(circle_mocks)
        assert isinstance(executor, TxExecutor)

    def test_address_property(self, circle_mocks):
        executor = _make_executor(circle_mocks)
        assert executor.address == FAKE_ADDRESS

    def test_repr(self, circle_mocks):
        executor = _make_executor(circle_mocks)
        r = repr(executor)
        assert "CircleTxExecutor" in r
        assert FAKE_WALLET_ID in r
        assert FAKE_ADDRESS in r


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestCircleTxExecutorInit:
    """Test constructor behavior."""

    def test_requires_circle_sdk_installed(self):
        with patch("circlekit.wallets.HAS_CIRCLE_WALLETS", False):
            from circlekit.wallets import CircleTxExecutor

            with pytest.raises(ImportError, match="circle-developer-controlled-wallets"):
                CircleTxExecutor(
                    wallet_id=FAKE_WALLET_ID,
                    wallet_address=FAKE_ADDRESS,
                    api_key=FAKE_API_KEY,
                    entity_secret=FAKE_ENTITY_SECRET,
                )

    def test_fetches_address_from_api(self, circle_mocks):
        """When wallet_address is not provided, fetch via WalletsApi.get_wallet."""
        mock_wallets_api = circle_mocks["wallets_api"]

        wallet_obj = SimpleNamespace(address=FAKE_ADDRESS)
        wallet_data = SimpleNamespace(wallet=wallet_obj)
        response = SimpleNamespace(data=wallet_data)
        mock_wallets_api.get_wallet.return_value = response

        from circlekit.wallets import CircleTxExecutor

        executor = CircleTxExecutor(
            wallet_id=FAKE_WALLET_ID,
            api_key=FAKE_API_KEY,
            entity_secret=FAKE_ENTITY_SECRET,
        )

        mock_wallets_api.get_wallet.assert_called_once_with(id=FAKE_WALLET_ID)
        assert executor.address == FAKE_ADDRESS

    def test_fetches_address_from_api_actual_instance_wrapper(self, circle_mocks):
        """Supports oneOf wrapper shape where wallet address is in actual_instance."""
        mock_wallets_api = circle_mocks["wallets_api"]

        wallet_obj = SimpleNamespace(actual_instance=SimpleNamespace(address=FAKE_ADDRESS))
        response = SimpleNamespace(data=SimpleNamespace(wallet=wallet_obj))
        mock_wallets_api.get_wallet.return_value = response

        from circlekit.wallets import CircleTxExecutor

        executor = CircleTxExecutor(
            wallet_id=FAKE_WALLET_ID,
            api_key=FAKE_API_KEY,
            entity_secret=FAKE_ENTITY_SECRET,
        )

        assert executor.address == FAKE_ADDRESS

    def test_uses_provided_address(self, circle_mocks):
        executor = _make_executor(circle_mocks, wallet_address=FAKE_ADDRESS)
        circle_mocks["wallets_api"].get_wallet.assert_not_called()
        assert executor.address == FAKE_ADDRESS

    def test_env_var_fallback(self):
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
            patch("circlekit.wallets.TransactionsApi"),
        ):
            mock_init.return_value = MagicMock()

            from circlekit.wallets import CircleTxExecutor

            executor = CircleTxExecutor(
                wallet_id=FAKE_WALLET_ID,
                wallet_address=FAKE_ADDRESS,
            )

            mock_init.assert_called_once_with(
                api_key="env-api-key",
                entity_secret="b" * 64,
            )
            assert executor.address == FAKE_ADDRESS

    def test_raises_without_api_key(self):
        with (
            patch("circlekit.wallets.HAS_CIRCLE_WALLETS", True),
            patch.dict("os.environ", {}, clear=True),
            patch("circlekit.wallets.init_developer_controlled_wallets_client"),
            patch("circlekit.wallets.SigningApi"),
            patch("circlekit.wallets.WalletsApi"),
            patch("circlekit.wallets.TransactionsApi"),
        ):
            from circlekit.wallets import CircleTxExecutor

            with pytest.raises(ValueError, match="api_key"):
                CircleTxExecutor(
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
            patch("circlekit.wallets.TransactionsApi"),
        ):
            from circlekit.wallets import CircleTxExecutor

            with pytest.raises(ValueError, match="entity_secret"):
                CircleTxExecutor(
                    wallet_id=FAKE_WALLET_ID,
                    wallet_address=FAKE_ADDRESS,
                    api_key=FAKE_API_KEY,
                )

    def test_custom_poll_interval_and_timeout(self, circle_mocks):
        executor = _make_executor(circle_mocks, poll_interval=2.5, timeout=60.0)
        assert executor._poll_interval == 2.5
        assert executor._timeout == 60.0


# ---------------------------------------------------------------------------
# _submit_and_wait
# ---------------------------------------------------------------------------


class TestCircleTxExecutorSubmitAndWait:
    """Test the core _submit_and_wait helper."""

    def test_success_flow(self, circle_mocks):
        """Transaction immediately reaches CONFIRMED state."""
        executor = _make_executor(circle_mocks)
        mock_tx = circle_mocks["transactions_api"]

        _mock_submit_response(mock_tx)
        _mock_poll_response(mock_tx, "CONFIRMED", tx_hash=FAKE_TX_HASH)

        result = executor._submit_and_wait("0xContract", "foo(uint256)", ["42"])
        assert result == FAKE_TX_HASH

    def test_success_complete_state(self, circle_mocks):
        """COMPLETE is also a success state."""
        executor = _make_executor(circle_mocks)
        mock_tx = circle_mocks["transactions_api"]

        _mock_submit_response(mock_tx)
        _mock_poll_response(mock_tx, "COMPLETE", tx_hash=FAKE_TX_HASH)

        result = executor._submit_and_wait("0xContract", "bar()", [])
        assert result == FAKE_TX_HASH

    def test_success_cleared_state(self, circle_mocks):
        """CLEARED is also a success state."""
        executor = _make_executor(circle_mocks)
        mock_tx = circle_mocks["transactions_api"]

        _mock_submit_response(mock_tx)
        _mock_poll_response(mock_tx, "CLEARED", tx_hash=FAKE_TX_HASH)

        result = executor._submit_and_wait("0xContract", "baz()", [])
        assert result == FAKE_TX_HASH

    def test_submit_response_with_flat_data_shape(self, circle_mocks):
        """Supports newer Circle SDK response shape where tx id is response.data.id."""
        executor = _make_executor(circle_mocks)
        mock_tx = circle_mocks["transactions_api"]

        _mock_submit_response_flat_data(mock_tx)
        _mock_poll_response(mock_tx, "CONFIRMED", tx_hash=FAKE_TX_HASH)

        result = executor._submit_and_wait("0xContract", "foo(uint256)", ["42"])
        assert result == FAKE_TX_HASH

    def test_poll_response_with_flat_data_shape(self, circle_mocks):
        """Supports poll shape where transaction fields are directly under response.data."""
        executor = _make_executor(circle_mocks)
        mock_tx = circle_mocks["transactions_api"]

        _mock_submit_response(mock_tx)
        poll = MagicMock()
        poll.data.transaction = None
        poll.data.state = "CONFIRMED"
        poll.data.tx_hash = FAKE_TX_HASH
        poll.data.error_reason = None
        mock_tx.get_transaction.return_value = poll

        result = executor._submit_and_wait("0xContract", "foo(uint256)", ["42"])
        assert result == FAKE_TX_HASH

    def test_failure_failed_state(self, circle_mocks):
        from circlekit.wallets import CircleTransactionError

        executor = _make_executor(circle_mocks)
        mock_tx = circle_mocks["transactions_api"]

        _mock_submit_response(mock_tx)
        _mock_poll_response(mock_tx, "FAILED", error_reason="out of gas")

        with pytest.raises(CircleTransactionError) as exc_info:
            executor._submit_and_wait("0xContract", "fail()", [])

        assert exc_info.value.state == "FAILED"
        assert exc_info.value.error_reason == "out of gas"
        assert exc_info.value.transaction_id == FAKE_TX_ID

    def test_failure_cancelled_state(self, circle_mocks):
        from circlekit.wallets import CircleTransactionError

        executor = _make_executor(circle_mocks)
        mock_tx = circle_mocks["transactions_api"]

        _mock_submit_response(mock_tx)
        _mock_poll_response(mock_tx, "CANCELLED")

        with pytest.raises(CircleTransactionError) as exc_info:
            executor._submit_and_wait("0xContract", "cancel()", [])
        assert exc_info.value.state == "CANCELLED"

    def test_failure_denied_state(self, circle_mocks):
        from circlekit.wallets import CircleTransactionError

        executor = _make_executor(circle_mocks)
        mock_tx = circle_mocks["transactions_api"]

        _mock_submit_response(mock_tx)
        _mock_poll_response(mock_tx, "DENIED")

        with pytest.raises(CircleTransactionError) as exc_info:
            executor._submit_and_wait("0xContract", "deny()", [])
        assert exc_info.value.state == "DENIED"

    def test_timeout(self, circle_mocks):
        from circlekit.wallets import CircleTransactionTimeoutError

        executor = _make_executor(circle_mocks, poll_interval=0.01, timeout=0.05)
        mock_tx = circle_mocks["transactions_api"]

        _mock_submit_response(mock_tx)
        # Always return PENDING, never reaches terminal
        _mock_poll_response(mock_tx, "PENDING")

        with pytest.raises(CircleTransactionTimeoutError) as exc_info:
            executor._submit_and_wait("0xContract", "slow()", [])
        assert exc_info.value.transaction_id == FAKE_TX_ID

    def test_multi_poll_progression(self, circle_mocks):
        """Transaction progresses through non-terminal states before confirming."""
        executor = _make_executor(circle_mocks, poll_interval=0.01)
        mock_tx = circle_mocks["transactions_api"]

        _mock_submit_response(mock_tx)

        # Sequence: INITIATED -> QUEUED -> SENT -> CONFIRMED
        states = ["INITIATED", "QUEUED", "SENT", "CONFIRMED"]
        responses = []
        for state in states:
            r = MagicMock()
            r.data.transaction.state = state
            r.data.transaction.tx_hash = FAKE_TX_HASH
            r.data.transaction.error_reason = None
            responses.append(r)
        mock_tx.get_transaction.side_effect = responses

        result = executor._submit_and_wait("0xContract", "multi()", [])
        assert result == FAKE_TX_HASH
        assert mock_tx.get_transaction.call_count == 4

    def test_error_reason_propagation(self, circle_mocks):
        from circlekit.wallets import CircleTransactionError

        executor = _make_executor(circle_mocks)
        mock_tx = circle_mocks["transactions_api"]

        _mock_submit_response(mock_tx)
        _mock_poll_response(mock_tx, "FAILED", error_reason="nonce too low")

        with pytest.raises(CircleTransactionError, match="nonce too low"):
            executor._submit_and_wait("0xContract", "err()", [])


# ---------------------------------------------------------------------------
# Execute methods
# ---------------------------------------------------------------------------


class TestCircleTxExecutorMethods:
    """Verify each execute method passes correct contract, ABI, and params."""

    def test_execute_approve(self, circle_mocks):
        executor = _make_executor(circle_mocks)
        mock_tx = circle_mocks["transactions_api"]
        _mock_submit_response(mock_tx)
        _mock_poll_response(mock_tx, "CONFIRMED")

        spender = "0xSpenderAddress"
        executor.execute_approve("arcTestnet", FAKE_ADDRESS, spender, 1_000_000)

        req = mock_tx.create_developer_transaction_contract_execution.call_args.args[0]
        assert req.abi_function_signature == "approve(address,uint256)"
        assert req.abi_parameters[0].actual_instance == spender
        assert req.abi_parameters[1].actual_instance == "1000000"

    def test_execute_deposit(self, circle_mocks):
        from circlekit.constants import get_chain_config

        executor = _make_executor(circle_mocks)
        mock_tx = circle_mocks["transactions_api"]
        _mock_submit_response(mock_tx)
        _mock_poll_response(mock_tx, "CONFIRMED")

        config = get_chain_config("arcTestnet")
        executor.execute_deposit("arcTestnet", FAKE_ADDRESS, 5_000_000)

        req = mock_tx.create_developer_transaction_contract_execution.call_args.args[0]
        assert req.contract_address == config.gateway_address
        assert req.abi_function_signature == "deposit(address,uint256)"
        assert req.abi_parameters[0].actual_instance == config.usdc_address
        assert req.abi_parameters[1].actual_instance == "5000000"

    def test_execute_deposit_for(self, circle_mocks):
        from circlekit.constants import get_chain_config

        executor = _make_executor(circle_mocks)
        mock_tx = circle_mocks["transactions_api"]
        _mock_submit_response(mock_tx)
        _mock_poll_response(mock_tx, "CONFIRMED")

        config = get_chain_config("arcTestnet")
        depositor = "0xDepositorAddr"
        executor.execute_deposit_for("arcTestnet", FAKE_ADDRESS, depositor, 2_000_000)

        req = mock_tx.create_developer_transaction_contract_execution.call_args.args[0]
        assert req.contract_address == config.gateway_address
        assert req.abi_function_signature == "depositFor(address,address,uint256)"
        assert req.abi_parameters[0].actual_instance == config.usdc_address
        assert req.abi_parameters[1].actual_instance == depositor
        assert req.abi_parameters[2].actual_instance == "2000000"

    def test_execute_gateway_mint_hex_strings(self, circle_mocks):
        from circlekit.constants import get_chain_config

        executor = _make_executor(circle_mocks)
        mock_tx = circle_mocks["transactions_api"]
        _mock_submit_response(mock_tx)
        _mock_poll_response(mock_tx, "CONFIRMED")

        config = get_chain_config("arcTestnet")
        attestation = "0xabcd"
        signature = "0x1234"
        executor.execute_gateway_mint("arcTestnet", attestation, signature)

        req = mock_tx.create_developer_transaction_contract_execution.call_args.args[0]
        assert req.contract_address == config.gateway_minter
        assert req.abi_function_signature == "gatewayMint(bytes,bytes)"
        assert req.abi_parameters[0].actual_instance == "0xabcd"
        assert req.abi_parameters[1].actual_instance == "0x1234"

    def test_execute_gateway_mint_bytes(self, circle_mocks):
        """bytes inputs are normalized to 0x-prefixed hex strings."""
        executor = _make_executor(circle_mocks)
        mock_tx = circle_mocks["transactions_api"]
        _mock_submit_response(mock_tx)
        _mock_poll_response(mock_tx, "CONFIRMED")

        att_bytes = b"\xab\xcd"
        sig_bytes = b"\x12\x34"
        executor.execute_gateway_mint("arcTestnet", att_bytes, sig_bytes)

        req = mock_tx.create_developer_transaction_contract_execution.call_args.args[0]
        assert req.abi_parameters[0].actual_instance == "0xabcd"
        assert req.abi_parameters[1].actual_instance == "0x1234"

    def test_execute_initiate_withdrawal(self, circle_mocks):
        from circlekit.constants import get_chain_config

        executor = _make_executor(circle_mocks)
        mock_tx = circle_mocks["transactions_api"]
        _mock_submit_response(mock_tx)
        _mock_poll_response(mock_tx, "CONFIRMED")

        config = get_chain_config("arcTestnet")
        amount = 1_000_000
        executor.execute_initiate_withdrawal("arcTestnet", FAKE_ADDRESS, amount)

        req = mock_tx.create_developer_transaction_contract_execution.call_args.args[0]
        assert req.contract_address == config.gateway_address
        assert req.abi_function_signature == "initiateWithdrawal(address,uint256)"
        assert req.abi_parameters[0].actual_instance == config.usdc_address
        assert req.abi_parameters[1].actual_instance == str(amount)

    def test_execute_complete_withdrawal(self, circle_mocks):
        from circlekit.constants import get_chain_config

        executor = _make_executor(circle_mocks)
        mock_tx = circle_mocks["transactions_api"]
        _mock_submit_response(mock_tx)
        _mock_poll_response(mock_tx, "CONFIRMED")

        config = get_chain_config("arcTestnet")
        executor.execute_complete_withdrawal("arcTestnet", FAKE_ADDRESS)

        req = mock_tx.create_developer_transaction_contract_execution.call_args.args[0]
        assert req.contract_address == config.gateway_address
        assert req.abi_function_signature == "withdraw(address)"
        assert req.abi_parameters[0].actual_instance == config.usdc_address

    def test_execute_approve_uses_usdc_address(self, circle_mocks):
        """execute_approve targets the USDC contract, not the gateway."""
        from circlekit.constants import get_chain_config

        executor = _make_executor(circle_mocks)
        mock_tx = circle_mocks["transactions_api"]
        _mock_submit_response(mock_tx)
        _mock_poll_response(mock_tx, "CONFIRMED")

        config = get_chain_config("arcTestnet")
        executor.execute_approve("arcTestnet", FAKE_ADDRESS, config.gateway_address, 100)

        req = mock_tx.create_developer_transaction_contract_execution.call_args.args[0]
        assert req.contract_address == config.usdc_address


# ---------------------------------------------------------------------------
# check_allowance
# ---------------------------------------------------------------------------


class TestCircleTxExecutorCheckAllowance:
    """Test check_allowance via direct RPC eth_call."""

    def test_check_allowance_basic(self, circle_mocks):
        executor = _make_executor(circle_mocks)

        # Mock the httpx client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": "0x00000000000000000000000000000000000000000000000000000000000f4240",
        }
        executor._http = MagicMock()
        executor._http.post.return_value = mock_response

        result = executor.check_allowance(
            "arcTestnet",
            "0x1111111111111111111111111111111111111111",
            "0x2222222222222222222222222222222222222222",
        )

        assert result == 1_000_000  # 0xf4240

    def test_check_allowance_calldata_encoding(self, circle_mocks):
        """Verify the calldata contains the allowance selector + padded addresses."""
        executor = _make_executor(circle_mocks)

        mock_response = MagicMock()
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": "0x0"}
        executor._http = MagicMock()
        executor._http.post.return_value = mock_response

        owner = "0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        spender = "0xBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
        executor.check_allowance("arcTestnet", owner, spender)

        call_args = executor._http.post.call_args
        payload = call_args.kwargs["json"]
        data = payload["params"][0]["data"]

        # Must start with allowance selector
        assert data.startswith("0xdd62ed3e")
        # Must contain padded owner and spender (lowercased)
        assert owner[2:].lower().zfill(64) in data
        assert spender[2:].lower().zfill(64) in data

    def test_check_allowance_rpc_url_override(self, circle_mocks):
        """When rpc_url is provided, it should be used instead of config default."""
        executor = _make_executor(circle_mocks)

        mock_response = MagicMock()
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": "0x0"}
        executor._http = MagicMock()
        executor._http.post.return_value = mock_response

        custom_rpc = "https://custom-rpc.example.com"
        executor.check_allowance("arcTestnet", FAKE_ADDRESS, FAKE_ADDRESS, rpc_url=custom_rpc)

        call_args = executor._http.post.call_args
        assert call_args.args[0] == custom_rpc

    def test_check_allowance_zero_result(self, circle_mocks):
        executor = _make_executor(circle_mocks)

        mock_response = MagicMock()
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": "0x0"}
        executor._http = MagicMock()
        executor._http.post.return_value = mock_response

        result = executor.check_allowance("arcTestnet", FAKE_ADDRESS, FAKE_ADDRESS)
        assert result == 0

    def test_check_allowance_empty_result_raises(self, circle_mocks):
        """Empty result string should raise RuntimeError, not silently return 0."""
        executor = _make_executor(circle_mocks)

        mock_response = MagicMock()
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": ""}
        executor._http = MagicMock()
        executor._http.post.return_value = mock_response

        with pytest.raises(RuntimeError, match="missing 'result'"):
            executor.check_allowance("arcTestnet", FAKE_ADDRESS, FAKE_ADDRESS)

    def test_check_allowance_http_error_raises(self, circle_mocks):
        """HTTP errors should propagate, not be silently swallowed."""
        executor = _make_executor(circle_mocks)

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=MagicMock()
        )
        executor._http = MagicMock()
        executor._http.post.return_value = mock_response

        with pytest.raises(httpx.HTTPStatusError):
            executor.check_allowance("arcTestnet", FAKE_ADDRESS, FAKE_ADDRESS)

    def test_check_allowance_rpc_error_raises(self, circle_mocks):
        """JSON-RPC error responses should raise RuntimeError."""
        executor = _make_executor(circle_mocks)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32000, "message": "execution reverted"},
        }
        executor._http = MagicMock()
        executor._http.post.return_value = mock_response

        with pytest.raises(RuntimeError, match="execution reverted"):
            executor.check_allowance("arcTestnet", FAKE_ADDRESS, FAKE_ADDRESS)


# ---------------------------------------------------------------------------
# GatewayClient integration
# ---------------------------------------------------------------------------


class TestCircleTxExecutorWithGatewayClient:
    """Verify CircleTxExecutor can be used with GatewayClient."""

    def test_works_as_gateway_client_tx_executor(self, circle_mocks):
        signer = _make_signer(circle_mocks)
        executor = _make_executor(circle_mocks)

        from circlekit import GatewayClient

        client = GatewayClient(chain="arcTestnet", signer=signer, tx_executor=executor)
        assert client.address == FAKE_ADDRESS

    def test_address_mismatch_rejected(self, circle_mocks):
        signer = _make_signer(circle_mocks)

        other_address = "0xAAAABBBBCCCCDDDDEEEEFFFF0000111122223333"
        executor = _make_executor(circle_mocks, wallet_address=other_address)

        from circlekit import GatewayClient

        with pytest.raises(ValueError, match="does not match"):
            GatewayClient(chain="arcTestnet", signer=signer, tx_executor=executor)


# ---------------------------------------------------------------------------
# _normalize_to_hex
# ---------------------------------------------------------------------------


class TestNormalizeToHex:
    """Test the _normalize_to_hex helper."""

    def test_bytes_input(self):
        from circlekit.wallets import _normalize_to_hex

        assert _normalize_to_hex(b"\xab\xcd") == "0xabcd"

    def test_hex_string_with_prefix(self):
        from circlekit.wallets import _normalize_to_hex

        assert _normalize_to_hex("0xabcd") == "0xabcd"

    def test_hex_string_without_prefix(self):
        from circlekit.wallets import _normalize_to_hex

        assert _normalize_to_hex("abcd") == "0xabcd"

    def test_empty_bytes_raises(self):
        from circlekit.wallets import _normalize_to_hex

        with pytest.raises(ValueError, match="non-empty"):
            _normalize_to_hex(b"")

    def test_empty_string_raises(self):
        from circlekit.wallets import _normalize_to_hex

        with pytest.raises(ValueError, match="non-empty"):
            _normalize_to_hex("")

    def test_bare_0x_prefix_raises(self):
        from circlekit.wallets import _normalize_to_hex

        with pytest.raises(ValueError, match="non-empty"):
            _normalize_to_hex("0x")
