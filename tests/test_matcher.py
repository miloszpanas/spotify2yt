import pytest
from unittest.mock import MagicMock

from spotify2yt.matcher import (
    normalize_title,
    normalize_artist,
    compute_match_score,
    SongMatcher,
    _parse_duration,
)
from spotify2yt.models import Track, MatchStatus


def test_normalize_title_removes_remastered():
    assert normalize_title("Bohemian Rhapsody (Remastered 2011)") == "Bohemian Rhapsody"


def test_normalize_title_removes_remastered_dash():
    assert normalize_title("Bohemian Rhapsody - Remastered 2011") == "Bohemian Rhapsody"


def test_normalize_title_removes_feat():
    assert normalize_title("HUMBLE. (feat. Someone)") == "HUMBLE."


def test_normalize_title_removes_ft():
    assert normalize_title("Song (ft. Artist)") == "Song"


def test_normalize_title_removes_deluxe():
    assert normalize_title("Album (Deluxe Edition)") == "Album"


def test_normalize_title_preserves_meaningful_parens():
    assert normalize_title("Come Together (Abbey Road)") == "Come Together (Abbey Road)"


def test_normalize_title_plain():
    assert normalize_title("Simple Title") == "Simple Title"


def test_normalize_artist_ampersand():
    assert normalize_artist("Simon & Garfunkel") == "simon and garfunkel"


def test_normalize_artist_extra_spaces():
    assert normalize_artist("  The   Beatles  ") == "the beatles"


def test_compute_match_score_exact_match():
    track = Track(title="Wonderwall", artists=["Oasis"], album="...", duration_seconds=258)
    score = compute_match_score(track, "Wonderwall", ["Oasis"], 258)
    assert score > 95


def test_compute_match_score_remastered_variant():
    track = Track(title="Bohemian Rhapsody", artists=["Queen"], album="...", duration_seconds=354)
    score = compute_match_score(track, "Bohemian Rhapsody (Remastered 2011)", ["Queen"], 354)
    assert score > 85


def test_compute_match_score_different_artist():
    track = Track(title="Hello", artists=["Adele"], album="...", duration_seconds=300)
    score = compute_match_score(track, "Hello", ["Lionel Richie"], 240)
    assert score < 65


def test_compute_match_score_duration_mismatch():
    track = Track(title="Song", artists=["Artist"], album="...", duration_seconds=200)
    score_close = compute_match_score(track, "Song", ["Artist"], 203)
    score_far = compute_match_score(track, "Song", ["Artist"], 260)
    assert score_close > score_far


def test_compute_match_score_word_order():
    track = Track(title="Come Together", artists=["The Beatles"], album="...", duration_seconds=200)
    score = compute_match_score(track, "Together Come", ["Beatles The"], 200)
    # token_sort_ratio handles word order
    assert score > 70


def test_parse_duration_minutes_seconds():
    assert _parse_duration("3:45") == 225


def test_parse_duration_hours():
    assert _parse_duration("1:02:30") == 3750


def test_parse_duration_none():
    assert _parse_duration(None) is None


def test_parse_duration_invalid():
    assert _parse_duration("abc") is None


def test_song_matcher_uses_fallback_strategies(mock_ytmusic):
    # First strategy returns nothing, second strategy returns a match
    mock_ytmusic.search.side_effect = [
        [],  # Strategy 1: filtered search returns nothing
        [    # Strategy 2: unfiltered search returns a result
            {
                "resultType": "song",
                "videoId": "yt123",
                "title": "Wonderwall",
                "artists": [{"name": "Oasis"}],
                "duration": "4:18",
            }
        ],
    ]

    matcher = SongMatcher(mock_ytmusic)
    track = Track(
        title="Wonderwall", artists=["Oasis"], album="...",
        duration_seconds=258, spotify_id="sp123"
    )
    result = matcher.find_match(track)

    assert result.match_status == MatchStatus.MATCHED
    assert result.youtube_id == "yt123"
    assert mock_ytmusic.search.call_count == 2


def test_song_matcher_unmatched_when_nothing_found(mock_ytmusic):
    mock_ytmusic.search.return_value = []

    matcher = SongMatcher(mock_ytmusic)
    track = Track(
        title="Super Obscure Song", artists=["Unknown Artist"], album="...",
        duration_seconds=200, spotify_id="sp999"
    )
    result = matcher.find_match(track)

    assert result.match_status == MatchStatus.UNMATCHED
    assert result.youtube_id is None
    assert mock_ytmusic.search.call_count == 3  # All 3 strategies tried
