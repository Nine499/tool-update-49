"""从 zip / tar 归档中只取出需要的成员。"""

from __future__ import annotations

import shutil
import tarfile
import zipfile
import zlib
from pathlib import Path, PurePosixPath

from .config import Tool, archive_kind, is_safe_name
from .errors import UpdateError, describe_error

COPY_BUFFER = 1 << 17


def extract(archive: Path, tool: Tool, workdir: Path) -> dict[str, Path]:
    """按 tool.files 提取成员，返回 安装名 -> 临时路径。"""
    kind = archive_kind(archive.name)
    if kind is None:
        raise UpdateError(f"无法识别归档格式: {archive.name}")

    for install in tool.files.values():
        if not is_safe_name(install):
            raise UpdateError(f"安装名不安全: {install!r}")

    remaining = {key.lower(): install for key, install in tool.files.items()}
    try:
        workdir.mkdir(parents=True, exist_ok=True)
        if kind == "zip":
            _extract_zip(archive, remaining, workdir)
        else:
            _extract_tar(archive, remaining, workdir)
    except (
        OSError,
        EOFError,
        zipfile.BadZipFile,
        tarfile.TarError,
        zlib.error,
    ) as exc:
        raise UpdateError(f"解包失败: {describe_error(exc)}") from exc

    if remaining:
        raise UpdateError(f"归档中缺少: {', '.join(sorted(remaining))}")
    return {install: workdir / install for install in tool.files.values()}


def _extract_zip(archive: Path, remaining: dict[str, str], workdir: Path) -> None:
    with zipfile.ZipFile(archive) as source:
        for info in source.infolist():
            if info.is_dir():
                continue
            key = _member_name(info.filename)
            install = remaining.get(key)
            if install is None:
                continue
            with source.open(info) as member, (workdir / install).open("wb") as target:
                shutil.copyfileobj(member, target, COPY_BUFFER)
            remaining.pop(key)
            if not remaining:
                return


def _extract_tar(archive: Path, remaining: dict[str, str], workdir: Path) -> None:
    with tarfile.open(archive, "r:*") as source:
        for info in source:
            if not info.isfile():
                continue
            key = _member_name(info.name)
            install = remaining.get(key)
            if install is None:
                continue
            member = source.extractfile(info)
            if member is None:
                continue
            with member, (workdir / install).open("wb") as target:
                shutil.copyfileobj(member, target, COPY_BUFFER)
            remaining.pop(key)
            if not remaining:
                return


def _member_name(name: str) -> str:
    return PurePosixPath(name.replace("\\", "/")).name.lower()
