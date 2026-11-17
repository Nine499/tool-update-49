"""读取并校验 $SECRETS49/tool-update-49.yaml。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

import yaml
from yaml.error import MarkedYAMLError

from .errors import ConfigError, one_line

CONFIG_NAME = "tool-update-49.yaml"
SECRETS_VAR = "SECRETS49"
FIELDS = frozenset({"name", "repo", "url", "files"})
TAR_SUFFIXES = (".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".tar")


@dataclass(frozen=True, slots=True)
class Tool:
    """清单里的一个工具。"""

    name: str
    repo: str
    url: str
    files: dict[str, str]

    @property
    def needs_version(self) -> bool:
        return "{ver}" in self.url

    @property
    def archive_kind(self) -> str | None:
        return archive_kind(filename_from_url(self.url))


def resolve_config_path() -> Path:
    """从 SECRETS49 推出清单路径；缺目录或变量时直接报错。"""
    raw = os.environ.get(SECRETS_VAR)
    if not raw:
        raise ConfigError(f"未设置环境变量 {SECRETS_VAR}")
    secrets = Path(raw).expanduser()
    if not secrets.is_dir():
        raise ConfigError(f"{SECRETS_VAR} 指向的目录不存在: {secrets}")
    return secrets / CONFIG_NAME


def load_tools(path: Path) -> list[Tool]:
    """读取 YAML 并逐项校验，任何歧义都拒绝。"""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"找不到工具清单: {path}") from exc
    except OSError as exc:
        raise ConfigError(f"读取工具清单失败: {path}（{exc}）") from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        detail = _yaml_problem(exc) if isinstance(exc, MarkedYAMLError) else str(exc)
        raise ConfigError(f"YAML 格式错误: {detail}") from exc

    if not isinstance(data, dict):
        raise ConfigError("工具清单顶层必须是映射，且包含 tools 列表")
    unknown = set(data) - {"tools"}
    if unknown:
        raise ConfigError(f"顶层存在未知字段: {_names(unknown)}")
    items = data.get("tools")
    if not isinstance(items, list) or not items:
        raise ConfigError("tools 必须是非空列表")

    tools = [_parse_tool(item, index) for index, item in enumerate(items, start=1)]
    _check_unique(tools)
    return tools


def filename_from_url(url: str) -> str:
    """取 URL 路径最后一段，作为下载文件名。"""
    path = urlsplit(url).path
    return unquote(PurePosixPath(path).name) or "download"


def archive_kind(filename: str) -> str | None:
    """按文件名后缀判断归档类型；不认识的返回 None。"""
    lowered = filename.lower()
    if lowered.endswith(".zip"):
        return "zip"
    if lowered.endswith(TAR_SUFFIXES):
        return "tar"
    return None


def is_safe_name(name: str) -> bool:
    """拒绝空名、路径分隔符和 . / ..，防止写出目标目录。"""
    return (
        bool(name)
        and name not in {".", ".."}
        and "/" not in name
        and "\\" not in name
        and "\0" not in name
    )


def _parse_tool(item: Any, index: int) -> Tool:
    where = f"第 {index} 项"
    if not isinstance(item, dict):
        raise ConfigError(f"{where}必须是映射")

    missing = FIELDS - set(item)
    if missing:
        raise ConfigError(f"{where}缺少字段: {_names(missing)}")
    unknown = set(item) - FIELDS
    if unknown:
        raise ConfigError(f"{where}存在未知字段: {_names(unknown)}")

    name = _text(item["name"], f"{where} name")
    repo = _text(item["repo"], f"{where} repo")
    url = _text(item["url"], f"{where} url")
    where = f"{where}（{name}）"

    if not is_safe_name(name):
        raise ConfigError(f"{where} name 不安全: {name!r}")
    parts = repo.split("/")
    has_blank = any(not part or any(ch.isspace() for ch in part) for part in parts)
    if len(parts) != 2 or has_blank:
        raise ConfigError(f"{where} repo 必须是 owner/repo 形式: {repo!r}")

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError(f"{where} url 必须是 http(s) 地址: {url!r}")
    try:
        url.format(ver="0.0.0")
    except (KeyError, IndexError, ValueError) as exc:
        raise ConfigError(f"{where} url 占位符无效: {exc}") from exc

    files = _files(item["files"], where)
    filename = filename_from_url(url)
    if archive_kind(filename) is None:
        if len(files) != 1:
            raise ConfigError(f"{where} 不是归档下载，files 只能有一个映射")
        key = next(iter(files))
        if key.lower() != filename.lower():
            raise ConfigError(
                f"{where} 的 files 键必须是下载文件名 {filename!r}，实际是 {key!r}"
            )
    return Tool(name=name, repo=repo, url=url, files=files)


def _files(value: Any, where: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise ConfigError(f"{where} files 必须是非空映射")

    files: dict[str, str] = {}
    seen: set[str] = set()
    for raw_key, raw_install in value.items():
        if not isinstance(raw_key, str) or not isinstance(raw_install, str):
            raise ConfigError(f"{where} files 的键和值都必须是字符串")
        key = raw_key.strip()
        install = raw_install.strip()
        if not key or not install:
            raise ConfigError(f"{where} files 的键和值不能为空")
        if key.lower() in seen:
            raise ConfigError(f"{where} files 的键重复（大小写不敏感）: {key!r}")
        seen.add(key.lower())
        if PurePosixPath(key.replace("\\", "/")).name != key:
            raise ConfigError(f"{where} files 的键必须是文件名，不能带路径: {key!r}")
        if not is_safe_name(install):
            raise ConfigError(f"{where} 安装名不安全: {install!r}")
        files[key] = install
    return files


def _check_unique(tools: list[Tool]) -> None:
    names: set[str] = set()
    installs: dict[str, str] = {}
    for tool in tools:
        if tool.name in names:
            raise ConfigError(f"工具名重复: {tool.name!r}")
        names.add(tool.name)
        for install in tool.files.values():
            if install in installs:
                other = installs[install]
                raise ConfigError(f"安装名重复: {install!r}（{other} 和 {tool.name}）")
            installs[install] = tool.name


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{where} 必须是字符串")
    text = value.strip()
    if not text:
        raise ConfigError(f"{where} 不能为空")
    if "\n" in text or "\r" in text:
        raise ConfigError(f"{where} 不能包含换行")
    return text


def _names(values: set[object]) -> str:
    return ", ".join(sorted(map(str, values)))


def _yaml_problem(error: MarkedYAMLError) -> str:
    mark = error.problem_mark or error.context_mark
    message = one_line(error.problem or error.context or "无法解析")
    if mark is None:
        return message
    return f"第 {mark.line + 1} 行第 {mark.column + 1} 列: {message}"
