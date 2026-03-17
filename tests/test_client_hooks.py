"""Tests for post-settlement hook integration in GatewayClient and GatewayClientSync."""

import asyncio
import base64
import json
import logging
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from circlekit.client import GatewayClient
from circlekit.hooks import HookResult, SettlementContext
from circlekit.sync_client import GatewayClientSync

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signer(address: str = "0xBuyerAddr") -> MagicMock:
    signer = MagicMock()
    signer.address = address
    signer.sign_typed_data.return_value = "0xfakesig"
    return signer


def _make_client(**kwargs) -> GatewayClient:
    """Create a GatewayClient with a mock signer (no private key needed)."""
    signer = kwargs.pop("signer", _make_signer())
    return GatewayClient(chain="arcTestnet", signer=signer, **kwargs)


def _make_402_response(
    amount: str = "10000",
    pay_to: str = "0xSellerAddr",
    network: str = "eip155:5042002",
) -> httpx.Response:
    """Build a fake 402 response with Gateway batching requirements."""
    body = {
        "x402Version": 1,
        "accepts": [
            {
                "scheme": "circle_gateway_batching",
                "network": network,
                "amount": amount,
                "asset": "0xUSDC",
                "payTo": pay_to,
                "resource": "http://example.com/api",
                "description": "Test resource",
                "maxTimeoutSeconds": 60,
                "extra": {
                    "name": "GatewayWalletBatched",
                    "version": "1",
                    "verifyingContract": "0xGateway",
                },
            }
        ],
    }
    return httpx.Response(
        status_code=402,
        json=body,
        request=httpx.Request("GET", "http://example.com/api"),
    )


def _make_paid_response(
    transaction: str = "0xtxhash123",
) -> httpx.Response:
    """Build a fake successful paid response with PAYMENT-RESPONSE header."""
    receipt = base64.b64encode(
        json.dumps({"success": True, "transaction": transaction}).encode()
    ).decode()
    return httpx.Response(
        status_code=200,
        json={"result": "ok"},
        headers={"content-type": "application/json", "payment-response": receipt},
        request=httpx.Request("GET", "http://example.com/api"),
    )


def _make_failed_paid_response() -> httpx.Response:
    """Build a fake failed payment response (non-2xx after payment)."""
    return httpx.Response(
        status_code=500,
        text="Internal Server Error",
        request=httpx.Request("GET", "http://example.com/api"),
    )


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
    """Hook that always raises."""

    async def on_settlement(self, context: SettlementContext) -> HookResult | None:
        raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_on_after_settle_returns_self():
    client = _make_client()
    hook = _RecordingAsyncHook()
    result = client.on_after_settle(hook)
    assert result is client


def test_on_after_settle_fluent_chaining():
    client = _make_client()
    h1 = _RecordingAsyncHook()
    h2 = _RecordingSyncHook()
    client.on_after_settle(h1).on_after_settle(h2)
    assert len(client._hooks) == 2


def test_on_after_settle_rejects_non_hook():
    client = _make_client()

    class _NotAHook:
        def do_something(self) -> None:
            pass

    with pytest.raises(TypeError, match="must implement on_settlement"):
        client.on_after_settle(_NotAHook())


# ---------------------------------------------------------------------------
# fire_and_forget default
# ---------------------------------------------------------------------------


def test_fire_and_forget_default_true():
    client = _make_client()
    assert client._fire_and_forget is True


# ---------------------------------------------------------------------------
# _background_tasks GC fix (tasks stored and discarded on completion)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fire_and_forget_stores_task_references():
    client = _make_client()
    hook = _RecordingAsyncHook()
    client.on_after_settle(hook)

    ctx = SettlementContext(
        payer="0xBuyer",
        amount=10000,
        network="eip155:5042002",
        nonce="0xabc",
    )
    await client._fire_hooks(ctx)

    # After completion, the done callback cleans up
    await asyncio.sleep(0.05)
    assert len(client._background_tasks) == 0
    assert len(hook.calls) == 1


@pytest.mark.asyncio
async def test_background_tasks_tracked_during_execution():
    client = _make_client()
    started = asyncio.Event()
    finish = asyncio.Event()

    class _SlowHook:
        async def on_settlement(self, ctx: SettlementContext) -> HookResult | None:
            started.set()
            await finish.wait()
            return None

    client.on_after_settle(_SlowHook())

    ctx = SettlementContext(
        payer="0xBuyer",
        amount=10000,
        network="eip155:5042002",
        nonce="0xabc",
    )
    await client._fire_hooks(ctx)

    await started.wait()
    # Task is in-flight: must be in the set
    assert len(client._background_tasks) == 1

    # Let it finish
    finish.set()
    await asyncio.sleep(0.05)
    assert len(client._background_tasks) == 0


# ---------------------------------------------------------------------------
# Hook fires after successful pay() with correct SettlementContext fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pay_fires_hook_with_correct_context():
    client = _make_client()
    # Force sequential so we can inspect calls immediately
    client._fire_and_forget = False
    hook = _RecordingAsyncHook()
    client.on_after_settle(hook)

    responses = [_make_402_response(), _make_paid_response(transaction="0xSettled")]

    with patch.object(client._http, "get", new_callable=AsyncMock, side_effect=responses):
        result = await client.pay("http://example.com/api")

    assert result.status == 200
    assert len(hook.calls) == 1

    ctx = hook.calls[0]
    # payer comes from signer.address
    assert ctx.payer == "0xBuyerAddr"
    # nonce is a 32-byte hex string from generate_nonce()
    assert ctx.nonce.startswith("0x")
    assert len(ctx.nonce) == 66  # "0x" + 64 hex chars
    # url is populated (client-side field)
    assert ctx.url == "http://example.com/api"
    # path is None (server-side field)
    assert ctx.path is None
    # seller comes from payTo in requirements
    assert ctx.seller == "0xSellerAddr"
    # transaction from PAYMENT-RESPONSE header
    assert ctx.transaction == "0xSettled"
    # amount matches requirements
    assert ctx.amount == 10000
    # network from requirements
    assert ctx.network == "eip155:5042002"


@pytest.mark.asyncio
async def test_pay_fires_sync_hook():
    client = _make_client()
    client._fire_and_forget = False
    hook = _RecordingSyncHook()
    client.on_after_settle(hook)

    responses = [_make_402_response(), _make_paid_response()]

    with patch.object(client._http, "get", new_callable=AsyncMock, side_effect=responses):
        await client.pay("http://example.com/api")

    assert len(hook.calls) == 1
    assert hook.calls[0].payer == "0xBuyerAddr"


# ---------------------------------------------------------------------------
# Hook does NOT fire when pay() fails
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pay_no_hook_on_payment_failure():
    client = _make_client()
    client._fire_and_forget = False
    hook = _RecordingAsyncHook()
    client.on_after_settle(hook)

    responses = [_make_402_response(), _make_failed_paid_response()]

    with (
        patch.object(client._http, "get", new_callable=AsyncMock, side_effect=responses),
        pytest.raises(httpx.HTTPStatusError),
    ):
        await client.pay("http://example.com/api")

    assert len(hook.calls) == 0


@pytest.mark.asyncio
async def test_pay_no_hook_on_non_402():
    """If URL doesn't return 402, no payment happens and no hooks fire."""
    client = _make_client()
    client._fire_and_forget = False
    hook = _RecordingAsyncHook()
    client.on_after_settle(hook)

    ok_response = httpx.Response(
        status_code=200,
        json={"free": True},
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", "http://example.com/free"),
    )

    with patch.object(client._http, "get", new_callable=AsyncMock, return_value=ok_response):
        result = await client.pay("http://example.com/free")

    assert result.status == 200
    assert len(hook.calls) == 0


# ---------------------------------------------------------------------------
# Failing hook does not break pay()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pay_succeeds_when_hook_fails():
    client = _make_client()
    client._fire_and_forget = False
    client.on_after_settle(_FailingHook())

    responses = [_make_402_response(), _make_paid_response()]

    with patch.object(client._http, "get", new_callable=AsyncMock, side_effect=responses):
        result = await client.pay("http://example.com/api")

    # Pay itself succeeds despite hook failure
    assert result.status == 200
    assert result.transaction == "0xtxhash123"


# ---------------------------------------------------------------------------
# Warning logged when payer or nonce missing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pay_warns_on_missing_payer(caplog):
    """If authorization somehow lacks 'from', warning is logged."""
    client = _make_client()
    client._fire_and_forget = False
    hook = _RecordingAsyncHook()
    client.on_after_settle(hook)

    responses = [_make_402_response(), _make_paid_response()]

    with (
        patch.object(client._http, "get", new_callable=AsyncMock, side_effect=responses),
        patch("circlekit.client.create_payment_payload") as mock_cpp,
    ):
        # Return a payload with empty "from"
        fake_payload = MagicMock()
        fake_payload.authorization = {"from": "", "nonce": "0xabc", "value": "10000"}
        fake_payload.to_header.return_value = "fake_header_b64"
        mock_cpp.return_value = fake_payload

        with caplog.at_level(logging.WARNING, logger="circlekit.client"):
            await client.pay("http://example.com/api")

    assert "missing payer or nonce" in caplog.text


@pytest.mark.asyncio
async def test_pay_warns_on_missing_nonce(caplog):
    """If authorization somehow lacks 'nonce', warning is logged."""
    client = _make_client()
    client._fire_and_forget = False
    hook = _RecordingAsyncHook()
    client.on_after_settle(hook)

    responses = [_make_402_response(), _make_paid_response()]

    with (
        patch.object(client._http, "get", new_callable=AsyncMock, side_effect=responses),
        patch("circlekit.client.create_payment_payload") as mock_cpp,
    ):
        fake_payload = MagicMock()
        fake_payload.authorization = {"from": "0xBuyer", "nonce": "", "value": "10000"}
        fake_payload.to_header.return_value = "fake_header_b64"
        mock_cpp.return_value = fake_payload

        with caplog.at_level(logging.WARNING, logger="circlekit.client"):
            await client.pay("http://example.com/api")

    assert "missing payer or nonce" in caplog.text


# ---------------------------------------------------------------------------
# GatewayClientSync.on_after_settle() delegates correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_hook_runs_off_event_loop_thread():
    """Sync hooks must not block the event loop thread."""
    loop_thread = threading.current_thread().ident

    class _ThreadRecordingHook:
        def __init__(self):
            self.thread_id = None

        def on_settlement(self, context):
            self.thread_id = threading.current_thread().ident
            return HookResult(hook_name="thread_check", success=True)

    client = _make_client()
    client._fire_and_forget = False
    hook = _ThreadRecordingHook()
    client.on_after_settle(hook)

    ctx = SettlementContext(
        payer="0xBuyer",
        amount=10000,
        network="eip155:5042002",
        nonce="0xabc",
    )
    results = await client._fire_hooks(ctx)

    assert hook.thread_id is not None
    assert hook.thread_id != loop_thread
    assert len(results) == 1
    assert results[0].success is True


# ---------------------------------------------------------------------------
# GatewayClientSync.on_after_settle() delegates correctly
# ---------------------------------------------------------------------------


def test_sync_client_on_after_settle_delegates():
    signer = _make_signer()
    sync_client = GatewayClientSync(chain="arcTestnet", signer=signer)
    hook = _RecordingAsyncHook()

    result = sync_client.on_after_settle(hook)

    # Returns self (GatewayClientSync), not the inner GatewayClient
    assert result is sync_client
    # Hook is registered on the inner GatewayClient
    assert len(sync_client._client._hooks) == 1
    assert sync_client._client._hooks[0] is hook


def test_sync_client_fluent_chaining():
    signer = _make_signer()
    sync_client = GatewayClientSync(chain="arcTestnet", signer=signer)
    h1 = _RecordingAsyncHook()
    h2 = _RecordingSyncHook()

    sync_client.on_after_settle(h1).on_after_settle(h2)

    assert len(sync_client._client._hooks) == 2


def test_sync_client_rejects_non_hook():
    signer = _make_signer()
    sync_client = GatewayClientSync(chain="arcTestnet", signer=signer)

    class _NotAHook:
        pass

    with pytest.raises(TypeError, match="must implement on_settlement"):
        sync_client.on_after_settle(_NotAHook())
