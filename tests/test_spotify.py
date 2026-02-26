from unittest.mock import MagicMock, call

import pytest
from spotipy.exceptions import SpotifyException

from spotify2yt.spotify import SpotifyClient


@pytest.fixture
def mock_sp():
    return MagicMock()


@pytest.fixture
def client(mock_sp):
    return SpotifyClient(mock_sp)


class TestResolvePlaylistId:
    def test_url(self, client):
        url = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc"
        assert client.resolve_playlist_id(url) == "37i9dQZF1DXcBWIGoYBM5M"

    def test_uri(self, client):
        uri = "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"
        assert client.resolve_playlist_id(uri) == "37i9dQZF1DXcBWIGoYBM5M"

    def test_raw_id(self, client):
        assert client.resolve_playlist_id("37i9dQZF1DXcBWIGoYBM5M") == "37i9dQZF1DXcBWIGoYBM5M"

    def test_empty_string(self, client):
        assert client.resolve_playlist_id("") == ""

    def test_url_without_query(self, client):
        url = "https://open.spotify.com/playlist/abc123"
        assert client.resolve_playlist_id(url) == "abc123"


class TestGetPlaylists:
    def test_single_page(self, client, mock_sp):
        mock_sp.current_user_playlists.return_value = {
            "items": [
                {"name": "My Playlist", "id": "p1", "description": "desc",
                 "tracks": {"total": 10}},
            ],
            "next": None,
        }
        playlists = client.get_playlists()
        assert len(playlists) == 1
        assert playlists[0].name == "My Playlist"
        assert playlists[0].track_count == 10

    def test_pagination(self, client, mock_sp):
        page1 = {
            "items": [{"name": "P1", "id": "1", "description": "", "tracks": {"total": 5}}],
            "next": "http://next",
        }
        page2 = {
            "items": [{"name": "P2", "id": "2", "description": "", "tracks": {"total": 3}}],
            "next": None,
        }
        mock_sp.current_user_playlists.return_value = page1
        mock_sp.next.return_value = page2

        playlists = client.get_playlists()
        assert len(playlists) == 2
        assert playlists[0].name == "P1"
        assert playlists[1].name == "P2"

    def test_get_playlists_uses_retry(self, client, mock_sp):
        """get_playlists should use _retry for the initial call."""
        mock_sp.current_user_playlists.side_effect = [
            SpotifyException(429, -1, "Rate limited", headers={"Retry-After": "0"}),
            {"items": [], "next": None},
        ]
        playlists = client.get_playlists()
        assert playlists == []
        assert mock_sp.current_user_playlists.call_count == 2


class TestGetPlaylistTracks:
    def test_basic_tracks(self, client, mock_sp):
        mock_sp.playlist_tracks.return_value = {
            "items": [
                {
                    "track": {
                        "name": "Song",
                        "type": "track",
                        "id": "t1",
                        "artists": [{"name": "Artist"}],
                        "album": {"name": "Album"},
                        "duration_ms": 200000,
                        "is_local": False,
                    }
                }
            ],
            "next": None,
        }
        tracks = client.get_playlist_tracks("pid")
        assert len(tracks) == 1
        assert tracks[0].title == "Song"
        assert tracks[0].duration_seconds == 200

    def test_skips_local_tracks(self, client, mock_sp):
        mock_sp.playlist_tracks.return_value = {
            "items": [
                {
                    "track": {
                        "name": "Local Song",
                        "type": "track",
                        "id": None,
                        "artists": [{"name": "A"}],
                        "album": {"name": "A"},
                        "duration_ms": 100000,
                        "is_local": True,
                    }
                }
            ],
            "next": None,
        }
        tracks = client.get_playlist_tracks("pid")
        assert len(tracks) == 0

    def test_skips_non_tracks(self, client, mock_sp):
        mock_sp.playlist_tracks.return_value = {
            "items": [
                {"track": {"name": "Episode", "type": "episode", "id": "e1"}},
            ],
            "next": None,
        }
        tracks = client.get_playlist_tracks("pid")
        assert len(tracks) == 0


class TestRetry:
    def test_retry_on_429(self, client, mock_sp):
        mock_sp.playlist.side_effect = [
            SpotifyException(429, -1, "Rate limited", headers={"Retry-After": "0"}),
            {"name": "PL", "id": "1", "description": "", "tracks": {"total": 0}},
        ]
        result = client.get_playlist_metadata("1")
        assert result.name == "PL"
        assert mock_sp.playlist.call_count == 2

    def test_non_429_raises_immediately(self, client, mock_sp):
        mock_sp.playlist.side_effect = SpotifyException(
            404, -1, "Not found", headers={}
        )
        with pytest.raises(SpotifyException):
            client.get_playlist_metadata("bad_id")
        assert mock_sp.playlist.call_count == 1
