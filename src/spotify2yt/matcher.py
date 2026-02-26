import logging
import re
import time

from rapidfuzz import fuzz
from ytmusicapi import YTMusic

from spotify2yt.models import Track, MatchStatus
from spotify2yt.config import MATCH_THRESHOLD_LOW, DURATION_TOLERANCE_SECONDS

logger = logging.getLogger(__name__)

_SEARCH_DELAY_SECONDS = 0.3

NOISE_PATTERNS = [
    r"\s*\(feat\.?\s+[^)]+\)",
    r"\s*\(ft\.?\s+[^)]+\)",
    r"\s*\[feat\.?\s+[^]]+\]",
    r"\s*\(with\s+[^)]+\)",
    r"\s*-\s*Remastered\s*\d*",
    r"\s*\(Remastered\s*\d*\)",
    r"\s*\[Remastered\s*\d*\]",
    r"\s*\(Deluxe\s*Edition?\)",
    r"\s*\[Deluxe\s*Edition?\]",
    r"\s*\(Bonus\s*Track\s*Version\)",
    r"\s*\(Anniversary\s*Edition?\)",
    r"\s*\(Live\)",
    r"\s*\(Radio\s*Edit\)",
    r"\s*\(Single\s*Version\)",
    r"\s*\(Original\s*Mix\)",
]


def normalize_title(title: str) -> str:
    result = title
    for pattern in NOISE_PATTERNS:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)
    return result.strip()


def normalize_artist(artist: str) -> str:
    result = artist.lower().strip()
    result = re.sub(r"\s*&\s*", " and ", result)
    result = re.sub(r"\s+", " ", result)
    return result


def compute_match_score(
    spotify_track: Track,
    yt_title: str,
    yt_artists: list[str],
    yt_duration_seconds: int | None,
) -> float:
    sp_title = normalize_title(spotify_track.title)
    sp_artists = [normalize_artist(a) for a in spotify_track.artists]
    yt_title_clean = normalize_title(yt_title)
    yt_artists_clean = [normalize_artist(a) for a in yt_artists]

    title_score = fuzz.token_sort_ratio(sp_title, yt_title_clean)

    sp_primary = sp_artists[0] if sp_artists else ""
    yt_primary = yt_artists_clean[0] if yt_artists_clean else ""
    artist_score = fuzz.token_sort_ratio(sp_primary, yt_primary)

    for sp_a in sp_artists:
        for yt_a in yt_artists_clean:
            if fuzz.partial_ratio(sp_a, yt_a) > 90:
                artist_score = max(artist_score, 90.0)

    duration_score = 100.0
    if yt_duration_seconds is not None and spotify_track.duration_seconds > 0:
        diff = abs(spotify_track.duration_seconds - yt_duration_seconds)
        if diff <= DURATION_TOLERANCE_SECONDS:
            duration_score = 100.0
        elif diff <= 15:
            duration_score = 80.0
        elif diff <= 30:
            duration_score = 50.0
        else:
            duration_score = max(0.0, 100.0 - diff * 2)

    return (title_score * 0.50) + (artist_score * 0.35) + (duration_score * 0.15)


def _parse_duration(duration_str: str | None) -> int | None:
    """Parse ytmusicapi duration string like '3:45' into seconds."""
    if not duration_str:
        return None
    parts = duration_str.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        return None
    return None


class SongMatcher:
    """Matches Spotify tracks to YouTube Music search results."""

    def __init__(self, ytmusic_client: YTMusic):
        self._yt = ytmusic_client

    def _safe_search(self, *args, **kwargs) -> list[dict]:
        """Wrapper around yt.search() with error handling."""
        try:
            return self._yt.search(*args, **kwargs)
        except Exception as e:
            logger.warning("YouTube Music search failed: %s", e)
            return []

    def find_match(self, track: Track) -> Track:
        # Strategy 1: Filtered song search with "Artist - Title"
        query = track.search_query
        results = self._safe_search(query, filter="songs", limit=5)
        best = self._pick_best(track, results)
        if best:
            track.youtube_id = best["videoId"]
            track.match_status = MatchStatus.MATCHED
            return track

        time.sleep(_SEARCH_DELAY_SECONDS)

        # Strategy 2: Unfiltered search (broader results)
        results = self._safe_search(query, limit=10)
        song_results = [r for r in results if r.get("resultType") in ("song", "video")]
        best = self._pick_best(track, song_results)
        if best:
            track.youtube_id = best["videoId"]
            track.match_status = MatchStatus.MATCHED
            return track

        time.sleep(_SEARCH_DELAY_SECONDS)

        # Strategy 3: Title-only search
        results = self._safe_search(normalize_title(track.title), filter="songs", limit=5)
        best = self._pick_best(track, results)
        if best:
            track.youtube_id = best["videoId"]
            track.match_status = MatchStatus.MATCHED
            return track

        track.match_status = MatchStatus.UNMATCHED
        return track

    def _pick_best(self, spotify_track: Track, results: list[dict]) -> dict | None:
        if not results:
            return None

        scored: list[tuple[float, dict]] = []
        for result in results:
            yt_title = result.get("title", "")
            yt_artists = [a.get("name", "") for a in result.get("artists", [])]

            yt_duration = result.get("duration_seconds")
            if yt_duration is None:
                yt_duration = _parse_duration(result.get("duration"))

            score = compute_match_score(
                spotify_track, yt_title, yt_artists, yt_duration
            )
            scored.append((score, result))

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_result = scored[0]

        if best_score >= MATCH_THRESHOLD_LOW:
            spotify_track.match_score = best_score
            return best_result

        return None
