import json
import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet
import keyring
from keyring.errors import KeyringError

from spotify2yt.config import KEYRING_SERVICE, CONFIG_DIR

logger = logging.getLogger(__name__)


def _secure_write(path: Path, data: bytes) -> None:
    """Write data to a file created with 0o600 permissions atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
    except BaseException:
        os.close(fd)
        raise


def _secure_write_text(path: Path, text: str) -> None:
    """Write text to a file created with 0o600 permissions atomically."""
    _secure_write(path, text.encode())


class TokenStorage:
    """Secure token storage with OS keyring primary and Fernet-encrypted file fallback."""

    def __init__(self):
        self._keyring_available: bool | None = None
        self._fernet: Fernet | None = None
        self._encrypted_file = CONFIG_DIR / "tokens.enc"
        self._key_file = CONFIG_DIR / "tokens.key"

    @property
    def keyring_available(self) -> bool:
        if self._keyring_available is None:
            self._keyring_available = self._test_keyring()
        return self._keyring_available

    def _test_keyring(self) -> bool:
        test_key = f"__{KEYRING_SERVICE}_test__"
        try:
            keyring.set_password(KEYRING_SERVICE, test_key, "test")
            keyring.delete_password(KEYRING_SERVICE, test_key)
            return True
        except (KeyringError, Exception):
            logger.warning(
                "OS keyring unavailable. Credentials will be stored in "
                "encrypted files at %s/",
                CONFIG_DIR,
            )
            return False

    def store(self, key: str, value: str) -> None:
        if self.keyring_available:
            keyring.set_password(KEYRING_SERVICE, key, value)
        else:
            self._store_encrypted(key, value)

    def retrieve(self, key: str) -> str | None:
        if self.keyring_available:
            return keyring.get_password(KEYRING_SERVICE, key)
        return self._retrieve_encrypted(key)

    def delete(self, key: str) -> None:
        if self.keyring_available:
            try:
                keyring.delete_password(KEYRING_SERVICE, key)
            except keyring.errors.PasswordDeleteError:
                pass
        else:
            self._delete_encrypted(key)

    def clear_all(self) -> None:
        known_keys = [
            "spotify_client_id", "spotify_token",
            "yt_client_id", "yt_client_secret", "yt_oauth_token",
        ]
        for k in known_keys:
            self.delete(k)
        for f in [self._encrypted_file, self._key_file]:
            if f.exists():
                f.unlink()

    def _get_fernet(self) -> Fernet:
        if self._fernet is None:
            if self._key_file.exists():
                key = self._key_file.read_bytes()
            else:
                key = Fernet.generate_key()
                _secure_write(self._key_file, key)
            self._fernet = Fernet(key)
        return self._fernet

    def _load_encrypted_store(self) -> dict:
        if not self._encrypted_file.exists():
            return {}
        fernet = self._get_fernet()
        encrypted = self._encrypted_file.read_bytes()
        decrypted = fernet.decrypt(encrypted)
        return json.loads(decrypted)

    def _save_encrypted_store(self, data: dict) -> None:
        fernet = self._get_fernet()
        encrypted = fernet.encrypt(json.dumps(data).encode())
        _secure_write(self._encrypted_file, encrypted)

    def _store_encrypted(self, key: str, value: str) -> None:
        data = self._load_encrypted_store()
        data[key] = value
        self._save_encrypted_store(data)

    def _retrieve_encrypted(self, key: str) -> str | None:
        data = self._load_encrypted_store()
        return data.get(key)

    def _delete_encrypted(self, key: str) -> None:
        data = self._load_encrypted_store()
        data.pop(key, None)
        self._save_encrypted_store(data)
