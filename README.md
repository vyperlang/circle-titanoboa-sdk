<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="titanoboa-logo-dark.png">
    <img src="titanoboa-logo.png" width="200" alt="Titanoboa logo">
  </picture>
</p>

# circle-titanoboa-sdk

Python SDK for [x402](https://github.com/coinbase/x402) with Circle Gateway batching. Uses **titanoboa** for on-chain interactions.

> Built for the [Vyper](https://github.com/vyperlang/vyper) ecosystem.

> **Note:** The pip package is `circle-titanoboa-sdk` but the Python import is `circlekit`:
> ```python
> from circlekit import GatewayClient
> ```

## Installation

```bash
# As a dependency
pip install .

# With x402 integration
pip install ".[x402]"

# For development
uv sync
```

## Getting Testnet USDC

You need testnet USDC on Arc Testnet (or another supported chain).

1. Go to **[faucet.circle.com](https://faucet.circle.com)**
2. Select **Arc Testnet**
3. Paste your wallet address
4. Get **20 USDC** (every 2 hours per address per network)

> On Arc Testnet, USDC is the native gas token. You only need USDC for both payments and gas.

## Quick Start

### Pay for a Resource (Buyer)

```python
import asyncio
from circlekit import GatewayClient

async def main():
    client = GatewayClient(
        chain="arcTestnet",
        private_key="0x..."
    )

    result = await client.pay("https://api.example.com/premium")
    print(f"Got: {result.data}")
    print(f"Paid: {result.formatted_amount} USDC")

    await client.close()

asyncio.run(main())
```

### Protect an Endpoint (Seller)

The middleware is framework-agnostic. Here's an example with FastAPI.
To run the examples: `pip install circlekit[examples]`

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from circlekit import create_gateway_middleware

app = FastAPI()

gateway = create_gateway_middleware(
    seller_address="0xYourAddress",
    chain="arcTestnet",
)

@app.get("/api/analyze")
async def analyze(request: Request):
    result = await gateway.process_request(
        payment_header=request.headers.get("PAYMENT-SIGNATURE"),
        path=request.url.path,
        price="$0.01",
    )

    if isinstance(result, dict):
        # 402: return body + PAYMENT-REQUIRED header
        resp = JSONResponse(result["body"], status_code=result["status"])
        for k, v in result.get("headers", {}).items():
            resp.headers[k] = v
        return resp

    # Success: return data + PAYMENT-RESPONSE header
    resp = JSONResponse({"data": "Premium content", "paid_by": result.payer})
    for k, v in result.response_headers.items():
        resp.headers[k] = v
    return resp
```

### Multi-chain Support

```python
gateway = create_gateway_middleware(
    seller_address="0xYourAddress",
    chain="arcTestnet",
    networks=["arcTestnet", "baseSepolia"],
)
```

The 402 response will include one `accepts` entry per network, and incoming
payments will be validated against the accepted set.

### Using with Standard x402

If you already use the [`x402` Python package](https://github.com/coinbase/x402/tree/main/python), add Circle Gateway as a facilitator:

```bash
pip install ".[x402]"
```

The x402 package API may change independently of circlekit. See https://github.com/x402/x402 for the latest usage.

```python
from circlekit.x402_integration import create_resource_server

server = create_resource_server(is_testnet=True)
server.initialize()

# Use with FastAPI, Flask, or any framework
```

Or use `BatchFacilitatorClient` directly with `x402ResourceServer`:

```python
from x402.server import x402ResourceServer
from circlekit import BatchFacilitatorClient

server = x402ResourceServer(BatchFacilitatorClient())
server.initialize()
```

## Using with Vyper Contracts

circle-titanoboa-sdk uses titanoboa internally, so you can combine x402 payments with Vyper contract interactions seamlessly.

```vyper
# storage.vy
stored_value: public(uint256)

@external
def set_value(val: uint256):
    self.stored_value = val
```

```python
import boa
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from circlekit import create_gateway_middleware

app = FastAPI()
gateway = create_gateway_middleware(
    seller_address="0xYourAddress",
    chain="arcTestnet",
)

boa.set_network_env("https://arc-testnet.drpc.org")
storage = boa.load("storage.vy")

@app.get("/read")
async def read_value(request: Request):
    result = await gateway.process_request(
        payment_header=request.headers.get("PAYMENT-SIGNATURE"),
        path=request.url.path,
        price="$0.001",
    )

    if isinstance(result, dict):
        resp = JSONResponse(result["body"], status_code=result["status"])
        for k, v in result.get("headers", {}).items():
            resp.headers[k] = v
        return resp

    value = storage.stored_value()
    resp = JSONResponse({"value": value, "paid_by": result.payer})
    for k, v in result.response_headers.items():
        resp.headers[k] = v
    return resp
```

## API Reference

### GatewayClient

`GatewayClient` separates two wallet capabilities:

| Capability | Protocol | Used by |
|------------|----------|---------|
| **EIP-712 signing** | `Signer` | `pay()`, `withdraw()` intent |
| **Onchain tx execution** | `TxExecutor` | `deposit()`, `withdraw()` mint |

```python
from circlekit import GatewayClient

# Simple: private_key creates both a Signer and TxExecutor:
client = GatewayClient(
    chain="arcTestnet",
    private_key="0x...",
    rpc_url=None             # Optional custom RPC
)

# Pay-only (signer is enough for gasless payments):
from circlekit import PrivateKeySigner
signer = PrivateKeySigner("0x...")
client = GatewayClient(chain="arcTestnet", signer=signer)
# client.pay() works; client.deposit()/withdraw() raise ValueError

# Advanced: inject capabilities separately:
from circlekit import BoaTxExecutor
client = GatewayClient(
    chain="arcTestnet",
    signer=my_signer,
    tx_executor=BoaTxExecutor("0x..."),
)

# Properties
client.address      # Your wallet address
client.chain_name   # "Arc Testnet"
client.chain_id     # 5042002
client.domain       # 26 (Gateway domain)

# Methods
result = await client.pay(url)                    # Pay for resource (gasless, needs Signer)
balances = await client.get_balances()            # Check balances (no capability needed)
support = await client.supports(url)              # Check if URL accepts payments
await client.deposit("10.0")                      # Deposit USDC to Gateway (needs TxExecutor)
await client.deposit_for("10.0", depositor="0x...")  # Deposit on behalf of another address
await client.withdraw("5.0", chain="baseSepolia") # Withdraw to another chain (needs both)
```

#### Trustless Withdrawal

An alternative to `withdraw()` that doesn't require the Gateway API. Uses on-chain delay instead:

```python
delay = await client.get_trustless_withdrawal_delay()     # Delay in blocks
await client.initiate_trustless_withdrawal("1.0")         # Start withdrawal
# ... wait for delay blocks ...
block = await client.get_trustless_withdrawal_block()     # Check eligible block
result = await client.complete_trustless_withdrawal()     # Complete after delay
```

#### TxExecutor

`TxExecutor` is a `Protocol` for executing onchain transactions. `BoaTxExecutor` is the default implementation using titanoboa with a private key.

```python
from circlekit import TxExecutor, BoaTxExecutor

# Default implementation:
executor = BoaTxExecutor("0xPrivateKey...")

# Custom implementations can wrap any execution backend (e.g., Circle
# Programmable Wallets). Just implement the TxExecutor protocol.
```

#### CircleWalletSigner / CircleTxExecutor

Use Circle Developer-Controlled Wallets (MPC-backed) instead of a raw private key. No private key ever leaves Circle's infrastructure.

```bash
pip install ".[wallets]"
```

```python
from circlekit import GatewayClient
from circlekit.wallets import CircleWalletSigner, CircleTxExecutor

signer = CircleWalletSigner(wallet_id="...", wallet_address="0x...")
tx_executor = CircleTxExecutor(wallet_id="...", wallet_address="0x...")

# CIRCLE_API_KEY and CIRCLE_ENTITY_SECRET are read from env vars automatically
client = GatewayClient(chain="arcTestnet", signer=signer, tx_executor=tx_executor)
```

### GatewayClientSync

Synchronous wrapper for scripts, CLIs, and Jupyter notebooks that cannot use `async`/`await`. Mirrors every `GatewayClient` method.

```python
from circlekit import GatewayClientSync

client = GatewayClientSync(chain="arcTestnet", private_key="0x...")
result = client.pay("https://api.example.com/premium")
balances = client.get_balances()
client.close()
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

# Framework-agnostic. Use process_request() in any handler:
result = await gateway.process_request(
    payment_header=request.headers.get("PAYMENT-SIGNATURE"),
    path=request.url.path,
    price="$0.01",
)

if isinstance(result, dict):
    # 402 response: set PAYMENT-REQUIRED header
    resp = JSONResponse(result["body"], status_code=result["status"])
    for k, v in result.get("headers", {}).items():
        resp.headers[k] = v
    return resp
else:
    # PaymentInfo: set PAYMENT-RESPONSE header
    resp = JSONResponse({"data": "..."})
    for k, v in result.response_headers.items():
        resp.headers[k] = v
    return resp
```

The returned `GatewayMiddleware` also exposes lower-level methods for custom flows:

```python
# Build a 402 response manually:
payment_required = gateway.require("$0.01", "/api/analyze")

# Verify a payment without settling:
verify_result = await gateway.verify(payment_header, "$0.01")

# Settle a verified payment:
payment_info = await gateway.settle(payment_header, "$0.01")
```

### BatchEvmScheme

Creates EIP-712 `TransferWithAuthorization` payment payloads for the Gateway batching protocol.

```python
from circlekit import BatchEvmScheme, PrivateKeySigner

signer = PrivateKeySigner("0x...")
scheme = BatchEvmScheme(signer)
payload = scheme.create_payment_payload(
    x402_version=2,
    requirements=requirements,
)
```

### Low-Level x402 Functions

```python
from circlekit.x402 import (
    parse_402_response,
    create_payment_header,
    decode_payment_header,
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

# Decode an existing payment header
payload = decode_payment_header(header)

# Retry with payment
response = httpx.get(url, headers={"PAYMENT-SIGNATURE": header})
```

### titanoboa Utilities

```python
from circlekit.boa_utils import (
    setup_boa_env,
    setup_boa_with_account,
    get_usdc_balance,
    get_gateway_balance,
    execute_approve,
    execute_deposit,
)
from circlekit.constants import get_chain_config

# Read-only setup
setup_boa_env("arcTestnet")
config = get_chain_config("arcTestnet")

import boa
usdc = boa.load_partial("path/to/IERC20.json").at(config.usdc_address)
balance = usdc.balanceOf("0x...")

# Transaction setup (adds signing account)
setup_boa_with_account("arcTestnet", "0xPrivateKey...")
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
| Sonic Testnet | 14601 | 13 | Testnet |
| World Chain Sepolia | 4801 | 14 | Testnet |
| Sei Atlantic Testnet | 1328 | 16 | Testnet |
| Arbitrum Sepolia | 421614 | 3 | Testnet |
| Optimism Sepolia | 11155420 | 2 | Testnet |
| Polygon Amoy | 80002 | 7 | Testnet |
| Unichain Sepolia | 1301 | 10 | Testnet |
| Ethereum | 1 | 0 | Mainnet |
| Base | 8453 | 6 | Mainnet |
| Arbitrum One | 42161 | 3 | Mainnet |
| Polygon | 137 | 7 | Mainnet |
| Optimism | 10 | 2 | Mainnet |
| Avalanche C-Chain | 43114 | 1 | Mainnet |
| Sonic | 146 | 13 | Mainnet |
| Unichain | 130 | 10 | Mainnet |
| World Chain | 480 | 14 | Mainnet |
| HyperEVM | 999 | 19 | Mainnet |
| Sei | 1329 | 16 | Mainnet |

USDC contract addresses sourced from https://developers.circle.com/stablecoins/usdc-contract-addresses

**Note:** Arc Testnet uses USDC as the native gas token. Gateway Domain IDs are Circle's internal domain identifiers, not chain IDs.

## Known Limitations

### titanoboa threading

titanoboa uses a global `boa.env` singleton with a SQLite-backed cache that is not thread-safe. `GatewayClient` mitigates this by routing all blocking boa calls through a single-thread `ThreadPoolExecutor`, but you should avoid creating multiple `GatewayClient` instances that call `deposit()`, `withdraw()`, or other on-chain methods concurrently in the same process. Gasless operations (`pay()`, `get_balances()`, `supports()`) use only HTTP and are safe to call concurrently.

If you need concurrent on-chain operations, run each in a separate process or use `GatewayClientSync` in separate threads with independent boa environments.

## Development

### Setup

```bash
uv sync                     # Install all deps including dev group
uv run pre-commit install   # Set up pre-commit hooks
```

### Running Tests

```bash
uv run pytest               # Unit tests (360 tests)

# E2E tests (requires testnet USDC):
PRIVATE_KEY=0x... uv run pytest tests/test_e2e.py -v -s
```

### Linting & Type Checking

Pre-commit runs automatically on `git commit`, or manually:

```bash
uv run ruff check --fix circlekit/ tests/   # Lint
uv run ruff format circlekit/ tests/         # Format
uv run mypy circlekit/                       # Type check
```

## Architecture

```
circlekit/
├── __init__.py            # Package exports
├── constants.py           # Chain configs, gateway addresses, protocol constants
├── signer.py              # Signer protocol + PrivateKeySigner (EIP-712)
├── tx_executor.py         # TxExecutor protocol + BoaTxExecutor (onchain txs)
├── facilitator.py         # BatchFacilitatorClient (Gateway API verify/settle)
├── boa_utils.py           # titanoboa helpers, contract ABIs, transactions
├── x402.py                # x402 protocol (parse 402, create signatures, headers)
├── x402_integration.py    # Optional x402 package integration
├── key_utils.py           # Private key normalization, PrivateKeyLike type
├── wallets.py             # Circle Developer-Controlled Wallets adapters
├── sync_client.py         # GatewayClientSync (synchronous wrapper)
├── client.py              # GatewayClient (pay, deposit, withdraw, balances)
└── server.py              # Framework-agnostic payment middleware
```

## License

MIT - see [LICENSE](./LICENSE)

---

*This is an unaudited reference implementation provided for educational and development purposes only. It is not production-ready software. Use at your own risk. The authors accept no liability for any losses or damages arising from its use or deployment.*
