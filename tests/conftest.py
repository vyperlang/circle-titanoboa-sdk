"""
Pytest configuration for circlekit tests.
"""
import pytest


def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "boa_snapshot: mark test as needing titanoboa evm_snapshot"
    )


@pytest.fixture(autouse=True)
def skip_boa_snapshot(request):
    """Skip titanoboa's automatic snapshot unless explicitly marked."""
    pass


@pytest.fixture
def test_private_key():
    """A test private key (DO NOT use with real funds)."""
    return "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


@pytest.fixture
def test_address():
    """Address corresponding to test_private_key."""
    return "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


@pytest.fixture
def sample_402_response():
    """Sample x402 response body for testing."""
    return {
        "x402Version": 2,
        "resource": {"url": "/api/test"},
        "accepts": [
            {
                "scheme": "exact",
                "network": "eip155:5042002",
                "asset": "0x3600000000000000000000000000000000000000",
                "amount": "10000",
                "payTo": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
                "maxTimeoutSeconds": 345600,
                "extra": {
                    "name": "GatewayWalletBatched",
                    "version": "1",
                    "verifyingContract": "0x0077777d7EBA4688BDeF3E311b846F25870A19B9",
                },
            }
        ],
    }


@pytest.fixture
def seller_address():
    """Test seller address."""
    return "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
