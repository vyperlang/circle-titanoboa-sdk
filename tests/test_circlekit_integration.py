"""
Integration tests for circlekit - tests actual HTTP communication.

These tests verify the full x402 flow works end-to-end.
"""

import pytest
import asyncio
import threading
import time
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestIntegration:
    """Integration tests with actual HTTP server."""
    
    @pytest.fixture
    def server_thread(self):
        """Start the Flask server in a background thread."""
        from flask import Flask
        from circlekit import create_gateway_middleware
        
        app = Flask(__name__)
        gateway = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
            chain="arcTestnet",
        )
        
        @app.route("/")
        def index():
            return {"status": "ok", "sdk": "circlekit-py"}
        
        @app.route("/health")
        def health():
            return {"healthy": True}
        
        @app.route("/api/paid")
        @gateway.require("$0.01")
        def paid(payment):
            return {
                "success": True,
                "paid_by": payment.payer,
                "amount": payment.amount,
            }
        
        # Run server in thread
        def run_server():
            app.run(host="127.0.0.1", port=4099, debug=False, use_reloader=False)
        
        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        
        # Wait for server to start
        time.sleep(1)
        
        yield "http://127.0.0.1:4099"
        
        # Server will be killed when thread ends
    
    def test_free_endpoint(self, server_thread):
        """Free endpoint should return 200."""
        import httpx
        
        response = httpx.get(f"{server_thread}/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["sdk"] == "circlekit-py"
    
    def test_health_endpoint(self, server_thread):
        """Health endpoint should return 200."""
        import httpx
        
        response = httpx.get(f"{server_thread}/health")
        
        assert response.status_code == 200
        assert response.json()["healthy"] == True
    
    def test_paid_endpoint_returns_402(self, server_thread):
        """Paid endpoint without payment should return 402."""
        import httpx
        
        response = httpx.get(f"{server_thread}/api/paid")
        
        assert response.status_code == 402
        data = response.json()
        assert "x402Version" in data
        assert data["x402Version"] == 2
        assert "accepts" in data
        assert len(data["accepts"]) == 1
        assert data["accepts"][0]["scheme"] == "exact"
        assert data["accepts"][0]["extra"]["name"] == "GatewayWalletBatched"
    
    @pytest.mark.asyncio
    async def test_client_can_pay(self, server_thread):
        """Client should be able to pay for resource."""
        from circlekit import GatewayClient
        
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        
        # Pay for the resource
        result = await client.pay(f"{server_thread}/api/paid")
        
        # Should succeed
        assert result.status == 200
        assert result.data["success"] == True
        assert result.data["paid_by"] == client.address
        assert result.formatted_amount == "$0.010000"
        
        await client.close()
    
    @pytest.mark.asyncio
    async def test_client_supports_check(self, server_thread):
        """Client.supports() should detect x402 support."""
        from circlekit import GatewayClient
        
        client = GatewayClient(
            chain="arcTestnet",
            private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
        )
        
        # Check free endpoint
        free_result = await client.supports(f"{server_thread}/")
        assert free_result.supported == True
        assert free_result.requirements is None  # Free resource
        
        # Check paid endpoint
        paid_result = await client.supports(f"{server_thread}/api/paid")
        assert paid_result.supported == True
        assert paid_result.requirements is not None
        assert paid_result.requirements["amount"] == "10000"
        
        await client.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
