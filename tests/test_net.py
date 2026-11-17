from __future__ import annotations

from pathlib import Path

import pytest

from tool_update_49.net import api_headers, github_token


def test_token_from_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("github-no-403 = 'abc'\n", encoding="utf-8")
    monkeypatch.setenv("SECRETS49", str(tmp_path))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert github_token() == "abc"


def test_token_falls_back_to_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text("github-no-403=\n", encoding="utf-8")
    monkeypatch.setenv("SECRETS49", str(tmp_path))
    monkeypatch.setenv("GITHUB_TOKEN", "from-env")

    assert github_token() == "from-env"


def test_token_absent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SECRETS49", str(tmp_path))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert github_token() is None


def test_api_headers_adds_bearer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text("github-no-403=tok\n", encoding="utf-8")
    monkeypatch.setenv("SECRETS49", str(tmp_path))

    headers = api_headers()

    assert headers["Authorization"] == "Bearer tok"
    assert headers["Accept"] == "application/vnd.github+json"
