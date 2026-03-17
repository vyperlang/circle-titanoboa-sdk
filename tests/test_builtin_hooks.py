"""Tests for circlekit.builtin_hooks — GenericContractHook."""

from unittest.mock import MagicMock, patch

from circlekit.builtin_hooks import GenericContractHook
from circlekit.hooks import SettlementContext, SyncAfterSettleHook

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DUMMY_ABI = [
    {
        "type": "function",
        "name": "recordPayment",
        "inputs": [
            {"name": "payer", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
        ],
        "outputs": [],
        "stateMutability": "nonpayable",
    }
]


def _make_ctx(**overrides) -> SettlementContext:
    defaults = dict(
        payer="0xBuyer",
        amount=10000,
        network="eip155:5042002",
        nonce="0xabc123",
        transaction="0xtx",
        seller="0xSeller",
    )
    defaults.update(overrides)
    return SettlementContext(**defaults)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_generic_contract_hook_is_sync_hook():
    hook = GenericContractHook(
        contract_address="0xContract",
        abi=DUMMY_ABI,
        function_name="recordPayment",
        args_builder=lambda ctx: [ctx.payer, ctx.amount, ctx.nonce],
        chain="arcTestnet",
    )
    assert isinstance(hook, SyncAfterSettleHook)


# ---------------------------------------------------------------------------
# Successful call
# ---------------------------------------------------------------------------


@patch("circlekit.boa_utils.setup_boa_with_account")
@patch("boa.loads_abi")
def test_on_settlement_success_with_private_key(mock_loads_abi, mock_setup):
    mock_contract = MagicMock()
    mock_factory = MagicMock()
    mock_factory.at.return_value = mock_contract
    mock_loads_abi.return_value = mock_factory

    hook = GenericContractHook(
        contract_address="0xContract",
        abi=DUMMY_ABI,
        function_name="recordPayment",
        args_builder=lambda ctx: [ctx.payer, ctx.amount, ctx.nonce],
        chain="arcTestnet",
        private_key="0xdeadbeef",
        hook_name="test_hook",
    )

    ctx = _make_ctx()
    result = hook.on_settlement(ctx)

    assert result is not None
    assert result.success is True
    assert result.hook_name == "test_hook"

    # Verify boa interactions
    mock_setup.assert_called_once_with("arcTestnet", "0xdeadbeef", None)
    mock_factory.at.assert_called_once_with("0xContract")
    mock_contract.recordPayment.assert_called_once_with("0xBuyer", 10000, "0xabc123")


@patch("circlekit.boa_utils.setup_boa_env")
@patch("boa.loads_abi")
def test_on_settlement_success_read_only(mock_loads_abi, mock_setup):
    mock_contract = MagicMock()
    mock_factory = MagicMock()
    mock_factory.at.return_value = mock_contract
    mock_loads_abi.return_value = mock_factory

    hook = GenericContractHook(
        contract_address="0xContract",
        abi=DUMMY_ABI,
        function_name="recordPayment",
        args_builder=lambda ctx: [ctx.payer],
        chain="arcTestnet",
        # no private_key — read-only
    )

    ctx = _make_ctx()
    result = hook.on_settlement(ctx)

    assert result is not None
    assert result.success is True
    mock_setup.assert_called_once_with("arcTestnet", None)


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


@patch("circlekit.boa_utils.setup_boa_with_account")
@patch("boa.loads_abi")
def test_on_settlement_failure_returns_error(mock_loads_abi, mock_setup):
    mock_contract = MagicMock()
    mock_contract.recordPayment.side_effect = RuntimeError("revert")
    mock_factory = MagicMock()
    mock_factory.at.return_value = mock_contract
    mock_loads_abi.return_value = mock_factory

    hook = GenericContractHook(
        contract_address="0xContract",
        abi=DUMMY_ABI,
        function_name="recordPayment",
        args_builder=lambda ctx: [ctx.payer, ctx.amount, ctx.nonce],
        chain="arcTestnet",
        private_key="0xdeadbeef",
    )

    ctx = _make_ctx()
    result = hook.on_settlement(ctx)

    assert result is not None
    assert result.success is False
    assert "revert" in result.error


# ---------------------------------------------------------------------------
# Custom args_builder
# ---------------------------------------------------------------------------


@patch("circlekit.boa_utils.setup_boa_with_account")
@patch("boa.loads_abi")
def test_args_builder_receives_context(mock_loads_abi, mock_setup):
    mock_contract = MagicMock()
    mock_factory = MagicMock()
    mock_factory.at.return_value = mock_contract
    mock_loads_abi.return_value = mock_factory

    received = []

    def builder(ctx):
        received.append(ctx)
        return [ctx.seller, ctx.amount]

    hook = GenericContractHook(
        contract_address="0xContract",
        abi=DUMMY_ABI,
        function_name="recordPayment",
        args_builder=builder,
        chain="arcTestnet",
        private_key="0xkey",
    )

    ctx = _make_ctx(seller="0xMyShop")
    hook.on_settlement(ctx)

    assert len(received) == 1
    assert received[0].seller == "0xMyShop"
    mock_contract.recordPayment.assert_called_once_with("0xMyShop", 10000)


# ---------------------------------------------------------------------------
# Custom rpc_url passthrough
# ---------------------------------------------------------------------------


@patch("circlekit.boa_utils.setup_boa_with_account")
@patch("boa.loads_abi")
def test_custom_rpc_url(mock_loads_abi, mock_setup):
    mock_loads_abi.return_value = MagicMock(at=MagicMock(return_value=MagicMock()))

    hook = GenericContractHook(
        contract_address="0xContract",
        abi=DUMMY_ABI,
        function_name="recordPayment",
        args_builder=lambda ctx: [],
        chain="arcTestnet",
        private_key="0xkey",
        rpc_url="https://custom-rpc.example.com",
    )

    hook.on_settlement(_make_ctx())

    mock_setup.assert_called_once_with(
        "arcTestnet",
        "0xkey",
        "https://custom-rpc.example.com",
    )
