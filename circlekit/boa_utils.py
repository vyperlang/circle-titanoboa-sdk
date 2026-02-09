"""
Titanoboa utilities for Circle Gateway interactions.

This module provides helpers for using titanoboa (boa) for all on-chain
interactions instead of web3.py. It handles:
- RPC connection management
- Contract loading and interaction
- Transaction building and signing
- ABI encoding/decoding
"""

from typing import Any, Dict, Optional, Tuple
import os
import json

import boa
from eth_account import Account
from eth_account.messages import encode_typed_data

from circlekit.constants import CHAIN_CONFIGS, ChainConfig


def get_chain_config(chain: str) -> ChainConfig:
    """
    Get the configuration for a chain by name.
    
    Args:
        chain: Chain name (e.g., 'arcTestnet', 'baseSepolia')
        
    Returns:
        ChainConfig with RPC URL, addresses, etc.
        
    Raises:
        ValueError: If chain is not supported
    """
    if chain not in CHAIN_CONFIGS:
        supported = ", ".join(CHAIN_CONFIGS.keys())
        raise ValueError(f"Unsupported chain: {chain}. Supported: {supported}")
    return CHAIN_CONFIGS[chain]


def get_rpc_url(chain: str) -> str:
    """Get the RPC URL for a chain."""
    return get_chain_config(chain).rpc_url


def setup_boa_env(chain: str, rpc_url: Optional[str] = None) -> None:
    """
    Configure titanoboa environment for a specific chain.
    
    Args:
        chain: Chain name (e.g., 'arcTestnet')
        rpc_url: Optional custom RPC URL (overrides default)
    """
    config = get_chain_config(chain)
    url = rpc_url or config.rpc_url
    
    # Set the RPC URL in boa environment
    boa.set_network_env(url)


def get_account_from_private_key(private_key: str) -> Tuple[str, Account]:
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


def sign_typed_data(
    private_key: str,
    domain_data: Dict[str, Any],
    message_types: Dict[str, list],
    message_data: Dict[str, Any],
    primary_type: str,
) -> str:
    """
    Sign EIP-712 typed data.
    
    This is used for signing USDC TransferWithAuthorization messages
    for gasless payments.
    
    Args:
        private_key: Hex-encoded private key
        domain_data: EIP-712 domain (name, version, chainId, verifyingContract)
        message_types: Type definitions for the message
        message_data: The actual message to sign
        primary_type: The primary type name
        
    Returns:
        Hex-encoded signature
    """
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key
    
    account = Account.from_key(private_key)
    
    # Construct the full typed data
    full_message = {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            **message_types,
        },
        "primaryType": primary_type,
        "domain": domain_data,
        "message": message_data,
    }
    
    # Sign the typed data
    signed = account.sign_typed_data(full_message=full_message)
    
    return signed.signature.hex()


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


# Gateway Wallet ABI (minimal for deposits/withdrawals)
GATEWAY_WALLET_ABI = json.loads("""[
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "amount", "type": "uint256"}],
        "name": "deposit",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "amount", "type": "uint256"},
            {"name": "recipient", "type": "address"}
        ],
        "name": "withdraw",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]""")


def load_usdc_contract(chain: str, rpc_url: Optional[str] = None):
    """
    Load the USDC contract for a chain using boa.
    
    Args:
        chain: Chain name
        rpc_url: Optional custom RPC URL
        
    Returns:
        Contract object with USDC methods
    """
    config = get_chain_config(chain)
    setup_boa_env(chain, rpc_url)
    
    # Load contract from ABI at the USDC address
    return boa.loads_abi(json.dumps(ERC20_ABI), config.usdc_address)


def load_gateway_contract(chain: str, rpc_url: Optional[str] = None):
    """
    Load the Gateway Wallet contract for a chain using boa.
    
    Args:
        chain: Chain name
        rpc_url: Optional custom RPC URL
        
    Returns:
        Contract object with Gateway methods
    """
    config = get_chain_config(chain)
    setup_boa_env(chain, rpc_url)
    
    # Load contract from ABI at the Gateway address
    return boa.loads_abi(json.dumps(GATEWAY_WALLET_ABI), config.gateway_address)


def format_usdc(amount: int) -> str:
    """Format a raw USDC amount (6 decimals) to a human-readable string."""
    return f"{amount / 10**6:.6f}"


def parse_usdc(amount: str) -> int:
    """Parse a human-readable USDC amount to raw integer (6 decimals)."""
    # Remove $ prefix if present
    if amount.startswith("$"):
        amount = amount[1:]
    return int(float(amount) * 10**6)


def generate_nonce() -> bytes:
    """Generate a random 32-byte nonce for TransferWithAuthorization."""
    return os.urandom(32)


def get_block_timestamp(chain: str, rpc_url: Optional[str] = None) -> int:
    """
    Get the current block timestamp for a chain.
    
    Uses titanoboa's RPC connection.
    """
    setup_boa_env(chain, rpc_url)
    return boa.env.vm.state.timestamp


# =============================================================================
# Transaction Execution Helpers
# =============================================================================

def setup_boa_with_account(
    chain: str,
    private_key: str,
    rpc_url: Optional[str] = None,
) -> Tuple[str, Any]:
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
    
    # Ensure private key has 0x prefix
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key
    
    # Get account
    account = Account.from_key(private_key)
    
    # Set up network environment with the account
    # titanoboa uses boa.env.add_account() for signing
    boa.set_network_env(url)
    boa.env.add_account(account)
    
    return account.address, boa.env


def execute_approve(
    chain: str,
    private_key: str,
    spender: str,
    amount: int,
    rpc_url: Optional[str] = None,
) -> str:
    """
    Approve a spender to transfer USDC on behalf of the signer.
    
    Uses titanoboa's account system for signing real transactions.
    
    Args:
        chain: Chain name
        private_key: Hex-encoded private key
        spender: Address to approve (e.g., Gateway contract)
        amount: Amount to approve (raw, 6 decimals)
        rpc_url: Optional custom RPC URL
        
    Returns:
        Transaction hash
        
    Note:
        Requires the account to have gas tokens for transaction fees.
        On Arc Testnet, gas is paid in USDC.
    """
    config = get_chain_config(chain)
    address, env = setup_boa_with_account(chain, private_key, rpc_url)
    
    # Load USDC contract with the signer's address set
    usdc = boa.loads_abi(json.dumps(ERC20_ABI), config.usdc_address)
    
    # Execute approve transaction
    # After add_account(), boa uses that account for signing transactions
    # The account added in setup_boa_with_account is used automatically
    tx = usdc.approve(spender, amount)
    
    # Return tx hash (boa returns the result, tx hash is in env)
    # For network transactions, we need to get the tx hash differently
    try:
        # Try to get last tx hash from boa environment
        if hasattr(boa.env, 'last_tx') and boa.env.last_tx:
            return boa.env.last_tx.hex() if hasattr(boa.env.last_tx, 'hex') else str(boa.env.last_tx)
        return str(tx) if tx else ""
    except Exception:
        return str(tx) if tx else ""


def execute_deposit(
    chain: str,
    private_key: str,
    amount: int,
    rpc_url: Optional[str] = None,
) -> str:
    """
    Deposit USDC into the Gateway contract.
    
    Uses titanoboa's account system for signing real transactions.
    
    Note: Requires prior approval of the Gateway contract to spend USDC.
    
    Args:
        chain: Chain name
        private_key: Hex-encoded private key
        amount: Amount to deposit (raw, 6 decimals)
        rpc_url: Optional custom RPC URL
        
    Returns:
        Transaction hash
        
    Note:
        Requires the account to have:
        1. USDC approved for the Gateway contract
        2. Gas tokens for transaction fees
    """
    config = get_chain_config(chain)
    address, env = setup_boa_with_account(chain, private_key, rpc_url)
    
    # Load Gateway contract
    gateway = boa.loads_abi(json.dumps(GATEWAY_WALLET_ABI), config.gateway_address)
    
    # Execute deposit transaction
    # The account added in setup_boa_with_account is used for signing
    tx = gateway.deposit(amount)
    
    try:
        if hasattr(boa.env, 'last_tx') and boa.env.last_tx:
            return boa.env.last_tx.hex() if hasattr(boa.env.last_tx, 'hex') else str(boa.env.last_tx)
        return str(tx) if tx else ""
    except Exception:
        return str(tx) if tx else ""


def check_allowance(
    chain: str,
    owner: str,
    spender: str,
    rpc_url: Optional[str] = None,
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
    
    usdc = boa.loads_abi(json.dumps(ERC20_ABI), config.usdc_address)
    return usdc.allowance(owner, spender)


def get_usdc_balance(
    chain: str,
    address: str,
    rpc_url: Optional[str] = None,
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
    
    usdc = boa.loads_abi(json.dumps(ERC20_ABI), config.usdc_address)
    return usdc.balanceOf(address)


def get_gateway_balance(
    chain: str,
    address: str,
    rpc_url: Optional[str] = None,
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
    
    gateway = boa.loads_abi(json.dumps(GATEWAY_WALLET_ABI), config.gateway_address)
    return gateway.balanceOf(address)
