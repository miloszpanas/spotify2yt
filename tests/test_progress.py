import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spotify2yt.models import Track, Playlist, TransferProgress, MatchStatus
from spotify2yt.progress import TransferEngine


@pytest.fixture
def mock_matcher():
    m = MagicMock()
    # Default: every track is matched
    def match(track):
        track.youtube_id = f"yt_{track.spotify_id}"
        track.match_status = MatchStatus.MATCHED
        track.match_score = 95.0
        return track
    m.find_match.side_effect = match
    return m


@pytest.fixture
def mock_yt_client():
    m = MagicMock()
    m.create_playlist.return_value = "yt_playlist_id"
    m.add_tracks.return_value = None
    return m


@pytest.fixture
def playlist():
    return Playlist(
        name="Test Playlist",
        description="A test",
        spotify_id="sp_playlist_123",
    )


@pytest.fixture
def tracks():
    return [
        Track(
            title=f"Song {i}",
            artists=[f"Artist {i}"],
            album="Album",
            duration_seconds=200,
            spotify_id=f"sp{i}",
        )
        for i in range(5)
    ]


class TestTransferPlaylist:
    @patch("spotify2yt.progress.PROGRESS_DIR")
    @patch("spotify2yt.progress.UNMATCHED_LOG_DIR")
    def test_full_transfer(
        self, mock_log_dir, mock_progress_dir, tmp_path,
        mock_matcher, mock_yt_client, playlist, tracks
    ):
        mock_progress_dir.__truediv__ = lambda self, x: tmp_path / x
        mock_log_dir.__truediv__ = lambda self, x: tmp_path / "logs" / x
        mock_log_dir.mkdir = MagicMock()

        engine = TransferEngine(mock_matcher, mock_yt_client)
        state = engine.transfer_playlist(playlist, tracks)

        assert state.completed is True
        assert len(state.matched_tracks) == 5
        assert len(state.unmatched_tracks) == 0
        mock_yt_client.create_playlist.assert_called_once()
        mock_yt_client.add_tracks.assert_called_once()

    @patch("spotify2yt.progress.PROGRESS_DIR")
    @patch("spotify2yt.progress.UNMATCHED_LOG_DIR")
    def test_resume_skips_already_matched(
        self, mock_log_dir, mock_progress_dir, tmp_path,
        mock_matcher, mock_yt_client, playlist, tracks
    ):
        mock_progress_dir.__truediv__ = lambda self, x: tmp_path / x
        mock_log_dir.__truediv__ = lambda self, x: tmp_path / "logs" / x
        mock_log_dir.mkdir = MagicMock()

        # Pre-create progress file as if 3 tracks were already matched
        progress_file = tmp_path / f"{playlist.spotify_id}.json"
        existing = TransferProgress(
            playlist_spotify_id=playlist.spotify_id,
            playlist_name=playlist.name,
            youtube_playlist_id="yt_pl",
            total_tracks=5,
            matched_tracks=[
                {"spotify_id": f"sp{i}", "youtube_id": f"yt_sp{i}",
                 "title": f"Song {i}", "artists": [f"Artist {i}"], "score": 95.0}
                for i in range(3)
            ],
            last_processed_index=3,
            tracks_added_to_yt=3,
        )
        existing.save(progress_file)

        engine = TransferEngine(mock_matcher, mock_yt_client)
        state = engine.transfer_playlist(playlist, tracks)

        # Only 2 new tracks should be matched
        assert mock_matcher.find_match.call_count == 2
        assert len(state.matched_tracks) == 5

        # add_tracks should only add the 2 remaining tracks
        add_call = mock_yt_client.add_tracks.call_args
        remaining_ids = add_call[0][1]
        assert len(remaining_ids) == 2

    @patch("spotify2yt.progress.PROGRESS_DIR")
    @patch("spotify2yt.progress.UNMATCHED_LOG_DIR")
    def test_corrupted_progress_starts_fresh(
        self, mock_log_dir, mock_progress_dir, tmp_path,
        mock_matcher, mock_yt_client, playlist, tracks
    ):
        mock_progress_dir.__truediv__ = lambda self, x: tmp_path / x
        mock_log_dir.__truediv__ = lambda self, x: tmp_path / "logs" / x
        mock_log_dir.mkdir = MagicMock()

        # Write corrupted progress
        progress_file = tmp_path / f"{playlist.spotify_id}.json"
        progress_file.write_text("{invalid json")

        engine = TransferEngine(mock_matcher, mock_yt_client)
        state = engine.transfer_playlist(playlist, tracks)

        assert state.completed is True
        assert len(state.matched_tracks) == 5
        mock_yt_client.create_playlist.assert_called_once()

    @patch("spotify2yt.progress.PROGRESS_DIR")
    def test_dry_run_skips_playlist_creation_and_add(
        self, mock_progress_dir, tmp_path,
        mock_matcher, mock_yt_client, playlist, tracks
    ):
        mock_progress_dir.__truediv__ = lambda self, x: tmp_path / x

        engine = TransferEngine(mock_matcher, mock_yt_client, dry_run=True)
        state = engine.transfer_playlist(playlist, tracks)

        mock_yt_client.create_playlist.assert_not_called()
        mock_yt_client.add_tracks.assert_not_called()
        assert len(state.matched_tracks) == 5
        assert state.completed is False

    @patch("spotify2yt.progress.PROGRESS_DIR")
    @patch("spotify2yt.progress.UNMATCHED_LOG_DIR")
    def test_unmatched_tracks_logged(
        self, mock_log_dir, mock_progress_dir, tmp_path,
        mock_yt_client, playlist, tracks
    ):
        mock_progress_dir.__truediv__ = lambda self, x: tmp_path / x
        log_dir = tmp_path / "logs"
        mock_log_dir.__truediv__ = lambda self, x: log_dir / x
        mock_log_dir.mkdir = MagicMock()

        # Matcher that returns unmatched for all tracks
        matcher = MagicMock()
        def unmatch(track):
            track.match_status = MatchStatus.UNMATCHED
            return track
        matcher.find_match.side_effect = unmatch

        engine = TransferEngine(matcher, mock_yt_client)
        state = engine.transfer_playlist(playlist, tracks)

        assert len(state.unmatched_tracks) == 5
        mock_yt_client.add_tracks.assert_not_called()
