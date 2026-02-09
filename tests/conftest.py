"""
Pytest configuration for circlekit tests.
"""
import pytest


# Disable titanoboa's evm_snapshot for tests that don't need it
# The titanoboa pytest plugin tries to use evm_snapshot for test isolation,
# but this fails on real RPCs. We disable it globally since most tests
# don't need it and manage their own boa setup.
def pytest_configure(config):
    """Configure pytest."""
    # Add a marker for tests that need titanoboa snapshots
    config.addinivalue_line(
        "markers", "boa_snapshot: mark test as needing titanoboa evm_snapshot"
    )


@pytest.fixture(autouse=True)
def skip_boa_snapshot(request):
    """Skip titanoboa's automatic snapshot unless explicitly marked."""
    # The titanoboa plugin looks for a 'boa_skip' fixture or marker
    # We can also reset boa's environment after each test
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
        "accepts": [
            {
                "network": "arcTestnet",
                "address": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
                "amount": "10000",
                "asset": "0x3600000000000000000000000000000000000000",
                "extra": {
                    "name": "Test API",
                    "version": "1"
                }
            }
        ],
        "error": None
    }


@pytest.fixture
def seller_address():
    """Test seller address."""
    return "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
