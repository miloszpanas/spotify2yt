import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from spotify2yt.auth import KeyringCacheHandler, AuthManager


class TestKeyringCacheHandler:
    def test_get_cached_token_returns_dict(self):
        storage = MagicMock()
        storage.retrieve.return_value = json.dumps({"access_token": "abc"})
        handler = KeyringCacheHandler(storage, "test_key")

        result = handler.get_cached_token()
        assert result == {"access_token": "abc"}
        storage.retrieve.assert_called_once_with("test_key")

    def test_get_cached_token_returns_none_when_empty(self):
        storage = MagicMock()
        storage.retrieve.return_value = None
        handler = KeyringCacheHandler(storage, "test_key")

        assert handler.get_cached_token() is None

    def test_save_token_to_cache(self):
        storage = MagicMock()
        handler = KeyringCacheHandler(storage, "test_key")

        token = {"access_token": "xyz", "refresh_token": "abc"}
        handler.save_token_to_cache(token)
        storage.store.assert_called_once_with("test_key", json.dumps(token))

    def test_roundtrip(self):
        """Store a token, then retrieve it — values should match."""
        store = {}
        storage = MagicMock()
        storage.store.side_effect = lambda k, v: store.__setitem__(k, v)
        storage.retrieve.side_effect = lambda k: store.get(k)

        handler = KeyringCacheHandler(storage, "tok")
        original = {"access_token": "a", "refresh_token": "r"}
        handler.save_token_to_cache(original)
        assert handler.get_cached_token() == original


class TestAuthManager:
    @patch("spotify2yt.auth.spotipy.Spotify")
    @patch("spotify2yt.auth.SpotifyPKCE")
    def test_setup_spotify_stores_client_id_after_auth(
        self, mock_pkce_cls, mock_spotify_cls
    ):
        mock_sp = MagicMock()
        mock_sp.current_user.return_value = {"display_name": "Test"}
        mock_spotify_cls.return_value = mock_sp

        manager = AuthManager()
        manager.storage = MagicMock()

        sp, user = manager.setup_spotify("test_client_id")

        # client_id should be stored AFTER current_user succeeds
        mock_sp.current_user.assert_called_once()
        manager.storage.store.assert_called_once_with(
            "spotify_client_id", "test_client_id"
        )
        assert user["display_name"] == "Test"

    @patch("spotify2yt.auth.spotipy.Spotify")
    @patch("spotify2yt.auth.SpotifyPKCE")
    def test_setup_spotify_does_not_store_on_failure(
        self, mock_pkce_cls, mock_spotify_cls
    ):
        mock_sp = MagicMock()
        mock_sp.current_user.side_effect = Exception("auth failed")
        mock_spotify_cls.return_value = mock_sp

        manager = AuthManager()
        manager.storage = MagicMock()

        with pytest.raises(Exception, match="auth failed"):
            manager.setup_spotify("bad_id")

        manager.storage.store.assert_not_called()

    def test_get_spotify_client_returns_none_without_credentials(self):
        manager = AuthManager()
        manager.storage = MagicMock()
        manager.storage.retrieve.return_value = None

        assert manager.get_spotify_client() is None

    def test_get_youtube_client_returns_none_without_credentials(self):
        manager = AuthManager()
        manager.storage = MagicMock()
        manager.storage.retrieve.return_value = None

        assert manager.get_youtube_client() is None

    def test_spotify_authenticated(self):
        manager = AuthManager()
        manager.storage = MagicMock()
        manager.storage.retrieve.side_effect = (
            lambda k: "token" if k == "spotify_token" else None
        )
        assert manager.spotify_authenticated() is True

    def test_spotify_not_authenticated(self):
        manager = AuthManager()
        manager.storage = MagicMock()
        manager.storage.retrieve.return_value = None
        assert manager.spotify_authenticated() is False

    def test_youtube_authenticated(self):
        manager = AuthManager()
        manager.storage = MagicMock()
        manager.storage.retrieve.side_effect = (
            lambda k: "token" if k == "yt_oauth_token" else None
        )
        assert manager.youtube_authenticated() is True

    def test_logout_clears_storage(self):
        manager = AuthManager()
        manager.storage = MagicMock()
        manager.logout()
        manager.storage.clear_all.assert_called_once()

    @patch("spotify2yt.auth.YTMusic")
    @patch("spotify2yt.auth._secure_write_text")
    def test_build_ytmusic_client_registers_atexit_only_once(
        self, mock_write, mock_ytmusic_cls
    ):
        manager = AuthManager()
        manager.storage = MagicMock()

        with patch("spotify2yt.auth.atexit.register") as mock_atexit:
            manager._build_ytmusic_client('{"token": "t"}', "cid", "csecret")
            manager._build_ytmusic_client('{"token": "t"}', "cid", "csecret")
            assert mock_atexit.call_count == 1
