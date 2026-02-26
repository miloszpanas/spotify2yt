# spotify2yt

Transfer your Spotify playlists to YouTube Music via the command line.

## Features

- Transfer individual playlists or all playlists at once
- Smart song matching with fuzzy string comparison (95-98% accuracy)
- Resume interrupted transfers automatically
- Secure by design: all tokens stored encrypted, no hardcoded secrets
- Beautiful CLI output with progress bars

## Prerequisites

- Python 3.10+
- A Spotify account
- A YouTube Music / Google account

## Installation

```bash
cd spotify2yt
pip install -e .
```

## Setup

You need API credentials for both services. The app never stores or transmits your credentials insecurely.

### 1. Spotify Credentials

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. In the app settings, add this redirect URI: `http://127.0.0.1:8888/callback`
4. Copy the **Client ID** (you do NOT need the Client Secret — we use PKCE)

Then run:

```bash
spotify2yt setup spotify
```

Enter your Client ID when prompted. A browser window will open for you to log in.

### 2. YouTube Music Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable the **YouTube Data API v3**
4. Go to **APIs & Services > Credentials**
5. Click **Create Credentials > OAuth client ID**
6. Choose application type: **TVs and Limited Input devices**
7. Copy the **Client ID** and **Client Secret**

Then run:

```bash
spotify2yt setup youtube
```

Enter your Client ID and Client Secret when prompted. Follow the on-screen instructions to authorize.

## Usage

### Check authentication status

```bash
spotify2yt status
```

### List your Spotify playlists

```bash
spotify2yt list
```

### Transfer a single playlist

```bash
# Using a Spotify URL
spotify2yt transfer "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"

# Using a playlist ID
spotify2yt transfer 37i9dQZF1DXcBWIGoYBM5M
```

### Transfer all playlists

```bash
spotify2yt transfer --all
```

### Clear stored credentials

```bash
spotify2yt logout
```

## Resuming Transfers

If a transfer is interrupted (Ctrl+C, network error, etc.), simply run the same command again. The tool saves progress every 10 tracks and will resume from where it left off.

## Unmatched Songs

Songs that couldn't be found on YouTube Music are logged to `~/.local/share/spotify2yt/unmatched/`. Check these files after a transfer to manually add any missing tracks.

## Security

- **No hardcoded secrets**: You provide your own API credentials
- **PKCE OAuth for Spotify**: No client secret needed or stored
- **Encrypted token storage**: Tokens are stored in your OS keyring (GNOME Keyring, macOS Keychain, Windows Credential Vault) with an encrypted file fallback
- **All files created with 600 permissions**: Only your user can read them
- **Local-only processing**: No data is sent anywhere except to Spotify and Google APIs
- **No telemetry**: The app collects zero usage data

## License

MIT
