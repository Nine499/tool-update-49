"""把下载好的文件原子安装到目标目录。"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .config import is_safe_name
from .errors import UpdateError


def install(source: Path, name: str, bin_dir: Path) -> Path:
    """复制到同目录临时文件后原子替换，避免留下写了一半的二进制。"""
    if not is_safe_name(name):
        raise UpdateError(f"安装名不安全: {name!r}")

    destination = bin_dir / name
    staging = destination.with_name(f".{name}.{os.getpid()}.tmp")
    try:
        bin_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, staging)
        staging.chmod(0o755)
        os.replace(staging, destination)
    except OSError as exc:
        raise UpdateError(f"安装到 {destination} 失败: {exc}") from exc
    finally:
        staging.unlink(missing_ok=True)
    return destination
