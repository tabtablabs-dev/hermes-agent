"""Tests for Honcho CLI helpers."""

from honcho_integration.cli import _is_configured, _resolve_api_key, _resolve_base_url


class TestResolveApiKey:
    def test_prefers_host_scoped_key(self):
        cfg = {
            "apiKey": "root-key",
            "hosts": {
                "hermes": {
                    "apiKey": "host-key",
                }
            },
        }
        assert _resolve_api_key(cfg) == "host-key"

    def test_falls_back_to_root_key(self):
        cfg = {
            "apiKey": "root-key",
            "hosts": {"hermes": {}},
        }
        assert _resolve_api_key(cfg) == "root-key"

    def test_falls_back_to_env_key(self, monkeypatch):
        monkeypatch.setenv("HONCHO_API_KEY", "env-key")
        assert _resolve_api_key({}) == "env-key"
        monkeypatch.delenv("HONCHO_API_KEY", raising=False)


class TestResolveBaseUrl:
    def test_prefers_host_scoped_base_url(self, monkeypatch):
        monkeypatch.setenv("HONCHO_BASE_URL", "http://env:9002")
        cfg = {
            "baseUrl": "http://root:9000",
            "hosts": {"hermes": {"baseUrl": "http://host:9001"}},
        }
        assert _resolve_base_url(cfg) == "http://host:9001"

    def test_supports_aliases(self, monkeypatch):
        monkeypatch.delenv("HONCHO_BASE_URL", raising=False)
        cfg = {
            "baseURL": "http://root:9000",
            "hosts": {"hermes": {"base_url": "http://host:9001"}},
        }
        assert _resolve_base_url(cfg) == "http://host:9001"


class TestIsConfigured:
    def test_true_when_base_url_only(self):
        cfg = {"hosts": {"hermes": {"baseUrl": "https://example.test"}}}
        assert _is_configured(cfg) is True

    def test_false_when_no_key_or_base_url(self):
        assert _is_configured({"hosts": {"hermes": {}}}) is False


class TestCmdIdentity:
    def test_allows_base_url_only_config(self, monkeypatch, capsys):
        import honcho_integration.cli as honcho_cli
        import honcho_integration.client as client_mod
        import honcho_integration.session as session_mod

        monkeypatch.setattr(
            honcho_cli,
            "_read_config",
            lambda: {"hosts": {"hermes": {"baseUrl": "https://example.test"}}},
        )

        class FakeConfig:
            peer_name = "genos"
            ai_peer = "hermes"

            def resolve_session_name(self):
                return "hermes"

        class FakeHonchoClientConfig:
            @classmethod
            def from_global_config(cls):
                return FakeConfig()

        class FakeSessionManager:
            def __init__(self, honcho, config):
                self.honcho = honcho
                self.config = config

            def get_or_create(self, key):
                return object()

        monkeypatch.setattr(client_mod, "HonchoClientConfig", FakeHonchoClientConfig)
        monkeypatch.setattr(client_mod, "get_honcho_client", lambda cfg: object())
        monkeypatch.setattr(session_mod, "HonchoSessionManager", FakeSessionManager)

        args = type("Args", (), {"file": None, "show": False})()
        honcho_cli.cmd_identity(args)

        out = capsys.readouterr().out
        assert "Honcho identity management" in out
        assert "No API key configured" not in out

