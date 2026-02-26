import json
import tempfile
from pathlib import Path

from spotify2yt.models import Track, Playlist, TransferProgress, MatchStatus


def test_track_search_query():
    t = Track(title="Wonderwall", artists=["Oasis"], album="...", duration_seconds=200)
    assert t.search_query == "Oasis - Wonderwall"


def test_track_search_query_multiple_artists():
    t = Track(title="Song", artists=["A", "B"], album="...", duration_seconds=200)
    assert t.search_query == "A, B - Song"


def test_track_album_search_query():
    t = Track(title="Song", artists=["Artist"], album="Album", duration_seconds=200)
    assert t.album_search_query == "Artist - Album"


def test_track_default_status():
    t = Track(title="X", artists=["Y"], album="Z", duration_seconds=100)
    assert t.match_status == MatchStatus.UNMATCHED
    assert t.match_score == 0.0


def test_transfer_progress_save_load_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "progress.json"
        progress = TransferProgress(
            playlist_spotify_id="abc123",
            playlist_name="Test Playlist",
            youtube_playlist_id="yt123",
            total_tracks=10,
            matched_tracks=[{"spotify_id": "s1", "youtube_id": "y1"}],
            unmatched_tracks=[{"spotify_id": "s2", "title": "Missing Song", "artists": ["X"]}],
            last_processed_index=5,
        )
        progress.save(path)

        loaded = TransferProgress.load(path)
        assert loaded.playlist_spotify_id == "abc123"
        assert loaded.playlist_name == "Test Playlist"
        assert loaded.youtube_playlist_id == "yt123"
        assert loaded.total_tracks == 10
        assert len(loaded.matched_tracks) == 1
        assert len(loaded.unmatched_tracks) == 1
        assert loaded.last_processed_index == 5
        assert loaded.completed is False


def test_transfer_progress_file_permissions():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "progress.json"
        progress = TransferProgress(
            playlist_spotify_id="abc", playlist_name="Test"
        )
        progress.save(path)
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600


def test_playlist_defaults():
    p = Playlist(name="Test", description="Desc", spotify_id="id123")
    assert p.tracks == []
    assert p.track_count == 0
