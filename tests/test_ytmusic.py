from unittest.mock import MagicMock, call, patch

import pytest

from spotify2yt.ytmusic import YouTubeMusicClient


@pytest.fixture
def mock_yt():
    return MagicMock()


@pytest.fixture
def client(mock_yt):
    return YouTubeMusicClient(mock_yt)


class TestCreatePlaylist:
    def test_returns_playlist_id(self, client, mock_yt):
        mock_yt.create_playlist.return_value = "PLid123"
        result = client.create_playlist("My Playlist", "desc")
        assert result == "PLid123"

    def test_raises_on_dict_result(self, client, mock_yt):
        mock_yt.create_playlist.return_value = {"error": "something"}
        with pytest.raises(RuntimeError, match="Failed to create playlist"):
            client.create_playlist("Fail")


class TestAddTracks:
    def test_single_batch(self, client, mock_yt):
        mock_yt.add_playlist_items.return_value = {"status": "ok"}
        client.add_tracks("pl1", ["v1", "v2", "v3"], batch_size=25)
        mock_yt.add_playlist_items.assert_called_once_with(
            playlistId="pl1", videoIds=["v1", "v2", "v3"], duplicates=True
        )

    def test_multiple_batches(self, client, mock_yt):
        mock_yt.add_playlist_items.return_value = {"status": "ok"}
        ids = [f"v{i}" for i in range(5)]
        with patch("spotify2yt.ytmusic.time.sleep"):
            client.add_tracks("pl1", ids, batch_size=2)

        assert mock_yt.add_playlist_items.call_count == 3
        calls = mock_yt.add_playlist_items.call_args_list
        assert calls[0] == call(playlistId="pl1", videoIds=["v0", "v1"], duplicates=True)
        assert calls[1] == call(playlistId="pl1", videoIds=["v2", "v3"], duplicates=True)
        assert calls[2] == call(playlistId="pl1", videoIds=["v4"], duplicates=True)

    def test_on_batch_done_callback(self, client, mock_yt):
        mock_yt.add_playlist_items.return_value = {"status": "ok"}
        callback = MagicMock()
        with patch("spotify2yt.ytmusic.time.sleep"):
            client.add_tracks("pl1", ["v1", "v2", "v3"], batch_size=2, on_batch_done=callback)

        assert callback.call_count == 2
        callback.assert_any_call(2)
        callback.assert_any_call(3)

    def test_error_in_result_raises(self, client, mock_yt):
        mock_yt.add_playlist_items.return_value = {"error": "something bad"}
        with pytest.raises(RuntimeError, match="Failed to add tracks"):
            client.add_tracks("pl1", ["v1"])

    def test_retry_on_transient_error(self, client, mock_yt):
        mock_yt.add_playlist_items.side_effect = [
            ConnectionError("network"),
            {"status": "ok"},
        ]
        with patch("spotify2yt.ytmusic.time.sleep"):
            client.add_tracks("pl1", ["v1"])

        assert mock_yt.add_playlist_items.call_count == 2

    def test_raises_after_max_retries(self, client, mock_yt):
        mock_yt.add_playlist_items.side_effect = ConnectionError("network")
        with patch("spotify2yt.ytmusic.time.sleep"):
            with pytest.raises(RuntimeError, match="after 3 retries"):
                client.add_tracks("pl1", ["v1"])

    def test_empty_list(self, client, mock_yt):
        client.add_tracks("pl1", [])
        mock_yt.add_playlist_items.assert_not_called()
