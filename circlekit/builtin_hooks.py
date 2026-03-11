"""
Built-in post-settlement hooks for circlekit.

Provides ready-made hooks that developers can register on
GatewayMiddleware or GatewayClient to trigger on-chain actions
after an x402 payment settles.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from typing import Any

from circlekit.hooks import HookResult, SettlementContext

logger = logging.getLogger(__name__)

# Serializes boa access across hooks — setup_boa_env / setup_boa_with_account
# mutate global state, so concurrent hooks on different chains would corrupt
# each other's environment without this lock.
_BOA_LOCK = threading.Lock()


class GenericContractHook:
    """Call an arbitrary smart contract function after settlement.

    Uses titanoboa's ABI-based contract interaction to invoke a function
    on any deployed contract.  The hook runs **synchronously** (boa calls
    are blocking), so it should be used with ``fire_and_forget=True``
    (the default) to avoid stalling HTTP responses.

    The contract function receives arguments built by an ``args_builder``
    callable that maps from :class:`SettlementContext` to a list of
    positional arguments.

    Args:
        contract_address: On-chain address of the target contract.
        abi: Contract ABI as a Python list of dicts (JSON ABI format).
        function_name: Name of the function to call on the contract.
        args_builder: Callable that takes a ``SettlementContext`` and
            returns a list of positional arguments for the function.
        chain: Chain name for boa environment setup (e.g. ``"arcTestnet"``).
        private_key: Hex-encoded private key for signing transactions.
            Required for state-changing (non-view) calls. Pass ``None``
            for read-only (view/pure) calls only.
        rpc_url: Optional custom RPC URL (overrides chain default).
        hook_name: Identifier used in :class:`HookResult` (default:
            ``"GenericContractHook"``)

    Example::

        from circlekit.builtin_hooks import GenericContractHook

        hook = GenericContractHook(
            contract_address="0xMyContract",
            abi=MY_ABI,
            function_name="recordPayment",
            args_builder=lambda ctx: [ctx.payer, ctx.amount, ctx.nonce],
            chain="arcTestnet",
            private_key="0x...",
        )
        gateway.on_after_settle(hook)
    """

    def __init__(
        self,
        contract_address: str,
        abi: list[dict[str, Any]],
        function_name: str,
        args_builder: Callable[[SettlementContext], list[Any]],
        chain: str,
        private_key: str | None = None,
        rpc_url: str | None = None,
        hook_name: str = "GenericContractHook",
    ):
        self._contract_address = contract_address
        self._abi = abi
        self._function_name = function_name
        self._args_builder = args_builder
        self._chain = chain
        self._private_key = private_key
        self._rpc_url = rpc_url
        self._hook_name = hook_name

    def on_settlement(self, context: SettlementContext) -> HookResult | None:
        """Execute the contract call. Blocking (boa is synchronous).

        Return values from the contract call are not captured.
        """
        import boa

        from circlekit.boa_utils import setup_boa_env, setup_boa_with_account

        if not self._private_key:
            logger.warning(
                "GenericContractHook: no private_key set. State-changing contract "
                "calls will use a dummy account and will revert on-chain."
            )

        try:
            with _BOA_LOCK:
                # Set up boa environment
                if self._private_key:
                    setup_boa_with_account(self._chain, self._private_key, self._rpc_url)
                else:
                    setup_boa_env(self._chain, self._rpc_url)

                # Load contract
                factory = boa.loads_abi(json.dumps(self._abi))
                contract = factory.at(self._contract_address)

                # Build args and call
                args = self._args_builder(context)
                fn = getattr(contract, self._function_name)
                fn(*args)

            return HookResult(hook_name=self._hook_name, success=True)

        except Exception as e:
            logger.exception(
                "GenericContractHook(%s) failed for nonce=%s",
                self._function_name,
                context.nonce,
            )
            return HookResult(
                hook_name=self._hook_name,
                success=False,
                error=str(e),
            )
