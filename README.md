# circlekit-py

Python SDK for Circle's x402 Protocol, Gateway API, and Wallet services. Uses **titanoboa** for all on-chain interactions (no web3.py).

## Features

- **x402 Payment Protocol** - HTTP 402 Payment Required flow implementation
- **Gateway Client** - Pay for x402-protected resources with USDC
- **Gateway Middleware** - Protect your API endpoints with paywalls (Flask/FastAPI)
- **Arc Testnet Support** - Full support for Circle's L2 (USDC as gas token)
- **Multi-chain** - Works with Arc, Base, Ethereum, Avalanche (testnets and mainnets)
- **Pure titanoboa** - No web3.py dependency, uses eth-account for signing

## Installation

```bash
pip install circlekit

# With Flask support
pip install circlekit[flask]

# With FastAPI support  
pip install circlekit[fastapi]

# With all optional dependencies
pip install circlekit[all]
```

## Quick Start

### As a Buyer (Pay for API Access)

```python
import asyncio
from circlekit import GatewayClient

async def main():
    # Initialize client
    client = GatewayClient(
        chain="arcTestnet",
        private_key="0x..."  # Your private key
    )
    
    # Check if an endpoint supports x402 payments
    supports = await client.supports("https://api.example.com/paid-endpoint")
    if supports["accepts"]:
        print(f"Accepts payments: min ${supports['minAmountRequired']}")
    
    # Pay for access
    result = await client.pay(
        url="https://api.example.com/paid-endpoint",
        method="GET"
    )
    
    if result["success"]:
        print(f"Response: {result['response']}")
        print(f"Paid: ${result['amountPaid']}")
    
    # Check balances
    balances = await client.get_balances()
    print(f"Gateway balance: {balances['gateway']}")
    print(f"Wallet balance: {balances['wallet']}")

asyncio.run(main())
```

### As a Seller (Create Paywalled APIs)

#### Flask

```python
from flask import Flask, jsonify
from circlekit import create_gateway_middleware

app = Flask(__name__)

# Create middleware
gateway = create_gateway_middleware(
    seller_address="0x...",  # Your address to receive payments
    chain="arcTestnet",
    description="My Premium API"
)

@app.route("/free")
def free_endpoint():
    return jsonify({"message": "This is free!"})

@app.route("/premium")
@gateway.require("0.01")  # Requires $0.01 USDC
def premium_endpoint():
    return jsonify({"data": "Premium content worth paying for"})

if __name__ == "__main__":
    app.run(port=8000)
```

#### FastAPI

```python
from fastapi import FastAPI, Depends
from circlekit import create_gateway_middleware

app = FastAPI()

gateway = create_gateway_middleware(
    seller_address="0x...",
    chain="arcTestnet"
)

@app.get("/premium")
async def premium(payment: dict = Depends(gateway.require_fastapi("0.05"))):
    return {"data": "Premium content", "payment": payment}
```

## API Reference

### GatewayClient

Client for paying for x402-protected resources.

```python
client = GatewayClient(
    chain="arcTestnet",      # Chain name
    private_key="0x...",     # Private key for signing
    rpc_url=None             # Optional custom RPC URL
)

# Properties
client.address      # Your wallet address
client.chain_name   # Chain name
client.chain_id     # Chain ID  
client.domain       # Gateway domain

# Methods
await client.pay(url, method="GET", headers=None, body=None)
await client.get_balances(address=None)
await client.supports(url)
await client.deposit(amount, approve_amount=None)  # Coming soon
await client.withdraw(amount, chain=None, recipient=None)  # Coming soon
```

### create_gateway_middleware

Factory function for creating payment middleware.

```python
middleware = create_gateway_middleware(
    seller_address="0x...",      # Required: address to receive payments
    networks=None,               # Optional: list of accepted networks
    description="Paid resource", # Optional: description for 402 response
    chain="arcTestnet"           # Optional: default chain
)

# Flask decorator
@middleware.require("0.01")  # Price in USDC
def my_endpoint():
    pass

# FastAPI dependency  
async def my_endpoint(payment = Depends(middleware.require_fastapi("0.01"))):
    pass
```

### x402 Utilities

Low-level x402 protocol functions.

```python
from circlekit.x402 import (
    parse_402_response,
    create_payment_payload,
    create_payment_header,
)

# Parse a 402 response
x402_response = parse_402_response(response_body)
requirements = x402_response.accepts[0]

# Create payment signature
header = create_payment_header(
    private_key="0x...",
    payer_address="0x...",
    requirements=requirements
)

# Make request with payment
response = httpx.get(url, headers={"Payment-Signature": header})
```

### Chain Configuration

```python
from circlekit.constants import CHAIN_CONFIGS, get_chain_config

# Available chains
print(CHAIN_CONFIGS.keys())
# ['arcTestnet', 'baseSepolia', 'ethereumSepolia', 'avalancheFuji', 
#  'base', 'ethereum', 'avalanche']

# Get config for a chain
config = get_chain_config("arcTestnet")
print(config.chain_id)      # 5042002
print(config.usdc_address)  # 0x3600000000000000000000000000000000000000
print(config.rpc_url)       # https://rpc.testnet.arc.circle.com
```

### Titanoboa Utilities

Direct blockchain interaction utilities.

```python
from circlekit.boa_utils import (
    setup_boa_for_chain,
    load_usdc_contract,
    load_gateway_contract,
    sign_typed_data,
)

# Setup titanoboa for a chain
setup_boa_for_chain("arcTestnet")

# Load USDC contract
usdc = load_usdc_contract("arcTestnet")
balance = usdc.balanceOf(address)

# Sign EIP-712 typed data
signature = sign_typed_data(
    private_key="0x...",
    domain_data={...},
    message_types={...},
    message_data={...},
    primary_type="TransferWithAuthorization"
)
```

## Supported Networks

| Network | Chain ID | Type |
|---------|----------|------|
| Arc Testnet | 5042002 | Testnet |
| Base Sepolia | 84532 | Testnet |
| Ethereum Sepolia | 11155111 | Testnet |
| Avalanche Fuji | 43113 | Testnet |
| Base | 8453 | Mainnet |
| Ethereum | 1 | Mainnet |
| Avalanche | 43114 | Mainnet |

## Development

```bash
# Clone repository
git clone https://github.com/example/circlekit-py
cd circlekit-py

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black circlekit tests
isort circlekit tests
```

## Architecture

```
circlekit/
├── __init__.py      # Package exports
├── constants.py     # Chain configs, protocol constants
├── boa_utils.py     # Titanoboa helpers, EIP-712 signing
├── x402.py          # x402 protocol implementation
├── client.py        # GatewayClient for buyers
└── server.py        # Middleware for sellers
```

## License

MIT
