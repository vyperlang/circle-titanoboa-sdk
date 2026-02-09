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
