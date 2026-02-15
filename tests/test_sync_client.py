"""Tests for GatewayClientSync, the synchronous wrapper around GatewayClient."""

import warnings
from unittest.mock import AsyncMock, MagicMock

import pytest
from circlekit.client import (
    Balances,
    DepositResult,
    GatewayBalance,
    PayResult,
    SupportsResult,
    TrustlessWithdrawalResult,
    WalletBalance,
    WithdrawResult,
)
from circlekit.sync_client import GatewayClientSync

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_ADDRESS = "0x" + "ab" * 20


@pytest.fixture()
def mock_signer():
    signer = MagicMock()
    signer.address = FAKE_ADDRESS
    return signer


@pytest.fixture()
def sync_client(mock_signer):
    """Create a GatewayClientSync with a mocked signer (no private key needed)."""
    client = GatewayClientSync(chain="arcTestnet", signer=mock_signer)
    yield client
    client.close()


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_creates_inner_gateway_client(self, sync_client):
        from circlekit.client import GatewayClient

        assert isinstance(sync_client._client, GatewayClient)

    def test_passes_chain(self, sync_client):
        assert sync_client._client.chain_name == "Arc Testnet"

    def test_has_background_loop_and_thread(self, sync_client):
        assert sync_client._loop.is_running()
        assert sync_client._thread.is_alive()

    def test_constructor_failure_stops_thread(self):
        """If GatewayClient(...) raises, the background thread must not leak."""
        import threading

        threads_before = set(threading.enumerate())
        with pytest.raises(ValueError):
            GatewayClientSync(chain="arcTestnet")  # no signer or private_key
        threads_after = set(threading.enumerate())
        leaked = threads_after - threads_before
        assert not leaked, f"Background thread leaked: {leaked}"


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    def test_address(self, sync_client, mock_signer):
        assert sync_client.address == mock_signer.address

    def test_chain_name(self, sync_client):
        assert sync_client.chain_name == "Arc Testnet"

    def test_chain_id(self, sync_client):
        assert sync_client.chain_id == 5042002

    def test_domain(self, sync_client):
        assert sync_client.domain == 26


# ---------------------------------------------------------------------------
# Sync method delegation
# ---------------------------------------------------------------------------


class TestSyncDelegation:
    """Each sync method should dispatch to the background loop."""

    def test_deposit(self, sync_client):
        expected = DepositResult(
            approval_tx_hash=None,
            deposit_tx_hash="0xdead",
            amount=1_000_000,
            formatted_amount="1.0",
            depositor=FAKE_ADDRESS,
        )
        sync_client._client.deposit = AsyncMock(return_value=expected)

        result = sync_client.deposit("1.0", approve_amount="2.0", skip_approval_check=True)

        assert result is expected
        sync_client._client.deposit.assert_awaited_once_with(
            "1.0", approve_amount="2.0", skip_approval_check=True
        )

    def test_pay(self, sync_client):
        expected = PayResult(
            data={"ok": True}, amount=100, formatted_amount="0.0001", transaction="0xtx", status=200
        )
        sync_client._client.pay = AsyncMock(return_value=expected)

        result = sync_client.pay(
            "https://example.com", method="POST", headers={"X": "1"}, body={"a": 1}
        )

        assert result is expected
        sync_client._client.pay.assert_awaited_once_with(
            "https://example.com", method="POST", headers={"X": "1"}, body={"a": 1}
        )

    def test_withdraw(self, sync_client):
        expected = WithdrawResult(
            mint_tx_hash="0xmint",
            transfer_id="tid",
            amount=5_000_000,
            formatted_amount="5.0",
            source_chain="Arc Testnet",
            destination_chain="Arc Testnet",
            recipient=FAKE_ADDRESS,
        )
        sync_client._client.withdraw = AsyncMock(return_value=expected)

        result = sync_client.withdraw("5.0", chain="arcTestnet", recipient=FAKE_ADDRESS, max_fee=0)

        assert result is expected
        sync_client._client.withdraw.assert_awaited_once_with(
            "5.0", chain="arcTestnet", recipient=FAKE_ADDRESS, max_fee=0
        )

    def test_get_gateway_balance(self, sync_client):
        expected = GatewayBalance(
            total=10,
            available=8,
            withdrawing=1,
            withdrawable=1,
            formatted_total="t",
            formatted_available="a",
            formatted_withdrawing="w",
            formatted_withdrawable="w2",
        )
        sync_client._client.get_gateway_balance = AsyncMock(return_value=expected)

        result = sync_client.get_gateway_balance("0xaddr")

        assert result is expected
        sync_client._client.get_gateway_balance.assert_awaited_once_with("0xaddr")

    def test_get_usdc_balance(self, sync_client):
        expected = WalletBalance(balance=100, formatted="0.0001")
        sync_client._client.get_usdc_balance = AsyncMock(return_value=expected)

        result = sync_client.get_usdc_balance()

        assert result is expected
        sync_client._client.get_usdc_balance.assert_awaited_once_with(None)

    def test_get_balance(self, sync_client):
        expected = GatewayBalance(
            total=10,
            available=10,
            withdrawing=0,
            withdrawable=0,
            formatted_total="t",
            formatted_available="a",
            formatted_withdrawing="0",
            formatted_withdrawable="0",
        )
        sync_client._client.get_balance = AsyncMock(return_value=expected)

        result = sync_client.get_balance()

        assert result is expected
        sync_client._client.get_balance.assert_awaited_once_with(None)

    def test_get_balances(self, sync_client):
        expected = Balances(
            wallet=WalletBalance(balance=1, formatted="f"),
            gateway=GatewayBalance(
                total=1,
                available=1,
                withdrawing=0,
                withdrawable=0,
                formatted_total="t",
                formatted_available="a",
                formatted_withdrawing="0",
                formatted_withdrawable="0",
            ),
        )
        sync_client._client.get_balances = AsyncMock(return_value=expected)

        result = sync_client.get_balances("0xaddr")

        assert result is expected
        sync_client._client.get_balances.assert_awaited_once_with("0xaddr")

    def test_supports(self, sync_client):
        expected = SupportsResult(supported=True, requirements={"scheme": "batch"})
        sync_client._client.supports = AsyncMock(return_value=expected)

        result = sync_client.supports("https://example.com")

        assert result is expected
        sync_client._client.supports.assert_awaited_once_with("https://example.com")

    def test_deposit_for(self, sync_client):
        expected = DepositResult(
            approval_tx_hash="0xappr",
            deposit_tx_hash="0xdep",
            amount=2_000_000,
            formatted_amount="2.0",
            depositor="0xother",
        )
        sync_client._client.deposit_for = AsyncMock(return_value=expected)

        result = sync_client.deposit_for(
            "2.0", "0xother", approve_amount="5.0", skip_approval_check=False
        )

        assert result is expected
        sync_client._client.deposit_for.assert_awaited_once_with(
            "2.0", "0xother", approve_amount="5.0", skip_approval_check=False
        )

    def test_get_trustless_withdrawal_delay(self, sync_client):
        sync_client._client.get_trustless_withdrawal_delay = AsyncMock(return_value=100)

        result = sync_client.get_trustless_withdrawal_delay()

        assert result == 100
        sync_client._client.get_trustless_withdrawal_delay.assert_awaited_once()

    def test_get_trustless_withdrawal_block(self, sync_client):
        sync_client._client.get_trustless_withdrawal_block = AsyncMock(return_value=42)

        result = sync_client.get_trustless_withdrawal_block("0xaddr")

        assert result == 42
        sync_client._client.get_trustless_withdrawal_block.assert_awaited_once_with("0xaddr")

    def test_initiate_trustless_withdrawal(self, sync_client):
        expected = TrustlessWithdrawalResult(
            tx_hash="0xinit", amount=1_000_000, formatted_amount="1.0", withdrawal_block=999
        )
        sync_client._client.initiate_trustless_withdrawal = AsyncMock(return_value=expected)

        result = sync_client.initiate_trustless_withdrawal("1.0")

        assert result is expected
        sync_client._client.initiate_trustless_withdrawal.assert_awaited_once_with("1.0")

    def test_complete_trustless_withdrawal(self, sync_client):
        expected = TrustlessWithdrawalResult(
            tx_hash="0xcomp", amount=1_000_000, formatted_amount="1.0"
        )
        sync_client._client.complete_trustless_withdrawal = AsyncMock(return_value=expected)

        result = sync_client.complete_trustless_withdrawal()

        assert result is expected
        sync_client._client.complete_trustless_withdrawal.assert_awaited_once()


# ---------------------------------------------------------------------------
# create_payment_payload (sync passthrough, no background loop dispatch)
# ---------------------------------------------------------------------------


class TestCreatePaymentPayload:
    def test_forwards_to_inner_client(self, sync_client):
        mock_payload = MagicMock()
        sync_client._client.create_payment_payload = MagicMock(return_value=mock_payload)
        mock_requirements = MagicMock()

        result = sync_client.create_payment_payload(mock_requirements, x402_version=2)

        assert result is mock_payload
        sync_client._client.create_payment_payload.assert_called_once_with(mock_requirements, 2)


# ---------------------------------------------------------------------------
# transfer() deprecated alias
# ---------------------------------------------------------------------------


class TestTransfer:
    def test_delegates_to_withdraw(self, sync_client):
        expected = WithdrawResult(
            mint_tx_hash="0xmint",
            transfer_id="tid",
            amount=1_000_000,
            formatted_amount="1.0",
            source_chain="Arc Testnet",
            destination_chain="Arc Testnet",
            recipient=FAKE_ADDRESS,
        )
        sync_client._client.withdraw = AsyncMock(return_value=expected)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = sync_client.transfer("1.0", "arcTestnet", recipient=FAKE_ADDRESS)

        assert result is expected
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "transfer()" in str(w[0].message)
        sync_client._client.withdraw.assert_awaited_once_with(
            "1.0", chain="arcTestnet", recipient=FAKE_ADDRESS, max_fee=None
        )


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_enter_returns_self(self, sync_client):
        assert sync_client.__enter__() is sync_client

    def test_exit_calls_close(self, sync_client):
        sync_client._client.close = AsyncMock()
        sync_client.__exit__(None, None, None)
        sync_client._client.close.assert_awaited_once()

    def test_with_statement(self, mock_signer):
        with GatewayClientSync(chain="arcTestnet", signer=mock_signer) as client:
            assert isinstance(client, GatewayClientSync)
            assert client._loop.is_running()
        # After exiting, the background loop has stopped
        assert not client._loop.is_running()

    def test_close_stops_background_thread(self, mock_signer):
        client = GatewayClientSync(chain="arcTestnet", signer=mock_signer)
        assert client._thread.is_alive()
        client.close()
        assert not client._thread.is_alive()

    def test_close_stops_thread_even_if_client_close_errors(self, mock_signer):
        """Loop/thread must be torn down even when _client.close() raises."""
        client = GatewayClientSync(chain="arcTestnet", signer=mock_signer)
        client._client.close = AsyncMock(side_effect=RuntimeError("boom"))
        with pytest.raises(RuntimeError, match="boom"):
            client.close()
        assert not client._thread.is_alive()
        assert not client._loop.is_running()


# ---------------------------------------------------------------------------
# _run dispatches to the background loop (not asyncio.run)
# ---------------------------------------------------------------------------


class TestRunDispatch:
    def test_multiple_calls_reuse_same_loop(self, sync_client):
        """Calling _run multiple times should not create new loops."""
        sync_client._client.get_usdc_balance = AsyncMock(
            return_value=WalletBalance(balance=0, formatted="0")
        )

        loop_before = sync_client._loop
        sync_client.get_usdc_balance()
        sync_client.get_usdc_balance()
        assert sync_client._loop is loop_before
        assert sync_client._client.get_usdc_balance.await_count == 2


# ---------------------------------------------------------------------------
# repr
# ---------------------------------------------------------------------------


class TestRepr:
    def test_repr(self, sync_client, mock_signer):
        r = repr(sync_client)
        assert "GatewayClientSync" in r
        assert "Arc Testnet" in r
        assert mock_signer.address in r


# ---------------------------------------------------------------------------
# Import from package root
# ---------------------------------------------------------------------------


class TestImport:
    def test_importable_from_circlekit(self):
        from circlekit import GatewayClientSync as GCS

        assert GCS is GatewayClientSync
