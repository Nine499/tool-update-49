from __future__ import annotations

from pathlib import Path

import pytest

from tool_update_49.config import (
    archive_kind,
    filename_from_url,
    is_safe_name,
    load_tools,
    resolve_config_path,
)
from tool_update_49.errors import ConfigError

VALID = """
tools:
  - name: qdns
    repo: natesales/q
    url: https://example.com/v{ver}/q.tar.gz
    files:
      q: qdns
"""


def write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "tool-update-49.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_load_valid_config(tmp_path: Path) -> None:
    tools = load_tools(write_config(tmp_path, VALID))
    assert len(tools) == 1
    tool = tools[0]
    assert tool.name == "qdns"
    assert tool.repo == "natesales/q"
    assert tool.files == {"q": "qdns"}
    assert tool.needs_version
    assert tool.archive_kind == "tar"


def test_bare_download(tmp_path: Path) -> None:
    body = """
tools:
  - name: yq
    repo: mikefarah/yq
    url: https://example.com/yq_linux_amd64
    files:
      yq_linux_amd64: yq
"""
    tool = load_tools(write_config(tmp_path, body))[0]
    assert not tool.needs_version
    assert tool.archive_kind is None


def test_archive_kind_and_filename() -> None:
    assert archive_kind("tool.zip") == "zip"
    assert archive_kind("tool.tar.gz") == "tar"
    assert archive_kind("tool.tgz") == "tar"
    assert archive_kind("tool") is None
    assert filename_from_url("https://example.com/a/b/tool.tar.gz?x=1") == "tool.tar.gz"


def test_is_safe_name() -> None:
    assert is_safe_name("tool")
    assert not is_safe_name("../tool")
    assert not is_safe_name("a/b")
    assert not is_safe_name("")
    assert not is_safe_name("..")


def test_resolve_config_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SECRETS49", str(tmp_path))
    assert resolve_config_path() == tmp_path / "tool-update-49.yaml"


def test_resolve_config_path_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRETS49", raising=False)
    with pytest.raises(ConfigError, match="SECRETS49"):
        resolve_config_path()


def test_resolve_config_path_requires_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SECRETS49", str(tmp_path / "missing"))
    with pytest.raises(ConfigError, match="不存在"):
        resolve_config_path()


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="找不到"):
        load_tools(tmp_path / "missing.yaml")


def test_yaml_syntax_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="YAML"):
        load_tools(write_config(tmp_path, "tools: [\n"))


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("", "顶层"),
        ("tools: []\n", "非空"),
        ("tools: {}\n", "非空"),
        ("tools:\n  - name: x\n", "缺少字段"),
        (
            """
tools:
  - name: x
    repo: a/b
    url: https://example.com/x
    files:
      x: x
    archive: true
""",
            "未知字段",
        ),
        (
            """
tools:
  - name: x
    repo: a/b
    url: https://example.com/x
    files:
      x: x
  - name: y
    repo: a/b
    url: https://example.com/y
    files:
      y: x
""",
            "安装名重复",
        ),
        (
            """
tools:
  - name: x
    repo: a/b
    url: https://example.com/x
    files:
      x: ../x
""",
            "不安全",
        ),
        (
            """
tools:
  - name: x
    repo: a/b
    url: https://example.com/x
    files:
      x: x
      y: y
""",
            "只能有一个映射",
        ),
        (
            """
tools:
  - name: x
    repo: a/b
    url: https://example.com/x
    files:
      wrong: x
""",
            "下载文件名",
        ),
        (
            """
tools:
  - name: ../x
    repo: a/b
    url: https://example.com/x
    files:
      x: x
""",
            "name 不安全",
        ),
    ],
)
def test_rejects_invalid_config(tmp_path: Path, body: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        load_tools(write_config(tmp_path, body))
