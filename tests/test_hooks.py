"""Tests for circlekit.hooks — SettlementContext, HookResult, and hook protocols."""

from circlekit.hooks import (
    AfterSettleHook,
    HookResult,
    SettlementContext,
    SyncAfterSettleHook,
)

# ============================================================================
# SettlementContext tests
# ============================================================================


def test_settlement_context_required_fields():
    ctx = SettlementContext(
        payer="0xBuyer",
        amount=10000,
        network="eip155:5042002",
        nonce="0xabc123",
    )
    assert ctx.payer == "0xBuyer"
    assert ctx.amount == 10000
    assert ctx.network == "eip155:5042002"
    assert ctx.nonce == "0xabc123"


def test_settlement_context_defaults():
    ctx = SettlementContext(
        payer="0xBuyer",
        amount=10000,
        network="eip155:5042002",
        nonce="0xabc123",
    )
    assert ctx.transaction is None
    assert ctx.seller == ""
    assert ctx.path is None
    assert ctx.url is None


def test_settlement_context_all_fields():
    ctx = SettlementContext(
        payer="0xBuyer",
        amount=50000,
        network="eip155:84532",
        nonce="0xdef456",
        transaction="0xtxhash",
        seller="0xSeller",
        path="/api/analyze",
        url="http://example.com/api/analyze",
    )
    assert ctx.transaction == "0xtxhash"
    assert ctx.seller == "0xSeller"
    assert ctx.path == "/api/analyze"
    assert ctx.url == "http://example.com/api/analyze"


# ============================================================================
# HookResult tests
# ============================================================================


def test_hook_result_success():
    result = HookResult(hook_name="my_hook", success=True)
    assert result.hook_name == "my_hook"
    assert result.success is True
    assert result.error is None


def test_hook_result_failure():
    result = HookResult(hook_name="failing_hook", success=False, error="connection timeout")
    assert result.success is False
    assert result.error == "connection timeout"


# ============================================================================
# Protocol conformance tests
# ============================================================================


class _AsyncHook:
    async def on_settlement(self, context: SettlementContext) -> HookResult | None:
        return HookResult(hook_name="async_test", success=True)


class _SyncHook:
    def on_settlement(self, context: SettlementContext) -> HookResult | None:
        return HookResult(hook_name="sync_test", success=True)


class _NotAHook:
    def do_something(self) -> None:
        pass


def test_async_hook_protocol_conformance():
    hook = _AsyncHook()
    assert isinstance(hook, AfterSettleHook)


def test_sync_hook_protocol_conformance():
    hook = _SyncHook()
    assert isinstance(hook, SyncAfterSettleHook)


def test_non_hook_does_not_match_protocol():
    obj = _NotAHook()
    assert not isinstance(obj, AfterSettleHook)
    assert not isinstance(obj, SyncAfterSettleHook)
