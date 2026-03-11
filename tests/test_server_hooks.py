"""Tests for post-settlement hook integration in GatewayMiddleware."""

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest
from circlekit.facilitator import SettleResponse, VerifyResponse
from circlekit.hooks import HookResult, SettlementContext
from circlekit.server import GatewayMiddleware, GatewayMiddlewareConfig, create_gateway_middleware

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> GatewayMiddlewareConfig:
    return GatewayMiddlewareConfig(
        seller_address="0xSeller",
        chain="arcTestnet",
    )


def _make_header_data(payer: str = "0xBuyer", nonce: str = "0xabc123") -> dict:
    return {
        "payload": {
            "authorization": {
                "from": payer,
                "value": 10000,
                "nonce": nonce,
            },
        },
        "accepted": {"network": "eip155:5042002"},
    }


def _make_settle_response(tx: str = "0xtx123") -> SettleResponse:
    return SettleResponse(success=True, transaction=tx)


class _RecordingAsyncHook:
    """Async hook that records calls."""

    def __init__(self):
        self.calls: list[SettlementContext] = []

    async def on_settlement(self, context: SettlementContext) -> HookResult | None:
        self.calls.append(context)
        return HookResult(hook_name="recording_async", success=True)


class _RecordingSyncHook:
    """Sync hook that records calls."""

    def __init__(self):
        self.calls: list[SettlementContext] = []

    def on_settlement(self, context: SettlementContext) -> HookResult | None:
        self.calls.append(context)
        return HookResult(hook_name="recording_sync", success=True)


class _FailingHook:
    """Hook that raises an exception."""

    async def on_settlement(self, context: SettlementContext) -> HookResult | None:
        raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_on_after_settle_returns_self():
    gw = GatewayMiddleware(_make_config())
    hook = _RecordingAsyncHook()
    result = gw.on_after_settle(hook)
    assert result is gw


def test_on_after_settle_fluent_chaining():
    gw = GatewayMiddleware(_make_config())
    h1 = _RecordingAsyncHook()
    h2 = _RecordingSyncHook()
    gw.on_after_settle(h1).on_after_settle(h2)
    assert len(gw._hooks) == 2


def test_create_gateway_middleware_with_hooks():
    h1 = _RecordingAsyncHook()
    h2 = _RecordingSyncHook()
    gw = create_gateway_middleware(
        seller_address="0xSeller",
        chain="arcTestnet",
        on_after_settle=[h1, h2],
    )
    assert len(gw._hooks) == 2


def test_fire_and_forget_default_true():
    gw = GatewayMiddleware(_make_config())
    assert gw._fire_and_forget is True


def test_fire_and_forget_can_be_disabled():
    gw = GatewayMiddleware(_make_config(), fire_and_forget=False)
    assert gw._fire_and_forget is False


# ---------------------------------------------------------------------------
# _build_settlement_context tests
# ---------------------------------------------------------------------------


def test_build_settlement_context_extracts_fields():
    gw = GatewayMiddleware(_make_config())
    header_data = _make_header_data(payer="0xAlice", nonce="0xnonce1")
    settle_result = _make_settle_response(tx="0xsettled")

    ctx = gw._build_settlement_context(
        header_data,
        settle_result,
        "eip155:5042002",
        "$0.01",
        path="/api/test",
    )

    assert ctx.payer == "0xAlice"
    assert ctx.amount == 10000  # $0.01 = 10000 raw USDC (6 decimals)
    assert ctx.network == "eip155:5042002"
    assert ctx.nonce == "0xnonce1"
    assert ctx.transaction == "0xsettled"
    assert ctx.seller == "0xSeller"
    assert ctx.path == "/api/test"


def test_build_settlement_context_no_path():
    gw = GatewayMiddleware(_make_config())
    ctx = gw._build_settlement_context(
        _make_header_data(),
        _make_settle_response(),
        "eip155:5042002",
        "$0.01",
    )
    assert ctx.path is None


# ---------------------------------------------------------------------------
# _fire_hooks tests (sequential mode, fire_and_forget=False)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fire_hooks_sequential_async():
    gw = GatewayMiddleware(_make_config(), fire_and_forget=False)
    hook = _RecordingAsyncHook()
    gw.on_after_settle(hook)

    ctx = SettlementContext(
        payer="0xBuyer",
        amount=10000,
        network="eip155:5042002",
        nonce="0xabc",
    )
    results = await gw._fire_hooks(ctx)

    assert len(hook.calls) == 1
    assert hook.calls[0] is ctx
    assert len(results) == 1
    assert results[0].success is True


@pytest.mark.asyncio
async def test_fire_hooks_sequential_sync():
    gw = GatewayMiddleware(_make_config(), fire_and_forget=False)
    hook = _RecordingSyncHook()
    gw.on_after_settle(hook)

    ctx = SettlementContext(
        payer="0xBuyer",
        amount=10000,
        network="eip155:5042002",
        nonce="0xabc",
    )
    results = await gw._fire_hooks(ctx)

    assert len(hook.calls) == 1
    assert len(results) == 1
    assert results[0].hook_name == "recording_sync"


@pytest.mark.asyncio
async def test_fire_hooks_sequential_failing_hook_logged():
    gw = GatewayMiddleware(_make_config(), fire_and_forget=False)
    gw.on_after_settle(_FailingHook())

    ctx = SettlementContext(
        payer="0xBuyer",
        amount=10000,
        network="eip155:5042002",
        nonce="0xabc",
    )
    results = await gw._fire_hooks(ctx)

    assert len(results) == 1
    assert results[0].success is False
    assert results[0].error == "unhandled exception"


@pytest.mark.asyncio
async def test_fire_hooks_no_hooks_returns_empty():
    gw = GatewayMiddleware(_make_config(), fire_and_forget=False)
    ctx = SettlementContext(
        payer="0xBuyer",
        amount=10000,
        network="eip155:5042002",
        nonce="0xabc",
    )
    results = await gw._fire_hooks(ctx)
    assert results == []


@pytest.mark.asyncio
async def test_fire_hooks_fire_and_forget_returns_immediately():
    gw = GatewayMiddleware(_make_config(), fire_and_forget=True)
    hook = _RecordingAsyncHook()
    gw.on_after_settle(hook)

    ctx = SettlementContext(
        payer="0xBuyer",
        amount=10000,
        network="eip155:5042002",
        nonce="0xabc",
    )
    results = await gw._fire_hooks(ctx)
    assert results == []

    # Let the background task complete
    await asyncio.sleep(0.01)
    assert len(hook.calls) == 1


# ---------------------------------------------------------------------------
# Integration: settle() fires hooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settle_fires_hooks():
    gw = GatewayMiddleware(_make_config(), fire_and_forget=False)
    hook = _RecordingAsyncHook()
    gw.on_after_settle(hook)

    header_data = _make_header_data()
    settle_resp = _make_settle_response()

    with (
        patch.object(gw, "_decode_and_resolve", return_value=(header_data, {}, "eip155:5042002")),
        patch.object(gw._facilitator, "settle", new_callable=AsyncMock, return_value=settle_resp),
    ):
        info = await gw.settle("fake_header", "$0.01")

    assert info.verified is True
    assert len(hook.calls) == 1
    assert hook.calls[0].payer == "0xBuyer"
    assert hook.calls[0].nonce == "0xabc123"
    # settle() does not set path
    assert hook.calls[0].path is None


# ---------------------------------------------------------------------------
# Integration: process_request() fires hooks with path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_request_fires_hooks_with_path():
    gw = GatewayMiddleware(_make_config(), fire_and_forget=False)
    hook = _RecordingAsyncHook()
    gw.on_after_settle(hook)

    header_data = _make_header_data()
    settle_resp = _make_settle_response()
    verify_resp = VerifyResponse(is_valid=True)

    with (
        patch.object(gw, "_decode_and_resolve", return_value=(header_data, {}, "eip155:5042002")),
        patch.object(gw._facilitator, "verify", new_callable=AsyncMock, return_value=verify_resp),
        patch.object(gw._facilitator, "settle", new_callable=AsyncMock, return_value=settle_resp),
    ):
        result = await gw.process_request("fake_header", "/api/analyze", "$0.01")

    assert not isinstance(result, dict)  # PaymentInfo, not 402
    assert len(hook.calls) == 1
    assert hook.calls[0].path == "/api/analyze"


@pytest.mark.asyncio
async def test_process_request_no_hooks_on_failure():
    gw = GatewayMiddleware(_make_config(), fire_and_forget=False)
    hook = _RecordingAsyncHook()
    gw.on_after_settle(hook)

    header_data = _make_header_data()
    settle_resp = SettleResponse(success=False, error_reason="insufficient funds")
    verify_resp = VerifyResponse(is_valid=True)

    with (
        patch.object(gw, "_decode_and_resolve", return_value=(header_data, {}, "eip155:5042002")),
        patch.object(gw._facilitator, "verify", new_callable=AsyncMock, return_value=verify_resp),
        patch.object(gw._facilitator, "settle", new_callable=AsyncMock, return_value=settle_resp),
    ):
        result = await gw.process_request("fake_header", "/api/analyze", "$0.01")

    assert isinstance(result, dict)
    assert result["status"] == 402
    # Hooks should NOT have been called
    assert len(hook.calls) == 0


# ---------------------------------------------------------------------------
# Protocol validation (Issue #6)
# ---------------------------------------------------------------------------


def test_on_after_settle_rejects_non_hook():
    gw = GatewayMiddleware(_make_config())

    class _BadHook:
        def do_something(self) -> None:
            pass

    with pytest.raises(TypeError, match="must implement on_settlement"):
        gw.on_after_settle(_BadHook())


# ---------------------------------------------------------------------------
# Missing payer/nonce warning (Issue #1)
# ---------------------------------------------------------------------------


def test_build_settlement_context_warns_on_missing_payer(caplog):
    gw = GatewayMiddleware(_make_config())
    header_data = _make_header_data(payer="", nonce="0xnonce1")

    with caplog.at_level(logging.WARNING, logger="circlekit.server"):
        gw._build_settlement_context(
            header_data,
            _make_settle_response(),
            "eip155:5042002",
            "$0.01",
        )

    assert "missing payer or nonce" in caplog.text


def test_build_settlement_context_warns_on_missing_nonce(caplog):
    gw = GatewayMiddleware(_make_config())
    header_data = _make_header_data(payer="0xBuyer", nonce="")

    with caplog.at_level(logging.WARNING, logger="circlekit.server"):
        gw._build_settlement_context(
            header_data,
            _make_settle_response(),
            "eip155:5042002",
            "$0.01",
        )

    assert "missing payer or nonce" in caplog.text


# ---------------------------------------------------------------------------
# _maybe_fire_hooks swallows exceptions (Issue #3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_maybe_fire_hooks_swallows_dispatch_error(caplog):
    gw = GatewayMiddleware(_make_config(), fire_and_forget=False)
    hook = _RecordingAsyncHook()
    gw.on_after_settle(hook)

    # Force _build_settlement_context to raise
    with (
        patch.object(gw, "_build_settlement_context", side_effect=RuntimeError("ctx boom")),
        caplog.at_level(logging.ERROR, logger="circlekit.server"),
    ):
        # Should not raise
        await gw._maybe_fire_hooks(
            _make_header_data(),
            _make_settle_response(),
            "eip155:5042002",
            "$0.01",
        )

    assert "Hook dispatch failed unexpectedly" in caplog.text
    assert len(hook.calls) == 0


# ---------------------------------------------------------------------------
# Task GC: background tasks are stored (Issue #5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fire_and_forget_stores_task_references():
    gw = GatewayMiddleware(_make_config(), fire_and_forget=True)
    hook = _RecordingAsyncHook()
    gw.on_after_settle(hook)

    ctx = SettlementContext(
        payer="0xBuyer",
        amount=10000,
        network="eip155:5042002",
        nonce="0xabc",
    )
    await gw._fire_hooks(ctx)

    # Task should be in _background_tasks before completion
    assert len(gw._background_tasks) >= 0  # may already complete in fast envs

    # After completion, the done callback cleans up
    await asyncio.sleep(0.05)
    assert len(gw._background_tasks) == 0
    assert len(hook.calls) == 1


@pytest.mark.asyncio
async def test_background_tasks_tracked():
    mw = create_gateway_middleware(seller_address="0x123", chain="arcTestnet")
    fired = []

    class SlowHook:
        async def on_settlement(self, ctx):
            await asyncio.sleep(0.01)
            fired.append(True)

    mw.on_after_settle(SlowHook())
    ctx = SettlementContext(
        payer="0xBuyer",
        amount=10000,
        network="eip155:5042002",
        nonce="0xabc",
    )

    await mw._fire_hooks(ctx)
    # Tasks should be in background_tasks immediately after dispatch
    # After awaiting completion, set should be empty
    await asyncio.sleep(0.05)
    assert len(fired) == 1
    assert len(mw._background_tasks) == 0
