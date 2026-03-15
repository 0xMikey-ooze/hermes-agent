"""
Tests for AgiClient.from_env() and check_agi_server() startup helpers.
"""

import logging
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agi_client import AgiClient, check_agi_server


class TestCheckAgiServer:
    def test_startup_ok(self):
        """check_agi_server(client) returns True when health() is True."""
        client = AgiClient("http://localhost:8080", "key")
        with patch.object(client, "health", return_value=True):
            result = check_agi_server(client)
        assert result is True

    def test_startup_fail(self):
        """check_agi_server() raises RuntimeError with helpful message when health() is False."""
        client = AgiClient("http://localhost:8080", "key")
        with patch.object(client, "health", return_value=False):
            with pytest.raises(RuntimeError) as exc_info:
                check_agi_server(client)
        error_msg = str(exc_info.value)
        assert "http://localhost:8080" in error_msg
        assert "agi-server" in error_msg.lower() or "AGI" in error_msg

    def test_startup_logs_url(self, caplog):
        """check_agi_server() logs the AGI server URL being checked."""
        client = AgiClient("http://my-agi-server:9000", "key")
        with patch.object(client, "health", return_value=True):
            with caplog.at_level(logging.INFO, logger="src.agi_client"):
                check_agi_server(client)
        assert "http://my-agi-server:9000" in caplog.text


class TestFromEnv:
    def test_env_from_environment(self, monkeypatch):
        """AgiClient.from_env() reads AGI_SERVER_URL and AGI_SERVER_API_KEY."""
        monkeypatch.setenv("AGI_SERVER_URL", "http://agi.example.com")
        monkeypatch.setenv("AGI_SERVER_API_KEY", "prod-key-123")
        client = AgiClient.from_env()
        assert client.url == "http://agi.example.com"
        assert client.api_key == "prod-key-123"

    def test_env_missing_url(self, monkeypatch):
        """AgiClient.from_env() raises ValueError if AGI_SERVER_URL not set."""
        monkeypatch.delenv("AGI_SERVER_URL", raising=False)
        monkeypatch.delenv("AGI_SERVER_API_KEY", raising=False)
        with pytest.raises(ValueError, match="AGI_SERVER_URL"):
            AgiClient.from_env()

    def test_env_no_api_key(self, monkeypatch):
        """AgiClient.from_env() works with no API key (dev mode)."""
        monkeypatch.setenv("AGI_SERVER_URL", "http://localhost:8080")
        monkeypatch.delenv("AGI_SERVER_API_KEY", raising=False)
        client = AgiClient.from_env()
        assert client.url == "http://localhost:8080"
        assert client.api_key is None
