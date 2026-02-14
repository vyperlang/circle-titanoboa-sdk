"""Tests for circlekit.key_utils — normalization and account creation."""

import pytest
from circlekit.key_utils import account_from_key_like, normalize_private_key
from eth_account import Account

# A well-known test key (private key = 1)
TEST_KEY_HEX = "0000000000000000000000000000000000000000000000000000000000000001"
TEST_KEY_0X = "0x" + TEST_KEY_HEX
TEST_ADDRESS = "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"


class TestNormalizePrivateKey:
    """Tests for normalize_private_key."""

    def test_with_0x_prefix(self):
        assert normalize_private_key(TEST_KEY_0X) == TEST_KEY_0X

    def test_without_0x_prefix(self):
        assert normalize_private_key(TEST_KEY_HEX) == TEST_KEY_0X

    def test_uppercase_to_lowercase(self):
        upper = TEST_KEY_HEX.upper()
        result = normalize_private_key(upper)
        assert result == TEST_KEY_0X

    def test_uppercase_0X_prefix(self):
        result = normalize_private_key("0X" + TEST_KEY_HEX)
        assert result == TEST_KEY_0X

    def test_strips_whitespace(self):
        assert normalize_private_key("  " + TEST_KEY_0X + "  ") == TEST_KEY_0X

    def test_strips_trailing_newline(self):
        assert normalize_private_key(TEST_KEY_0X + "\n") == TEST_KEY_0X

    def test_rejects_short_key(self):
        with pytest.raises(ValueError, match="64 hex chars"):
            normalize_private_key("0xdead")

    def test_rejects_long_key(self):
        with pytest.raises(ValueError, match="64 hex chars"):
            normalize_private_key("0x" + "a" * 65)

    def test_rejects_non_hex(self):
        with pytest.raises(ValueError, match="non-hex"):
            normalize_private_key("0x" + "g" * 64)

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="must not be empty"):
            normalize_private_key("")

    def test_rejects_whitespace_only(self):
        with pytest.raises(ValueError, match="must not be empty"):
            normalize_private_key("   ")

    def test_rejects_non_string(self):
        with pytest.raises(ValueError, match="must be a string"):
            normalize_private_key(12345)  # type: ignore[arg-type]

    def test_error_never_contains_key_material(self):
        short_key = "abcd"
        try:
            normalize_private_key(short_key)
        except ValueError as e:
            assert short_key not in str(e)


class TestAccountFromKeyLike:
    """Tests for account_from_key_like."""

    def test_from_string(self):
        account = account_from_key_like(TEST_KEY_0X)
        assert account.address == TEST_ADDRESS

    def test_from_local_account_passthrough(self):
        original = Account.from_key(TEST_KEY_0X)
        result = account_from_key_like(original)
        assert result is original

    def test_from_string_without_prefix(self):
        account = account_from_key_like(TEST_KEY_HEX)
        assert account.address == TEST_ADDRESS

    def test_rejects_invalid_string(self):
        with pytest.raises(ValueError):
            account_from_key_like("not-a-valid-key")
