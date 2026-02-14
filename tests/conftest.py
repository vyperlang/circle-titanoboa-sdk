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


