from pathlib import Path
import platformdirs

APP_NAME = "spotify2yt"

CONFIG_DIR: Path = Path(platformdirs.user_config_dir(APP_NAME))
DATA_DIR: Path = Path(platformdirs.user_data_dir(APP_NAME))
CACHE_DIR: Path = Path(platformdirs.user_cache_dir(APP_NAME))

PROGRESS_DIR: Path = DATA_DIR / "transfers"
UNMATCHED_LOG_DIR: Path = DATA_DIR / "unmatched"

SPOTIFY_REDIRECT_URI = "http://127.0.0.1:8888/callback"
SPOTIFY_SCOPES = "playlist-read-private playlist-read-collaborative"

KEYRING_SERVICE = "spotify2yt"
KEYRING_SPOTIFY_CLIENT_ID = "spotify_client_id"
KEYRING_SPOTIFY_TOKEN = "spotify_token"
KEYRING_YT_CLIENT_ID = "yt_client_id"
KEYRING_YT_CLIENT_SECRET = "yt_client_secret"
KEYRING_YT_TOKEN = "yt_oauth_token"
KEYRING_YT_BROWSER_HEADERS = "yt_browser_headers"

MATCH_THRESHOLD_HIGH = 85.0
MATCH_THRESHOLD_LOW = 60.0
DURATION_TOLERANCE_SECONDS = 5
