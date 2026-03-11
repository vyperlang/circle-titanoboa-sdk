"""
Post-settlement hook types for circlekit.

Provides the SettlementContext dataclass and hook protocols for executing
application logic after an x402 payment settles. Hooks are used by both
GatewayMiddleware (server-side) and GatewayClient (client-side).

Important: The ``transaction`` field in SettlementContext is an opaque
settlement reference from Circle Gateway. For batched payments it may be
a batch identifier rather than an on-chain transaction hash. Use
``(payer, amount, nonce)`` from the EIP-712 authorization as the
canonical proof-of-payment tuple when interacting with on-chain contracts.

For advanced users who need protocol-level hooks (before-verify,
before-settle, failure recovery), use the upstream x402 ResourceServer
via ``circlekit.x402_integration.create_resource_server()`` which exposes
the full hook lifecycle from the x402 Python SDK.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class SettlementContext:
    """Context passed to post-settlement hooks.

    Contains payment details extracted from the EIP-712 authorization and
    the settlement response. All fields except ``transaction`` are
    guaranteed to be present after a successful settlement.

    Attributes:
        payer: Buyer's wallet address (from authorization.from).
        amount: Server-requested price in raw USDC units (6 decimals).
            Reflects the server's requested price (from
            PaymentRequirements.amount), not the buyer's authorized value.
            These differ only if the buyer overpaid. For the buyer's actual
            authorized value use ``PaymentInfo.amount``.
        network: CAIP-2 network identifier (e.g. "eip155:5042002").
        nonce: 32-byte hex nonce from the EIP-712 authorization.
            Together with ``payer`` and ``amount``, this forms the
            canonical proof-of-payment tuple for on-chain verification.
        transaction: Opaque settlement reference from Circle Gateway.
            May be a batch identifier, not an on-chain tx hash.
            Can be None if the facilitator has not yet assigned one.
        seller: Recipient wallet address (payTo).
        path: Request path (server-side hooks only, e.g. "/api/analyze").
        url: Full request URL (client-side hooks only).
    """

    payer: str
    amount: int
    network: str
    nonce: str
    transaction: str | None = None
    seller: str = ""
    path: str | None = None
    url: str | None = None


@dataclass
class HookResult:
    """Result of a single hook execution.

    Attributes:
        hook_name: Identifier for the hook that ran.
        success: Whether the hook completed without error.
        error: Error message if the hook failed, None otherwise.
    """

    hook_name: str
    success: bool
    error: str | None = None


@runtime_checkable
class AfterSettleHook(Protocol):
    """Protocol for async post-settlement hooks.

    Implement this to execute logic after a successful x402 payment.
    The hook receives a SettlementContext with payment details.

    Hooks should be resilient to failure — they run after the payment
    has already been accepted, so errors should be logged rather than
    raised to the caller.

    Example::

        class MyHook:
            async def on_settlement(self, ctx: SettlementContext) -> HookResult | None:
                # Record payment on-chain, send notification, etc.
                return HookResult(hook_name="my_hook", success=True)
    """

    async def on_settlement(self, context: SettlementContext) -> HookResult | None: ...


@runtime_checkable
class SyncAfterSettleHook(Protocol):
    """Protocol for synchronous post-settlement hooks.

    Same as AfterSettleHook but for sync execution contexts.
    """

    def on_settlement(self, context: SettlementContext) -> HookResult | None: ...
