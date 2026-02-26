from dataclasses import dataclass, field, asdict
from enum import Enum
import json
import os
from pathlib import Path


class MatchStatus(Enum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    SKIPPED = "skipped"


@dataclass
class Track:
    title: str
    artists: list[str]
    album: str
    duration_seconds: int
    spotify_id: str | None = None
    youtube_id: str | None = None
    match_status: MatchStatus = MatchStatus.UNMATCHED
    match_score: float = 0.0

    @property
    def search_query(self) -> str:
        return f"{', '.join(self.artists)} - {self.title}"

    @property
    def album_search_query(self) -> str:
        return f"{self.artists[0]} - {self.album}" if self.artists else self.album


@dataclass
class Playlist:
    name: str
    description: str
    spotify_id: str
    tracks: list[Track] = field(default_factory=list)
    track_count: int = 0


@dataclass
class TransferProgress:
    playlist_spotify_id: str
    playlist_name: str
    youtube_playlist_id: str | None = None
    total_tracks: int = 0
    matched_tracks: list[dict] = field(default_factory=list)
    unmatched_tracks: list[dict] = field(default_factory=list)
    last_processed_index: int = 0
    tracks_added_to_yt: int = 0
    completed: bool = False

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        content = json.dumps(data, indent=2).encode()
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(content)

    @classmethod
    def load(cls, path: Path) -> "TransferProgress | None":
        try:
            data = json.loads(path.read_text())
            return cls(**data)
        except (json.JSONDecodeError, KeyError, TypeError):
            return None
