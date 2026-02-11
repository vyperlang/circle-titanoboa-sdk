"""
Integration tests for circlekit - tests the process_request() adapter pattern.

These tests verify the middleware flow works correctly using mocked facilitator.
"""

import pytest
import json
import base64
from unittest.mock import patch, AsyncMock

from circlekit.server import create_gateway_middleware
from circlekit.x402 import create_payment_header, PaymentRequirements
from circlekit.signer import PrivateKeySigner
from circlekit.facilitator import VerifyResponse, SettleResponse
from circlekit.x402 import PaymentInfo


class TestIntegration:
    """Integration tests using process_request() adapter pattern."""

    @pytest.mark.asyncio
    async def test_no_payment_returns_402(self):
        """Request without payment header returns 402."""
        gateway = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
            chain="arcTestnet",
        )

        result = await gateway.process_request(
            payment_header=None,
            path="/api/paid",
            price="$0.01",
        )

        assert isinstance(result, dict)
        assert result["status"] == 402
        body = result["body"]
        assert "x402Version" in body
        assert body["x402Version"] == 2
        assert "accepts" in body
        assert len(body["accepts"]) == 1
        assert body["accepts"][0]["scheme"] == "exact"
        assert body["accepts"][0]["extra"]["name"] == "GatewayWalletBatched"
        await gateway.close()

    @pytest.mark.asyncio
    async def test_valid_payment_returns_payment_info(self):
        """Request with valid payment returns PaymentInfo."""
        gateway = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
            chain="arcTestnet",
        )

        # Create a signed payment header
        signer = PrivateKeySigner(
            "0x0000000000000000000000000000000000000000000000000000000000000001"
        )
        requirements = PaymentRequirements(
            scheme="exact",
            network="eip155:5042002",
            asset="0x3600000000000000000000000000000000000000",
            amount="10000",
            pay_to="0x1234567890123456789012345678901234567890",
            extra={
                "name": "GatewayWalletBatched",
                "version": "1",
                "verifyingContract": "0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
            },
        )
        resource = {"url": "/api/paid", "description": "Paid resource"}
        header = create_payment_header(signer, requirements, resource=resource)

        # Mock the facilitator to approve
        with patch.object(
            gateway._facilitator, "verify", new_callable=AsyncMock
        ) as mock_verify, patch.object(
            gateway._facilitator, "settle", new_callable=AsyncMock
        ) as mock_settle:
            mock_verify.return_value = VerifyResponse(is_valid=True)
            mock_settle.return_value = SettleResponse(
                success=True, transaction="0xtx123"
            )

            result = await gateway.process_request(
                payment_header=header,
                path="/api/paid",
                price="$0.01",
            )

        assert isinstance(result, PaymentInfo)
        assert result.verified is True
        assert result.payer == signer.address
        assert result.transaction == "0xtx123"
        await gateway.close()

    @pytest.mark.asyncio
    async def test_invalid_payment_returns_402(self):
        """Request with invalid payment header returns 402 error."""
        gateway = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
            chain="arcTestnet",
        )

        # Send a garbage header
        result = await gateway.process_request(
            payment_header="not-valid-base64!!!",
            path="/api/paid",
            price="$0.01",
        )

        assert isinstance(result, dict)
        assert result["status"] == 402
        assert "error" in result["body"]
        await gateway.close()

    @pytest.mark.asyncio
    async def test_failed_verification_returns_402(self):
        """Request that fails verification returns 402."""
        gateway = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
            chain="arcTestnet",
        )

        # Create a valid header structure
        fake_header = base64.b64encode(
            json.dumps(
                {
                    "payload": {
                        "authorization": {"from": "0xabc", "value": "10000"},
                        "signature": "0x123",
                    },
                    "accepted": {},
                }
            ).encode()
        ).decode()

        with patch.object(
            gateway._facilitator, "verify", new_callable=AsyncMock
        ) as mock_verify:
            mock_verify.return_value = VerifyResponse(is_valid=False)

            result = await gateway.process_request(
                payment_header=fake_header,
                path="/api/paid",
                price="$0.01",
            )

        assert isinstance(result, dict)
        assert result["status"] == 402
        assert "invalid" in result["body"]["error"].lower()
        await gateway.close()


    @pytest.mark.asyncio
    async def test_multi_network_payment_on_accepted_chain(self):
        """Payment on an accepted network succeeds with correct chain config."""
        gateway = create_gateway_middleware(
            seller_address="0x1234567890123456789012345678901234567890",
            chain="arcTestnet",
            networks=["arcTestnet", "baseSepolia"],
        )

        # Create a payment for baseSepolia (not the primary chain)
        signer = PrivateKeySigner(
            "0x0000000000000000000000000000000000000000000000000000000000000001"
        )
        requirements = PaymentRequirements(
            scheme="exact",
            network="eip155:84532",
            asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
            amount="10000",
            pay_to="0x1234567890123456789012345678901234567890",
            extra={
                "name": "GatewayWalletBatched",
                "version": "1",
                "verifyingContract": "0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
            },
        )
        resource = {"url": "/api/paid", "description": "Paid resource"}
        header = create_payment_header(signer, requirements, resource=resource)

        with patch.object(
            gateway._facilitator, "verify", new_callable=AsyncMock
        ) as mock_verify, patch.object(
            gateway._facilitator, "settle", new_callable=AsyncMock
        ) as mock_settle:
            mock_verify.return_value = VerifyResponse(is_valid=True)
            mock_settle.return_value = SettleResponse(
                success=True, transaction="0xtx_base"
            )

            result = await gateway.process_request(
                payment_header=header,
                path="/api/paid",
                price="$0.01",
            )

        assert isinstance(result, PaymentInfo)
        assert result.verified is True
        assert result.network == "eip155:84532"
        assert result.transaction == "0xtx_base"
        await gateway.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
