# circle-titanoboa-sdk

Python SDK for Circle's x402 Protocol and Gateway API. Uses **titanoboa** for all on-chain interactions (no web3.py).

> Built for the [Vyper](https://github.com/vyperlang/vyper) ecosystem. Port of Circle's TypeScript SDK (`@circlefin/x402-batching`).

## What It Does

**circle-titanoboa-sdk** enables gasless micropayments for Python applications:

1. **Buyers** can pay for API access without gas fees (signatures only)
2. **Sellers** can monetize APIs with simple decorators
3. **Settlement** happens in batches via Circle Gateway

```
User Request -> 402 Payment Required -> Sign Message (free) -> Access Granted
                                             |
                              Circle Gateway batches payments on-chain
```

## Features

- **x402 Payment Protocol** - HTTP 402 Payment Required flow
- **Gateway Client** - Pay for x402-protected resources with USDC
- **Gateway Middleware** - Protect Flask/FastAPI endpoints with paywalls
- **Programmable Wallets** - Circle-managed wallets for agent identity (no raw private keys)
- **Arc Testnet** - Circle's L2 where USDC is the native gas token
- **Multi-chain** - Arc, Base, Ethereum, Avalanche (testnets + mainnets)
- **Pure titanoboa** - No web3.py dependency

## Circle Products Used

| Product | Purpose | Module |
|---------|---------|--------|
| **Circle Gateway** | Gasless batched payments | `GatewayClient` |
| **Programmable Wallets** | Agent wallet identity/signing | `AgentWalletManager` |
| **USDC** | Payment token (EIP-3009) | All payment flows |
| **x402 Protocol** | HTTP payment negotiation | `x402.py` |

## Installation

```bash
pip install -e .

# With Flask support
pip install -e ".[flask]"

# With all dependencies
pip install -e ".[all]"
```

## Getting Testnet USDC

Before using the SDK, you need testnet USDC on Arc Testnet (or another supported chain).

### Option 1: Public Faucet (Recommended)

No login required. Works with any wallet address.

1. Go to **[faucet.circle.com](https://faucet.circle.com)**
2. Select **Arc Testnet**
3. Paste your wallet address (`0x...`)
4. Get **10 USDC** (once per 24 hours)

### Option 2: Developer Console Faucet

Requires Circle account. Gives more tokens and native gas.

1. Go to **[console.circle.com/faucet](https://console.circle.com/faucet)**
2. Log in with your Circle developer account
3. Use your **Wallet ID** (for Circle Programmable Wallets) or fund via API
4. Get **20 USDC** + native tokens (10 requests per 24 hours)

### Option 3: API Faucet

Fund wallets programmatically:

```bash
curl -X POST https://api.circle.com/v1/faucet/drips \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"address": "0xYourAddress", "blockchain": "ARC-TESTNET", "usdc": true}'
```

> **Note:** On Arc Testnet, USDC is the native gas token—you only need USDC!

## Quick Start

### As a Buyer (Pay for API Access)

```python
import asyncio
from circlekit import GatewayClient

async def main():
    client = GatewayClient(
        chain="arcTestnet",
        private_key="0x..."
    )
    
    # Pay for a resource (gasless!)
    result = await client.pay("https://api.example.com/premium")
    
    print(f"Got: {result.data}")
    print(f"Paid: {result.formatted_amount} USDC")
    
    await client.close()

asyncio.run(main())
```

### As a Seller (Create Paywalled APIs)

```python
from flask import Flask, jsonify
from circlekit import create_gateway_middleware

app = Flask(__name__)

gateway = create_gateway_middleware(
    seller_address="0xYourAddress",
    chain="arcTestnet"
)

@app.route("/premium")
@gateway.require("0.01")  # $0.01 USDC
def premium_endpoint():
    return jsonify({"data": "Premium content"})

if __name__ == "__main__":
    app.run(port=8000)
```

### Agent Wallets (Circle Programmable Wallets)

Create agent wallets without managing raw private keys - Circle handles key security:

```python
from circlekit import AgentWalletManager

# Initialize with Circle API credentials
manager = AgentWalletManager(
    api_key="your-api-key",        # From https://console.circle.com
    entity_secret="your-secret"     # Generated in Circle dashboard
)

# Create a wallet for an agent
wallet = manager.create_wallet(
    name="trading-agent-001",
    blockchain="arcTestnet"
)

print(f"Agent address: {wallet.address}")
print(f"Wallet ID: {wallet.wallet_id}")

# List all agent wallets
wallets = manager.list_wallets()

# Sign messages (for verification or custom protocols)
signature = manager.sign_message(wallet.wallet_id, "Hello World")

# Sign EIP-712 typed data (for x402 payments or permits)
typed_data_sig = manager.sign_typed_data(wallet.wallet_id, {
    "domain": {...},
    "types": {...},
    "primaryType": "TransferWithAuthorization",
    "message": {...}
})
```

**Why use Programmable Wallets?**
- No private key management - Circle handles security
- Perfect for AI agents that need persistent identities
- Integrates with the rest of circlekit-py
- Supports multiple blockchains

---

## Using with Vyper Contracts

circle-titanoboa-sdk uses titanoboa internally, which means you can combine x402 payments with Vyper contract interactions seamlessly.

### Demo 1: Paid Contract Query

A Vyper contract that stores data, with a Python API that charges for reads:

```vyper
# storage.vy
stored_value: public(uint256)

@external
def set_value(val: uint256):
    self.stored_value = val
```

```python
# paid_storage_api.py
import boa
from flask import Flask, jsonify
from circlekit import create_gateway_middleware

app = Flask(__name__)
gateway = create_gateway_middleware(
    seller_address="0xYourAddress",
    chain="arcTestnet"
)

# Deploy or load Vyper contract using titanoboa
boa.set_network_env("https://arc-testnet.drpc.org")
storage = boa.load("storage.vy")

@app.route("/read")
@gateway.require("0.001")  # Pay $0.001 to read
def read_value(payment):
    value = storage.stored_value()
    return jsonify({
        "value": value,
        "paid_by": payment.payer
    })

@app.route("/write/<int:val>", methods=["POST"])
@gateway.require("0.01")  # Pay $0.01 to write
def write_value(val, payment):
    storage.set_value(val)
    return jsonify({
        "success": True,
        "new_value": val,
        "paid_by": payment.payer
    })
```

### Demo 2: Agent Reputation with Payments

Combine on-chain reputation (Vyper) with paid agent services:

```vyper
# agent_reputation.vy
struct Feedback:
    score: uint8
    timestamp: uint256

agent_scores: public(HashMap[address, DynArray[Feedback, 100]])

@external
def submit_feedback(agent: address, score: uint8):
    assert score <= 100, "Score must be 0-100"
    self.agent_scores[agent].append(Feedback({
        score: score,
        timestamp: block.timestamp
    }))

@view
@external
def get_average(agent: address) -> uint256:
    feedbacks: DynArray[Feedback, 100] = self.agent_scores[agent]
    if len(feedbacks) == 0:
        return 0
    total: uint256 = 0
    for fb: Feedback in feedbacks:
        total += convert(fb.score, uint256)
    return total / len(feedbacks)
```

```python
# agent_with_reputation.py
import boa
from circlekit import GatewayClient
from circlekit.boa_utils import setup_boa_with_account

async def pay_and_rate_agent():
    # Set up client for payments
    client = GatewayClient(
        chain="arcTestnet",
        private_key="0x..."
    )
    
    # Load reputation contract via titanoboa
    setup_boa_with_account("arcTestnet", "0x...")
    reputation = boa.load("agent_reputation.vy")
    
    # 1. Check agent reputation before paying
    agent_addr = "0xAgentAddress..."
    avg_score = reputation.get_average(agent_addr)
    print(f"Agent reputation: {avg_score}/100")
    
    # 2. Pay for agent service (gasless via Gateway)
    result = await client.pay("http://agent.example.com/api/analyze")
    print(f"Paid {result.formatted_amount} for: {result.data}")
    
    # 3. Submit feedback on-chain (uses titanoboa)
    reputation.submit_feedback(agent_addr, 85)
    print("Submitted feedback: 85/100")
    
    await client.close()
```

---

## API Reference

### GatewayClient

```python
from circlekit import GatewayClient

client = GatewayClient(
    chain="arcTestnet",      # Chain name
    private_key="0x...",     # Private key for signing
    rpc_url=None             # Optional custom RPC
)

# Properties
client.address      # Your wallet address
client.chain_name   # "Arc Testnet"
client.chain_id     # 5042002
client.domain       # 26 (Gateway domain)

# Methods
result = await client.pay(url)                    # Pay for resource (gasless)
balances = await client.get_balances()            # Check balances
support = await client.supports(url)              # Check if URL accepts payments
await client.deposit("10.0")                      # Deposit USDC to Gateway
await client.withdraw("5.0", chain="baseSepolia") # Withdraw to another chain
```

### create_gateway_middleware

```python
from circlekit import create_gateway_middleware

gateway = create_gateway_middleware(
    seller_address="0x...",      # Where to receive payments
    chain="arcTestnet",          # Chain for pricing
    description="My API"         # Description in 402 response
)

# Flask decorator
@gateway.require("0.01")
def endpoint():
    pass

# FastAPI dependency
async def endpoint(payment=Depends(gateway.require_fastapi("0.01"))):
    pass
```

### Low-Level x402 Functions

```python
from circlekit.x402 import (
    parse_402_response,
    create_payment_header,
    is_batch_payment,
    get_verifying_contract,
)

# Parse 402 response
x402 = parse_402_response(response.content)
requirements = x402.get_gateway_option()

# Check if requirements use Gateway batching
if is_batch_payment(requirements):
    contract = get_verifying_contract(requirements)
    print(f"Gateway contract: {contract}")

# Create payment signature
header = create_payment_header(
    private_key="0x...",
    payer_address="0x...",
    requirements=requirements
)

# Retry with payment
response = httpx.get(url, headers={"Payment-Signature": header})
```

### titanoboa Utilities

```python
from circlekit.boa_utils import (
    setup_boa_env,
    setup_boa_with_account,
    load_usdc_contract,
    load_gateway_contract,
    get_usdc_balance,
    get_gateway_balance,
    execute_approve,
    execute_deposit,
)

# Read-only setup
setup_boa_env("arcTestnet")
usdc = load_usdc_contract("arcTestnet")
balance = usdc.balanceOf("0x...")

# Transaction setup (adds signing account)
address, env = setup_boa_with_account("arcTestnet", "0xPrivateKey...")
# Now you can deploy/call Vyper contracts with real transactions
```

## Supported Networks

| Network | Chain ID | Gateway Domain | Type |
|---------|----------|----------------|------|
| Arc Testnet | 5042002 | 26 | Testnet |
| Base Sepolia | 84532 | 84532 | Testnet |
| Ethereum Sepolia | 11155111 | 11155111 | Testnet |
| Avalanche Fuji | 43113 | 43113 | Testnet |
| Base | 8453 | 8453 | Mainnet |
| Ethereum | 1 | 1 | Mainnet |

**Note:** Arc Testnet uses USDC as the native gas token.

## Testing

```bash
# Unit tests (fast, no network)
python3 -m pytest tests/test_circlekit.py tests/test_battle.py -v

# Integration tests (spins up Flask server)
python3 -m pytest tests/test_circlekit_integration.py -v

# Live verification (requires network, catches hallucinations)
python3 -m pytest tests/test_live_verification.py -v -s
```

## Architecture

```
circlekit/
├── __init__.py      # Package exports
├── constants.py     # Chain configs (verified against live RPCs)
├── boa_utils.py     # titanoboa helpers, EIP-712 signing, transactions
├── x402.py          # x402 protocol (parse 402, create signatures)
├── client.py        # GatewayClient (pay, deposit, withdraw, balances)
└── server.py        # Flask/FastAPI middleware
```

## How x402 Works

```
1. Client: GET /premium
2. Server: 402 Payment Required
   {
     "x402Version": 2,
     "accepts": [{
       "scheme": "exact",
       "network": "eip155:5042002",
       "amount": "10000",
       "payTo": "0xSeller..."
     }]
   }
3. Client: Signs EIP-712 TransferWithAuthorization (free, no gas)
4. Client: GET /premium + Payment-Signature header
5. Server: Verifies signature, serves content
6. Gateway: Batches signatures, settles on-chain later
```

## TypeScript SDK Parity

This SDK ports the following from `@circlefin/x402-batching`:

| TypeScript | Python | Status |
|------------|--------|--------|
| `GatewayClient` | `GatewayClient` | Complete |
| `createGatewayMiddleware` | `create_gateway_middleware` | Complete |
| `BatchEvmScheme` | `x402.create_payment_payload` | Complete |
| `BatchFacilitatorClient` | `server.GatewayMiddleware` | Complete |
| `supportsBatching` | `is_batch_payment` | Complete |
| `getVerifyingContract` | `get_verifying_contract` | Complete |
| `CHAIN_CONFIGS` | `CHAIN_CONFIGS` | Complete |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest -v

# Format code
black circlekit tests
isort circlekit tests
```

## License

TBD
