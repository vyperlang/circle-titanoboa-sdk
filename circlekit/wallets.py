"""
Circle Programmable Wallets integration for AI agent identity management.

This module provides a wrapper around Circle's official Developer-Controlled
Wallets SDK, enabling agents to have persistent, secure wallets without managing
raw private keys. Circle handles key security.

Official docs: https://developers.circle.com/sdks/developer-controlled-wallets-python-sdk

Usage:
    from circlekit.wallets import AgentWalletManager
    
    manager = AgentWalletManager(
        api_key="your-api-key",
        entity_secret="your-entity-secret"
    )
    
    # Create a wallet set first (one-time)
    wallet_set = manager.create_wallet_set("my-agents")
    
    # Create a wallet for an agent
    wallet = manager.create_wallet(
        name="agent-001",
        wallet_set_id=wallet_set.wallet_set_id,
        blockchain="arcTestnet"
    )
    print(f"Agent wallet address: {wallet.address}")

Note:
    This module complements titanoboa (used for on-chain Vyper interactions).
    Circle SDK handles wallet identity/signing; titanoboa handles contract calls.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import os
import uuid

# Import from Circle's official SDK
# Using the high-level helper functions for proper setup
from circle.web3.utils import (
    init_developer_controlled_wallets_client,
    generate_entity_secret_ciphertext,
)
from circle.web3.developer_controlled_wallets import (
    WalletsApi,
    WalletSetsApi,
    SigningApi,
    TransactionsApi,
    CreateWalletRequest,
    CreateWalletSetRequest,
    SignMessageRequest,
    SignTypedDataRequest,
    WalletMetadata,
)


# Map friendly names to Circle's blockchain format
BLOCKCHAIN_MAPPING = {
    # Testnets
    "arcTestnet": "ARC-TESTNET",
    "ARC_TESTNET": "ARC-TESTNET",
    "baseSepolia": "BASE-SEPOLIA",
    "BASE_SEPOLIA": "BASE-SEPOLIA",
    "ethereumSepolia": "ETH-SEPOLIA",
    "ETH_SEPOLIA": "ETH-SEPOLIA",
    "avalancheFuji": "AVAX-FUJI",
    "AVAX_FUJI": "AVAX-FUJI",
    "maticAmoy": "MATIC-AMOY",
    "MATIC_AMOY": "MATIC-AMOY",
    # Mainnets
    "ethereum": "ETH",
    "ETH": "ETH",
    "base": "BASE",
    "BASE": "BASE",
    "polygon": "MATIC",
    "MATIC": "MATIC",
    "arbitrum": "ARB",
    "ARB": "ARB",
    "avalanche": "AVAX",
    "AVAX": "AVAX",
    "optimism": "OP",
    "OP": "OP",
}


@dataclass
class AgentWallet:
    """
    Represents a Circle-managed wallet for an agent.
    
    Attributes:
        wallet_id: Circle's internal wallet ID (use for API calls)
        address: On-chain wallet address (use for transactions)
        blockchain: Blockchain this wallet is on
        name: Human-readable name
        state: Wallet state (e.g., "LIVE")
        wallet_set_id: The wallet set this wallet belongs to
    """
    wallet_id: str
    address: str
    blockchain: str
    name: Optional[str] = None
    state: Optional[str] = None
    wallet_set_id: Optional[str] = None


@dataclass
class WalletSet:
    """
    Represents a Circle wallet set (container for wallets).
    
    You need to create a wallet set before creating wallets.
    """
    wallet_set_id: str
    name: Optional[str] = None
    custody_type: Optional[str] = None


@dataclass
class SignatureResult:
    """Result of a signing operation."""
    signature: str
    wallet_id: str


class AgentWalletManager:
    """
    Manages Circle Programmable Wallets for AI agents.
    
    This enables agents to have persistent, secure wallets without managing
    raw private keys - Circle handles key security server-side.
    
    Prerequisites:
        - API key from Circle Developer Console (https://console.circle.com)
        - Entity secret (generated in Circle dashboard under Developer > Entity Secret)
    
    Args:
        api_key: Circle API key (or set CIRCLE_API_KEY env var)
        entity_secret: Circle entity secret (or set CIRCLE_ENTITY_SECRET env var)
    
    Example:
        manager = AgentWalletManager()
        
        # First, create a wallet set (one-time setup)
        wallet_set = manager.create_wallet_set("my-agent-wallets")
        
        # Then create wallets in that set
        wallet = manager.create_wallet(
            name="trading-agent-001",
            wallet_set_id=wallet_set.wallet_set_id,
            blockchain="arcTestnet"
        )
        
        print(f"Agent address: {wallet.address}")
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        entity_secret: Optional[str] = None,
    ):
        self._api_key = api_key or os.environ.get("CIRCLE_API_KEY")
        self._entity_secret = entity_secret or os.environ.get("CIRCLE_ENTITY_SECRET")
        
        if not self._api_key:
            raise ValueError(
                "Circle API key required. Set CIRCLE_API_KEY env var or pass api_key parameter. "
                "Get one from: https://console.circle.com"
            )
        
        if not self._entity_secret:
            raise ValueError(
                "Circle entity secret required. Set CIRCLE_ENTITY_SECRET env var or pass entity_secret parameter. "
                "Generate one in Circle Console under Developer > Entity Secret."
            )
        
        # Use Circle's official helper to initialize the ApiClient properly
        # This handles API key configuration, entity secret, and public key for encryption
        self._api_client = init_developer_controlled_wallets_client(
            api_key=self._api_key,
            entity_secret=self._entity_secret,
        )
        
        # Generate entity secret ciphertext for wallet operations
        self._entity_secret_ciphertext = generate_entity_secret_ciphertext(
            api_key=self._api_key,
            entity_secret_hex=self._entity_secret,
        )
        
        # Create API instances from the ApiClient
        self._wallets_api = WalletsApi(api_client=self._api_client)
        self._wallet_sets_api = WalletSetsApi(api_client=self._api_client)
        self._signing_api = SigningApi(api_client=self._api_client)
    
    def _normalize_blockchain(self, blockchain: str) -> str:
        """Convert friendly blockchain names to Circle's format."""
        return BLOCKCHAIN_MAPPING.get(blockchain, blockchain)
    
    def _generate_idempotency_key(self) -> str:
        """Generate a unique idempotency key for requests."""
        return str(uuid.uuid4())
    
    def create_wallet_set(self, name: str) -> WalletSet:
        """
        Create a wallet set (container for wallets).
        
        You must create a wallet set before creating wallets.
        Typically you only need one wallet set per application.
        
        Args:
            name: Human-readable name for the wallet set
            
        Returns:
            WalletSet with wallet_set_id
            
        Example:
            wallet_set = manager.create_wallet_set("my-agent-wallets")
            print(f"Wallet set ID: {wallet_set.wallet_set_id}")
        """
        response = self._wallet_sets_api.create_wallet_set(
            create_wallet_set_request=CreateWalletSetRequest(
                idempotencyKey=self._generate_idempotency_key(),
                entitySecretCiphertext=self._entity_secret_ciphertext,
                name=name,
            )
        )
        
        wallet_set_wrapper = response.data.wallet_set
        # SDK uses a wrapper class with actual_instance containing the real data
        wallet_set_data = wallet_set_wrapper.actual_instance if hasattr(wallet_set_wrapper, 'actual_instance') else wallet_set_wrapper
        
        return WalletSet(
            wallet_set_id=wallet_set_data.id,
            name=getattr(wallet_set_data, 'name', name),
            custody_type=getattr(wallet_set_data, 'custody_type', None),
        )
    
    def list_wallet_sets(self) -> List[WalletSet]:
        """
        List all wallet sets.
        
        Returns:
            List of WalletSet instances
        """
        response = self._wallet_sets_api.get_wallet_sets()
        
        result = []
        for ws in response.data.wallet_sets:
            # SDK uses a wrapper class with actual_instance
            actual = ws.actual_instance if hasattr(ws, 'actual_instance') else ws
            result.append(WalletSet(
                wallet_set_id=actual.id,
                name=getattr(actual, 'name', None),
                custody_type=getattr(actual, 'custody_type', None),
            ))
        return result
    
    def create_wallet(
        self,
        wallet_set_id: str,
        name: str = "agent-wallet",
        blockchain: str = "arcTestnet",
    ) -> AgentWallet:
        """
        Create a new Circle-managed wallet for an agent.
        
        Args:
            wallet_set_id: ID of the wallet set to create wallet in (required)
            name: Human-readable name (e.g., "trading-agent-001")
            blockchain: Target blockchain (default: arcTestnet)
                Supported: arcTestnet, baseSepolia, ethereumSepolia, 
                          ethereum, base, polygon, arbitrum, etc.
            
        Returns:
            AgentWallet with wallet_id and on-chain address
            
        Example:
            wallet = manager.create_wallet(
                wallet_set_id="ws-123",
                name="my-agent",
                blockchain="arcTestnet"
            )
            print(f"Address: {wallet.address}")
        """
        normalized_blockchain = self._normalize_blockchain(blockchain)
        
        # Call Circle API
        response = self._wallets_api.create_wallet(
            create_wallet_request=CreateWalletRequest(
                idempotencyKey=self._generate_idempotency_key(),
                entitySecretCiphertext=self._entity_secret_ciphertext,
                walletSetId=wallet_set_id,
                blockchains=[normalized_blockchain],
                metadata=[WalletMetadata(name=name)],
            )
        )
        
        # Extract wallet from response (SDK uses wrapper class)
        wallet_wrapper = response.data.wallets[0]
        wallet_data = wallet_wrapper.actual_instance if hasattr(wallet_wrapper, 'actual_instance') else wallet_wrapper
        
        return AgentWallet(
            wallet_id=wallet_data.id,
            address=wallet_data.address,
            blockchain=wallet_data.blockchain,
            name=name,
            state=getattr(wallet_data, 'state', None),
            wallet_set_id=wallet_set_id,
        )
    
    def get_wallet(self, wallet_id: str) -> AgentWallet:
        """
        Retrieve an existing wallet by ID.
        
        Args:
            wallet_id: Circle wallet ID
            
        Returns:
            AgentWallet with current details
        """
        response = self._wallets_api.get_wallet(id=wallet_id)
        wallet_wrapper = response.data.wallet
        # SDK uses wrapper class with actual_instance
        wallet_data = wallet_wrapper.actual_instance if hasattr(wallet_wrapper, 'actual_instance') else wallet_wrapper
        
        return AgentWallet(
            wallet_id=wallet_data.id,
            address=wallet_data.address,
            blockchain=wallet_data.blockchain,
            name=getattr(wallet_data, 'name', None),
            state=getattr(wallet_data, 'state', None),
            wallet_set_id=getattr(wallet_data, 'wallet_set_id', None),
        )
    
    def list_wallets(self, wallet_set_id: Optional[str] = None) -> List[AgentWallet]:
        """
        List all wallets.
        
        Args:
            wallet_set_id: Filter by wallet set (optional)
            
        Returns:
            List of AgentWallet instances
        """
        # Call without extra params - the SDK handles pagination internally
        if wallet_set_id:
            response = self._wallets_api.get_wallets(wallet_set_id=wallet_set_id)
        else:
            response = self._wallets_api.get_wallets()
        
        result = []
        for w in response.data.wallets:
            # SDK uses wrapper class with actual_instance
            actual = w.actual_instance if hasattr(w, 'actual_instance') else w
            result.append(AgentWallet(
                wallet_id=actual.id,
                address=actual.address,
                blockchain=actual.blockchain,
                name=getattr(actual, 'name', None),
                state=getattr(actual, 'state', None),
                wallet_set_id=getattr(actual, 'wallet_set_id', None),
            ))
        return result
    
    def sign_message(
        self,
        wallet_id: str,
        message: str,
    ) -> SignatureResult:
        """
        Sign a message using the wallet's key (managed by Circle).
        
        This can be used for:
        - Verifying wallet ownership
        - Off-chain authentication
        - Custom signing needs
        
        Args:
            wallet_id: Circle wallet ID
            message: Message to sign (will be prefixed with EIP-191)
            
        Returns:
            SignatureResult with hex signature
        """
        response = self._signing_api.sign_message(
            sign_message_request=SignMessageRequest(
                walletId=wallet_id,
                message=message,
                entitySecretCiphertext=self._entity_secret_ciphertext,
            )
        )
        
        return SignatureResult(
            signature=response.data.signature,
            wallet_id=wallet_id,
        )
    
    def sign_typed_data(
        self,
        wallet_id: str,
        typed_data: Dict[str, Any],
    ) -> SignatureResult:
        """
        Sign EIP-712 typed data using the wallet's key.
        
        This is used for:
        - x402 TransferWithAuthorization signatures
        - Permit signatures
        - Any EIP-712 structured data
        
        Args:
            wallet_id: Circle wallet ID
            typed_data: EIP-712 typed data structure with:
                - domain: EIP-712 domain
                - types: Type definitions
                - primaryType: Primary type name
                - message: Message data
            
        Returns:
            SignatureResult with hex signature
            
        Example:
            typed_data = {
                "domain": {...},
                "types": {...},
                "primaryType": "TransferWithAuthorization",
                "message": {...}
            }
            result = manager.sign_typed_data(wallet_id, typed_data)
        """
        import json
        
        # Circle SDK expects the typed data as a JSON string in the 'data' field
        response = self._signing_api.sign_typed_data(
            sign_typed_data_request=SignTypedDataRequest(
                walletId=wallet_id,
                data=json.dumps(typed_data),
                entitySecretCiphertext=self._entity_secret_ciphertext,
            )
        )
        
        return SignatureResult(
            signature=response.data.signature,
            wallet_id=wallet_id,
        )
    
    def get_wallet_balance(
        self,
        wallet_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get token balances for a wallet.
        
        Args:
            wallet_id: Circle wallet ID
            
        Returns:
            List of balance objects with token info
        """
        response = self._wallets_api.list_wallet_balance(id=wallet_id)
        
        return [
            {
                "token": b.token.symbol if hasattr(b.token, 'symbol') else str(b.token),
                "amount": b.amount,
                "blockchain": b.blockchain if hasattr(b, 'blockchain') else None,
            }
            for b in response.data.token_balances
        ]


def create_agent_wallet_manager(
    api_key: Optional[str] = None,
    entity_secret: Optional[str] = None,
) -> AgentWalletManager:
    """
    Create an AgentWalletManager instance.
    
    Convenience function for quick setup.
    
    Args:
        api_key: Circle API key (or set CIRCLE_API_KEY env var)
        entity_secret: Circle entity secret (or set CIRCLE_ENTITY_SECRET env var)
    
    Example:
        manager = create_agent_wallet_manager()
        
        # Create wallet set first
        wallet_set = manager.create_wallet_set("my-agents")
        
        # Then create wallet
        wallet = manager.create_wallet(wallet_set.wallet_set_id, "my-agent")
    """
    return AgentWalletManager(api_key=api_key, entity_secret=entity_secret)
