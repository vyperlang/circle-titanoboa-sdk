#!/usr/bin/env python3
"""
Paywall Server Example - FastAPI adapter for circlekit's framework-agnostic middleware.

Usage:
    export SELLER_ADDRESS=0x...
    pip install fastapi uvicorn
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
from functools import wraps

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from circlekit import create_gateway_middleware
from circlekit.x402 import PaymentInfo

PORT = int(os.environ.get("PORT", 4022))
SELLER_ADDRESS = os.environ.get("SELLER_ADDRESS")

if not SELLER_ADDRESS:
    print("Error: SELLER_ADDRESS environment variable is required")
    sys.exit(1)


app = FastAPI()

gateway = create_gateway_middleware(
    seller_address=SELLER_ADDRESS,
    chain="arcTestnet",
    description="Python Agent API",
)


def require_payment(price):
    """FastAPI adapter: wraps gateway.process_request into a decorator."""
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            result = await gateway.process_request(
                payment_header=request.headers.get("Payment-Signature"),
                path=request.url.path,
                price=price,
            )
            if isinstance(result, dict):
                resp = JSONResponse(result["body"], status_code=result["status"])
                for k, v in result.get("headers", {}).items():
                    resp.headers[k] = v
                return resp
            kwargs["payment"] = result
            response = await func(request, *args, **kwargs)
            # Attach PAYMENT-RESPONSE header if present
            if hasattr(result, 'response_headers') and result.response_headers:
                for k, v in result.response_headers.items():
                    response.headers[k] = v
            return response
        return wrapper
    return decorator


@app.get("/")
async def agent_info():
    return {"success": True, "message": "Use x402 payments to access /api/analyze"}


@app.get("/health")
async def health_check():
    return {"status": "ok", "seller": SELLER_ADDRESS, "sdk": "circlekit-py"}


@app.get("/api/analyze")
@require_payment("$0.01")
async def analyze(request: Request, payment: PaymentInfo = None):
    return JSONResponse({
        "success": True,
        "result": {"summary": "Analysis complete.", "confidence": 0.92},
        "payment": {"amount": payment.amount, "payer": payment.payer, "transaction": payment.transaction},
    })


@app.post("/api/generate")
@require_payment("$0.05")
async def generate(request: Request, payment: PaymentInfo = None):
    data = await request.json()
    prompt = data.get("prompt", "default prompt")
    return JSONResponse({
        "success": True,
        "result": {"content": f"Generated content for: {prompt}", "generatedAt": datetime.now().isoformat()},
        "payment": {"amount": payment.amount, "payer": payment.payer, "transaction": payment.transaction},
    })


if __name__ == "__main__":
    print(f"Server: http://localhost:{PORT} | Seller: {SELLER_ADDRESS}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
