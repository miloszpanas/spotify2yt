import atexit
import json
import os
from pathlib import Path

import spotipy
from spotipy.oauth2 import SpotifyPKCE, CacheHandler
from ytmusicapi import YTMusic, OAuthCredentials, setup_oauth, setup as setup_browser

from spotify2yt.config import (
    SPOTIFY_REDIRECT_URI, SPOTIFY_SCOPES,
    KEYRING_SPOTIFY_CLIENT_ID, KEYRING_SPOTIFY_TOKEN,
    KEYRING_YT_CLIENT_ID, KEYRING_YT_CLIENT_SECRET, KEYRING_YT_TOKEN,
    KEYRING_YT_BROWSER_HEADERS,
    CONFIG_DIR,
)
from spotify2yt.security import TokenStorage, _secure_write_text


class KeyringCacheHandler(CacheHandler):
    """Spotipy CacheHandler that stores tokens in our secure TokenStorage."""

    def __init__(self, storage: TokenStorage, key: str):
        self._storage = storage
        self._key = key

    def get_cached_token(self) -> dict | None:
        raw = self._storage.retrieve(self._key)
        if raw:
            return json.loads(raw)
        return None

    def save_token_to_cache(self, token_info: dict) -> None:
        self._storage.store(self._key, json.dumps(token_info))


class AuthManager:
    """Manages authentication state for both Spotify and YouTube Music."""

    def __init__(self):
        self.storage = TokenStorage()
        self._cleanup_registered = False

    # --- Spotify ---

    def setup_spotify(self, client_id: str) -> spotipy.Spotify:
        cache_handler = KeyringCacheHandler(self.storage, KEYRING_SPOTIFY_TOKEN)

        auth_manager = SpotifyPKCE(
            client_id=client_id,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope=SPOTIFY_SCOPES,
            cache_handler=cache_handler,
            open_browser=True,
        )
        sp = spotipy.Spotify(auth_manager=auth_manager, requests_timeout=30)
        user = sp.current_user()
        self.storage.store(KEYRING_SPOTIFY_CLIENT_ID, client_id)
        return sp, user

    def get_spotify_client(self) -> spotipy.Spotify | None:
        client_id = self.storage.retrieve(KEYRING_SPOTIFY_CLIENT_ID)
        if not client_id:
            return None

        cache_handler = KeyringCacheHandler(self.storage, KEYRING_SPOTIFY_TOKEN)
        auth_manager = SpotifyPKCE(
            client_id=client_id,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope=SPOTIFY_SCOPES,
            cache_handler=cache_handler,
            open_browser=False,
        )
        return spotipy.Spotify(auth_manager=auth_manager, requests_timeout=30)

    # --- YouTube Music ---

    def setup_youtube(self, client_id: str, client_secret: str) -> YTMusic:
        oauth_file = CONFIG_DIR / "yt_oauth_temp.json"
        oauth_file.parent.mkdir(parents=True, exist_ok=True)

        old_umask = os.umask(0o077)
        try:
            setup_oauth(
                filepath=str(oauth_file),
                client_id=client_id,
                client_secret=client_secret,
                open_browser=True,
            )
        finally:
            os.umask(old_umask)

        try:
            token_data = oauth_file.read_text()
            self.storage.store(KEYRING_YT_CLIENT_ID, client_id)
            self.storage.store(KEYRING_YT_CLIENT_SECRET, client_secret)
            self.storage.store(KEYRING_YT_TOKEN, token_data)

            yt = self._build_ytmusic_client(token_data, client_id, client_secret)
            return yt
        finally:
            if oauth_file.exists():
                oauth_file.unlink()

    def get_youtube_client(self) -> YTMusic | None:
        token_data = self.storage.retrieve(KEYRING_YT_TOKEN)
        client_id = self.storage.retrieve(KEYRING_YT_CLIENT_ID)
        client_secret = self.storage.retrieve(KEYRING_YT_CLIENT_SECRET)

        if not all([token_data, client_id, client_secret]):
            return None

        return self._build_ytmusic_client(token_data, client_id, client_secret)

    # --- YouTube Music (Browser Auth) ---

    def setup_youtube_browser(self) -> YTMusic:
        """Set up YouTube Music with browser cookie authentication."""
        headers_file = CONFIG_DIR / "yt_browser_temp.json"
        headers_file.parent.mkdir(parents=True, exist_ok=True)

        old_umask = os.umask(0o077)
        try:
            setup_browser(filepath=str(headers_file))
        finally:
            os.umask(old_umask)

        try:
            headers_data = headers_file.read_text()
            self.storage.store(KEYRING_YT_BROWSER_HEADERS, headers_data)
            yt = YTMusic(str(headers_file))
            return yt
        finally:
            if headers_file.exists():
                headers_file.unlink()

    def get_youtube_browser_client_path(self) -> str | None:
        """Write stored browser auth headers to a temp file and return its path."""
        headers_data = self.storage.retrieve(KEYRING_YT_BROWSER_HEADERS)
        if not headers_data:
            return None

        tmp_path = CONFIG_DIR / "_yt_browser_session.json"
        _secure_write_text(tmp_path, headers_data)

        def _cleanup_browser():
            if tmp_path.exists():
                tmp_path.unlink()

        atexit.register(_cleanup_browser)
        return str(tmp_path)

    def youtube_browser_authenticated(self) -> bool:
        return self.storage.retrieve(KEYRING_YT_BROWSER_HEADERS) is not None

    def _build_ytmusic_client(
        self, token_data: str, client_id: str, client_secret: str
    ) -> YTMusic:
        tmp_path = CONFIG_DIR / "_yt_session.json"
        _secure_write_text(tmp_path, token_data)

        original_token_data = token_data

        def _cleanup():
            if tmp_path.exists():
                refreshed = tmp_path.read_text()
                if refreshed != original_token_data:
                    self.storage.store(KEYRING_YT_TOKEN, refreshed)
                tmp_path.unlink()

        if not self._cleanup_registered:
            atexit.register(_cleanup)
            self._cleanup_registered = True

        return YTMusic(
            str(tmp_path),
            oauth_credentials=OAuthCredentials(
                client_id=client_id,
                client_secret=client_secret,
            ),
        )

    # --- Status ---

    def spotify_authenticated(self) -> bool:
        return self.storage.retrieve(KEYRING_SPOTIFY_TOKEN) is not None

    def get_youtube_credentials(self) -> dict | None:
        """Return raw YouTube OAuth credentials for YouTube Data API v3."""
        token_data = self.storage.retrieve(KEYRING_YT_TOKEN)
        client_id = self.storage.retrieve(KEYRING_YT_CLIENT_ID)
        client_secret = self.storage.retrieve(KEYRING_YT_CLIENT_SECRET)
        if not all([token_data, client_id, client_secret]):
            return None
        token = json.loads(token_data)
        return {
            "access_token": token["access_token"],
            "refresh_token": token["refresh_token"],
            "client_id": client_id,
            "client_secret": client_secret,
        }

    def youtube_authenticated(self) -> bool:
        return self.storage.retrieve(KEYRING_YT_TOKEN) is not None

    def logout(self) -> None:
        self.storage.clear_all()
