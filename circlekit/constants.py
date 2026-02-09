"""
Constants for Circle Gateway x402 protocol.

These match the TypeScript SDK's CHAIN_CONFIGS, GATEWAY_DOMAINS, etc.
"""

from dataclasses import dataclass
from typing import Dict, Optional


# Protocol constants (match TypeScript SDK)
CIRCLE_BATCHING_NAME = "GatewayWalletBatched"
CIRCLE_BATCHING_VERSION = "1"
CIRCLE_BATCHING_SCHEME = "exact"

# x402 protocol version
X402_VERSION = 2

# Minimum signature validity (4 days in seconds)
MIN_SIGNATURE_VALIDITY_SECONDS = 4 * 24 * 60 * 60

# USDC decimals
USDC_DECIMALS = 6


@dataclass
class ChainConfig:
    """Configuration for a supported chain."""
    
    chain_id: int
    name: str
    rpc_url: str
    usdc_address: str
    gateway_address: str
    gateway_domain: int
    explorer_url: Optional[str] = None
    is_testnet: bool = True


# Chain configurations
# These are the networks supported by Circle Gateway
CHAIN_CONFIGS: Dict[str, ChainConfig] = {
    # ============ TESTNETS ============
    # NOTE: On Arc, USDC is the NATIVE gas token (like ETH on Ethereum).
    # However, there's a sentinel contract at 0x3600... that wraps native USDC
    # as an ERC-20, so standard balanceOf/approve/transferFrom work normally.
    "arcTestnet": ChainConfig(
        chain_id=5042002,
        name="Arc Testnet",
        rpc_url="https://arc-testnet.drpc.org",  # dRPC public endpoint (more reliable)
        usdc_address="0x3600000000000000000000000000000000000000",  # Native USDC sentinel address
        gateway_address="0x0077777d7eba4688bdef3e311b846f25870a19b9",  # Gateway Wallet (verified)
        gateway_domain=26,  # Arc Testnet domain ID from Circle docs
        explorer_url="https://testnet.arcscan.app",  # Real Arc explorer
        is_testnet=True,
    ),
    "baseSepolia": ChainConfig(
        chain_id=84532,
        name="Base Sepolia",
        rpc_url="https://sepolia.base.org",
        usdc_address="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        gateway_address="0x0077777d7eba4688bdef3e311b846f25870a19b9",
        gateway_domain=84532,
        explorer_url="https://sepolia.basescan.org",
        is_testnet=True,
    ),
    "ethereumSepolia": ChainConfig(
        chain_id=11155111,
        name="Ethereum Sepolia",
        rpc_url="https://sepolia.drpc.org",
        usdc_address="0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",
        gateway_address="0x0077777d7eba4688bdef3e311b846f25870a19b9",
        gateway_domain=11155111,
        explorer_url="https://sepolia.etherscan.io",
        is_testnet=True,
    ),
    "avalancheFuji": ChainConfig(
        chain_id=43113,
        name="Avalanche Fuji",
        rpc_url="https://api.avax-test.network/ext/bc/C/rpc",
        usdc_address="0x5425890298aed601595a70AB815c96711a31Bc65",
        gateway_address="0x0077777d7eba4688bdef3e311b846f25870a19b9",
        gateway_domain=43113,
        explorer_url="https://testnet.snowtrace.io",
        is_testnet=True,
    ),
    
    # ============ MAINNETS ============
    "ethereum": ChainConfig(
        chain_id=1,
        name="Ethereum",
        rpc_url="https://eth.drpc.org",
        usdc_address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        gateway_address="0x0077777d7eba4688bdef3e311b846f25870a19b9",
        gateway_domain=1,
        explorer_url="https://etherscan.io",
        is_testnet=False,
    ),
    "base": ChainConfig(
        chain_id=8453,
        name="Base",
        rpc_url="https://mainnet.base.org",
        usdc_address="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        gateway_address="0x0077777d7eba4688bdef3e311b846f25870a19b9",
        gateway_domain=8453,
        explorer_url="https://basescan.org",
        is_testnet=False,
    ),
    "arbitrum": ChainConfig(
        chain_id=42161,
        name="Arbitrum One",
        rpc_url="https://arb1.arbitrum.io/rpc",
        usdc_address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        gateway_address="0x0077777d7eba4688bdef3e311b846f25870a19b9",
        gateway_domain=42161,
        explorer_url="https://arbiscan.io",
        is_testnet=False,
    ),
    "polygon": ChainConfig(
        chain_id=137,
        name="Polygon",
        rpc_url="https://polygon.drpc.org",
        usdc_address="0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
        gateway_address="0x0077777d7eba4688bdef3e311b846f25870a19b9",
        gateway_domain=137,
        explorer_url="https://polygonscan.com",
        is_testnet=False,
    ),
    "optimism": ChainConfig(
        chain_id=10,
        name="Optimism",
        rpc_url="https://mainnet.optimism.io",
        usdc_address="0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
        gateway_address="0x0077777d7eba4688bdef3e311b846f25870a19b9",
        gateway_domain=10,
        explorer_url="https://optimistic.etherscan.io",
        is_testnet=False,
    ),
    "avalanche": ChainConfig(
        chain_id=43114,
        name="Avalanche C-Chain",
        rpc_url="https://api.avax.network/ext/bc/C/rpc",
        usdc_address="0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E",
        gateway_address="0x0077777d7eba4688bdef3e311b846f25870a19b9",
        gateway_domain=43114,
        explorer_url="https://snowtrace.io",
        is_testnet=False,
    ),
}


# Gateway API endpoints (real Circle endpoints)
GATEWAY_API_BASE_URL = "https://gateway-api.circle.com"
GATEWAY_API_TESTNET_URL = "https://gateway-api-testnet.circle.com"


def get_gateway_api_url(is_testnet: bool = True) -> str:
    """Get the Gateway API base URL for the given environment."""
    return GATEWAY_API_TESTNET_URL if is_testnet else GATEWAY_API_BASE_URL


# EIP-712 type definitions for USDC TransferWithAuthorization
EIP712_DOMAIN_TYPE = [
    {"name": "name", "type": "string"},
    {"name": "version", "type": "string"},
    {"name": "chainId", "type": "uint256"},
    {"name": "verifyingContract", "type": "address"},
]

TRANSFER_WITH_AUTHORIZATION_TYPE = [
    {"name": "from", "type": "address"},
    {"name": "to", "type": "address"},
    {"name": "value", "type": "uint256"},
    {"name": "validAfter", "type": "uint256"},
    {"name": "validBefore", "type": "uint256"},
    {"name": "nonce", "type": "bytes32"},
]


# USDC token info for EIP-712 domain
USDC_TOKEN_NAME = "USD Coin"
USDC_TOKEN_VERSION = "2"


def get_chain_config(chain: str) -> ChainConfig:
    """
    Get chain configuration by name.
    
    Args:
        chain: Chain identifier (e.g., "arcTestnet", "baseSepolia")
        
    Returns:
        ChainConfig for the specified chain
        
    Raises:
        ValueError: If chain is not supported
    """
    if chain not in CHAIN_CONFIGS:
        supported = ", ".join(CHAIN_CONFIGS.keys())
        raise ValueError(f"Unsupported chain: {chain}. Supported chains: {supported}")
    return CHAIN_CONFIGS[chain]


def get_chain_by_id(chain_id: int) -> Optional[ChainConfig]:
    """
    Get chain configuration by chain ID.
    
    Args:
        chain_id: The numeric chain ID
        
    Returns:
        ChainConfig if found, None otherwise
    """
    for config in CHAIN_CONFIGS.values():
        if config.chain_id == chain_id:
            return config
    return None
