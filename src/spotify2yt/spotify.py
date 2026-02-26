import random
import time

import spotipy
from spotipy.exceptions import SpotifyException

from spotify2yt.models import Track, Playlist


class SpotifyClient:
    """High-level Spotify API wrapper with pagination and retry."""

    def __init__(self, sp: spotipy.Spotify):
        self._sp = sp

    def get_playlists(self) -> list[Playlist]:
        playlists: list[Playlist] = []
        results = self._retry(lambda: self._sp.current_user_playlists(limit=50))

        while results:
            for item in results["items"]:
                if not item:
                    continue
                playlists.append(Playlist(
                    name=item["name"],
                    description=item.get("description", ""),
                    spotify_id=item["id"],
                    track_count=(item.get("items") or item.get("tracks") or {}).get("total", 0),
                ))
            if results.get("next"):
                results = self._retry(lambda r=results: self._sp.next(r))
            else:
                results = None

        return playlists

    def get_playlist_tracks(self, playlist_id: str) -> list[Track]:
        tracks: list[Track] = []
        # Use /items instead of the deprecated /tracks endpoint (returns 403 on newer Spotify API)
        results = self._retry(
            lambda: self._sp._get(
                f"playlists/{playlist_id}/items",
                limit=100,
                additional_types="track",
            )
        )

        while results:
            for entry in results["items"]:
                # Spotify renamed "track" → "item" in the /items endpoint
                track_data = entry.get("item") or entry.get("track")
                if not track_data or track_data.get("type") != "track":
                    continue
                if track_data.get("is_local"):
                    continue

                tracks.append(Track(
                    title=track_data["name"],
                    artists=[a["name"] for a in track_data["artists"]],
                    album=track_data["album"]["name"],
                    duration_seconds=track_data["duration_ms"] // 1000,
                    spotify_id=track_data["id"],
                ))

            if results.get("next"):
                results = self._retry(lambda r=results: self._sp.next(r))
            else:
                results = None

        return tracks

    def get_playlist_metadata(self, playlist_id: str) -> Playlist:
        data = self._retry(lambda: self._sp.playlist(playlist_id, fields="id,name,description,items.total,type"))
        return Playlist(
            name=data["name"],
            description=data.get("description", ""),
            spotify_id=data["id"],
            track_count=(data.get("items") or data.get("tracks") or {}).get("total", 0),
        )

    def resolve_playlist_id(self, url_or_id: str) -> str:
        if "open.spotify.com/playlist/" in url_or_id:
            path = url_or_id.split("playlist/")[1]
            return path.split("?")[0].split("/")[0]
        if url_or_id.startswith("spotify:playlist:"):
            return url_or_id.split(":")[-1]
        return url_or_id

    def _retry(self, func, max_retries: int = 3):
        for attempt in range(max_retries):
            try:
                return func()
            except SpotifyException as e:
                if e.http_status == 429:
                    retry_after = int(e.headers.get("Retry-After", 2 ** attempt))
                    jitter = random.uniform(0, retry_after * 0.25)
                    time.sleep(retry_after + jitter)
                elif e.http_status == 403:
                    raise SpotifyException(
                        403, -1,
                        "Access denied (403). Spotify blocks reading tracks from "
                        "playlists you don't own. Only your own playlists can be transferred."
                    ) from e
                else:
                    raise
        return func()
