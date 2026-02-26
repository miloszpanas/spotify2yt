from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from spotify2yt.models import Track, Playlist, TransferProgress, MatchStatus
from spotify2yt.matcher import SongMatcher
from spotify2yt.security import _secure_write_text
from spotify2yt.ytmusic import YouTubeMusicClient
from spotify2yt.config import PROGRESS_DIR, UNMATCHED_LOG_DIR

console = Console()


class TransferEngine:
    """Orchestrates the full transfer of a Spotify playlist to YouTube Music."""

    def __init__(
        self,
        matcher: SongMatcher,
        yt_client: YouTubeMusicClient,
        dry_run: bool = False,
    ):
        self._matcher = matcher
        self._yt = yt_client
        self._dry_run = dry_run

    def transfer_playlist(self, playlist: Playlist, tracks: list[Track]) -> TransferProgress:
        progress_file = PROGRESS_DIR / f"{playlist.spotify_id}.json"

        if self._dry_run:
            state = TransferProgress(
                playlist_spotify_id=playlist.spotify_id,
                playlist_name=playlist.name,
                total_tracks=len(tracks),
            )
        else:
            state = self._load_or_create_progress(progress_file, playlist)
            if not state.youtube_playlist_id:
                console.print(f"[bold]Creating YouTube Music playlist:[/bold] {playlist.name}")
                state.youtube_playlist_id = self._yt.create_playlist(
                    title=playlist.name,
                    description=playlist.description,
                )
                state.total_tracks = len(tracks)
                state.save(progress_file)

        start_index = state.last_processed_index
        already_matched_ids = {m["spotify_id"] for m in state.matched_tracks}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress_bar:
            task = progress_bar.add_task(
                "Matching songs...", total=len(tracks), completed=start_index
            )

            for i, track in enumerate(tracks):
                if i < start_index:
                    continue
                if track.spotify_id in already_matched_ids:
                    progress_bar.advance(task)
                    continue

                matched_track = self._matcher.find_match(track)

                if matched_track.match_status == MatchStatus.MATCHED:
                    state.matched_tracks.append({
                        "spotify_id": track.spotify_id,
                        "youtube_id": matched_track.youtube_id,
                        "title": track.title,
                        "artists": track.artists,
                        "score": matched_track.match_score,
                    })
                else:
                    state.unmatched_tracks.append({
                        "spotify_id": track.spotify_id,
                        "title": track.title,
                        "artists": track.artists,
                    })

                state.last_processed_index = i + 1
                progress_bar.advance(task)

                if not self._dry_run and (i + 1) % 10 == 0:
                    state.save(progress_file)

        if self._dry_run:
            console.print()
            console.print("[bold]Dry run results:[/bold]")
            console.print(f"  Matched:   {len(state.matched_tracks)}/{len(tracks)}")
            console.print(f"  Unmatched: {len(state.unmatched_tracks)}/{len(tracks)}")
            if state.unmatched_tracks:
                console.print("[yellow]Unmatched tracks:[/yellow]")
                for t in state.unmatched_tracks:
                    artists = ", ".join(t["artists"])
                    console.print(f"    {artists} - {t['title']}")
            return state

        state.save(progress_file)

        video_ids = [m["youtube_id"] for m in state.matched_tracks]
        remaining_ids = video_ids[state.tracks_added_to_yt:]
        if remaining_ids:
            already_added = state.tracks_added_to_yt
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as add_bar:
                add_task = add_bar.add_task(
                    "Adding tracks...", total=len(remaining_ids),
                )

                def _on_batch(count: int) -> None:
                    self._update_added_count(
                        state, progress_file, already_added + count
                    )
                    add_bar.update(add_task, completed=count)

                self._yt.add_tracks(
                    state.youtube_playlist_id,
                    remaining_ids,
                    on_batch_done=_on_batch,
                )

        if state.unmatched_tracks:
            self._save_unmatched_log(playlist, state)
            console.print(
                f"[yellow]{len(state.unmatched_tracks)} tracks could not be matched.[/yellow] "
                f"See log in {UNMATCHED_LOG_DIR}"
            )

        state.completed = True
        state.save(progress_file)

        console.print()
        console.print("[green bold]Transfer complete![/green bold]")
        console.print(f"  Matched:   {len(state.matched_tracks)}/{len(tracks)}")
        console.print(f"  Unmatched: {len(state.unmatched_tracks)}/{len(tracks)}")

        return state

    def _update_added_count(
        self, state: TransferProgress, progress_file: Path, count: int
    ) -> None:
        state.tracks_added_to_yt = count
        state.save(progress_file)

    def _load_or_create_progress(
        self, path: Path, playlist: Playlist
    ) -> TransferProgress:
        if path.exists():
            state = TransferProgress.load(path)
            if state is not None:
                console.print("[cyan]Resuming previous transfer...[/cyan]")
                return state
            console.print(
                "[yellow]Progress file is corrupted. Starting fresh.[/yellow]"
            )
        return TransferProgress(
            playlist_spotify_id=playlist.spotify_id,
            playlist_name=playlist.name,
        )

    def _save_unmatched_log(self, playlist: Playlist, state: TransferProgress) -> None:
        UNMATCHED_LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = UNMATCHED_LOG_DIR / f"{playlist.spotify_id}_{timestamp}.txt"
        lines = [f"Unmatched tracks from: {playlist.name}\n\n"]
        for t in state.unmatched_tracks:
            artists = ", ".join(t["artists"])
            lines.append(f"  {artists} - {t['title']}\n")
        _secure_write_text(log_path, "".join(lines))
