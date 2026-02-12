"""
Constants for x402 batching via Circle Gateway.
"""

from dataclasses import dataclass
from typing import Dict, Optional


# Protocol constants
CIRCLE_BATCHING_NAME = "GatewayWalletBatched"
CIRCLE_BATCHING_VERSION = "1"
CIRCLE_BATCHING_SCHEME = "exact"

# x402 protocol version
X402_VERSION = 2

# USDC decimals
USDC_DECIMALS = 6

# Gateway contract addresses (per client/index.mjs:292-295)
TESTNET_GATEWAY_WALLET = "0x0077777d7EBA4688BDeF3E311b846F25870A19B9"
TESTNET_GATEWAY_MINTER = "0x0022222ABE238Cc2C7Bb1f21003F0a260052475B"
MAINNET_GATEWAY_WALLET = "0x77777777Dcc4d5A8B6E418Fd04D8997ef11000eE"
MAINNET_GATEWAY_MINTER = "0x2222222d7164433c4C09B0b0D809a9b52C04C205"


@dataclass
class ChainConfig:
    """Configuration for a supported chain."""

    chain_id: int
    name: str
    rpc_url: str
    usdc_address: str
    gateway_address: str
    gateway_minter: str
    gateway_domain: int
    explorer_url: Optional[str] = None
    is_testnet: bool = True


# Chain configurations
# gateway_domain values are Circle's internal domain IDs, NOT chain IDs
CHAIN_CONFIGS: Dict[str, ChainConfig] = {
    # ============ TESTNETS ============
    # NOTE: On Arc, USDC is the NATIVE gas token (like ETH on Ethereum).
    # However, there's a sentinel contract at 0x3600... that wraps native USDC
    # as an ERC-20, so standard balanceOf/approve/transferFrom work normally.
    "arcTestnet": ChainConfig(
        chain_id=5042002,
        name="Arc Testnet",
        rpc_url="https://arc-testnet.drpc.org",
        usdc_address="0x3600000000000000000000000000000000000000",
        gateway_address=TESTNET_GATEWAY_WALLET,
        gateway_minter=TESTNET_GATEWAY_MINTER,
        gateway_domain=26,
        explorer_url="https://testnet.arcscan.app",
        is_testnet=True,
    ),
    "baseSepolia": ChainConfig(
        chain_id=84532,
        name="Base Sepolia",
        rpc_url="https://sepolia.base.org",
        usdc_address="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        gateway_address=TESTNET_GATEWAY_WALLET,
        gateway_minter=TESTNET_GATEWAY_MINTER,
        gateway_domain=6,
        explorer_url="https://sepolia.basescan.org",
        is_testnet=True,
    ),
    "ethereumSepolia": ChainConfig(
        chain_id=11155111,
        name="Ethereum Sepolia",
        rpc_url="https://sepolia.drpc.org",
        usdc_address="0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",
        gateway_address=TESTNET_GATEWAY_WALLET,
        gateway_minter=TESTNET_GATEWAY_MINTER,
        gateway_domain=0,
        explorer_url="https://sepolia.etherscan.io",
        is_testnet=True,
    ),
    "avalancheFuji": ChainConfig(
        chain_id=43113,
        name="Avalanche Fuji",
        rpc_url="https://api.avax-test.network/ext/bc/C/rpc",
        usdc_address="0x5425890298aed601595a70AB815c96711a31Bc65",
        gateway_address=TESTNET_GATEWAY_WALLET,
        gateway_minter=TESTNET_GATEWAY_MINTER,
        gateway_domain=1,
        explorer_url="https://testnet.snowtrace.io",
        is_testnet=True,
    ),
    "hyperEvmTestnet": ChainConfig(
        chain_id=998,
        name="HyperEVM Testnet",
        rpc_url="https://rpc.hyperliquid-testnet.xyz/evm",
        usdc_address="0x2Af537e09F5765B1F06CDB48cD5498c83B6ce3ae",
        gateway_address=TESTNET_GATEWAY_WALLET,
        gateway_minter=TESTNET_GATEWAY_MINTER,
        gateway_domain=19,
        explorer_url="https://testnet.purrsec.com",
        is_testnet=True,
    ),
    "sonicTestnet": ChainConfig(
        chain_id=64165,
        name="Sonic Testnet",
        rpc_url="https://rpc.blaze.soniclabs.com",
        usdc_address="0x29219dd400f2Bf60E5a23d13Be72B486D4038894",
        gateway_address=TESTNET_GATEWAY_WALLET,
        gateway_minter=TESTNET_GATEWAY_MINTER,
        gateway_domain=13,
        explorer_url="https://testnet.soniclabs.com",
        is_testnet=True,
    ),
    "worldChainSepolia": ChainConfig(
        chain_id=4801,
        name="World Chain Sepolia",
        rpc_url="https://worldchain-sepolia.g.alchemy.com/public",
        usdc_address="0x20bB2a4ea658C5AE8b4b3a7E5E29d9C55FD5f3a6",
        gateway_address=TESTNET_GATEWAY_WALLET,
        gateway_minter=TESTNET_GATEWAY_MINTER,
        gateway_domain=14,
        explorer_url="https://sepolia.worldscan.org",
        is_testnet=True,
    ),
    "seiAtlantic": ChainConfig(
        chain_id=1328,
        name="Sei Atlantic Testnet",
        rpc_url="https://evm-rpc-testnet.sei-apis.com",
        usdc_address="0x3894085Ef7Ff0f0aeDf52E2A2704928d1Ec074F1",
        gateway_address=TESTNET_GATEWAY_WALLET,
        gateway_minter=TESTNET_GATEWAY_MINTER,
        gateway_domain=16,
        explorer_url="https://seistream.app",
        is_testnet=True,
    ),

    # ============ MAINNETS ============
    "ethereum": ChainConfig(
        chain_id=1,
        name="Ethereum",
        rpc_url="https://eth.drpc.org",
        usdc_address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        gateway_address=MAINNET_GATEWAY_WALLET,
        gateway_minter=MAINNET_GATEWAY_MINTER,
        gateway_domain=0,
        explorer_url="https://etherscan.io",
        is_testnet=False,
    ),
    "base": ChainConfig(
        chain_id=8453,
        name="Base",
        rpc_url="https://mainnet.base.org",
        usdc_address="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        gateway_address=MAINNET_GATEWAY_WALLET,
        gateway_minter=MAINNET_GATEWAY_MINTER,
        gateway_domain=6,
        explorer_url="https://basescan.org",
        is_testnet=False,
    ),
    "arbitrum": ChainConfig(
        chain_id=42161,
        name="Arbitrum One",
        rpc_url="https://arb1.arbitrum.io/rpc",
        usdc_address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        gateway_address=MAINNET_GATEWAY_WALLET,
        gateway_minter=MAINNET_GATEWAY_MINTER,
        gateway_domain=3,
        explorer_url="https://arbiscan.io",
        is_testnet=False,
    ),
    "polygon": ChainConfig(
        chain_id=137,
        name="Polygon",
        rpc_url="https://polygon.drpc.org",
        usdc_address="0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
        gateway_address=MAINNET_GATEWAY_WALLET,
        gateway_minter=MAINNET_GATEWAY_MINTER,
        gateway_domain=7,
        explorer_url="https://polygonscan.com",
        is_testnet=False,
    ),
    "optimism": ChainConfig(
        chain_id=10,
        name="Optimism",
        rpc_url="https://mainnet.optimism.io",
        usdc_address="0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
        gateway_address=MAINNET_GATEWAY_WALLET,
        gateway_minter=MAINNET_GATEWAY_MINTER,
        gateway_domain=2,
        explorer_url="https://optimistic.etherscan.io",
        is_testnet=False,
    ),
    "avalanche": ChainConfig(
        chain_id=43114,
        name="Avalanche C-Chain",
        rpc_url="https://api.avax.network/ext/bc/C/rpc",
        usdc_address="0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E",
        gateway_address=MAINNET_GATEWAY_WALLET,
        gateway_minter=MAINNET_GATEWAY_MINTER,
        gateway_domain=1,
        explorer_url="https://snowtrace.io",
        is_testnet=False,
    ),
    "sonic": ChainConfig(
        chain_id=146,
        name="Sonic",
        rpc_url="https://rpc.soniclabs.com",
        usdc_address="0x29219dd400f2Bf60E5a23d13Be72B486D4038894",
        gateway_address=MAINNET_GATEWAY_WALLET,
        gateway_minter=MAINNET_GATEWAY_MINTER,
        gateway_domain=13,
        explorer_url="https://sonicscan.org",
        is_testnet=False,
    ),
    "unichain": ChainConfig(
        chain_id=130,
        name="Unichain",
        rpc_url="https://mainnet.unichain.org",
        usdc_address="0x078D782b760474a361dDA0AF3839290b0EF57AD6",
        gateway_address=MAINNET_GATEWAY_WALLET,
        gateway_minter=MAINNET_GATEWAY_MINTER,
        gateway_domain=10,
        explorer_url="https://uniscan.xyz",
        is_testnet=False,
    ),
    "worldChain": ChainConfig(
        chain_id=480,
        name="World Chain",
        rpc_url="https://worldchain-mainnet.g.alchemy.com/public",
        usdc_address="0x79A02482A880bCE3B13e43a30CFD5a1feFC55043",
        gateway_address=MAINNET_GATEWAY_WALLET,
        gateway_minter=MAINNET_GATEWAY_MINTER,
        gateway_domain=14,
        explorer_url="https://worldscan.org",
        is_testnet=False,
    ),
    "hyperEvm": ChainConfig(
        chain_id=999,
        name="HyperEVM",
        rpc_url="https://rpc.hyperliquid.xyz/evm",
        usdc_address="0x2Af537e09F5765B1F06CDB48cD5498c83B6ce3ae",
        gateway_address=MAINNET_GATEWAY_WALLET,
        gateway_minter=MAINNET_GATEWAY_MINTER,
        gateway_domain=19,
        explorer_url="https://purrsec.com",
        is_testnet=False,
    ),
    "sei": ChainConfig(
        chain_id=1329,
        name="Sei",
        rpc_url="https://evm-rpc.sei-apis.com",
        usdc_address="0x3894085Ef7Ff0f0aeDf52E2A2704928d1Ec074F1",
        gateway_address=MAINNET_GATEWAY_WALLET,
        gateway_minter=MAINNET_GATEWAY_MINTER,
        gateway_domain=16,
        explorer_url="https://seistream.app",
        is_testnet=False,
    ),
}


# Chain name aliases
CHAIN_ALIASES: Dict[str, str] = {
    "sepolia": "ethereumSepolia",
    "mainnet": "ethereum",
}

# Gateway API endpoints (real Circle endpoints)
GATEWAY_API_BASE_URL = "https://gateway-api.circle.com"
GATEWAY_API_TESTNET_URL = "https://gateway-api-testnet.circle.com"


def get_gateway_api_url(is_testnet: bool = True) -> str:
    """Get the Gateway API base URL for the given environment."""
    return GATEWAY_API_TESTNET_URL if is_testnet else GATEWAY_API_BASE_URL


def get_chain_config(chain: str) -> ChainConfig:
    """
    Get chain configuration by name.

    Args:
        chain: Chain identifier (e.g., "arcTestnet", "baseSepolia", "sepolia", "mainnet")

    Returns:
        ChainConfig for the specified chain

    Raises:
        ValueError: If chain is not supported
    """
    # Resolve aliases first
    resolved = CHAIN_ALIASES.get(chain, chain)
    if resolved not in CHAIN_CONFIGS:
        supported = ", ".join(list(CHAIN_CONFIGS.keys()) + list(CHAIN_ALIASES.keys()))
        raise ValueError(f"Unsupported chain: {chain}. Supported chains: {supported}")
    return CHAIN_CONFIGS[resolved]


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
