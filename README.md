# circle-titanoboa-sdk

Python SDK for x402 with Circle Gateway batching and API access. Uses **titanoboa** for on-chain interactions.

> Built for the [Vyper](https://github.com/vyperlang/vyper) ecosystem. Port of Circle's TypeScript SDK (`@circlefin/x402-batching`).

## What It Does

**circle-titanoboa-sdk** enables gasless micropayments for Python applications:

1. **Buyers** can pay for API access without gas fees (signatures only)
2. **Sellers** can monetize APIs with framework-agnostic middleware
3. **Settlement** happens in batches via Circle Gateway

```
User Request -> 402 Payment Required -> Sign Message (free) -> Access Granted
                                             |
                              Circle Gateway batches payments on-chain
```

## Features

- **x402 Payment Protocol** - HTTP 402 Payment Required flow
- **Gateway Client** - Pay for x402-protected resources with USDC
- **Gateway Middleware** - Framework-agnostic middleware for paywalled endpoints
- **Multi-chain** - Arc, Base, Ethereum, Avalanche, Polygon, Optimism, and more (testnets + mainnets)
- **Arc Testnet** - Circle's L2 where USDC is the native gas token
- **Titanoboa-based** - On-chain interactions via titanoboa

## Circle Products Used

| Product | Purpose | Module |
|---------|---------|--------|
| **Circle Gateway** | Gasless batched payments | `GatewayClient` |
| **USDC** | Payment token (EIP-3009) | All payment flows |
| **x402 Protocol** | HTTP payment negotiation | `x402.py` |

## Installation

```bash
pip install -e .

# With dev dependencies (testing, linting)
pip install -e ".[dev]"
```

## Getting Testnet USDC

Before using the SDK, you need testnet USDC on Arc Testnet (or another supported chain).

### Which Faucet Should I Use?

| Wallet Type | Faucet | What You Get |
|------------|--------|--------------|
| **External wallet** (MetaMask, private key) | [Public Faucet](https://faucet.circle.com) | 20 USDC every 2 hours |

### Public Faucet (Any Wallet)

Use for wallets you control directly (MetaMask, private key, hardware wallet):

1. Go to **[faucet.circle.com](https://faucet.circle.com)**
2. Select **Arc Testnet**
3. Paste your wallet **address** (`0x...`)
4. Get **20 USDC** (every 2 hours per address per network)

No login required. Works with any wallet address.

> **Note:** On Arc Testnet, USDC is the native gas token. You only need USDC for both payments and gas.

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

The middleware is framework-agnostic. Use `process_request()` to handle payment logic,
then adapt it to any framework:

```python
import asyncio
from flask import Flask, request, jsonify
from circlekit import create_gateway_middleware
from circlekit.x402 import PaymentInfo

app = Flask(__name__)

gateway = create_gateway_middleware(
    seller_address="0xYourAddress",
    chain="arcTestnet",
    description="My API",
)

def require_payment(price):
    """Flask adapter: wraps gateway.process_request into a decorator."""
    def decorator(func):
        from functools import wraps
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = asyncio.run(gateway.process_request(
                payment_header=request.headers.get("Payment-Signature"),
                path=request.path,
                price=price,
            ))
            if isinstance(result, dict):
                return jsonify(result["body"]), result["status"]
            kwargs["payment"] = result
            return func(*args, **kwargs)
        return wrapper
    return decorator

@app.route("/api/analyze")
@require_payment("$0.01")
def analyze(payment):
    return jsonify({"data": "Premium content", "paid_by": payment.payer})

if __name__ == "__main__":
    app.run(port=4022)
```

### Multi-chain Support

Accept payments on multiple chains by passing the `networks` option:

```python
gateway = create_gateway_middleware(
    seller_address="0xYourAddress",
    chain="arcTestnet",
    networks=["arcTestnet", "baseSepolia"],  # Accept both chains
)
```

The 402 response will include one `accepts` entry per network, and incoming
payments will be validated against the accepted set.

### Using with Standard x402

If you already use the [`x402` Python package](https://github.com/coinbase/x402/tree/main/python), add Circle Gateway as a facilitator:

```bash
pip install circlekit[x402]
```

```python
from circlekit.x402_integration import create_resource_server

server = create_resource_server(is_testnet=True)
server.initialize()

# Use with FastAPI, Flask, or any x402 middleware
```

Or use `BatchFacilitatorClient` directly with `x402ResourceServer`:

```python
from x402.server import x402ResourceServer
from circlekit import BatchFacilitatorClient

server = x402ResourceServer(BatchFacilitatorClient())
server.initialize()
```

---

## Using with Vyper Contracts

circle-titanoboa-sdk uses titanoboa internally, which means you can combine x402 payments with Vyper contract interactions seamlessly.

### Paid Contract Query

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
import asyncio
import boa
from flask import Flask, request, jsonify
from circlekit import create_gateway_middleware
from circlekit.x402 import PaymentInfo

app = Flask(__name__)
gateway = create_gateway_middleware(
    seller_address="0xYourAddress",
    chain="arcTestnet",
)

# Deploy or load Vyper contract using titanoboa
boa.set_network_env("https://arc-testnet.drpc.org")
storage = boa.load("storage.vy")

def require_payment(price):
    def decorator(func):
        from functools import wraps
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = asyncio.run(gateway.process_request(
                payment_header=request.headers.get("Payment-Signature"),
                path=request.path,
                price=price,
            ))
            if isinstance(result, dict):
                return jsonify(result["body"]), result["status"]
            kwargs["payment"] = result
            return func(*args, **kwargs)
        return wrapper
    return decorator

@app.route("/read")
@require_payment("$0.001")
def read_value(payment):
    value = storage.stored_value()
    return jsonify({"value": value, "paid_by": payment.payer})
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

# Or with a custom Signer:
from circlekit import PrivateKeySigner
signer = PrivateKeySigner("0x...")
client = GatewayClient(chain="arcTestnet", signer=signer)

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
    chain="arcTestnet",          # Primary chain
    networks=["arcTestnet", "baseSepolia"],  # Accepted networks (optional)
    description="My API",       # Description in 402 response
)

# Framework-agnostic — use process_request() in any handler:
result = await gateway.process_request(
    payment_header=request.headers.get("Payment-Signature"),
    path=request.path,
    price="$0.01",
)

if isinstance(result, dict):
    # 402 response needed
    return jsonify(result["body"]), result["status"]
else:
    # PaymentInfo — request is paid
    print(result.payer, result.amount, result.transaction)
```

### Low-Level x402 Functions

```python
from circlekit.x402 import (
    parse_402_response,
    create_payment_header,
    is_batch_payment,
    get_verifying_contract,
)
from circlekit import PrivateKeySigner

# Parse 402 response
x402 = parse_402_response(response.content)
requirements = x402.get_gateway_option()

# Check if requirements use Gateway batching
if is_batch_payment(requirements):
    contract = get_verifying_contract(requirements)
    print(f"Gateway contract: {contract}")

# Create payment signature
signer = PrivateKeySigner("0x...")
header = create_payment_header(signer=signer, requirements=requirements)

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
| Base Sepolia | 84532 | 6 | Testnet |
| Ethereum Sepolia | 11155111 | 0 | Testnet |
| Avalanche Fuji | 43113 | 1 | Testnet |
| HyperEVM Testnet | 998 | 19 | Testnet |
| Sonic Testnet | 64165 | 13 | Testnet |
| World Chain Sepolia | 4801 | 14 | Testnet |
| Sei Atlantic | 1328 | 16 | Testnet |
| Ethereum | 1 | 0 | Mainnet |
| Base | 8453 | 6 | Mainnet |
| Arbitrum | 42161 | 3 | Mainnet |
| Polygon | 137 | 7 | Mainnet |
| Optimism | 10 | 2 | Mainnet |
| Avalanche | 43114 | 1 | Mainnet |
| Sonic | 146 | 13 | Mainnet |
| Unichain | 130 | 10 | Mainnet |
| World Chain | 480 | 14 | Mainnet |
| HyperEVM | 999 | 19 | Mainnet |
| Sei | 1329 | 16 | Mainnet |

**Note:** Arc Testnet uses USDC as the native gas token. Gateway Domain IDs are Circle's internal domain identifiers, not chain IDs.

## Testing

```bash
# Set up dev environment
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Unit tests (fast, no network)
.venv/bin/pytest tests/test_circlekit.py tests/test_battle.py -v

# Integration tests (mocked facilitator)
.venv/bin/pytest tests/test_circlekit_integration.py -v

# Parity tests (SDK matches TS behavior)
.venv/bin/pytest tests/test_parity.py -v

# Live verification (requires network, catches hallucinations)
.venv/bin/pytest tests/test_live_verification.py -v -s

# All tests
.venv/bin/pytest tests/ -v
```

## Architecture

```
circlekit/
├── __init__.py       # Package exports
├── constants.py      # Chain configs, gateway addresses, protocol constants
├── signer.py         # Signer protocol + PrivateKeySigner (EIP-712)
├── facilitator.py    # BatchFacilitatorClient (Gateway API verify/settle)
├── boa_utils.py      # titanoboa helpers, contract ABIs, transactions
├── x402.py           # x402 protocol (parse 402, create signatures, headers)
├── client.py         # GatewayClient (pay, deposit, withdraw, balances)
└── server.py         # Framework-agnostic payment middleware
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
| `BatchFacilitatorClient` | `facilitator.BatchFacilitatorClient` | Complete |
| `supportsBatching` | `is_batch_payment` | Complete |
| `getVerifyingContract` | `get_verifying_contract` | Complete |
| `CHAIN_CONFIGS` | `CHAIN_CONFIGS` | Complete |

## Development

```bash
# Set up with uv
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Run tests
.venv/bin/pytest -v

# Format code
black circlekit tests
isort circlekit tests
```

## License

TBD
