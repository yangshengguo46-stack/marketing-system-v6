"""Unit tests for scripts/doctor.py.

Run from repo root:
    cd backend && uv run pytest tests/test_doctor.py -v
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import doctor

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_script(path: Path, name: str):
    assert path.exists(), f"{path} must exist"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# check_python
# ---------------------------------------------------------------------------


class TestCheckPython:
    def test_current_python_passes(self):
        result = doctor.check_python()
        assert sys.version_info >= (3, 12)
        assert result.status == "ok"


# ---------------------------------------------------------------------------
# check_pnpm
# ---------------------------------------------------------------------------


class TestCheckPnpm:
    def test_resolves_shared_runner_from_relative_script_path(self, monkeypatch):
        # Load the script as `scripts/doctor.py`, as a user would from the
        # repository root. The derived paths must not depend on that relative
        # invocation path.
        monkeypatch.chdir(REPO_ROOT)
        relative_doctor = _load_script(Path("scripts/doctor.py"), "deerflow_doctor_relative")

        assert relative_doctor.PNPM_SCRIPT_PATH == REPO_ROOT / "scripts" / "pnpm.py"
        assert relative_doctor.PNPM_SCRIPT_PATH.is_absolute()
        assert relative_doctor.FRONTEND_DIR == REPO_ROOT / "frontend"
        assert relative_doctor.FRONTEND_DIR.is_absolute()

    def test_uses_shared_runner_from_frontend(self, monkeypatch):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return doctor.subprocess.CompletedProcess(cmd, 0, stdout="10.26.2\n", stderr="")

        monkeypatch.setattr(doctor.subprocess, "run", fake_run)

        result = doctor.check_pnpm()

        expected_runner = doctor.Path(doctor.__file__).with_name("pnpm.py")
        assert result.status == "ok"
        assert result.detail == "10.26.2"
        assert captured["cmd"] == [sys.executable, str(expected_runner), "-v"]
        assert captured["kwargs"]["cwd"] == expected_runner.parent.parent / "frontend"
        assert captured["kwargs"]["shell"] is False
        assert captured["kwargs"]["check"] is False

    def test_runner_failure_is_reported_as_failure(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            return doctor.subprocess.CompletedProcess(
                cmd,
                42,
                stdout="",
                stderr="Error: pnpm command failed with exit status 42.\n",
            )

        monkeypatch.setattr(doctor.subprocess, "run", fake_run)

        result = doctor.check_pnpm()

        assert result.status == "fail"
        assert "exit status 42" in result.detail
        assert result.fix is not None


# ---------------------------------------------------------------------------
# check_config_exists
# ---------------------------------------------------------------------------


class TestCheckConfigExists:
    def test_missing_config(self, tmp_path):
        result = doctor.check_config_exists(tmp_path / "config.yaml")
        assert result.status == "fail"
        assert result.fix is not None

    def test_present_config(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\n")
        result = doctor.check_config_exists(cfg)
        assert result.status == "ok"


# ---------------------------------------------------------------------------
# check_config_version
# ---------------------------------------------------------------------------


class TestCheckConfigVersion:
    def test_up_to_date(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\n")
        example = tmp_path / "config.example.yaml"
        example.write_text("config_version: 5\n")
        result = doctor.check_config_version(cfg, tmp_path)
        assert result.status == "ok"

    def test_outdated(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 3\n")
        example = tmp_path / "config.example.yaml"
        example.write_text("config_version: 5\n")
        result = doctor.check_config_version(cfg, tmp_path)
        assert result.status == "warn"
        assert result.fix is not None

    def test_missing_config_skipped(self, tmp_path):
        result = doctor.check_config_version(tmp_path / "config.yaml", tmp_path)
        assert result.status == "skip"


# ---------------------------------------------------------------------------
# check_config_loadable
# ---------------------------------------------------------------------------


class TestCheckConfigLoadable:
    def test_loadable_config(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\n")
        monkeypatch.setattr(doctor, "_load_app_config", lambda _path: object())
        result = doctor.check_config_loadable(cfg)
        assert result.status == "ok"

    def test_invalid_config(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\n")

        def fail(_path):
            raise ValueError("bad config")

        monkeypatch.setattr(doctor, "_load_app_config", fail)
        result = doctor.check_config_loadable(cfg)
        assert result.status == "fail"
        assert "bad config" in result.detail


# ---------------------------------------------------------------------------
# check_models_configured
# ---------------------------------------------------------------------------


class TestCheckModelsConfigured:
    def test_no_models(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\nmodels: []\n")
        result = doctor.check_models_configured(cfg)
        assert result.status == "fail"

    def test_one_model(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\nmodels:\n  - name: default\n    use: langchain_openai:ChatOpenAI\n    model: gpt-4o\n    api_key: $OPENAI_API_KEY\n")
        result = doctor.check_models_configured(cfg)
        assert result.status == "ok"

    def test_missing_config_skipped(self, tmp_path):
        result = doctor.check_models_configured(tmp_path / "config.yaml")
        assert result.status == "skip"


# ---------------------------------------------------------------------------
# check_llm_api_key
# ---------------------------------------------------------------------------


class TestCheckLLMApiKey:
    def test_key_set(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\nmodels:\n  - name: default\n    use: langchain_openai:ChatOpenAI\n    model: gpt-4o\n    api_key: $OPENAI_API_KEY\n")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        results = doctor.check_llm_api_key(cfg)
        assert any(r.status == "ok" for r in results)
        assert all(r.status != "fail" for r in results)

    def test_key_missing(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\nmodels:\n  - name: default\n    use: langchain_openai:ChatOpenAI\n    model: gpt-4o\n    api_key: $OPENAI_API_KEY\n")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        results = doctor.check_llm_api_key(cfg)
        assert any(r.status == "fail" for r in results)
        failed = [r for r in results if r.status == "fail"]
        assert all(r.fix is not None for r in failed)
        assert any("OPENAI_API_KEY" in (r.fix or "") for r in failed)

    def test_missing_config_returns_empty(self, tmp_path):
        results = doctor.check_llm_api_key(tmp_path / "config.yaml")
        assert results == []


# ---------------------------------------------------------------------------
# check_llm_auth
# ---------------------------------------------------------------------------


class TestCheckLLMAuth:
    def test_codex_auth_file_missing_fails(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\nmodels:\n  - name: codex\n    use: deerflow.models.openai_codex_provider:CodexChatModel\n    model: gpt-5.4\n")
        monkeypatch.setenv("CODEX_AUTH_PATH", str(tmp_path / "missing-auth.json"))
        results = doctor.check_llm_auth(cfg)
        assert any(result.status == "fail" and "Codex CLI auth available" in result.label for result in results)

    def test_claude_oauth_env_passes(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\nmodels:\n  - name: claude\n    use: deerflow.models.claude_provider:ClaudeChatModel\n    model: claude-sonnet-4-6\n")
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token")
        results = doctor.check_llm_auth(cfg)
        assert any(result.status == "ok" and "Claude auth available" in result.label for result in results)


# ---------------------------------------------------------------------------
# check_douyin_openapi
# ---------------------------------------------------------------------------


class TestCheckDouyinOpenAPI:
    @staticmethod
    def _write_extensions_config(
        tmp_path: Path,
        *,
        enabled: bool = True,
        scope: str = "aweme.dy.video_search",
        public_root: Path | None = None,
    ) -> None:
        (tmp_path / "backend/.venv/bin").mkdir(parents=True, exist_ok=True)
        (tmp_path / "backend/.venv/bin/deerflow-capability-mcp").touch()
        servers = {
            "deerflow_capabilities": {
                "enabled": enabled,
                "type": "stdio",
                "command": "deerflow-capability-mcp",
                "env": {
                    "DOUYIN_CLIENT_KEY": "$DOUYIN_CLIENT_KEY",
                    "DOUYIN_CLIENT_SECRET": "$DOUYIN_CLIENT_SECRET",
                    "DOUYIN_APPROVED_SCOPES": scope,
                    "DOUYIN_PUBLIC_EVIDENCE_ROOT": (str(public_root) if public_root is not None else ""),
                    "DOUYIN_PUBLIC_EVIDENCE_UV": "uv",
                },
            }
        }
        (tmp_path / "extensions_config.json").write_text(
            json.dumps({"mcpServers": servers}),
            encoding="utf-8",
        )

    def test_public_evidence_provider_can_be_ready_without_official_credentials(
        self,
        tmp_path,
        monkeypatch,
    ):
        provider_root = tmp_path / "provider"
        provider_root.mkdir()
        (provider_root / "readonly_server.py").touch()
        self._write_extensions_config(tmp_path, public_root=provider_root)
        monkeypatch.delenv("DOUYIN_CLIENT_KEY", raising=False)
        monkeypatch.delenv("DOUYIN_CLIENT_SECRET", raising=False)
        monkeypatch.setattr(doctor.shutil, "which", lambda command: f"/usr/local/bin/{command}")

        results = doctor.check_douyin_openapi(tmp_path)

        gateway = next(result for result in results if result.label == "DeerFlow capability gateway")
        public = next(result for result in results if result.label == "Douyin public-evidence provider")
        official = next(result for result in results if result.label == "Douyin official API provider")
        assert gateway.status == "ok"
        assert public.status == "ok"
        assert official.status == "skip"
        rendered = "\n".join(f"{result.label} {result.detail} {result.fix}" for result in results)
        assert "client-secret-value" not in rendered

    def test_current_v1_scope_and_credentials_are_ready(self, tmp_path, monkeypatch):
        self._write_extensions_config(tmp_path)
        monkeypatch.setenv("DOUYIN_CLIENT_KEY", "client-key-value")
        monkeypatch.setenv("DOUYIN_CLIENT_SECRET", "client-secret-value")
        monkeypatch.setattr(doctor.shutil, "which", lambda command: f"/usr/local/bin/{command}")

        results = doctor.check_douyin_openapi(tmp_path)

        assert not any(result.status == "fail" for result in results)
        official = next(result for result in results if result.label == "Douyin official API provider")
        assert official.status == "ok"
        scope = next(result for result in results if result.label == "Douyin video-search contract")
        assert "v1" in scope.detail
        rendered = "\n".join(f"{result.label} {result.detail} {result.fix}" for result in results)
        assert "client-key-value" not in rendered
        assert "client-secret-value" not in rendered

    def test_previously_approved_v2_scope_remains_supported(self, tmp_path, monkeypatch):
        self._write_extensions_config(tmp_path, scope="aweme.dy.video_search_v2")
        monkeypatch.setenv("DOUYIN_CLIENT_KEY", "client-key-value")
        monkeypatch.setenv("DOUYIN_CLIENT_SECRET", "client-secret-value")
        monkeypatch.setattr(doctor.shutil, "which", lambda command: f"/usr/local/bin/{command}")

        results = doctor.check_douyin_openapi(tmp_path)

        scope = next(result for result in results if result.label == "Douyin video-search contract")
        assert scope.status == "ok"
        assert "v2" in scope.detail

    def test_disabled_gateway_is_skipped(self, tmp_path):
        self._write_extensions_config(tmp_path, enabled=False)

        results = doctor.check_douyin_openapi(tmp_path)

        assert len(results) == 1
        assert results[0].label == "DeerFlow capability gateway"
        assert results[0].status == "skip"
        assert results[0].detail == "disabled"

    def test_legacy_parallel_douyin_servers_require_migration(self, tmp_path):
        (tmp_path / "extensions_config.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "douyin_openapi": {"enabled": True},
                        "douyin_official_mcp": {"enabled": False},
                    }
                }
            ),
            encoding="utf-8",
        )

        results = doctor.check_douyin_openapi(tmp_path)

        assert len(results) == 1
        assert results[0].label == "DeerFlow capability gateway"
        assert results[0].status == "fail"
        assert results[0].detail == "legacy parallel Douyin MCP entries detected"
        assert "deerflow_capabilities" in (results[0].fix or "")


# ---------------------------------------------------------------------------
# check_web_search
# ---------------------------------------------------------------------------


class TestCheckWebSearch:
    def test_ddg_always_ok(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            "config_version: 5\nmodels:\n  - name: default\n    use: langchain_openai:ChatOpenAI\n    model: gpt-4o\n    api_key: $OPENAI_API_KEY\ntools:\n  - name: web_search\n    use: deerflow.community.ddg_search.tools:web_search_tool\n"
        )
        result = doctor.check_web_search(cfg)
        assert result.status == "ok"
        assert "DuckDuckGo" in result.detail

    def test_tavily_with_key_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.tavily.tools:web_search_tool\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "ok"

    def test_tavily_without_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.tavily.tools:web_search_tool\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "warn"
        assert result.fix is not None
        assert "make setup" in result.fix

    def test_brave_with_key_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "bsa-test")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.brave.tools:web_search_tool\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "ok"

    def test_brave_without_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.brave.tools:web_search_tool\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "warn"
        assert result.fix is not None
        assert "BRAVE_SEARCH_API_KEY" in result.fix

    def test_brave_with_inline_api_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text('config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.brave.tools:web_search_tool\n    api_key: "inline-key"\n')
        result = doctor.check_web_search(cfg)
        assert result.status == "warn"
        assert "literal api_key set in config" in result.detail
        assert "BRAVE_SEARCH_API_KEY" in (result.fix or "")

    def test_brave_with_api_key_env_ref_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "bsa-test")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.brave.tools:web_search_tool\n    api_key: $BRAVE_SEARCH_API_KEY\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "ok"
        assert "BRAVE_SEARCH_API_KEY set from config" in result.detail

    def test_serper_with_key_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "test-key")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.serper.tools:web_search_tool\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "ok"
        assert "serper" in result.detail

    def test_serper_without_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.serper.tools:web_search_tool\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "warn"
        assert "SERPER_API_KEY" in (result.fix or "")

    def test_serper_inline_api_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.serper.tools:web_search_tool\n    api_key: inline-key\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "warn"
        assert "literal api_key set in config" in result.detail
        assert "SERPER_API_KEY" in (result.fix or "")

    def test_serper_config_env_ref_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "test-key")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.serper.tools:web_search_tool\n    api_key: $SERPER_API_KEY\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "ok"
        assert "SERPER_API_KEY set from config" in result.detail

    def test_serper_unresolved_env_ref_falls_back_to_default_var(self, tmp_path, monkeypatch):
        # The referenced $VAR is unset, but the default SERPER_API_KEY is set,
        # which the tool uses as a runtime fallback; report ok rather than warn.
        monkeypatch.delenv("MY_CUSTOM_SERPER_KEY", raising=False)
        monkeypatch.setenv("SERPER_API_KEY", "test-key")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.serper.tools:web_search_tool\n    api_key: $MY_CUSTOM_SERPER_KEY\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "ok"
        assert "SERPER_API_KEY set" in result.detail

    def test_serper_unresolved_env_ref_without_default_warns(self, tmp_path, monkeypatch):
        # Neither the referenced $VAR nor the default SERPER_API_KEY is set.
        monkeypatch.delenv("MY_CUSTOM_SERPER_KEY", raising=False)
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.serper.tools:web_search_tool\n    api_key: $MY_CUSTOM_SERPER_KEY\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "warn"
        assert "SERPER_API_KEY" in (result.fix or "")

    def test_no_search_tool_warns(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools: []\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "warn"
        assert result.fix is not None
        assert "make setup" in result.fix

    def test_missing_config_skipped(self, tmp_path):
        result = doctor.check_web_search(tmp_path / "config.yaml")
        assert result.status == "skip"

    def test_invalid_provider_use_fails(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_search\n    use: deerflow.community.not_real.tools:web_search_tool\n")
        result = doctor.check_web_search(cfg)
        assert result.status == "fail"


# ---------------------------------------------------------------------------
# check_web_fetch
# ---------------------------------------------------------------------------


class TestCheckWebFetch:
    def test_jina_always_ok(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_fetch\n    use: deerflow.community.jina_ai.tools:web_fetch_tool\n")
        result = doctor.check_web_fetch(cfg)
        assert result.status == "ok"
        assert "Jina AI" in result.detail

    def test_firecrawl_without_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_fetch\n    use: deerflow.community.firecrawl.tools:web_fetch_tool\n")
        result = doctor.check_web_fetch(cfg)
        assert result.status == "warn"
        assert "FIRECRAWL_API_KEY" in (result.fix or "")

    def test_no_fetch_tool_warns(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools: []\n")
        result = doctor.check_web_fetch(cfg)
        assert result.status == "warn"
        assert result.fix is not None

    def test_invalid_provider_use_fails(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_fetch\n    use: deerflow.community.not_real.tools:web_fetch_tool\n")
        result = doctor.check_web_fetch(cfg)
        assert result.status == "fail"


# ---------------------------------------------------------------------------
# check_web_capture
# ---------------------------------------------------------------------------


class TestCheckWebCapture:
    def test_browserless_self_host_without_token_ok(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BROWSERLESS_TOKEN", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_capture\n    use: deerflow.community.browserless.tools:web_capture_tool\n    base_url: http://localhost:3032\n")

        result = doctor.check_web_capture(cfg)

        assert result.status == "ok"
        assert "self-hosted" in result.detail

    def test_browserless_token_env_ref_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BROWSERLESS_TOKEN", "browserless-test")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_capture\n    use: deerflow.community.browserless.tools:web_capture_tool\n    base_url: https://production-sfo.browserless.io\n    token: $BROWSERLESS_TOKEN\n")

        result = doctor.check_web_capture(cfg)

        assert result.status == "ok"
        assert "BROWSERLESS_TOKEN set from config" in result.detail

    def test_browserless_cloud_without_token_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BROWSERLESS_TOKEN", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: web_capture\n    use: deerflow.community.browserless.tools:web_capture_tool\n    base_url: https://production-sfo.browserless.io\n")

        result = doctor.check_web_capture(cfg)

        assert result.status == "warn"
        assert "BROWSERLESS_TOKEN" in (result.fix or "")


# ---------------------------------------------------------------------------
# check_image_search
# ---------------------------------------------------------------------------


class TestCheckImageSearch:
    def test_ddg_always_ok(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.image_search.tools:image_search_tool\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "ok"
        assert "DuckDuckGo" in result.detail

    def test_serper_with_key_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "test-key")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.serper.tools:image_search_tool\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "ok"
        assert "serper" in result.detail

    def test_serper_without_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.serper.tools:image_search_tool\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "warn"
        assert "SERPER_API_KEY" in (result.fix or "")

    def test_serper_inline_api_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.serper.tools:image_search_tool\n    api_key: inline-key\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "warn"
        assert "literal api_key set in config" in result.detail
        assert "SERPER_API_KEY" in (result.fix or "")

    def test_serper_config_env_ref_without_env_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.serper.tools:image_search_tool\n    api_key: $SERPER_API_KEY\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "warn"
        assert "SERPER_API_KEY" in (result.fix or "")

    def test_brave_image_search_with_key_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "bsa-test")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.brave.tools:image_search_tool\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "ok"
        assert "brave" in result.detail

    def test_brave_image_search_without_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.brave.tools:image_search_tool\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "warn"
        assert "BRAVE_SEARCH_API_KEY" in (result.fix or "")

    def test_brave_image_search_inline_api_key_warns(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.brave.tools:image_search_tool\n    api_key: inline-key\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "warn"
        assert "literal api_key set in config" in result.detail
        assert "BRAVE_SEARCH_API_KEY" in (result.fix or "")

    def test_infoquest_with_key_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INFOQUEST_API_KEY", "test-key")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.infoquest.tools:image_search_tool\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "ok"
        assert "infoquest" in result.detail

    def test_no_image_search_tool_warns(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools: []\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "warn"
        assert result.fix is not None

    def test_invalid_provider_use_fails(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\ntools:\n  - name: image_search\n    use: deerflow.community.not_real.tools:image_search_tool\n")
        result = doctor.check_image_search(cfg)
        assert result.status == "fail"


# ---------------------------------------------------------------------------
# check_env_file
# ---------------------------------------------------------------------------


class TestCheckEnvFile:
    def test_missing(self, tmp_path):
        result = doctor.check_env_file(tmp_path)
        assert result.status == "warn"

    def test_present(self, tmp_path):
        (tmp_path / ".env").write_text("KEY=val\n")
        result = doctor.check_env_file(tmp_path)
        assert result.status == "ok"


# ---------------------------------------------------------------------------
# check_frontend_env
# ---------------------------------------------------------------------------


class TestCheckFrontendEnv:
    def test_missing(self, tmp_path):
        result = doctor.check_frontend_env(tmp_path)
        assert result.status == "warn"

    def test_present(self, tmp_path):
        frontend_dir = tmp_path / "frontend"
        frontend_dir.mkdir()
        (frontend_dir / ".env").write_text("KEY=val\n")
        result = doctor.check_frontend_env(tmp_path)
        assert result.status == "ok"


# ---------------------------------------------------------------------------
# check_sandbox
# ---------------------------------------------------------------------------


class TestCheckSandbox:
    def test_missing_sandbox_fails(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\n")
        results = doctor.check_sandbox(cfg)
        assert results[0].status == "fail"

    def test_local_sandbox_with_disabled_host_bash_warns(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\nsandbox:\n  use: deerflow.sandbox.local:LocalSandboxProvider\n  allow_host_bash: false\ntools:\n  - name: bash\n    use: deerflow.sandbox.tools:bash_tool\n")
        results = doctor.check_sandbox(cfg)
        assert any(result.status == "warn" for result in results)

    def test_container_sandbox_without_runtime_warns(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\nsandbox:\n  use: deerflow.community.aio_sandbox:AioSandboxProvider\ntools: []\n")
        monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)
        results = doctor.check_sandbox(cfg)
        assert any(result.label == "container runtime available" and result.status == "warn" for result in results)


# ---------------------------------------------------------------------------
# main() exit code
# ---------------------------------------------------------------------------


class TestMainExitCode:
    def test_returns_int(self, tmp_path, monkeypatch, capsys):
        """main() should return 0 or 1 without raising."""
        repo_root = tmp_path / "repo"
        scripts_dir = repo_root / "scripts"
        scripts_dir.mkdir(parents=True)
        fake_doctor = scripts_dir / "doctor.py"
        fake_doctor.write_text("# test-only shim for __file__ resolution\n")

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(doctor, "__file__", str(fake_doctor))
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)

        exit_code = doctor.main()

        captured = capsys.readouterr()
        output = captured.out + captured.err

        assert exit_code in (0, 1)
        assert output
        assert "config.yaml" in output
        assert ".env" in output
