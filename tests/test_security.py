import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from spotify2yt.security import TokenStorage


@pytest.fixture
def storage(tmp_path):
    """TokenStorage that uses encrypted file fallback (keyring disabled)."""
    s = TokenStorage()
    s._keyring_available = False
    s._encrypted_file = tmp_path / "tokens.enc"
    s._key_file = tmp_path / "tokens.key"
    return s


def test_store_and_retrieve(storage):
    storage.store("test_key", "test_value")
    assert storage.retrieve("test_key") == "test_value"


def test_retrieve_nonexistent(storage):
    assert storage.retrieve("nonexistent") is None


def test_delete(storage):
    storage.store("key1", "value1")
    storage.delete("key1")
    assert storage.retrieve("key1") is None


def test_multiple_keys(storage):
    storage.store("key1", "value1")
    storage.store("key2", "value2")
    assert storage.retrieve("key1") == "value1"
    assert storage.retrieve("key2") == "value2"


def test_overwrite_key(storage):
    storage.store("key1", "old_value")
    storage.store("key1", "new_value")
    assert storage.retrieve("key1") == "new_value"


def test_encrypted_file_permissions(storage):
    storage.store("key", "value")
    assert storage._encrypted_file.exists()
    mode = storage._encrypted_file.stat().st_mode & 0o777
    assert mode == 0o600


def test_key_file_permissions(storage):
    storage.store("key", "value")
    assert storage._key_file.exists()
    mode = storage._key_file.stat().st_mode & 0o777
    assert mode == 0o600


def test_clear_all(storage):
    storage.store("spotify_client_id", "id123")
    storage.store("spotify_token", "tok123")
    storage.clear_all()
    assert storage.retrieve("spotify_client_id") is None
    assert storage.retrieve("spotify_token") is None


def test_clear_all_removes_files(storage):
    storage.store("key", "value")
    assert storage._encrypted_file.exists()
    assert storage._key_file.exists()
    storage.clear_all()
    assert not storage._encrypted_file.exists()
    assert not storage._key_file.exists()
