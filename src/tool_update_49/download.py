"""下载文件，支持 Range 分段并发。"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO, NoReturn

import httpx

from .errors import RetryableError, UpdateError, describe_error
from .net import MAX_ATTEMPTS, RETRYABLE_STATUS, wait_before_retry

if TYPE_CHECKING:
    from .config import Tool
    from .ui import Reporter

SEGMENTS = 5
MIN_SEGMENT_SIZE = 1 << 20
MIN_SEGMENTED_SIZE = 2 * MIN_SEGMENT_SIZE
CHUNK_SIZE = 1 << 17


@dataclass(frozen=True, slots=True)
class Segment:
    """文件的一段字节闭区间。"""

    start: int
    end: int


class SegmentFile:
    """按偏移并发写入固定长度的文件。"""

    def __init__(self, path: Path, size: int) -> None:
        self._path = path
        self._size = size
        self._fd = -1

    def __enter__(self) -> SegmentFile:
        self._fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        os.ftruncate(self._fd, self._size)
        return self

    def __exit__(self, *exc_info: object) -> None:
        os.close(self._fd)

    def write(self, offset: int, data: bytes) -> None:
        view = memoryview(data)
        while view:
            written = os.pwrite(self._fd, view, offset)
            offset += written
            view = view[written:]


def plan_segments(total: int) -> list[Segment]:
    """把 total 字节切成最多 SEGMENTS 段，覆盖完整且不重叠。"""
    if total <= 0:
        raise ValueError("total 必须大于 0")

    count = max(1, min(SEGMENTS, total // MIN_SEGMENT_SIZE))
    base, remainder = divmod(total, count)
    segments: list[Segment] = []
    start = 0
    for index in range(count):
        size = base + (1 if index < remainder else 0)
        segments.append(Segment(start, start + size - 1))
        start += size
    return segments


async def download(
    client: httpx.AsyncClient,
    url: str,
    target: Path,
    tool: Tool,
    reporter: Reporter,
) -> None:
    """下载 url 到 target；支持 Range 时并发分段。"""
    for attempt in range(MAX_ATTEMPTS):
        try:
            await _download_once(client, url, target, tool, reporter)
            return
        except (httpx.TransportError, RetryableError) as exc:
            if attempt == MAX_ATTEMPTS - 1:
                raise UpdateError(f"下载失败: {describe_error(exc)}") from exc
            await wait_before_retry(attempt, exc, reporter, f"{tool.name} ")


async def _download_once(
    client: httpx.AsyncClient,
    url: str,
    target: Path,
    tool: Tool,
    reporter: Reporter,
) -> None:
    # 用 1 字节的 Range 探测：206 表示支持分段，200 表示响应体就是整个文件。
    probe_headers = {"Range": "bytes=0-0", "Accept-Encoding": "identity"}
    async with client.stream("GET", url, headers=probe_headers) as response:
        if response.status_code == 200:
            total = content_length(response.headers)
            reporter.begin_download(tool, total)
            with target.open("wb") as file:
                received = await _consume(response, file, tool, reporter)
            if total is not None and received != total:
                raise RetryableError(f"响应被截断（{received}/{total} 字节）")
            return
        if response.status_code != 206:
            raise_download_status(response)
        total = content_range_total(response.headers.get("content-range"))

    if total is None or total < MIN_SEGMENTED_SIZE:
        await _stream_to_file(client, url, target, tool, reporter)
        return
    await _segmented_download(client, url, target, total, tool, reporter)


async def _stream_to_file(
    client: httpx.AsyncClient,
    url: str,
    target: Path,
    tool: Tool,
    reporter: Reporter,
) -> None:
    headers = {"Accept-Encoding": "identity"}
    async with client.stream("GET", url, headers=headers) as response:
        if response.status_code != 200:
            raise_download_status(response)
        total = content_length(response.headers)
        reporter.begin_download(tool, total)
        with target.open("wb") as file:
            received = await _consume(response, file, tool, reporter)
        if total is not None and received != total:
            raise RetryableError(f"响应被截断（{received}/{total} 字节）")


async def _segmented_download(
    client: httpx.AsyncClient,
    url: str,
    target: Path,
    total: int,
    tool: Tool,
    reporter: Reporter,
) -> None:
    reporter.begin_download(tool, total)
    with SegmentFile(target, total) as writer:
        await gather_all(
            _fetch_segment(client, url, writer, segment, tool, reporter)
            for segment in plan_segments(total)
        )


async def _fetch_segment(
    client: httpx.AsyncClient,
    url: str,
    writer: SegmentFile,
    segment: Segment,
    tool: Tool,
    reporter: Reporter,
) -> None:
    headers = {
        "Range": f"bytes={segment.start}-{segment.end}",
        "Accept-Encoding": "identity",
    }
    async with client.stream("GET", url, headers=headers) as response:
        if response.status_code == 200:
            raise RetryableError("服务器忽略了 Range 请求")
        if response.status_code != 206:
            raise_download_status(response)

        position = segment.start
        async for chunk in response.aiter_raw(CHUNK_SIZE):
            remaining = segment.end + 1 - position
            if len(chunk) > remaining:
                raise RetryableError("分段响应超出请求范围")
            writer.write(position, chunk)
            position += len(chunk)
            reporter.advance(tool, len(chunk))

    if position != segment.end + 1:
        raise RetryableError(f"分段 {segment.start}-{segment.end} 响应被截断")


async def _consume(
    response: httpx.Response,
    file: BinaryIO,
    tool: Tool,
    reporter: Reporter,
) -> int:
    received = 0
    async for chunk in response.aiter_raw(CHUNK_SIZE):
        file.write(chunk)
        received += len(chunk)
        reporter.advance(tool, len(chunk))
    return received


async def gather_all(coroutines: Iterable[Coroutine[Any, Any, None]]) -> None:
    """并发执行；任一任务失败时取消其余任务。"""
    tasks = [asyncio.create_task(coroutine) for coroutine in coroutines]
    try:
        await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


def raise_download_status(response: httpx.Response) -> NoReturn:
    status = response.status_code
    if status in RETRYABLE_STATUS:
        raise RetryableError(f"HTTP {status}")
    if status == 206:
        raise RetryableError("服务器返回了意外的分段响应")
    if status == 404:
        raise UpdateError(f"下载地址不存在（HTTP 404）: {response.url}")
    if status == 403:
        raise UpdateError(f"下载被拒绝（HTTP 403）: {response.url}")
    raise UpdateError(f"下载失败 HTTP {status}: {response.url}")


def content_length(headers: httpx.Headers) -> int | None:
    value = headers.get("content-length")
    return int(value) if value and value.isdigit() else None


def content_range_total(value: str | None) -> int | None:
    if not value:
        return None
    _, _, total = value.rpartition("/")
    return int(total) if total.isdigit() else None
