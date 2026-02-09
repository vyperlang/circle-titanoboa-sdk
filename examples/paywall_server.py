#!/usr/bin/env python3
"""
Paywall Server Example - Python equivalent of examples/agent-marketplace/server.ts

This demonstrates how to create an API with x402 paywalls using circlekit.

Usage:
    export SELLER_ADDRESS=0x...
    python paywall_server.py

Endpoints:
    GET  /              - Agent info (free)
    GET  /health        - Health check (free)
    GET  /api/analyze   - Data analysis ($0.01)
    POST /api/generate  - Content generation ($0.05)
"""

import os
import sys
from datetime import datetime
from flask import Flask, request, jsonify

# Add parent directory to path for circlekit import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from circlekit import create_gateway_middleware


# ============================================================================
# CONFIGURATION
# ============================================================================

PORT = int(os.environ.get("PORT", 4022))
SELLER_ADDRESS = os.environ.get("SELLER_ADDRESS")

if not SELLER_ADDRESS:
    print("Error: SELLER_ADDRESS environment variable is required")
    print("Usage: SELLER_ADDRESS=0x... python paywall_server.py")
    sys.exit(1)


# ============================================================================
# AGENT METADATA (ERC-8004 style)
# ============================================================================

AGENT_METADATA = {
    "agentId": 1,
    "name": "PythonAnalyzer-v1",
    "description": "Python AI agent specializing in data analysis (circlekit demo)",
    "owner": SELLER_ADDRESS,
    "tokenURI": "ipfs://QmPythonAgentMetadata...",
    "registeredAt": datetime.now().isoformat(),
    "capabilities": ["data-analysis", "content-generation", "python-execution"],
    "serviceEndpoints": {
        "info": "/",
        "analyze": "/api/analyze",
        "generate": "/api/generate",
    },
    "pricing": {
        "analyze": "$0.01",
        "generate": "$0.05",
    },
    "x402Support": True,
    "gatewayNetworks": ["eip155:5042002"],  # Arc Testnet
}


# ============================================================================
# FLASK APP
# ============================================================================

app = Flask(__name__)

# Create Gateway middleware
gateway = create_gateway_middleware(
    seller_address=SELLER_ADDRESS,
    chain="arcTestnet",
    description="Python Agent API",
)


# ============================================================================
# FREE ENDPOINTS
# ============================================================================

@app.route("/")
def agent_info():
    """Agent Discovery (free) - Returns ERC-8004 style metadata."""
    return jsonify({
        "success": True,
        "agent": AGENT_METADATA,
        "message": "Use x402 payments to access /api/analyze and /api/generate",
        "sdk": "circlekit-py",
    })


@app.route("/health")
def health_check():
    """Health check (free)."""
    return jsonify({
        "status": "ok",
        "agent": AGENT_METADATA["name"],
        "seller": SELLER_ADDRESS,
        "sdk": "circlekit-py",
    })


# ============================================================================
# PAID ENDPOINTS (x402 paywall)
# ============================================================================

@app.route("/api/analyze")
@gateway.require("$0.01")
def analyze(payment):
    """
    Data Analysis ($0.01)
    
    Protected by gateway.require('$0.01')
    - Without payment: Returns 402 Payment Required
    - With payment: Verifies, settles, and returns analysis
    """
    print(f"[PAYMENT] Analyze request paid by {payment.payer}")
    print(f"          Amount: {payment.amount}")
    print(f"          Network: {payment.network}")
    
    return jsonify({
        "success": True,
        "service": "analyze",
        "result": {
            "summary": "Python analysis complete. Key findings indicate positive trends.",
            "confidence": 0.92,
            "dataPoints": 128,
            "insights": [
                "Trend A shows 18% growth (Python model)",
                "Pattern B correlates with external factor C",
                "Anomaly detected in sector D using numpy",
            ],
        },
        "payment": {
            "amount": payment.amount,
            "payer": payment.payer,
            "network": payment.network,
            "transaction": payment.transaction,
        },
        "reputationHint": {
            "message": "Submit feedback with this transaction hash as proofOfPayment",
            "proofOfPayment": payment.transaction,
        },
    })


@app.route("/api/generate", methods=["POST"])
@gateway.require("$0.05")
def generate(payment):
    """
    Content Generation ($0.05)
    
    Accepts a prompt in the request body and generates content.
    """
    data = request.get_json() or {}
    prompt = data.get("prompt", "default prompt")
    style = data.get("style", "professional")
    
    print(f"[PAYMENT] Generate request paid by {payment.payer}")
    print(f"          Prompt: \"{prompt[:50]}...\"")
    print(f"          Amount: {payment.amount}")
    
    return jsonify({
        "success": True,
        "service": "generate",
        "input": {"prompt": prompt, "style": style},
        "result": {
            "content": f"Generated {style} content based on: \"{prompt}\" (Python/circlekit)",
            "wordCount": 175,
            "generatedAt": datetime.now().isoformat(),
            "model": "python-gpt-local",
        },
        "payment": {
            "amount": payment.amount,
            "payer": payment.payer,
            "network": payment.network,
            "transaction": payment.transaction,
        },
    })


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print(f"""
╔════════════════════════════════════════════════════════════════╗
║        Agent Marketplace - Python x402 Seller (circlekit)      ║
╚════════════════════════════════════════════════════════════════╝

Server:    http://localhost:{PORT}
Agent:     {AGENT_METADATA["name"]}
Seller:    {SELLER_ADDRESS}
SDK:       circlekit-py (Python)

Endpoints:
  GET  /              - Agent info (free)
  GET  /health        - Health check (free)
  GET  /api/analyze   - Data analysis ($0.01)
  POST /api/generate  - Content generation ($0.05)

Test free endpoints:
  curl http://localhost:{PORT}/
  curl http://localhost:{PORT}/health

Test paywalled endpoints (returns 402):
  curl http://localhost:{PORT}/api/analyze

To pay, run agent_client.py in another terminal:
  PRIVATE_KEY=0x... python agent_client.py

Get testnet USDC from: https://faucet.circle.com
""")
    
    app.run(host="0.0.0.0", port=PORT, debug=True)
