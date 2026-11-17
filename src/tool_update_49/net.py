"""GitHub API、token 读取和通用 HTTP 重试。"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from . import __version__
from .errors import UpdateError, describe_error

if TYPE_CHECKING:
    from .ui import Reporter

MAX_ATTEMPTS = 3
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
TOKEN_KEY = "github-no-403"
TOKEN_ENV = "GITHUB_TOKEN"
API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def github_token() -> str | None:
    """优先读 $SECRETS49/.env 的 github-no-403，退回 GITHUB_TOKEN。"""
    secrets = os.environ.get("SECRETS49")
    if secrets:
        env_file = Path(secrets).expanduser() / ".env"
        try:
            lines = env_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            key, sep, value = stripped.partition("=")
            if sep and key.strip() == TOKEN_KEY:
                token = value.strip().strip("'\"")
                if token:
                    return token
    return os.environ.get(TOKEN_ENV) or None


def api_headers() -> dict[str, str]:
    """只给 api.github.com 的请求带 token。"""
    headers = dict(API_HEADERS)
    if token := github_token():
        headers["Authorization"] = f"Bearer {token}"
    return headers


def make_client(max_connections: int) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        http2=True,
        headers={"User-Agent": f"tool-update-49/{__version__}"},
        timeout=TIMEOUT,
        follow_redirects=True,
        limits=httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_connections,
        ),
    )


async def fetch(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    reporter: Reporter | None = None,
    label: str = "",
) -> httpx.Response:
    """GET 小响应；网络错误和可重试状态码按指数退避重试。"""
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = await client.get(url, headers=headers)
        except httpx.TransportError as exc:
            if attempt == MAX_ATTEMPTS - 1:
                raise UpdateError(f"{label}请求失败: {describe_error(exc)}") from exc
            await wait_before_retry(attempt, exc, reporter, label)
            continue

        if response.status_code in RETRYABLE_STATUS and attempt < MAX_ATTEMPTS - 1:
            status = response.status_code
            retry_after = response.headers.get("retry-after")
            await response.aclose()
            await wait_before_retry(
                attempt, f"HTTP {status}", reporter, label, retry_after
            )
            continue
        return response

    raise AssertionError("unreachable")


async def wait_before_retry(
    attempt: int,
    reason: object,
    reporter: Reporter | None,
    label: str,
    retry_after: str | None = None,
) -> None:
    wait = 2**attempt
    if retry_after and retry_after.isdigit():
        wait = min(int(retry_after), 30)
    if reporter is not None:
        reporter.log(f"{label}{describe_error(reason)}，{wait}s 后重试", "warn")
    await asyncio.sleep(wait)


async def latest_version(
    client: httpx.AsyncClient,
    repo: str,
    reporter: Reporter | None = None,
) -> str:
    """查询 latest release，返回去掉 v 前缀的版本号。"""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    response = await fetch(
        client,
        url,
        headers=api_headers(),
        reporter=reporter,
        label=f"{repo} ",
    )
    _raise_api_error(response, repo)

    try:
        tag = response.json()["tag_name"]
    except (KeyError, TypeError, ValueError) as exc:
        raise UpdateError(f"{repo}: release 响应缺少 tag_name") from exc
    if not isinstance(tag, str) or not tag.strip():
        raise UpdateError(f"{repo}: tag_name 无效: {tag!r}")

    version = tag.strip().removeprefix("v")
    if not version:
        raise UpdateError(f"{repo}: tag_name 无效: {tag!r}")
    return version


def _raise_api_error(response: httpx.Response, repo: str) -> None:
    if response.is_success:
        return

    status = response.status_code
    if status == 401:
        raise UpdateError(f"{repo}: GitHub token 无效或已过期")
    if status == 403 and response.headers.get("x-ratelimit-remaining") == "0":
        reset = _reset_time(response.headers.get("x-ratelimit-reset"))
        raise UpdateError(f"{repo}: GitHub API 已限流，{reset} 后恢复")
    if status == 403:
        raise UpdateError(f"{repo}: GitHub API 拒绝访问（403），请检查 token 权限")
    if status == 404:
        raise UpdateError(f"{repo}: 找不到仓库或 latest release")
    raise UpdateError(f"{repo}: GitHub API 返回 HTTP {status}")


def _reset_time(value: str | None) -> str:
    if not value or not value.isdigit():
        return "稍后"
    try:
        moment = datetime.fromtimestamp(int(value)).astimezone()
    except (OverflowError, OSError, ValueError):
        return "稍后"
    return moment.strftime("%m-%d %H:%M")
