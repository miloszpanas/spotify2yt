from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from spotify2yt.cli import app

runner = CliRunner()


class TestStatus:
    @patch("spotify2yt.cli.auth")
    def test_status_shows_not_configured(self, mock_auth):
        mock_auth.spotify_authenticated.return_value = False
        mock_auth.youtube_authenticated.return_value = False
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Not configured" in result.output

    @patch("spotify2yt.cli.auth")
    def test_status_shows_authenticated(self, mock_auth):
        mock_auth.spotify_authenticated.return_value = True
        mock_auth.youtube_authenticated.return_value = True
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Authenticated" in result.output


class TestLogout:
    @patch("spotify2yt.cli.auth")
    def test_logout_clears_all(self, mock_auth):
        result = runner.invoke(app, ["logout"])
        assert result.exit_code == 0
        mock_auth.logout.assert_called_once()
        assert "cleared" in result.output.lower()


class TestTransfer:
    def test_transfer_requires_argument_or_all(self):
        result = runner.invoke(app, ["transfer"])
        assert result.exit_code == 1

    @patch("spotify2yt.cli.auth")
    def test_transfer_fails_without_spotify(self, mock_auth):
        mock_auth.get_spotify_client.return_value = None
        result = runner.invoke(app, ["transfer", "some_id"])
        assert result.exit_code == 1
        assert "Spotify not configured" in result.output

    @patch("spotify2yt.cli.auth")
    def test_transfer_fails_without_youtube(self, mock_auth):
        mock_auth.get_spotify_client.return_value = MagicMock()
        mock_auth.get_youtube_client.return_value = None
        result = runner.invoke(app, ["transfer", "some_id"])
        assert result.exit_code == 1
        assert "YouTube Music not configured" in result.output


class TestList:
    @patch("spotify2yt.cli.auth")
    def test_list_fails_without_spotify(self, mock_auth):
        mock_auth.get_spotify_client.return_value = None
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 1
        assert "Spotify not configured" in result.output
