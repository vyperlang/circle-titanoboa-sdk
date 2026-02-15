"""Synchronous wrapper around GatewayClient for scripts and CLIs."""

from __future__ import annotations

import asyncio
import threading
import warnings
from collections.abc import Coroutine
from typing import Any, TypeVar

from circlekit.client import (
    Balances,
    DepositResult,
    GatewayBalance,
    GatewayClient,
    PayResult,
    SupportsResult,
    TrustlessWithdrawalResult,
    WalletBalance,
    WithdrawResult,
)
from circlekit.key_utils import PrivateKeyLike
from circlekit.signer import Signer
from circlekit.tx_executor import TxExecutor
from circlekit.x402 import PaymentPayload, PaymentRequirements

_T = TypeVar("_T")


class GatewayClientSync:
    """
    Synchronous wrapper around :class:`GatewayClient`.

    A dedicated background event loop is used so that the underlying
    ``httpx.AsyncClient`` is always accessed from the same loop.  This avoids
    the "async client reused across different event loops" failure mode that
    would occur with ``asyncio.run()``-per-call.

    Because a background loop is involved, this class must **not** be used
    inside an already-running event loop (e.g. Jupyter, FastAPI).
    Use :class:`GatewayClient` directly in async contexts.

    Constructor arguments are identical to :class:`GatewayClient`.
    """

    def __init__(
        self,
        chain: str,
        signer: Signer | None = None,
        tx_executor: TxExecutor | None = None,
        rpc_url: str | None = None,
        private_key: PrivateKeyLike | None = None,
    ):
        # Spin up a dedicated event loop on a daemon thread so that all async
        # work (including the httpx.AsyncClient) is bound to a single loop.
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

        try:
            self._client = GatewayClient(
                chain=chain,
                signer=signer,
                tx_executor=tx_executor,
                rpc_url=rpc_url,
                private_key=private_key,
            )
        except Exception:
            self._stop_loop()
            raise

    def _run(self, coro: Coroutine[Any, Any, _T]) -> _T:
        """Schedule *coro* on the background loop and block until it completes."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    # -- Properties (forwarded) --------------------------------------------------

    @property
    def address(self) -> str:
        """The account's wallet address."""
        return self._client.address

    @property
    def chain_name(self) -> str:
        """Human-readable chain name."""
        return self._client.chain_name

    @property
    def chain_id(self) -> int:
        """Chain ID."""
        return self._client.chain_id

    @property
    def domain(self) -> int:
        """Gateway domain identifier."""
        return self._client.domain

    # -- Sync wrappers -----------------------------------------------------------

    def deposit(
        self,
        amount: str,
        approve_amount: str | None = None,
        skip_approval_check: bool = False,
    ) -> DepositResult:
        """Deposit USDC from wallet into Gateway contract.

        See :meth:`GatewayClient.deposit` for full documentation.
        """
        return self._run(
            self._client.deposit(
                amount,
                approve_amount=approve_amount,
                skip_approval_check=skip_approval_check,
            )
        )

    def create_payment_payload(
        self,
        requirements: PaymentRequirements,
        x402_version: int = 1,
    ) -> PaymentPayload:
        """Create a signed payment payload for the given requirements.

        This method is already synchronous on :class:`GatewayClient`; it is
        forwarded directly.
        """
        return self._client.create_payment_payload(requirements, x402_version)

    def pay(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: Any | None = None,
    ) -> PayResult:
        """Pay for an x402-protected resource.

        See :meth:`GatewayClient.pay` for full documentation.
        """
        return self._run(self._client.pay(url, method=method, headers=headers, body=body))

    def withdraw(
        self,
        amount: str,
        chain: str | None = None,
        recipient: str | None = None,
        max_fee: int | None = None,
    ) -> WithdrawResult:
        """Withdraw USDC from Gateway to wallet.

        See :meth:`GatewayClient.withdraw` for full documentation.
        """
        return self._run(
            self._client.withdraw(amount, chain=chain, recipient=recipient, max_fee=max_fee)
        )

    def get_gateway_balance(self, address: str | None = None) -> GatewayBalance:
        """Get Gateway balance for an address.

        See :meth:`GatewayClient.get_gateway_balance` for full documentation.
        """
        return self._run(self._client.get_gateway_balance(address))

    def get_usdc_balance(self, address: str | None = None) -> WalletBalance:
        """Get on-chain USDC wallet balance for an address.

        See :meth:`GatewayClient.get_usdc_balance` for full documentation.
        """
        return self._run(self._client.get_usdc_balance(address))

    def get_balance(self, address: str | None = None) -> GatewayBalance:
        """Alias for :meth:`get_gateway_balance`.

        See :meth:`GatewayClient.get_balance` for full documentation.
        """
        return self._run(self._client.get_balance(address))

    def get_balances(self, address: str | None = None) -> Balances:
        """Get wallet and Gateway balances.

        See :meth:`GatewayClient.get_balances` for full documentation.
        """
        return self._run(self._client.get_balances(address))

    def supports(self, url: str) -> SupportsResult:
        """Check if a URL supports Gateway batching.

        See :meth:`GatewayClient.supports` for full documentation.
        """
        return self._run(self._client.supports(url))

    def deposit_for(
        self,
        amount: str,
        depositor: str,
        approve_amount: str | None = None,
        skip_approval_check: bool = False,
    ) -> DepositResult:
        """Deposit USDC into Gateway on behalf of another address.

        See :meth:`GatewayClient.deposit_for` for full documentation.
        """
        return self._run(
            self._client.deposit_for(
                amount,
                depositor,
                approve_amount=approve_amount,
                skip_approval_check=skip_approval_check,
            )
        )

    def get_trustless_withdrawal_delay(self) -> int:
        """Get the trustless withdrawal delay (in blocks).

        See :meth:`GatewayClient.get_trustless_withdrawal_delay` for full documentation.
        """
        return self._run(self._client.get_trustless_withdrawal_delay())

    def get_trustless_withdrawal_block(self, address: str | None = None) -> int:
        """Get the block at which a trustless withdrawal becomes completable.

        See :meth:`GatewayClient.get_trustless_withdrawal_block` for full documentation.
        """
        return self._run(self._client.get_trustless_withdrawal_block(address))

    def initiate_trustless_withdrawal(self, amount: str) -> TrustlessWithdrawalResult:
        """Initiate a trustless (on-chain) withdrawal.

        See :meth:`GatewayClient.initiate_trustless_withdrawal` for full documentation.
        """
        return self._run(self._client.initiate_trustless_withdrawal(amount))

    def complete_trustless_withdrawal(self) -> TrustlessWithdrawalResult:
        """Complete a previously initiated trustless withdrawal.

        See :meth:`GatewayClient.complete_trustless_withdrawal` for full documentation.
        """
        return self._run(self._client.complete_trustless_withdrawal())

    def transfer(
        self,
        amount: str,
        destination_chain: str,
        recipient: str | None = None,
    ) -> WithdrawResult:
        """Transfer USDC from Gateway to another chain/wallet.

        .. deprecated::
            Use :meth:`withdraw` instead.

        See :meth:`GatewayClient.transfer` for full documentation.
        """
        warnings.warn(
            "transfer() is deprecated, use withdraw() instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.withdraw(amount, chain=destination_chain, recipient=recipient)

    # -- Lifecycle ---------------------------------------------------------------

    def _stop_loop(self) -> None:
        """Stop the background event loop and join the thread."""
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    def close(self) -> None:
        """Close the underlying HTTP client and stop the background loop."""
        if not self._loop.is_running():
            return
        try:
            self._run(self._client.close())
        finally:
            self._stop_loop()

    def __enter__(self) -> GatewayClientSync:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[type-arg]
        self.close()

    def __repr__(self) -> str:
        return (
            f"GatewayClientSync(chain={self._client.chain_name!r}, address={self._client.address})"
        )
