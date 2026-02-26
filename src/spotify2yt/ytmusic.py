import logging
import random
import time
from collections.abc import Callable

import requests
from ytmusicapi import YTMusic

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_YT_API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeMusicClient:
    """YouTube playlist operations via the official YouTube Data API v3.

    The YouTube Music internal API (used by ytmusicapi) rejects OAuth tokens
    from TV/Limited Input device apps, so we use the public Data API instead.
    """

    def __init__(
        self,
        access_token: str,
        refresh_token: str,
        client_id: str,
        client_secret: str,
    ):
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._client_id = client_id
        self._client_secret = client_secret

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token}"}

    def _refresh_access_token(self) -> None:
        r = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "refresh_token",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
            },
        )
        r.raise_for_status()
        self._access_token = r.json()["access_token"]

    def _api_request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make a YouTube Data API v3 request with automatic token refresh."""
        url = f"{_YT_API_BASE}/{endpoint}"
        r = requests.request(method, url, headers=self._auth_headers(), **kwargs)
        if r.status_code == 401:
            self._refresh_access_token()
            r = requests.request(method, url, headers=self._auth_headers(), **kwargs)
        r.raise_for_status()
        return r.json()

    def create_playlist(self, title: str, description: str = "") -> str:
        data = self._api_request(
            "POST",
            "playlists",
            params={"part": "snippet,status"},
            json={
                "snippet": {
                    "title": title,
                    "description": description or "Transferred from Spotify",
                },
                "status": {"privacyStatus": "private"},
            },
        )
        return data["id"]

    def add_tracks(
        self,
        playlist_id: str,
        video_ids: list[str],
        batch_size: int = 25,
        on_batch_done: Callable[[int], None] | None = None,
    ) -> None:
        added = 0
        for i in range(0, len(video_ids), batch_size):
            batch = video_ids[i : i + batch_size]
            for video_id in batch:
                self._insert_playlist_item(playlist_id, video_id)
            added += len(batch)
            if on_batch_done:
                on_batch_done(added)
            if i + batch_size < len(video_ids):
                time.sleep(0.5 + random.uniform(0, 0.3))

    def _insert_playlist_item(self, playlist_id: str, video_id: str) -> None:
        for attempt in range(_MAX_RETRIES):
            try:
                self._api_request(
                    "POST",
                    "playlistItems",
                    params={"part": "snippet"},
                    json={
                        "snippet": {
                            "playlistId": playlist_id,
                            "resourceId": {
                                "kind": "youtube#video",
                                "videoId": video_id,
                            },
                        },
                    },
                )
                return
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 409:
                    return  # duplicate, skip
                if attempt == _MAX_RETRIES - 1:
                    raise RuntimeError(
                        f"Failed to add video {video_id} after {_MAX_RETRIES} retries: {e}"
                    ) from e
                wait = 2**attempt + random.uniform(0, 1)
                logger.warning(
                    "Insert %s failed (attempt %d/%d), retrying in %.1fs: %s",
                    video_id, attempt + 1, _MAX_RETRIES, wait, e,
                )
                time.sleep(wait)


class YTMusicBrowserClient:
    """YouTube Music operations via ytmusicapi with browser cookie authentication.

    Uses browser auth headers (cookies/SAPISID) which authenticate as whichever
    YouTube channel the browser is logged into — including brand accounts.
    """

    def __init__(self, auth_filepath: str):
        self._yt = YTMusic(auth_filepath)

    def create_playlist(self, title: str, description: str = "") -> str:
        result = self._yt.create_playlist(
            title=title,
            description=description or "Transferred from Spotify",
            privacy_status="PRIVATE",
        )
        if isinstance(result, dict):
            raise RuntimeError(f"Failed to create playlist: {result}")
        return result

    def add_tracks(
        self,
        playlist_id: str,
        video_ids: list[str],
        batch_size: int = 25,
        on_batch_done: Callable[[int], None] | None = None,
    ) -> None:
        added = 0
        for i in range(0, len(video_ids), batch_size):
            batch = video_ids[i : i + batch_size]
            result = self._yt.add_playlist_items(playlist_id, batch)
            if result and result.get("status") == "STATUS_FAILED":
                logger.warning("Some tracks failed to add: %s", result)
            added += len(batch)
            if on_batch_done:
                on_batch_done(added)
            if i + batch_size < len(video_ids):
                time.sleep(0.5 + random.uniform(0, 0.3))
