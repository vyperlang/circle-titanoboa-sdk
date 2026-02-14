"""
Titanoboa utilities for Circle Gateway interactions.

This module provides helpers for using titanoboa (boa) for on-chain
interactions. It handles:
- RPC connection management
- Contract loading and interaction
- Transaction building and signing
- ABI encoding/decoding
"""

import json
import os
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import boa
from eth_account import Account

from circlekit.constants import USDC_DECIMALS, get_chain_config


def get_rpc_url(chain: str) -> str:
    """Get the RPC URL for a chain."""
    return get_chain_config(chain).rpc_url


def setup_boa_env(chain: str, rpc_url: str | None = None) -> None:
    """
    Configure titanoboa environment for a specific chain.

    Args:
        chain: Chain name (e.g., 'arcTestnet')
        rpc_url: Optional custom RPC URL (overrides default)

    Note:
        Adds a dummy account because titanoboa's NetworkEnv requires
        an EOA even for read-only (view) function calls.
    """
    config = get_chain_config(chain)
    url = rpc_url or config.rpc_url

    # Set the RPC URL in boa environment
    boa.set_network_env(url)

    # Add a dummy account for read-only operations
    # (titanoboa requires an EOA even for view calls)
    if boa.env.eoa is None:
        dummy_key = "0x0000000000000000000000000000000000000000000000000000000000000001"
        dummy_account = Account.from_key(dummy_key)
        boa.env.add_account(dummy_account)


def get_account_from_private_key(private_key: str) -> tuple[str, Account]:
    """
    Get an account from a private key.

    Args:
        private_key: Hex-encoded private key (with or without 0x prefix)

    Returns:
        Tuple of (address, Account object)
    """
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    account = Account.from_key(private_key)
    return account.address, account


# ERC-20 ABI (minimal for balance checks)
ERC20_ABI = json.loads("""[
    {
        "constant": true,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": true,
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": false,
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": false,
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    }
]""")


# Gateway Wallet ABI (matches @circlefin/x402-batching)
GATEWAY_WALLET_ABI = json.loads("""[
    {
        "name": "deposit",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "token", "type": "address"},
            {"name": "value", "type": "uint256"}
        ],
        "outputs": []
    },
    {
        "name": "depositFor",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "token", "type": "address"},
            {"name": "depositor", "type": "address"},
            {"name": "value", "type": "uint256"}
        ],
        "outputs": []
    },
    {
        "name": "totalBalance",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "token", "type": "address"},
            {"name": "depositor", "type": "address"}
        ],
        "outputs": [{"name": "", "type": "uint256"}]
    },
    {
        "name": "availableBalance",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "token", "type": "address"},
            {"name": "depositor", "type": "address"}
        ],
        "outputs": [{"name": "", "type": "uint256"}]
    },
    {
        "name": "withdrawingBalance",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "token", "type": "address"},
            {"name": "depositor", "type": "address"}
        ],
        "outputs": [{"name": "", "type": "uint256"}]
    },
    {
        "name": "withdrawableBalance",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "token", "type": "address"},
            {"name": "depositor", "type": "address"}
        ],
        "outputs": [{"name": "", "type": "uint256"}]
    },
    {
        "name": "withdrawalDelay",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}]
    },
    {
        "name": "withdrawalBlock",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "token", "type": "address"},
            {"name": "depositor", "type": "address"}
        ],
        "outputs": [{"name": "", "type": "uint256"}]
    },
    {
        "name": "initiateWithdrawal",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "token", "type": "address"},
            {"name": "amount", "type": "uint256"}
        ],
        "outputs": []
    },
    {
        "name": "withdraw",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "token", "type": "address"}
        ],
        "outputs": []
    }
]""")


# Gateway Minter ABI for cross-chain minting
GATEWAY_MINTER_ABI = json.loads("""[
    {
        "name": "gatewayMint",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "attestationPayload", "type": "bytes"},
            {"name": "signature", "type": "bytes"}
        ],
        "outputs": []
    }
]""")


def format_usdc(amount: int) -> str:
    """Format a raw USDC amount (6 decimals) to a human-readable string."""
    return f"{amount / 10**USDC_DECIMALS:.{USDC_DECIMALS}f}"


def parse_usdc(amount: str) -> int:
    """
    Parse a human-readable USDC amount to raw integer (6 decimals).

    Uses Decimal for proper rounding (half-up).
    """
    if amount.startswith("$"):
        amount = amount[1:]
    return int((Decimal(amount) * 10**USDC_DECIMALS).quantize(1, ROUND_HALF_UP))


def generate_nonce() -> bytes:
    """Generate a random 32-byte nonce for TransferWithAuthorization."""
    return os.urandom(32)


def get_block_number(chain: str, rpc_url: str | None = None) -> int:
    """
    Get the current block number for a chain.

    Uses titanoboa's RPC connection.
    """
    setup_boa_env(chain, rpc_url)
    result: int = boa.env.vm.state.block_number
    return result


# =============================================================================
# Transaction Execution Helpers
# =============================================================================


def setup_boa_with_account(
    chain: str,
    private_key: str,
    rpc_url: str | None = None,
) -> tuple[str, Any]:
    """
    Set up titanoboa environment with a signing account.

    This configures boa to sign and broadcast transactions using the
    provided private key.

    Args:
        chain: Chain name (e.g., 'arcTestnet')
        private_key: Hex-encoded private key
        rpc_url: Optional custom RPC URL

    Returns:
        Tuple of (address, boa environment)
    """
    config = get_chain_config(chain)
    url = rpc_url or config.rpc_url

    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    account = Account.from_key(private_key)

    boa.set_network_env(url)
    boa.env.add_account(account, force_eoa=True)

    return account.address, boa.env


def execute_approve(
    chain: str,
    private_key: str,
    spender: str,
    amount: int,
    rpc_url: str | None = None,
) -> str:
    """
    Approve a spender to transfer USDC on behalf of the signer.

    Args:
        chain: Chain name
        private_key: Hex-encoded private key
        spender: Address to approve (e.g., Gateway contract)
        amount: Amount to approve (raw, 6 decimals)
        rpc_url: Optional custom RPC URL

    Returns:
        Transaction hash
    """
    config = get_chain_config(chain)
    setup_boa_with_account(chain, private_key, rpc_url)

    factory = boa.loads_abi(json.dumps(ERC20_ABI))
    usdc = factory.at(config.usdc_address)

    tx = usdc.approve(spender, amount)

    try:
        if hasattr(boa.env, "last_tx") and boa.env.last_tx:
            return (
                boa.env.last_tx.hex() if hasattr(boa.env.last_tx, "hex") else str(boa.env.last_tx)
            )
        return str(tx) if tx else ""
    except Exception:
        return str(tx) if tx else ""


def execute_deposit(
    chain: str,
    private_key: str,
    amount: int,
    rpc_url: str | None = None,
) -> str:
    """
    Deposit USDC into the Gateway contract.

    Args:
        chain: Chain name
        private_key: Hex-encoded private key
        amount: Amount to deposit (raw, 6 decimals)
        rpc_url: Optional custom RPC URL

    Returns:
        Transaction hash
    """
    config = get_chain_config(chain)
    setup_boa_with_account(chain, private_key, rpc_url)

    factory = boa.loads_abi(json.dumps(GATEWAY_WALLET_ABI))
    gateway = factory.at(config.gateway_address)

    try:
        tx = gateway.deposit(config.usdc_address, amount)
    except Exception as e:
        error_str = str(e)
        if "0x" in error_str and len(error_str) > 100:
            if hasattr(boa.env, "last_tx") and boa.env.last_tx:
                tx_hash = (
                    boa.env.last_tx.hex()
                    if hasattr(boa.env.last_tx, "hex")
                    else str(boa.env.last_tx)
                )
                return tx_hash
            return ""
        raise

    try:
        if hasattr(boa.env, "last_tx") and boa.env.last_tx:
            return (
                boa.env.last_tx.hex() if hasattr(boa.env.last_tx, "hex") else str(boa.env.last_tx)
            )
        return str(tx) if tx else ""
    except Exception:
        return str(tx) if tx else ""


def execute_gateway_mint(
    chain: str,
    private_key: str,
    attestation: bytes,
    signature: bytes,
    rpc_url: str | None = None,
) -> str:
    """
    Call gatewayMint on the destination chain's minter contract.

    Args:
        chain: Chain name
        private_key: Hex-encoded private key
        attestation: Attestation payload bytes
        signature: Signature bytes
        rpc_url: Optional custom RPC URL

    Returns:
        Transaction hash
    """
    config = get_chain_config(chain)
    setup_boa_with_account(chain, private_key, rpc_url)

    factory = boa.loads_abi(json.dumps(GATEWAY_MINTER_ABI))
    minter = factory.at(config.gateway_minter)

    tx = minter.gatewayMint(attestation, signature)

    try:
        if hasattr(boa.env, "last_tx") and boa.env.last_tx:
            return (
                boa.env.last_tx.hex() if hasattr(boa.env.last_tx, "hex") else str(boa.env.last_tx)
            )
        return str(tx) if tx else ""
    except Exception:
        return str(tx) if tx else ""


def check_allowance(
    chain: str,
    owner: str,
    spender: str,
    rpc_url: str | None = None,
) -> int:
    """
    Check USDC allowance for a spender.

    Args:
        chain: Chain name
        owner: Token owner address
        spender: Spender address (e.g., Gateway)
        rpc_url: Optional custom RPC URL

    Returns:
        Current allowance (raw, 6 decimals)
    """
    config = get_chain_config(chain)
    setup_boa_env(chain, rpc_url)

    factory = boa.loads_abi(json.dumps(ERC20_ABI))
    usdc = factory.at(config.usdc_address)
    result: int = usdc.allowance(owner, spender)
    return result


def get_withdrawal_delay(
    chain: str,
    rpc_url: str | None = None,
) -> int:
    """
    Get the trustless withdrawal delay (in blocks) from the Gateway contract.

    Args:
        chain: Chain name
        rpc_url: Optional custom RPC URL

    Returns:
        Withdrawal delay in blocks
    """
    setup_boa_env(chain, rpc_url)

    factory = boa.loads_abi(json.dumps(GATEWAY_WALLET_ABI))
    config = get_chain_config(chain)
    gateway = factory.at(config.gateway_address)
    result: int = gateway.withdrawalDelay()
    return result


def get_withdrawal_block(
    chain: str,
    address: str,
    rpc_url: str | None = None,
) -> int:
    """
    Get the block number at which a trustless withdrawal becomes completable.

    Args:
        chain: Chain name
        address: Depositor address
        rpc_url: Optional custom RPC URL

    Returns:
        Block number (0 if no pending withdrawal)
    """
    config = get_chain_config(chain)
    setup_boa_env(chain, rpc_url)

    factory = boa.loads_abi(json.dumps(GATEWAY_WALLET_ABI))
    gateway = factory.at(config.gateway_address)
    result: int = gateway.withdrawalBlock(config.usdc_address, address)
    return result


def execute_initiate_withdrawal(
    chain: str,
    private_key: str,
    amount: int,
    rpc_url: str | None = None,
) -> str:
    """
    Initiate a trustless withdrawal from the Gateway contract.

    Args:
        chain: Chain name
        private_key: Hex-encoded private key
        amount: Amount to withdraw (raw, 6 decimals)
        rpc_url: Optional custom RPC URL

    Returns:
        Transaction hash
    """
    config = get_chain_config(chain)
    setup_boa_with_account(chain, private_key, rpc_url)

    factory = boa.loads_abi(json.dumps(GATEWAY_WALLET_ABI))
    gateway = factory.at(config.gateway_address)

    tx = gateway.initiateWithdrawal(config.usdc_address, amount)

    try:
        if hasattr(boa.env, "last_tx") and boa.env.last_tx:
            return (
                boa.env.last_tx.hex() if hasattr(boa.env.last_tx, "hex") else str(boa.env.last_tx)
            )
        return str(tx) if tx else ""
    except Exception:
        return str(tx) if tx else ""


def execute_complete_withdrawal(
    chain: str,
    private_key: str,
    rpc_url: str | None = None,
) -> str:
    """
    Complete a trustless withdrawal from the Gateway contract.

    Args:
        chain: Chain name
        private_key: Hex-encoded private key
        rpc_url: Optional custom RPC URL

    Returns:
        Transaction hash
    """
    config = get_chain_config(chain)
    setup_boa_with_account(chain, private_key, rpc_url)

    factory = boa.loads_abi(json.dumps(GATEWAY_WALLET_ABI))
    gateway = factory.at(config.gateway_address)

    tx = gateway.withdraw(config.usdc_address)

    try:
        if hasattr(boa.env, "last_tx") and boa.env.last_tx:
            return (
                boa.env.last_tx.hex() if hasattr(boa.env.last_tx, "hex") else str(boa.env.last_tx)
            )
        return str(tx) if tx else ""
    except Exception:
        return str(tx) if tx else ""


def execute_deposit_for(
    chain: str,
    private_key: str,
    depositor: str,
    amount: int,
    rpc_url: str | None = None,
) -> str:
    """
    Deposit USDC into the Gateway contract on behalf of another address.

    Args:
        chain: Chain name
        private_key: Hex-encoded private key
        depositor: Address to credit the deposit to
        amount: Amount to deposit (raw, 6 decimals)
        rpc_url: Optional custom RPC URL

    Returns:
        Transaction hash
    """
    config = get_chain_config(chain)
    setup_boa_with_account(chain, private_key, rpc_url)

    factory = boa.loads_abi(json.dumps(GATEWAY_WALLET_ABI))
    gateway = factory.at(config.gateway_address)

    tx = gateway.depositFor(config.usdc_address, depositor, amount)

    try:
        if hasattr(boa.env, "last_tx") and boa.env.last_tx:
            return (
                boa.env.last_tx.hex() if hasattr(boa.env.last_tx, "hex") else str(boa.env.last_tx)
            )
        return str(tx) if tx else ""
    except Exception:
        return str(tx) if tx else ""


def get_usdc_balance(
    chain: str,
    address: str,
    rpc_url: str | None = None,
) -> int:
    """
    Get USDC balance for an address.

    Args:
        chain: Chain name
        address: Address to check
        rpc_url: Optional custom RPC URL

    Returns:
        Balance (raw, 6 decimals)
    """
    config = get_chain_config(chain)
    setup_boa_env(chain, rpc_url)

    factory = boa.loads_abi(json.dumps(ERC20_ABI))
    usdc = factory.at(config.usdc_address)
    result: int = usdc.balanceOf(address)
    return result


def get_gateway_balance(
    chain: str,
    address: str,
    rpc_url: str | None = None,
) -> int:
    """
    Get Gateway balance for an address.

    Args:
        chain: Chain name
        address: Address to check
        rpc_url: Optional custom RPC URL

    Returns:
        Balance (raw, 6 decimals)
    """
    config = get_chain_config(chain)
    setup_boa_env(chain, rpc_url)

    factory = boa.loads_abi(json.dumps(GATEWAY_WALLET_ABI))
    gateway = factory.at(config.gateway_address)
    result: int = gateway.totalBalance(config.usdc_address, address)
    return result
