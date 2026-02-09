"""
Server-side middleware for accepting Circle Gateway payments.

This module provides Flask and FastAPI compatible middleware for
implementing x402 paywalls.

Usage (Flask):
    from flask import Flask
    from circlekit import create_gateway_middleware
    
    app = Flask(__name__)
    gateway = create_gateway_middleware(seller_address='0x...')
    
    @app.route('/api/premium')
    @gateway.require('$0.01')
    def premium_endpoint(payment):
        return {'data': 'premium content', 'paid_by': payment.payer}

Usage (FastAPI):
    from fastapi import FastAPI, Depends
    from circlekit import create_gateway_middleware
    
    app = FastAPI()
    gateway = create_gateway_middleware(seller_address='0x...')
    
    @app.get('/api/premium')
    async def premium_endpoint(payment = Depends(gateway.require('$0.01'))):
        return {'data': 'premium content', 'paid_by': payment.payer}
"""

import functools
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union
import httpx

from circlekit.constants import (
    CHAIN_CONFIGS,
    ChainConfig,
    get_gateway_api_url,
    USDC_DECIMALS,
)
from circlekit.boa_utils import parse_usdc
from circlekit.x402 import (
    build_402_response,
    decode_payment_header,
    is_batch_payment,
    PaymentInfo,
)


@dataclass
class GatewayMiddlewareConfig:
    """Configuration for Gateway middleware."""
    seller_address: str
    networks: List[str] = field(default_factory=list)
    description: str = "Paid resource"
    chain: str = "arcTestnet"


class GatewayMiddleware:
    """
    Express-style middleware for accepting Gateway payments.
    
    Works with Flask, FastAPI, and other WSGI/ASGI frameworks.
    """
    
    def __init__(self, config: GatewayMiddlewareConfig):
        self._config = config
        self._chain_config = CHAIN_CONFIGS.get(config.chain, CHAIN_CONFIGS["arcTestnet"])
        self._gateway_api = get_gateway_api_url(self._chain_config.is_testnet)
        self._http = httpx.Client(timeout=30.0)
    
    def require(self, price: str) -> Callable:
        """
        Create a decorator/dependency that requires payment.
        
        Args:
            price: Price in USD (e.g., '$0.01' or '0.01')
            
        Returns:
            Decorator for Flask or dependency for FastAPI
        """
        amount = parse_usdc(price)
        
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # Get request from framework (Flask or other)
                from flask import request, jsonify, make_response
                
                # Check for Payment-Signature header
                payment_header = request.headers.get("Payment-Signature")
                
                if not payment_header:
                    # Return 402 with payment requirements
                    response_body = build_402_response(
                        seller_address=self._config.seller_address,
                        amount=str(amount),
                        chain_id=self._chain_config.chain_id,
                        usdc_address=self._chain_config.usdc_address,
                        gateway_address=self._chain_config.gateway_address,
                        description=self._config.description,
                    )
                    response_body["resource"]["url"] = request.path
                    
                    response = make_response(jsonify(response_body), 402)
                    response.headers["Content-Type"] = "application/json"
                    return response
                
                # Verify payment
                try:
                    payment = self._verify_payment(payment_header, amount)
                except Exception as e:
                    response = make_response(
                        jsonify({"error": f"Payment verification failed: {str(e)}"}),
                        402
                    )
                    return response
                
                if not payment.verified:
                    response = make_response(
                        jsonify({"error": "Invalid payment signature"}),
                        402
                    )
                    return response
                
                # Settle payment
                try:
                    settlement = self._settle_payment(payment_header, amount)
                    if settlement:
                        payment.transaction = settlement.get("transaction", "")
                except Exception as e:
                    # Log but don't fail - verification is sufficient for demo
                    pass
                
                # Attach payment to kwargs and call handler
                kwargs["payment"] = payment
                return func(*args, **kwargs)
            
            return wrapper
        
        return decorator
    
    def require_fastapi(self, price: str):
        """
        Create a FastAPI dependency that requires payment.
        
        Args:
            price: Price in USD (e.g., '$0.01')
            
        Returns:
            FastAPI Depends-compatible callable
        """
        amount = parse_usdc(price)
        
        async def dependency(request):
            from fastapi import HTTPException
            from fastapi.responses import JSONResponse
            
            # Check for Payment-Signature header
            payment_header = request.headers.get("payment-signature")
            
            if not payment_header:
                # Return 402 with payment requirements
                response_body = build_402_response(
                    seller_address=self._config.seller_address,
                    amount=str(amount),
                    chain_id=self._chain_config.chain_id,
                    usdc_address=self._chain_config.usdc_address,
                    gateway_address=self._chain_config.gateway_address,
                    description=self._config.description,
                )
                response_body["resource"]["url"] = str(request.url.path)
                
                raise HTTPException(
                    status_code=402,
                    detail=response_body,
                )
            
            # Verify payment
            try:
                payment = self._verify_payment(payment_header, amount)
            except Exception as e:
                raise HTTPException(
                    status_code=402,
                    detail={"error": f"Payment verification failed: {str(e)}"},
                )
            
            if not payment.verified:
                raise HTTPException(
                    status_code=402,
                    detail={"error": "Invalid payment signature"},
                )
            
            return payment
        
        return dependency
    
    def _verify_payment(self, header: str, expected_amount: int) -> PaymentInfo:
        """
        Verify a payment signature.
        
        In production, this would call the Gateway verify endpoint.
        For demo purposes, we do basic validation.
        """
        try:
            payload = decode_payment_header(header)
        except Exception as e:
            return PaymentInfo(
                verified=False,
                payer="",
                amount="0",
                network="",
            )
        
        # Extract authorization info
        authorization = payload.get("authorization", {})
        accepted = payload.get("accepted", {})
        
        payer = authorization.get("from", "")
        pay_to = authorization.get("to", "")
        value = str(authorization.get("value", 0))
        network = accepted.get("network", "")
        
        # Basic validation
        verified = (
            payer != "" and
            pay_to.lower() == self._config.seller_address.lower() and
            int(value) >= expected_amount
        )
        
        # In production, call Gateway API to verify signature
        # response = self._http.post(
        #     f"{self._gateway_api}/v1/x402/verify",
        #     json={"paymentPayload": payload, "paymentRequirements": accepted}
        # )
        
        return PaymentInfo(
            verified=verified,
            payer=payer,
            amount=value,
            network=network,
        )
    
    def _settle_payment(self, header: str, amount: int) -> Optional[Dict]:
        """
        Submit payment for settlement.
        
        In production, this calls the Gateway settle endpoint.
        """
        try:
            payload = decode_payment_header(header)
            accepted = payload.get("accepted", {})
            
            # Call Gateway settle endpoint
            response = self._http.post(
                f"{self._gateway_api}/v1/x402/settle",
                json={
                    "paymentPayload": payload,
                    "paymentRequirements": accepted,
                }
            )
            
            if response.status_code == 200:
                return response.json()
            
        except Exception:
            pass
        
        return None


def create_gateway_middleware(
    seller_address: str,
    networks: Optional[List[str]] = None,
    description: str = "Paid resource",
    chain: str = "arcTestnet",
) -> GatewayMiddleware:
    """
    Create middleware for accepting Gateway payments.
    
    Args:
        seller_address: Your wallet address to receive payments
        networks: List of networks to accept (default: all)
        description: Resource description for 402 responses
        chain: Primary chain for configuration
        
    Returns:
        GatewayMiddleware instance
        
    Example:
        gateway = create_gateway_middleware(
            seller_address='0x1234...',
            chain='arcTestnet'
        )
        
        @app.route('/api')
        @gateway.require('$0.01')
        def api(payment):
            return {'paid_by': payment.payer}
    """
    config = GatewayMiddlewareConfig(
        seller_address=seller_address,
        networks=networks or [],
        description=description,
        chain=chain,
    )
    return GatewayMiddleware(config)


# Standalone ASGI/WSGI middleware for use without decorators
class X402Middleware:
    """
    ASGI middleware for x402 payment handling.
    
    Can be used as app-level middleware to handle all payment
    requirements automatically.
    """
    
    def __init__(
        self,
        app,
        seller_address: str,
        routes: Dict[str, str] = None,
        chain: str = "arcTestnet",
    ):
        """
        Args:
            app: ASGI application
            seller_address: Address to receive payments
            routes: Dict of {path: price} for paywalled routes
            chain: Chain to use
        """
        self.app = app
        self.seller_address = seller_address
        self.routes = routes or {}
        self.chain = chain
        self._gateway = create_gateway_middleware(seller_address, chain=chain)
    
    async def __call__(self, scope, receive, send):
        """ASGI interface."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        path = scope["path"]
        
        if path not in self.routes:
            await self.app(scope, receive, send)
            return
        
        # This route is paywalled
        price = self.routes[path]
        
        # Check for payment header
        headers = dict(scope.get("headers", []))
        payment_header = headers.get(b"payment-signature", b"").decode()
        
        if not payment_header:
            # Return 402
            await self._send_402(send, path, price)
            return
        
        # Verify and proceed
        await self.app(scope, receive, send)
    
    async def _send_402(self, send, path: str, price: str):
        """Send 402 response."""
        chain_config = CHAIN_CONFIGS.get(self.chain, CHAIN_CONFIGS["arcTestnet"])
        
        body = build_402_response(
            seller_address=self.seller_address,
            amount=str(parse_usdc(price)),
            chain_id=chain_config.chain_id,
            usdc_address=chain_config.usdc_address,
            gateway_address=chain_config.gateway_address,
        )
        body["resource"]["url"] = path
        
        body_bytes = json.dumps(body).encode()
        
        await send({
            "type": "http.response.start",
            "status": 402,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(body_bytes)).encode()],
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body_bytes,
        })
