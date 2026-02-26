# spotify2yt — Complete Documentation

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture Overview](#2-architecture-overview)
3. [File Reference](#3-file-reference)
   - [pyproject.toml](#31-pyprojecttoml)
   - [src/spotify2yt/\_\_init\_\_.py](#32-srcspotify2yt__init__py)
   - [src/spotify2yt/\_\_main\_\_.py](#33-srcspotify2yt__main__py)+
   - [src/spotify2yt/config.py](#34-srcspotify2ytconfigpy)
   - [src/spotify2yt/models.py](#35-srcspotify2ytmodelspy)
   - [src/spotify2yt/security.py](#36-srcspotify2ytsecuritypy)
   - [src/spotify2yt/auth.py](#37-srcspotify2ytauthpy)
   - [src/spotify2yt/spotify.py](#38-srcspotify2ytspotifypy)
   - [src/spotify2yt/ytmusic.py](#39-srcspotify2ytytmusicpy)
   - [src/spotify2yt/matcher.py](#310-srcspotify2ytmatcherpy)
   - [src/spotify2yt/progress.py](#311-srcspotify2ytprogresspy)
   - [src/spotify2yt/cli.py](#312-srcspotify2ytclipy)
   - [tests/](#313-tests)
4. [Installation](#4-installation)
5. [Spotify Developer App Setup](#5-spotify-developer-app-setup)
6. [Google Cloud OAuth Setup (YouTube Music)](#6-google-cloud-oauth-setup-youtube-music)
7. [Usage Guide](#7-usage-guide)
   - [First-time Setup](#71-first-time-setup)
   - [Listing Playlists](#72-listing-playlists)
   - [Transferring a Single Playlist](#73-transferring-a-single-playlist)
   - [Transferring All Playlists](#74-transferring-all-playlists)
   - [Checking Auth Status](#75-checking-auth-status)
   - [Logging Out](#76-logging-out)
   - [Resuming an Interrupted Transfer](#77-resuming-an-interrupted-transfer)
8. [How Song Matching Works](#8-how-song-matching-works)
9. [Security Architecture](#9-security-architecture)
10. [File Locations on Disk](#10-file-locations-on-disk)
11. [Troubleshooting](#11-troubleshooting)
12. [Dependencies](#12-dependencies)

---

## 1. Project Overview

`spotify2yt` is a command-line tool that transfers playlists from a user's Spotify account to their YouTube Music account. It is designed with security as a first priority:

- **No secrets are ever hardcoded** — you register your own API applications on both platforms
- **All tokens are stored encrypted** — in your OS's native keyring (GNOME Keyring, macOS Keychain, Windows Credential Vault) with an encrypted file fallback
- **Processing is entirely local** — your playlist data never leaves your machine except for direct API calls to Spotify and Google
- **Zero telemetry** — no usage data is collected, tracked, or transmitted

The tool uses [Spotify's PKCE OAuth flow](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow) (which requires no client secret) and [YouTube Music's device/TV OAuth flow](https://ytmusicapi.readthedocs.io/en/stable/setup/oauth.html) via the unofficial `ytmusicapi` library (since Google has no official YouTube Music API).

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  User                                                           │
│    │  runs: spotify2yt transfer <url>                          │
│    ▼                                                            │
│  cli.py  ──── parses commands, validates auth ─────────────────┤
│    │                                                            │
│    ├── auth.py ──── retrieves authenticated clients            │
│    │       └── security.py ──── keyring / encrypted file       │
│    │                                                            │
│    ├── spotify.py ──── fetches playlist + tracks (Spotify API) │
│    │                                                            │
│    └── progress.py ──── orchestrates the transfer              │
│            ├── matcher.py ──── finds songs on YouTube Music     │
│            │       └── ytmusicapi.search()                      │
│            └── ytmusic.py ──── creates playlist, adds tracks   │
│                    └── ytmusicapi.create_playlist() / add()     │
│                                                                 │
│  Data flow:                                                     │
│    Spotify track list ──► matcher ──► YouTube video IDs ──►    │
│    YouTube Music playlist                                       │
└─────────────────────────────────────────────────────────────────┘
```

Each layer has a single responsibility:

| Layer | Files | Responsibility |
|---|---|---|
| CLI | `cli.py` | Parse user commands, display output |
| Auth | `auth.py`, `security.py` | OAuth flows, token storage |
| Config | `config.py` | Paths, constants, thresholds |
| Models | `models.py` | Data structures |
| API Clients | `spotify.py`, `ytmusic.py` | Talk to external APIs |
| Matching | `matcher.py` | Find YouTube equivalents |
| Orchestration | `progress.py` | Run the transfer, handle resume |

---

## 3. File Reference

### 3.1 `pyproject.toml`

The project configuration file following [PEP 621](https://peps.python.org/pep-0621/). Uses `hatchling` as the build backend.

**Key sections:**

```toml
[project.scripts]
spotify2yt = "spotify2yt.cli:app_runner"
```
This registers the `spotify2yt` command on your system when the package is installed.

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```
Tells pytest where to find tests and how to resolve imports from the `src/` layout.

**Dependencies declared:**

| Package | Version | Purpose |
|---|---|---|
| `spotipy` | >=2.24.0 | Spotify Web API client |
| `ytmusicapi` | >=1.8.0 | YouTube Music API client (unofficial) |
| `typer` | >=0.12.0 | CLI framework (built on Click) |
| `rich` | >=13.0.0 | Terminal output (tables, progress bars, colors) |
| `keyring` | >=25.0.0 | OS native credential storage |
| `rapidfuzz` | >=3.0.0 | Fast fuzzy string matching |
| `cryptography` | >=42.0.0 | Fernet symmetric encryption (token fallback) |
| `platformdirs` | >=4.0.0 | XDG-compliant config/data directories |

---

### 3.2 `src/spotify2yt/__init__.py`

Minimal package initializer. Exports only the version string.

```python
__version__ = "0.1.0"
```

Nothing else lives here intentionally — keeping the public API surface minimal.

---

### 3.3 `src/spotify2yt/__main__.py`

Enables running the package directly with `python -m spotify2yt`. Delegates immediately to the Typer app in `cli.py`.

```python
from spotify2yt.cli import app

if __name__ == "__main__":
    app()
```

This means both `spotify2yt` (via the installed script) and `python -m spotify2yt` work identically.

---

### 3.4 `src/spotify2yt/config.py`

Central configuration module. Contains **no secrets** — only paths, service names, and tuning constants.

**Directory paths** are resolved using `platformdirs`, which automatically returns the correct OS-appropriate locations:

| OS | `CONFIG_DIR` | `DATA_DIR` |
|---|---|---|
| Linux | `~/.config/spotify2yt/` | `~/.local/share/spotify2yt/` |
| macOS | `~/Library/Application Support/spotify2yt/` | `~/Library/Application Support/spotify2yt/` |
| Windows | `%APPDATA%\spotify2yt\` | `%APPDATA%\spotify2yt\` |

**Constants defined:**

| Constant | Value | Purpose |
|---|---|---|
| `SPOTIFY_REDIRECT_URI` | `http://127.0.0.1:8888/callback` | OAuth callback — Spotify-mandated loopback address |
| `SPOTIFY_SCOPES` | `playlist-read-private playlist-read-collaborative` | Minimal read-only permissions |
| `KEYRING_SERVICE` | `"spotify2yt"` | Namespace for all keyring entries |
| `MATCH_THRESHOLD_LOW` | `60.0` | Minimum score to accept a match (0-100 scale) |
| `MATCH_THRESHOLD_HIGH` | `85.0` | Score considered a high-confidence match |
| `DURATION_TOLERANCE_SECONDS` | `5` | How many seconds difference is still considered a duration match |

---

### 3.5 `src/spotify2yt/models.py`

Pure data structures with no external dependencies beyond the standard library. Uses Python's `dataclasses` for automatic `__init__`, `__repr__`, and serialization support.

#### `MatchStatus` (Enum)

Represents the outcome of attempting to match a Spotify track to YouTube Music:

| Value | Meaning |
|---|---|
| `MATCHED` | A YouTube Music video ID was found |
| `UNMATCHED` | No suitable match was found after all strategies |
| `SKIPPED` | Track was skipped (e.g., podcast episode, local file) |

#### `Track` (dataclass)

Represents a single audio track from either platform.

| Field | Type | Description |
|---|---|---|
| `title` | `str` | Track name |
| `artists` | `list[str]` | All artist names (primary first) |
| `album` | `str` | Album name |
| `duration_seconds` | `int` | Track length |
| `spotify_id` | `str \| None` | Spotify track ID |
| `youtube_id` | `str \| None` | YouTube video ID (set after matching) |
| `match_status` | `MatchStatus` | Result of matching attempt |
| `match_score` | `float` | Confidence score 0-100 from the matching algorithm |

**Computed properties:**

- `search_query` → `"Artist1, Artist2 - Title"` — the primary search string used in Strategy 1 matching
- `album_search_query` → `"Artist1 - Album"` — used as an alternative search vector

#### `Playlist` (dataclass)

Represents a Spotify playlist container.

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Playlist name |
| `description` | `str` | Playlist description |
| `spotify_id` | `str` | Spotify playlist ID |
| `tracks` | `list[Track]` | Track objects (populated lazily) |
| `track_count` | `int` | Total tracks reported by Spotify API |

#### `TransferProgress` (dataclass)

Serializable state object that tracks how far a transfer has progressed. This is what enables the **resume** feature — it is saved to disk every 10 tracks.

| Field | Type | Description |
|---|---|---|
| `playlist_spotify_id` | `str` | Identifies which playlist this progress belongs to |
| `playlist_name` | `str` | Human-readable name for display |
| `youtube_playlist_id` | `str \| None` | The YT Music playlist created for this transfer |
| `total_tracks` | `int` | How many tracks were in the Spotify playlist |
| `matched_tracks` | `list[dict]` | Successfully matched tracks with both IDs and score |
| `unmatched_tracks` | `list[dict]` | Tracks that couldn't be matched |
| `last_processed_index` | `int` | Index of the last track that was processed |
| `completed` | `bool` | Whether the transfer finished successfully |

**Methods:**

- `save(path)` — serializes to JSON and writes to disk with `chmod 0o600`
- `load(path)` — class method that deserializes from a JSON file

---

### 3.6 `src/spotify2yt/security.py`

The security foundation of the application. Provides a unified `TokenStorage` interface that transparently uses either the OS keyring or an encrypted fallback file.

#### `TokenStorage` class

**How storage is chosen:**

On instantiation, `TokenStorage` is lazy — it doesn't test the keyring until the first `store()` or `retrieve()` call. At that point it runs a quick test:

```
1. Try to write a test value to keyring
2. Try to delete that test value from keyring
3. If both succeed → use keyring for all operations
4. If either fails → use Fernet encrypted file fallback
```

This means the app works on headless servers, Docker containers, and systems without a desktop keyring daemon — it silently falls back to encrypted file storage.

**Keyring storage (primary):**

Credentials are stored in your OS's native secret store under the service name `"spotify2yt"`. On Linux this uses GNOME Keyring (via `SecretService` D-Bus API), on macOS it uses Keychain, and on Windows it uses Credential Vault. These stores protect secrets with the user's login credentials — they cannot be read by other users on the same machine.

**Encrypted file storage (fallback):**

When keyring is unavailable, credentials are stored in two files:

- `tokens.key` — a randomly generated 32-byte Fernet key (AES-128-CBC + HMAC-SHA256)
- `tokens.enc` — all credentials stored as a JSON dict, encrypted with that key

Both files are created with `chmod 0o600` (owner read/write only). The Fernet encryption scheme provides authenticated encryption — an attacker who obtains `tokens.enc` cannot decrypt it without `tokens.key`, and cannot tamper with the ciphertext without detection.

**Public API:**

```python
storage = TokenStorage()
storage.store("my_key", "my_secret_value")   # Save
value = storage.retrieve("my_key")           # Load (returns None if not found)
storage.delete("my_key")                     # Remove one key
storage.clear_all()                          # Remove everything + delete files
```

---

### 3.7 `src/spotify2yt/auth.py`

Manages the full authentication lifecycle for both Spotify and YouTube Music. Bridges the OAuth libraries (`spotipy`, `ytmusicapi`) to our `TokenStorage`.

#### `KeyringCacheHandler` class

Spotipy normally writes tokens to a `.cache` file on disk in plaintext. This class replaces that behavior by implementing spotipy's `CacheHandler` interface and redirecting all reads/writes through `TokenStorage`.

```python
class KeyringCacheHandler(CacheHandler):
    def get_cached_token(self) -> dict | None:
        # Read from secure storage instead of a .cache file
    def save_token_to_cache(self, token_info: dict) -> None:
        # Write to secure storage instead of a .cache file
```

This means **no `.cache` file is ever created on disk**.

#### `AuthManager` class

**Spotify — `setup_spotify(client_id)`:**

Runs the PKCE OAuth flow:
1. Stores the Client ID in `TokenStorage`
2. Creates a `SpotifyPKCE` auth manager with `KeyringCacheHandler`
3. Opens a browser window to `accounts.spotify.com/authorize`
4. Spotipy starts a local HTTP server on `127.0.0.1:8888` to receive the callback
5. After the user approves, the authorization code is exchanged for tokens
6. `KeyringCacheHandler.save_token_to_cache()` stores the token securely
7. Calls `sp.current_user()` to verify the token works

**Why PKCE? No client secret needed.** PKCE (Proof Key for Code Exchange) is an OAuth 2.0 extension for public clients (like CLI apps) that cannot safely store a client secret. Instead of a secret, it uses a one-time cryptographic challenge generated fresh for each auth flow. This means you only need your Spotify Client ID — never your Client Secret.

**Spotify — `get_spotify_client()`:**

For subsequent runs (after setup), retrieves the stored Client ID and token, constructs a `SpotifyPKCE` with `open_browser=False`. Spotipy will automatically use the cached token and refresh it when expired using the stored refresh token.

**YouTube Music — `setup_youtube(client_id, client_secret)`:**

Runs ytmusicapi's device code flow:
1. Stores Client ID and Client Secret in `TokenStorage`
2. Calls `YTMusic.setup_oauth()` which prints a URL and code for the user to visit
3. The user visits the URL, enters the code, and approves on their Google account
4. ytmusicapi writes the resulting token to a temporary file (`yt_oauth_temp.json`)
5. The token data is read from that file and stored in `TokenStorage`
6. The temporary file is deleted in a `finally` block (always deleted, even on errors)

**YouTube Music — `_build_ytmusic_client()`:**

ytmusicapi requires a file path to initialize — it cannot work purely from in-memory credentials. The solution:

1. Write the stored token data to a temporary session file (`_yt_session.json`) with `chmod 0o600`
2. Create the `YTMusic` instance pointing to that file
3. Register an `atexit` handler that, when the process exits:
   - Checks if ytmusicapi refreshed the token (the file content changed)
   - If yes, saves the refreshed token back to `TokenStorage`
   - Deletes the temporary file

This ensures refreshed tokens are persisted without leaving credentials files lying around between runs.

---

### 3.8 `src/spotify2yt/spotify.py`

High-level wrapper around the `spotipy.Spotify` client. Handles all Spotify-specific concerns: pagination, URL parsing, and rate limit retry.

#### `SpotifyClient` class

**`get_playlists() → list[Playlist]`:**

Fetches all of the authenticated user's playlists. The Spotify API returns a maximum of 50 playlists per request. This method follows the `next` cursor automatically until all playlists are loaded.

Returns a list of `Playlist` objects with `name`, `description`, `spotify_id`, and `track_count` populated. The `tracks` list is *not* populated here — it's fetched separately for efficiency.

**`get_playlist_tracks(playlist_id) → list[Track]`:**

Fetches all tracks from a specific playlist, using pagination (100 tracks per request — the maximum allowed by Spotify). Automatically filters out:

- `None` track entries (can appear if a track was deleted from Spotify)
- Podcast episodes (type != "track")
- Local files (`is_local == True`) — these have no Spotify ID and can't be searched

Each track is converted to a `Track` dataclass with `title`, `artists` (all of them), `album`, `duration_seconds`, and `spotify_id`.

**`get_playlist_metadata(playlist_id) → Playlist`:**

Fetches just the metadata (name, description, track count) for a playlist by ID. Uses the `fields` parameter to request only the fields we need, minimizing response size.

**`resolve_playlist_id(url_or_id) → str`:**

Accepts any of these three formats and returns the bare playlist ID:

```
https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc
spotify:playlist:37i9dQZF1DXcBWIGoYBM5M
37i9dQZF1DXcBWIGoYBM5M
```

**`_retry(func, max_retries=3)`:**

Wraps any API call with exponential backoff retry on HTTP 429 (rate limit) responses:

1. First attempt — runs immediately
2. On 429: reads the `Retry-After` header (how many seconds Spotify says to wait), adds up to 25% random jitter to avoid thundering herd, waits, then retries
3. Up to 3 attempts total, then raises the exception

Non-429 exceptions are re-raised immediately (they are not transient).

---

### 3.9 `src/spotify2yt/ytmusic.py`

High-level wrapper around the `ytmusicapi.YTMusic` client. Handles playlist creation and rate-limit-safe batch track addition.

#### `YouTubeMusicClient` class

**`create_playlist(title, description) → str`:**

Creates a new private playlist on YouTube Music and returns its ID. The playlist is always created as `PRIVATE` — you can change visibility in YouTube Music after the transfer. If the API returns a dict (which ytmusicapi does on errors), a `RuntimeError` is raised.

**`add_tracks(playlist_id, video_ids, batch_size=25) → None`:**

Adds tracks to a playlist in batches to avoid overwhelming the API:

- Splits the list of video IDs into chunks of 25
- After each batch (except the last), waits 1.0 to 1.5 seconds (with random jitter)
- Uses `duplicates=True` so re-running after an interrupt doesn't cause duplicate errors
- Detects error responses and raises `RuntimeError` with the batch number for debugging

**`raw` property:**

Exposes the underlying `YTMusic` instance directly, used by `SongMatcher` which needs to call `search()` directly.

---

### 3.10 `src/spotify2yt/matcher.py`

The most algorithmically complex module. Finds the best YouTube Music equivalent for a Spotify track using a multi-strategy approach with fuzzy string matching.

#### Noise Pattern Removal

Before any string comparison, song titles are normalized by stripping common suffixes that differ between platforms:

| Pattern stripped | Example |
|---|---|
| `(feat. Artist)` / `(ft. Artist)` | "HUMBLE. (feat. XXXX)" → "HUMBLE." |
| `(with Artist)` | "Song (with Y)" → "Song" |
| `(Remastered YYYY)` / `- Remastered YYYY` | "Song (Remastered 2011)" → "Song" |
| `[Remastered YYYY]` | "Song [Remastered]" → "Song" |
| `(Deluxe Edition)` / `[Deluxe Edition]` | "Album (Deluxe Edition)" → "Album" |
| `(Bonus Track Version)` | removed |
| `(Anniversary Edition)` | removed |
| `(Live)` | removed |
| `(Radio Edit)` | removed |
| `(Single Version)` | removed |
| `(Original Mix)` | removed |

Artist names are also normalized: converted to lowercase, `&` replaced with `and`, extra whitespace collapsed.

#### `compute_match_score()` function

Produces a single 0-100 confidence score for a Spotify track vs a YouTube result. The score is a weighted composite of three dimensions:

```
Score = (title_score × 0.50) + (artist_score × 0.35) + (duration_score × 0.15)
```

**Title score (50%):** Uses `rapidfuzz.fuzz.token_sort_ratio()`. This function sorts both strings into alphabetical word order before comparing, making it robust to word-order differences (e.g., "Come Together" vs "Together Come" both score high).

**Artist score (35%):** Compares the primary artists of both results using `token_sort_ratio`. Additionally, if *any* of the Spotify artists fuzzy-matches *any* of the YouTube artists at 90%+ using `partial_ratio` (substring matching), the artist score is raised to at least 90. This handles cases like "The Beatles" matching "Beatles".

**Duration score (15%):** Acts as a tiebreaker and catches mismatches (live versions vs studio, different edits):

| Duration difference | Score |
|---|---|
| ≤ 5 seconds | 100 |
| 6–15 seconds | 80 |
| 16–30 seconds | 50 |
| > 30 seconds | `max(0, 100 - diff * 2)` |

#### `SongMatcher` class — Three-strategy search

For each Spotify track, up to three strategies are tried in order. As soon as any strategy finds a result above the acceptance threshold (60), it's returned immediately without trying further strategies.

**Strategy 1 — Filtered artist+title search (highest precision):**
```python
query = "Oasis - Wonderwall"
results = yt.search(query, filter="songs", limit=5)
```
The `filter="songs"` parameter tells YouTube Music to return only songs (not videos, albums, artists). This is the most precise search and handles the majority of cases.

**Strategy 2 — Unfiltered search (broader net):**
```python
results = yt.search("Oasis - Wonderwall", limit=10)
# then filter client-side for resultType in ("song", "video")
```
Same query but without the server-side filter. Catches cases where ytmusicapi's song filter is too narrow — for example, some tracks exist only as music videos on YouTube Music.

**Strategy 3 — Title-only search (handles artist name mismatches):**
```python
results = yt.search("Wonderwall", filter="songs", limit=5)
```
Drops the artist from the query entirely. Useful when artist names are spelled differently, use different separators, or differ in punctuation between platforms. The artist score component in `compute_match_score` still validates the result even if the search query omitted the artist.

#### Acceptance threshold

Results are only accepted if `compute_match_score >= 60`. Below 60, the track is marked `UNMATCHED` and logged for manual review. This threshold was chosen to balance:
- Accepting real matches where metadata slightly differs between platforms
- Rejecting wrong songs that happen to share a common word in the title

---

### 3.11 `src/spotify2yt/progress.py`

Orchestrates the entire transfer flow for one playlist. Coordinates the matcher, YouTube Music client, progress state, and Rich output.

#### `TransferEngine` class

**`transfer_playlist(playlist, tracks) → TransferProgress`:**

The main method. Executes these phases sequentially:

**Phase 1 — Resume check:**
Looks for a progress file at `~/.local/share/spotify2yt/transfers/{spotify_playlist_id}.json`. If found, loads it and prints "Resuming previous transfer...". If not found, creates a new `TransferProgress` state.

**Phase 2 — Create YouTube playlist (if not already created):**
Only runs if `state.youtube_playlist_id` is None. Creates the playlist on YouTube Music with the same name and description, stores its ID in the progress state, and saves to disk. On resume, this step is skipped since the playlist ID is already saved.

**Phase 3 — Match tracks:**
Iterates over all tracks, skipping any already processed (either by index or already in `matched_tracks`). For each track:
- Calls `matcher.find_match(track)` which runs up to 3 search strategies
- Appends result to `matched_tracks` or `unmatched_tracks`
- Shows a Rich progress bar with spinner, percentage, and ETA
- Saves progress state to disk every 10 tracks (so at most 10 tracks are lost if interrupted)

**Phase 4 — Add to YouTube Music:**
Takes all matched YouTube video IDs and calls `yt_client.add_tracks()` which handles batching and rate limiting.

**Phase 5 — Log unmatched:**
If any tracks couldn't be matched, writes a log file to `~/.local/share/spotify2yt/unmatched/{playlist_id}_{timestamp}.txt` listing each unmatched track for manual review.

**Phase 6 — Finalize:**
Sets `state.completed = True`, saves the final progress state, and prints a summary table.

**Resume behavior:**

If you press Ctrl+C during Phase 3 (matching), the SIGINT handler in `cli.py` prints a message and exits. The progress file saved up to that point is left intact. The next time you run `spotify2yt transfer <same-playlist>`, it detects the progress file, loads it, and continues from `last_processed_index`.

**Important:** After resume, Phase 4 re-adds all matched tracks to the YouTube playlist from scratch. The `duplicates=True` flag in `YouTubeMusicClient.add_tracks()` prevents duplicate entries.

---

### 3.12 `src/spotify2yt/cli.py`

The user-facing entry point. Defines all CLI commands using Typer and wires together all other modules.

#### Command structure

```
spotify2yt
├── setup spotify       # Configure Spotify PKCE auth
├── setup youtube       # Configure YouTube Music OAuth
├── status              # Show auth status table
├── list                # List all Spotify playlists
├── transfer [URL]      # Transfer one playlist
│   └── --all           # Transfer all playlists
└── logout              # Clear all stored tokens
```

#### Interrupt handling

The SIGINT handler (Ctrl+C) is registered at module load time:

```python
signal.signal(signal.SIGINT, _handle_sigint)
```

When triggered, it prints a yellow message informing the user that progress was saved, then exits with code 130 (the conventional exit code for SIGINT). This prevents Python's default `KeyboardInterrupt` traceback from appearing.

#### Auth guard helpers

`_require_spotify()` and `_require_youtube()` are used before any command that needs API access. If the respective service isn't authenticated, they print a helpful error message with the exact command to run for setup, then call `raise typer.Exit(1)`.

#### `app_runner()` function

The function referenced in `pyproject.toml`'s `[project.scripts]` section. Just calls `app()` — the Typer application object. This indirection is needed because the entry point must be a callable, not the Typer object itself.

---

### 3.13 `tests/`

#### `tests/conftest.py`

Shared pytest fixtures:

- `sample_track` — a `Track` object for "Bohemian Rhapsody" by Queen
- `sample_track_feat` — a `Track` with featured artist in the title
- `mock_ytmusic` — a `MagicMock` for `YTMusic` used in matcher tests

#### `tests/test_models.py`

Tests the data model behavior:
- `search_query` and `album_search_query` property formatting
- Default `MatchStatus.UNMATCHED` on new tracks
- `TransferProgress` save/load round-trip (JSON serialization)
- File permission `0o600` after save
- Playlist defaults

#### `tests/test_matcher.py`

The most important test file. Tests the matching algorithm entirely in isolation (no real API calls):
- Title normalization for all noise patterns
- Artist normalization (ampersand, extra spaces)
- `compute_match_score` with exact matches, remastered variants, different artists, duration mismatches, word-order variants
- Duration parsing from "3:45" format
- Multi-strategy fallback behavior (mocked YTMusic returning empty then results)
- Full UNMATCHED flow when all strategies return nothing

#### `tests/test_security.py`

Tests `TokenStorage` using the encrypted file fallback (keyring disabled in the fixture):
- Store and retrieve a value
- Retrieve a nonexistent key returns `None`
- Delete a key
- Multiple independent keys
- Overwriting an existing key
- Encrypted file created with `0o600` permissions
- Key file created with `0o600` permissions
- `clear_all()` removes all keys
- `clear_all()` deletes the physical files

---

## 4. Installation

**Requirements:** Python 3.10 or higher.

```bash
# Clone or download the project
cd /path/to/spotify2yt

# Install (creates the 'spotify2yt' command)
pip install -e .

# Or install with dev dependencies (for running tests)
pip install -e ".[dev]"

# Verify installation
spotify2yt --help
```

To uninstall:

```bash
pip uninstall spotify2yt
```

---

## 5. Spotify Developer App Setup

You need a Spotify Developer App to get a **Client ID**. This is free and takes about 5 minutes.

> **Note:** As of 2025, Spotify requires a registered organization for apps that access other users' data. For personal use (transferring your own playlists), your own account works fine in Development Mode.

### Step 1 — Log in to Spotify Developer Dashboard

Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and log in with your Spotify account.

### Step 2 — Create a new app

1. Click **"Create app"**
2. Fill in the form:
   - **App name**: `spotify2yt` (or anything you like)
   - **App description**: "Personal playlist transfer tool" (any description)
   - **Redirect URI**: `http://127.0.0.1:8888/callback`
     - Click **"Add"** after typing the URI — it must appear as a tag, not just text
   - **Which API/SDKs are you planning to use?**: Check "Web API"
3. Check the box to agree to the Developer Terms of Service
4. Click **"Save"**

### Step 3 — Get your Client ID

1. After creating the app, you'll be taken to the app's overview page
2. Your **Client ID** is displayed prominently (a 32-character hex string like `abc123def456...`)
3. Copy it

> **Do NOT copy the Client Secret.** The `spotify2yt` tool uses PKCE and doesn't need it.

### Step 4 — Verify the redirect URI

1. Click **"Settings"** in the top right of your app page
2. Under **"Redirect URIs"**, confirm `http://127.0.0.1:8888/callback` is listed
3. If it's not there, click **"Edit Settings"**, add it under "Redirect URIs", click **"Add"**, then **"Save"**

### Step 5 — Run the setup command

```bash
spotify2yt setup spotify
```

When prompted, paste your Client ID. A browser window will open to Spotify's authorization page. Click **"Agree"** and you'll be redirected to localhost. The CLI will show your Spotify display name confirming success.

---

## 6. Google Cloud OAuth Setup (YouTube Music)

`ytmusicapi` uses Google's OAuth system. You need to create a Google Cloud project and register an OAuth app. This is free.

### Step 1 — Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Sign in with the **same Google account that has your YouTube Music library**
3. At the top, click the project dropdown → **"New Project"**
4. Name it `spotify2yt` (or anything) → click **"Create"**
5. Make sure the new project is selected in the dropdown

### Step 2 — Enable YouTube Data API v3

1. In the left sidebar, navigate to **"APIs & Services" → "Library"**
2. Search for **"YouTube Data API v3"**
3. Click on it → click **"Enable"**

### Step 3 — Configure the OAuth consent screen

1. Navigate to **"APIs & Services" → "OAuth consent screen"**
2. Choose **"External"** → click **"Create"**
3. Fill in the required fields:
   - **App name**: `spotify2yt`
   - **User support email**: your email
   - **Developer contact information**: your email
4. Click **"Save and Continue"**
5. On the **Scopes** page, click **"Save and Continue"** without adding any scopes (ytmusicapi handles this)
6. On the **Test users** page:
   - Click **"Add Users"**
   - Add your own Google account email
   - Click **"Save and Continue"**
7. Click **"Back to Dashboard"**

> **Why "External" mode?** Internal is for Google Workspace organizations. External allows personal Google accounts. Test users are accounts allowed to use the app while it's in testing mode — add your own account here.

### Step 4 — Create an OAuth Client ID

1. Navigate to **"APIs & Services" → "Credentials"**
2. Click **"+ Create Credentials" → "OAuth client ID"**
3. For **Application type**, select **"TV and Limited Input devices"**
   - This is critical — ytmusicapi's OAuth flow uses the device code flow designed for TVs/devices without a browser
4. For **Name**, type `spotify2yt-cli` (or anything)
5. Click **"Create"**
6. A dialog shows your **Client ID** and **Client Secret**
7. Copy both values — you'll need them in the next step

> **Keep your Client Secret private.** Unlike Spotify's PKCE flow, YouTube Music OAuth requires a client secret. Store it only in this CLI tool — never share it, commit it to git, or paste it anywhere else.

### Step 5 — Run the setup command

```bash
spotify2yt setup youtube
```

When prompted, enter your Client ID and Client Secret. The tool will display a URL and a short code, like:

```
Please open the following URL in your browser and enter the code:
URL: https://accounts.google.com/o/oauth2/device/usercode
Code: XXXX-XXXX
```

1. Open the URL in your browser
2. Sign in with the Google account that has YouTube Music
3. Enter the code shown in the terminal
4. Click **"Allow"** to grant access
5. Return to the terminal — it will say "YouTube Music authentication successful!"

---

## 7. Usage Guide

### 7.1 First-time Setup

Before using the tool, you must authenticate with both services:

```bash
# Step 1: Configure Spotify
spotify2yt setup spotify
# → Prompts for Client ID
# → Opens browser for authorization

# Step 2: Configure YouTube Music
spotify2yt setup youtube
# → Prompts for Client ID and Client Secret
# → Shows device code to enter in browser
```

After both setup commands succeed, verify:

```bash
spotify2yt status
```

You should see:

```
    Authentication Status
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ Service       ┃ Status        ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ Spotify       │ Authenticated │
│ YouTube Music │ Authenticated │
└───────────────┴───────────────┘
```

### 7.2 Listing Playlists

See all your Spotify playlists with their track counts and IDs:

```bash
spotify2yt list
```

Output:

```
       Your Spotify Playlists (12)
┏━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ # ┃ Name                  ┃ Tracks ┃ ID                       ┃
┡━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 1 │ My Favorites          │    142 │ 37i9dQZF1DXcBWIGoYBM5M   │
│ 2 │ Workout Mix           │     38 │ 5ABcDeFgHiJkLmNoPqRsTuV  │
│ 3 │ Chill Vibes           │     67 │ ...                      │
└───┴───────────────────────┴────────┴──────────────────────────┘
```

### 7.3 Transferring a Single Playlist

You can use a Spotify URL, a Spotify URI, or a bare playlist ID:

```bash
# Using a full Spotify URL (copied from "Share" in Spotify)
spotify2yt transfer "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc123"

# Using a Spotify URI
spotify2yt transfer "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"

# Using just the playlist ID
spotify2yt transfer 37i9dQZF1DXcBWIGoYBM5M
```

The transfer runs in three visible phases:

```
Transferring: My Favorites (142 tracks)
Creating YouTube Music playlist: My Favorites
⠸ Matching songs... ━━━━━━━━━━━━━━━━━━━  67/142
Adding 134 tracks to YouTube Music...
8 tracks could not be matched. See log in ~/.local/share/spotify2yt/unmatched/

Transfer complete!
  Matched:   134/142
  Unmatched: 8/142
```

### 7.4 Transferring All Playlists

```bash
spotify2yt transfer --all
```

Transfers every playlist in your Spotify library sequentially. Each playlist shows its own progress. If one fails, the others still run.

### 7.5 Checking Auth Status

```bash
spotify2yt status
```

Shows whether each service is authenticated. Does not make any API calls.

### 7.6 Logging Out

```bash
spotify2yt logout
```

Removes all stored credentials from the keyring (and encrypted files if applicable). After this command, you will need to run `setup spotify` and `setup youtube` again before transferring.

### 7.7 Resuming an Interrupted Transfer

If a transfer is interrupted (Ctrl+C, network error, system shutdown), the next time you run the same transfer command it will automatically resume:

```bash
# First attempt — interrupted at track 67/142
spotify2yt transfer 37i9dQZF1DXcBWIGoYBM5M
# → Ctrl+C
# Interrupted. Progress has been saved. Run again to resume.

# Second attempt — continues from track 67
spotify2yt transfer 37i9dQZF1DXcBWIGoYBM5M
# Resuming previous transfer...
# ⠸ Matching songs... ━━━━━━━━━  67/142  (starts here)
```

The YouTube Music playlist is NOT re-created on resume — the same playlist ID from the first run is used.

**To start fresh** (discard progress and start over), delete the progress file:

```bash
# Linux/macOS
rm ~/.local/share/spotify2yt/transfers/<playlist-id>.json

# Windows
del %APPDATA%\spotify2yt\transfers\<playlist-id>.json
```

---

## 8. How Song Matching Works

Finding a Spotify song on YouTube Music is a non-trivial problem because:

- Metadata is inconsistent (Spotify says "The Beatles", YouTube might say "Beatles")
- Spotify tracks have tags like "(Remastered 2011)" that YouTube doesn't always have
- The same song may exist as a "song" (from YT Music) or a "video" (from YouTube proper)
- Some songs exist only as music videos on YouTube

The matching algorithm uses a three-strategy waterfall approach:

```
Spotify track: "Wonderwall" by Oasis, album "...(What's the Story) Morning Glory?", 258s
   │
   ▼
Strategy 1: Search "Oasis - Wonderwall" (filter=songs, top 5 results)
   │  Score each result: title 50% + artist 35% + duration 15%
   │  Best score >= 60? ──YES──► Accept match
   │  No results or all < 60?
   ▼
Strategy 2: Search "Oasis - Wonderwall" (unfiltered, filter client-side, top 10)
   │  Best score >= 60? ──YES──► Accept match
   │  No results or all < 60?
   ▼
Strategy 3: Search "Wonderwall" (filter=songs, top 5 results, title-only)
   │  Best score >= 60? ──YES──► Accept match
   │  Still nothing?
   ▼
UNMATCHED → logged to file for manual review
```

**Expected match rates** based on typical playlists:
- Mainstream pop/rock: ~97-99% match rate
- Niche genres, local releases, rare tracks: ~85-92% match rate
- Classical, jazz with specific recordings: ~80-90% match rate

**What causes unmatched tracks:**
- Song genuinely doesn't exist on YouTube Music
- Very unusual or non-Latin characters in the title/artist name
- Region-locked content (not available in your YouTube Music region)
- Brand-new releases not yet indexed by YouTube Music

---

## 9. Security Architecture

### What credentials does the app store?

| Credential | Stored where | Format |
|---|---|---|
| Spotify Client ID | Keyring / encrypted file | Plain string |
| Spotify OAuth token | Keyring / encrypted file | JSON (access_token, refresh_token, expiry) |
| YouTube Client ID | Keyring / encrypted file | Plain string |
| YouTube Client Secret | Keyring / encrypted file | Plain string |
| YouTube OAuth token | Keyring / encrypted file | JSON (access_token, refresh_token, expiry) |

### What credentials does the app NOT store or transmit?

- Your Spotify username or password (OAuth handles auth, not credentials)
- Your Google username or password (same)
- Your Spotify Client Secret (PKCE doesn't need it)
- Any of your playlist data (only processed in memory during transfer)

### Token lifecycle

**Spotify tokens** expire after 1 hour. `spotipy` automatically refreshes them using the stored refresh token via the PKCE flow — no user interaction required. The refreshed token is saved by `KeyringCacheHandler`.

**YouTube Music tokens** expire after 1 hour. `ytmusicapi` automatically refreshes them internally. The `atexit` handler in `auth.py` detects when the session file changed (indicating a refresh occurred) and saves the new token to `TokenStorage` before process exit.

### Defense-in-depth model

```
Layer 1: No secrets in code
  → Client secret is never in source code; user provides it at runtime

Layer 2: Minimal scope
  → Spotify: only playlist-read-private, playlist-read-collaborative
  → YouTube Music: only what ytmusicapi requests (playlist management)

Layer 3: OS keyring
  → Primary storage uses native OS crypto (tied to user session)
  → Cannot be read by other system users or processes

Layer 4: Encrypted file fallback
  → AES-128-CBC + HMAC-SHA256 via Fernet
  → Separate key file (two files needed to decrypt)
  → Both files chmod 0o600

Layer 5: No persistence of intermediate data
  → Session token file deleted on process exit
  → Temp OAuth setup file deleted in finally block
  → No plain-text .cache file from spotipy

Layer 6: HTTPS-only API calls
  → Enforced by underlying libraries (spotipy, ytmusicapi)
  → No HTTP allowed for API calls

Layer 7: .gitignore
  → Blocks oauth.json, *.token, .env, *.key, *.pem, tokens.enc
```

---

## 10. File Locations on Disk

All files written by `spotify2yt` use XDG-compliant paths:

### Linux

| File | Path | Contents | Permissions |
|---|---|---|---|
| Encryption key | `~/.config/spotify2yt/tokens.key` | 32-byte Fernet key | `600` |
| Encrypted tokens | `~/.config/spotify2yt/tokens.enc` | AES-encrypted JSON dict | `600` |
| Transfer progress | `~/.local/share/spotify2yt/transfers/<id>.json` | Resume state | `600` |
| Unmatched logs | `~/.local/share/spotify2yt/unmatched/<id>_<ts>.txt` | Unmatched track list | `600` |

### macOS

| File | Path |
|---|---|
| Config files | `~/Library/Application Support/spotify2yt/` |
| Data files | `~/Library/Application Support/spotify2yt/` |

### Windows

| File | Path |
|---|---|
| All files | `%APPDATA%\spotify2yt\` |

---

## 11. Troubleshooting

### "Spotify not configured. Run: spotify2yt setup spotify"

You haven't completed Spotify setup yet, or you ran `logout`. Run `spotify2yt setup spotify` and follow the prompts.

### "YouTube Music not configured. Run: spotify2yt setup youtube"

Same as above but for YouTube Music. Run `spotify2yt setup youtube`.

### Browser doesn't open during Spotify setup

The tool calls `open_browser=True` which uses Python's `webbrowser` module. On some Linux systems this may not work. If so, look for a URL printed in the terminal and open it manually.

### "Authentication failed" during YouTube setup

- Confirm you added your Google account as a Test User in the OAuth consent screen (Step 3.6 in the setup guide)
- Confirm the OAuth client type is "TV and Limited Input devices" — other types use a different flow that won't work
- Make sure the YouTube Data API v3 is enabled in your Google Cloud project

### Transfer shows 0% matched

- Verify YouTube Music is set up: `spotify2yt status`
- Try a single well-known track to test: create a test playlist on Spotify with a popular song and transfer it
- Check if your YouTube Music account is in the same region as your Google account

### Low match rate (< 80%)

This is usually expected for playlists with many niche, regional, or classical tracks. Check the unmatched log file:

```bash
ls ~/.local/share/spotify2yt/unmatched/
cat ~/.local/share/spotify2yt/unmatched/<file>.txt
```

You can then manually search for those tracks in YouTube Music.

### "Failed to create playlist" error

YouTube Music has undocumented rate limits on playlist creation. If you're creating many playlists in quick succession, wait 5-10 minutes and try again.

### Progress file corrupted or want to restart

Delete the specific progress file to start the transfer over:

```bash
ls ~/.local/share/spotify2yt/transfers/
rm ~/.local/share/spotify2yt/transfers/<playlist-id>.json
```

### Running on a headless server (no browser)

Both OAuth flows require a browser interaction. If you're on a server:
1. Run the setup commands on your local machine first to generate and store tokens
2. Copy the config directory to the server:
   - Linux: copy `~/.config/spotify2yt/` to the same path on the server

---

## 12. Dependencies

| Package | Version | License | Purpose |
|---|---|---|---|
| [spotipy](https://spotipy.readthedocs.io/) | >=2.24.0 | MIT | Spotify Web API Python client |
| [ytmusicapi](https://ytmusicapi.readthedocs.io/) | >=1.8.0 | MIT | YouTube Music API (unofficial reverse-engineered) |
| [typer](https://typer.tiangolo.com/) | >=0.12.0 | MIT | CLI framework built on Click |
| [rich](https://rich.readthedocs.io/) | >=13.0.0 | MIT | Beautiful terminal output |
| [keyring](https://keyring.readthedocs.io/) | >=25.0.0 | MIT | OS native credential storage |
| [rapidfuzz](https://rapidfuzz.github.io/RapidFuzz/) | >=3.0.0 | MIT | Fast fuzzy string matching |
| [cryptography](https://cryptography.io/) | >=42.0.0 | Apache/BSD | Fernet symmetric encryption |
| [platformdirs](https://platformdirs.readthedocs.io/) | >=4.0.0 | MIT | XDG-compliant directory paths |

**Dev dependencies:**

| Package | Purpose |
|---|---|
| pytest | Test runner |
| pytest-cov | Code coverage reporting |
| pytest-mock | Mock/patch utilities |
