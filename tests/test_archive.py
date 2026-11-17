from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from tool_update_49.archive import extract
from tool_update_49.config import Tool
from tool_update_49.errors import UpdateError


def make_tool(files: dict[str, str] | None = None) -> Tool:
    return Tool(
        name="tool",
        repo="owner/repo",
        url="https://example.com/tool.tar.gz",
        files=files or {"tool": "tool"},
    )


def test_extract_zip_only_wanted(tmp_path: Path) -> None:
    archive = tmp_path / "tool.zip"
    with zipfile.ZipFile(archive, "w") as source:
        source.writestr("pkg/tool", b"binary")
        source.writestr("pkg/README", b"readme")

    result = extract(archive, make_tool(), tmp_path / "out")

    assert result["tool"].read_bytes() == b"binary"
    assert not (tmp_path / "out" / "README").exists()


def test_extract_tar_only_wanted(tmp_path: Path) -> None:
    archive = tmp_path / "tool.tar.gz"
    payload = b"binary"
    with tarfile.open(archive, "w:gz") as target:
        info = tarfile.TarInfo("pkg/tool")
        info.size = len(payload)
        target.addfile(info, io.BytesIO(payload))
        readme = tarfile.TarInfo("pkg/README")
        readme.size = 6
        target.addfile(readme, io.BytesIO(b"readme"))

    result = extract(archive, make_tool(), tmp_path / "out")

    assert result["tool"].read_bytes() == payload


def test_extract_is_case_insensitive(tmp_path: Path) -> None:
    archive = tmp_path / "tool.zip"
    with zipfile.ZipFile(archive, "w") as source:
        source.writestr("pkg/ToOl", b"binary")

    result = extract(archive, make_tool(), tmp_path / "out")

    assert result["tool"].read_bytes() == b"binary"


def test_extract_missing_member(tmp_path: Path) -> None:
    archive = tmp_path / "tool.zip"
    with zipfile.ZipFile(archive, "w") as source:
        source.writestr("other", b"x")

    with pytest.raises(UpdateError, match="缺少"):
        extract(archive, make_tool(), tmp_path / "out")


def test_extract_bad_archive(tmp_path: Path) -> None:
    archive = tmp_path / "tool.zip"
    archive.write_bytes(b"not a zip")

    with pytest.raises(UpdateError, match="解包失败"):
        extract(archive, make_tool(), tmp_path / "out")


def test_extract_rejects_unsafe_install_name(tmp_path: Path) -> None:
    archive = tmp_path / "tool.zip"
    with zipfile.ZipFile(archive, "w") as source:
        source.writestr("tool", b"binary")

    with pytest.raises(UpdateError, match="不安全"):
        extract(archive, make_tool({"tool": "../tool"}), tmp_path / "out")
