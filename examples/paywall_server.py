#!/usr/bin/env python3
"""
Paywall Server Example - Flask adapter for circlekit's framework-agnostic middleware.

Usage:
    export SELLER_ADDRESS=0x...
    pip install flask
    python paywall_server.py

Endpoints:
    GET  /              - Agent info (free)
    GET  /health        - Health check (free)
    GET  /api/analyze   - Data analysis ($0.01)
    POST /api/generate  - Content generation ($0.05)
"""

import asyncio
import os
import sys
from datetime import datetime
from flask import Flask, request, jsonify

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from circlekit import create_gateway_middleware
from circlekit.x402 import PaymentInfo

PORT = int(os.environ.get("PORT", 4022))
SELLER_ADDRESS = os.environ.get("SELLER_ADDRESS")

if not SELLER_ADDRESS:
    print("Error: SELLER_ADDRESS environment variable is required")
    sys.exit(1)


app = Flask(__name__)

gateway = create_gateway_middleware(
    seller_address=SELLER_ADDRESS,
    chain="arcTestnet",
    description="Python Agent API",
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


@app.route("/")
def agent_info():
    return jsonify({"success": True, "message": "Use x402 payments to access /api/analyze"})


@app.route("/health")
def health_check():
    return jsonify({"status": "ok", "seller": SELLER_ADDRESS, "sdk": "circlekit-py"})


@app.route("/api/analyze")
@require_payment("$0.01")
def analyze(payment):
    return jsonify({
        "success": True,
        "result": {"summary": "Analysis complete.", "confidence": 0.92},
        "payment": {"amount": payment.amount, "payer": payment.payer, "transaction": payment.transaction},
    })


@app.route("/api/generate", methods=["POST"])
@require_payment("$0.05")
def generate(payment):
    data = request.get_json() or {}
    prompt = data.get("prompt", "default prompt")
    return jsonify({
        "success": True,
        "result": {"content": f"Generated content for: {prompt}", "generatedAt": datetime.now().isoformat()},
        "payment": {"amount": payment.amount, "payer": payment.payer, "transaction": payment.transaction},
    })


if __name__ == "__main__":
    print(f"Server: http://localhost:{PORT} | Seller: {SELLER_ADDRESS}")
    app.run(host="0.0.0.0", port=PORT, debug=True)
