import signal
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from spotify2yt.auth import AuthManager
from spotify2yt.spotify import SpotifyClient
from spotify2yt.ytmusic import YouTubeMusicClient, YTMusicBrowserClient
from spotify2yt.matcher import SongMatcher
from spotify2yt.progress import TransferEngine

app = typer.Typer(
    name="spotify2yt",
    help="Transfer Spotify playlists to YouTube Music.",
    no_args_is_help=True,
)
setup_app = typer.Typer(help="Configure authentication for Spotify and YouTube Music.")
app.add_typer(setup_app, name="setup")

console = Console()
auth = AuthManager()


def _handle_sigint(sig, frame):
    console.print("\n[yellow]Interrupted. Progress has been saved. Run again to resume.[/yellow]")
    sys.exit(130)


signal.signal(signal.SIGINT, _handle_sigint)


# --- Setup commands ---

@setup_app.command("spotify")
def setup_spotify(
    client_id: str = typer.Option(
        ..., prompt="Spotify Client ID",
        help="Your Spotify Developer App Client ID",
    ),
):
    """Configure Spotify authentication (PKCE OAuth flow)."""
    console.print("[bold]Starting Spotify authentication...[/bold]")
    console.print("A browser window will open. Log in and authorize the app.")
    try:
        sp, user = auth.setup_spotify(client_id)
        console.print(f"[green]Authenticated as: {user['display_name']}[/green]")
    except Exception as e:
        console.print("[red]Authentication failed. Run with PYTHONPATH debug logging for details.[/red]")
        raise typer.Exit(1)


@setup_app.command("youtube")
def setup_youtube(
    client_id: str = typer.Option(
        ..., prompt="Google OAuth Client ID",
        help="Your Google Cloud OAuth Client ID (TV/Limited Input type)",
    ),
    client_secret: str = typer.Option(
        ..., prompt="Google OAuth Client Secret (input hidden)",
        help="Your Google Cloud OAuth Client Secret",
        hide_input=True,
    ),
):
    """Configure YouTube Music authentication (Google OAuth flow)."""
    console.print("[bold]Starting YouTube Music authentication...[/bold]")
    console.print("Follow the instructions to authorize with your Google account.")
    try:
        auth.setup_youtube(client_id, client_secret)
        console.print("[green]YouTube Music authentication successful![/green]")
    except Exception as e:
        console.print(f"[red]Authentication failed: {e}[/red]")
        raise typer.Exit(1)


@setup_app.command("youtube-browser")
def setup_youtube_browser():
    """Configure YouTube Music via browser cookies (supports brand accounts)."""
    console.print("[bold]Starting YouTube Music browser authentication...[/bold]")
    console.print(
        "\n[cyan]Instructions:[/cyan]\n"
        "  1. Open YouTube Music in your browser (music.youtube.com)\n"
        "  2. Make sure you're logged into the correct channel/account\n"
        "  3. Open Developer Tools (F12) → Network tab\n"
        "  4. Click on any request to music.youtube.com\n"
        "  5. Copy the request headers and paste them below\n"
    )
    try:
        auth.setup_youtube_browser()
        console.print("[green]YouTube Music browser authentication successful![/green]")
        console.print("[dim]Playlists will be created on whichever channel you were logged into.[/dim]")
    except Exception as e:
        console.print(f"[red]Authentication failed: {e}[/red]")
        raise typer.Exit(1)


# --- Main commands ---

@app.command()
def status(
    verify: bool = typer.Option(
        False, "--verify", help="Make test API calls to verify token validity"
    ),
):
    """Show authentication status for both services."""
    table = Table(title="Authentication Status")
    table.add_column("Service", style="bold")
    table.add_column("Status")

    if verify:
        sp_status = _verify_spotify()
        yt_status = _verify_youtube()
    else:
        sp_status = "[green]Authenticated[/green]" if auth.spotify_authenticated() else "[red]Not configured[/red]"
        yt_status = "[green]Authenticated[/green]" if auth.youtube_authenticated() else "[red]Not configured[/red]"

    yt_browser_status = "[green]Authenticated[/green]" if auth.youtube_browser_authenticated() else "[red]Not configured[/red]"

    table.add_row("Spotify", sp_status)
    table.add_row("YouTube Music (OAuth)", yt_status)
    table.add_row("YouTube Music (Browser)", yt_browser_status)
    console.print(table)


def _verify_spotify() -> str:
    sp = auth.get_spotify_client()
    if not sp:
        return "[red]Not configured[/red]"
    try:
        sp.current_user()
        return "[green]Verified[/green]"
    except Exception:
        return "[yellow]Token expired or invalid[/yellow]"


def _verify_youtube() -> str:
    yt = auth.get_youtube_client()
    if not yt:
        return "[red]Not configured[/red]"
    try:
        yt.get_library_playlists(limit=1)
        return "[green]Verified[/green]"
    except Exception:
        return "[yellow]Token expired or invalid[/yellow]"


@app.command("list")
def list_playlists():
    """List your Spotify playlists."""
    sp = _require_spotify()
    client = SpotifyClient(sp)

    console.print("[bold]Fetching your Spotify playlists...[/bold]")
    playlists = client.get_playlists()

    table = Table(title=f"Your Spotify Playlists ({len(playlists)})")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Name", style="bold")
    table.add_column("Tracks", justify="right")
    table.add_column("ID", style="dim")

    for i, pl in enumerate(playlists, 1):
        table.add_row(str(i), pl.name, str(pl.track_count), pl.spotify_id)

    console.print(table)


@app.command()
def transfer(
    playlist: Optional[str] = typer.Argument(
        None, help="Spotify playlist URL, URI, or ID"
    ),
    all_playlists: bool = typer.Option(
        False, "--all", help="Transfer all playlists"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview matching results without creating playlists"
    ),
):
    """Transfer a Spotify playlist to YouTube Music."""
    if not playlist and not all_playlists:
        console.print("[red]Provide a playlist URL/ID or use --all[/red]")
        raise typer.Exit(1)

    sp = _require_spotify()

    sp_client = SpotifyClient(sp)

    # Prefer browser auth (supports brand accounts) over OAuth + Data API v3
    browser_path = auth.get_youtube_browser_client_path()
    if browser_path:
        console.print("[dim]Using browser authentication (brand account support)[/dim]")
        yt_client = YTMusicBrowserClient(browser_path)
    else:
        yt_creds = _require_youtube_credentials()
        yt_client = YouTubeMusicClient(**yt_creds)

    # Anonymous YTMusic for search — authenticated requests to the internal
    # YouTube Music API are rejected, but unauthenticated search works fine.
    from ytmusicapi import YTMusic as _YTMusic
    matcher = SongMatcher(_YTMusic())
    engine = TransferEngine(matcher, yt_client, dry_run=dry_run)

    if all_playlists:
        playlists = sp_client.get_playlists()
        console.print(f"[bold]Transferring {len(playlists)} playlists...[/bold]")
        failed: list[tuple[str, str]] = []
        for i, pl in enumerate(playlists, 1):
            console.print(f"\n[bold cyan]({i}/{len(playlists)}) {pl.name}[/bold cyan]")
            try:
                tracks = sp_client.get_playlist_tracks(pl.spotify_id)
                engine.transfer_playlist(pl, tracks)
            except Exception as e:
                console.print(f"[red]Failed to transfer '{pl.name}': {e}[/red]")
                failed.append((pl.name, str(e)))
                continue
        if failed:
            console.print(f"\n[yellow bold]{len(failed)} playlist(s) failed:[/yellow bold]")
            for name, err in failed:
                console.print(f"  [red]- {name}:[/red] {err}")
    else:
        playlist_id = sp_client.resolve_playlist_id(playlist)
        tracks = sp_client.get_playlist_tracks(playlist_id)
        pl_meta = sp_client.get_playlist_metadata(playlist_id)
        console.print(f"[bold]Transferring: {pl_meta.name} ({len(tracks)} tracks)[/bold]")
        engine.transfer_playlist(pl_meta, tracks)


@app.command()
def logout():
    """Clear all stored authentication tokens."""
    auth.logout()
    console.print("[green]All credentials cleared.[/green]")


# --- Helpers ---

def _require_spotify():
    sp = auth.get_spotify_client()
    if not sp:
        console.print("[red]Spotify not configured. Run: spotify2yt setup spotify[/red]")
        raise typer.Exit(1)
    return sp


def _require_youtube():
    yt = auth.get_youtube_client()
    if not yt:
        console.print("[red]YouTube Music not configured. Run: spotify2yt setup youtube[/red]")
        raise typer.Exit(1)
    return yt


def _require_youtube_credentials() -> dict:
    creds = auth.get_youtube_credentials()
    if not creds:
        console.print("[red]YouTube Music not configured. Run: spotify2yt setup youtube[/red]")
        raise typer.Exit(1)
    return creds


def app_runner():
    app()
