"""Tests for Honcho CLI helpers."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from honcho_integration.cli import (
    _has_honcho_credentials,
    _resolve_api_key,
    _resolve_base_url,
    clone_honcho_for_profile,
    cmd_identity,
    cmd_setup,
    cmd_status,
    sync_honcho_profiles_quiet,
)
from honcho_integration.client import HonchoClientConfig


class TestResolveApiKey:
    def test_prefers_host_scoped_key(self):
        cfg = {
            "apiKey": "***",
            "hosts": {
                "hermes": {
                    "apiKey": "***",
                }
            },
        }
        assert _resolve_api_key(cfg) == "host-key"

    def test_falls_back_to_root_key(self):
        cfg = {
            "apiKey": "***",
            "hosts": {"hermes": {}},
        }
        assert _resolve_api_key(cfg) == "root-key"

    def test_falls_back_to_env_key(self, monkeypatch):
        monkeypatch.setenv("HONCHO_API_KEY", "env-key")
        assert _resolve_api_key({}) == "env-key"
        monkeypatch.delenv("HONCHO_API_KEY", raising=False)


class TestResolveBaseUrl:
    def test_prefers_host_scoped_snake_case_value(self):
        cfg = {
            "baseUrl": "http://root:8000",
            "hosts": {"hermes": {"base_url": "http://host:8000"}},
        }
        assert _resolve_base_url(cfg) == "http://host:8000"

    def test_prefers_canonical_baseUrl_within_same_scope(self):
        cfg = {
            "base_url": "http://root-snake:8000",
            "baseUrl": "http://root-camel:8000",
        }
        assert _resolve_base_url(cfg) == "http://root-camel:8000"

    def test_accepts_root_level_aliases(self):
        assert _resolve_base_url({"baseURL": "http://root:8001"}) == "http://root:8001"

    def test_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("HONCHO_BASE_URL", "http://env:8000")
        assert _resolve_base_url({}) == "http://env:8000"
        monkeypatch.delenv("HONCHO_BASE_URL", raising=False)


class TestHasHonchoCredentials:
    def test_true_with_api_key(self):
        assert _has_honcho_credentials({"apiKey": "***"}) is True

    def test_true_with_base_url_only(self):
        assert _has_honcho_credentials({"base_url": "http://local:8000"}) is True

    def test_false_without_key_or_base_url(self, monkeypatch):
        monkeypatch.delenv("HONCHO_API_KEY", raising=False)
        monkeypatch.delenv("HONCHO_BASE_URL", raising=False)
        assert _has_honcho_credentials({}) is False


class TestCloneHonchoForProfile:
    def test_clones_default_settings_to_new_profile(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "apiKey": "***",
            "hosts": {
                "hermes": {
                    "peerName": "alice",
                    "memoryMode": "honcho",
                    "recallMode": "tools",
                    "writeFrequency": "turn",
                    "dialecticReasoningLevel": "medium",
                    "enabled": True,
                },
            },
        }))

        with patch("honcho_integration.cli._config_path", return_value=config_file), \
             patch("honcho_integration.cli._local_config_path", return_value=config_file):
            result = clone_honcho_for_profile("coder")

        assert result is True

        cfg = json.loads(config_file.read_text())
        new_block = cfg["hosts"]["hermes.coder"]
        assert new_block["peerName"] == "alice"
        assert new_block["memoryMode"] == "honcho"
        assert new_block["recallMode"] == "tools"
        assert new_block["writeFrequency"] == "turn"
        assert new_block["aiPeer"] == "hermes.coder"
        assert new_block["workspace"] == "hermes"
        assert new_block["enabled"] is True

    def test_skips_when_no_honcho_configured(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        with patch("honcho_integration.cli._config_path", return_value=config_file), \
             patch("honcho_integration.cli._local_config_path", return_value=config_file):
            result = clone_honcho_for_profile("coder")

        assert result is False

    def test_skips_when_host_block_already_exists(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "apiKey": "***",
            "hosts": {
                "hermes": {"peerName": "alice"},
                "hermes.coder": {"peerName": "existing"},
            },
        }))

        with patch("honcho_integration.cli._config_path", return_value=config_file), \
             patch("honcho_integration.cli._local_config_path", return_value=config_file):
            result = clone_honcho_for_profile("coder")

        assert result is False
        cfg = json.loads(config_file.read_text())
        assert cfg["hosts"]["hermes.coder"]["peerName"] == "existing"

    def test_inherits_peer_name_from_root_when_not_in_host(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "apiKey": "***",
            "peerName": "root-alice",
            "hosts": {"hermes": {}},
        }))

        with patch("honcho_integration.cli._config_path", return_value=config_file), \
             patch("honcho_integration.cli._local_config_path", return_value=config_file):
            clone_honcho_for_profile("dreamer")

        cfg = json.loads(config_file.read_text())
        assert cfg["hosts"]["hermes.dreamer"]["peerName"] == "root-alice"

    def test_works_with_api_key_only_no_host_block(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"apiKey": "***"}))

        with patch("honcho_integration.cli._config_path", return_value=config_file), \
             patch("honcho_integration.cli._local_config_path", return_value=config_file):
            result = clone_honcho_for_profile("coder")

        assert result is True
        cfg = json.loads(config_file.read_text())
        assert cfg["hosts"]["hermes.coder"]["aiPeer"] == "hermes.coder"
        assert cfg["hosts"]["hermes.coder"]["workspace"] == "hermes"


class TestSyncHonchoProfilesQuiet:
    def test_syncs_missing_profiles(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "apiKey": "***",
            "hosts": {"hermes": {"peerName": "alice", "memoryMode": "honcho"}},
        }))

        class FakeProfile:
            def __init__(self, name):
                self.name = name
                self.is_default = name == "default"

        profiles = [FakeProfile("default"), FakeProfile("coder"), FakeProfile("dreamer")]

        with patch("honcho_integration.cli._config_path", return_value=config_file), \
             patch("honcho_integration.cli._local_config_path", return_value=config_file), \
             patch("hermes_cli.profiles.list_profiles", return_value=profiles):
            count = sync_honcho_profiles_quiet()

        assert count == 2
        cfg = json.loads(config_file.read_text())
        assert "hermes.coder" in cfg["hosts"]
        assert "hermes.dreamer" in cfg["hosts"]

    def test_returns_zero_when_no_honcho(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        with patch("honcho_integration.cli._config_path", return_value=config_file), \
             patch("honcho_integration.cli._local_config_path", return_value=config_file):
            count = sync_honcho_profiles_quiet()

        assert count == 0

    def test_skips_already_synced(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "apiKey": "***",
            "hosts": {
                "hermes": {"peerName": "alice"},
                "hermes.coder": {"peerName": "existing"},
            },
        }))

        class FakeProfile:
            def __init__(self, name):
                self.name = name
                self.is_default = name == "default"

        with patch("honcho_integration.cli._config_path", return_value=config_file), \
             patch("hermes_cli.profiles.list_profiles", return_value=[FakeProfile("default"), FakeProfile("coder")]):
            count = sync_honcho_profiles_quiet()

        assert count == 0


class TestHonchoCliCommands:
    def test_identity_allows_base_url_only_config(self, monkeypatch, capsys):
        cfg = {"hosts": {"hermes": {"base_url": "http://localhost:8000"}}}
        manager = MagicMock()
        manager.get_or_create.return_value = object()

        monkeypatch.setattr("honcho_integration.cli._read_config", lambda: cfg)
        monkeypatch.setattr(
            "honcho_integration.client.HonchoClientConfig.from_global_config",
            lambda: HonchoClientConfig(base_url="http://localhost:8000", enabled=True),
        )
        monkeypatch.setattr("honcho_integration.client.get_honcho_client", lambda hcfg: MagicMock())
        monkeypatch.setattr("honcho_integration.session.HonchoSessionManager", lambda honcho, config: manager)

        cmd_identity(SimpleNamespace(file=None, show=False))
        out = capsys.readouterr().out

        assert "No API key configured" not in out
        manager.get_or_create.assert_called_once()

    def test_setup_allows_existing_base_url_without_api_key(self, monkeypatch, capsys):
        cfg = {"hosts": {"hermes": {"base_url": "http://localhost:8000"}}}
        prompts = iter(["", "http://localhost:8000", "eri", "hermes", "hybrid", "async", "hybrid", "per-session"])

        monkeypatch.setattr("honcho_integration.cli._read_config", lambda: cfg)
        monkeypatch.setattr("honcho_integration.cli._write_config", lambda updated: None)
        monkeypatch.setattr("honcho_integration.cli._ensure_sdk_installed", lambda: True)
        monkeypatch.setattr("honcho_integration.cli._prompt", lambda *args, **kwargs: next(prompts))
        monkeypatch.setattr("honcho_integration.client.reset_honcho_client", lambda: None)
        monkeypatch.setattr(
            "honcho_integration.client.HonchoClientConfig.from_global_config",
            lambda: HonchoClientConfig(base_url="http://localhost:8000", enabled=True, peer_name="eri"),
        )
        monkeypatch.setattr("honcho_integration.client.get_honcho_client", lambda hcfg: MagicMock())

        cmd_setup(SimpleNamespace())
        out = capsys.readouterr().out

        assert "No API key configured" not in out
        assert "Honcho is ready" in out

    def test_status_treats_base_url_only_as_connectable(self, monkeypatch, capsys):
        cfg = {"hosts": {"hermes": {"base_url": "http://localhost:8000", "enabled": True}}}
        hcfg = HonchoClientConfig(base_url="http://localhost:8000", enabled=True)
        get_client = MagicMock(return_value=MagicMock())

        monkeypatch.setattr("honcho_integration.cli._read_config", lambda: cfg)
        monkeypatch.setattr("honcho_integration.client.HonchoClientConfig.from_global_config", lambda: hcfg)
        monkeypatch.setattr("honcho_integration.client.get_honcho_client", get_client)
        monkeypatch.setitem(__import__("sys").modules, "honcho", MagicMock())

        cmd_status(SimpleNamespace())
        out = capsys.readouterr().out

        assert "Base URL:" in out
        assert "Connection... OK" in out
        get_client.assert_called_once_with(hcfg)
