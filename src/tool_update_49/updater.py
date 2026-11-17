"""串起查询、下载、解包、安装的完整流程。"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import httpx

from .archive import extract
from .config import Tool, filename_from_url
from .download import SEGMENTS, download
from .errors import UpdateError
from .install import install
from .net import latest_version, make_client
from .ui import Reporter

CONCURRENCY = 3


async def update_tool(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    tool: Tool,
    bin_dir: Path,
    reporter: Reporter,
) -> bool:
    async with semaphore:
        reporter.start_tool(tool)
        try:
            version = "latest"
            if tool.needs_version:
                reporter.set_phase(tool, "查询版本")
                version = await latest_version(client, tool.repo, reporter)
            reporter.set_version(tool, version)

            url = tool.url.format(ver=version)
            with tempfile.TemporaryDirectory(
                prefix=f"tool-update-49-{tool.name}-"
            ) as tmp:
                workdir = Path(tmp)
                download_path = workdir / filename_from_url(url)
                reporter.set_phase(tool, "下载")
                await download(client, url, download_path, tool, reporter)

                if tool.archive_kind is None:
                    reporter.set_phase(tool, "安装")
                    sources = {next(iter(tool.files.values())): download_path}
                else:
                    reporter.set_phase(tool, "解包")
                    sources = extract(download_path, tool, workdir / "payload")
                    reporter.set_phase(tool, "安装")

                installed = [
                    install(source, name, bin_dir) for name, source in sources.items()
                ]

            reporter.finish_tool(tool, installed)
            return True
        except UpdateError as exc:
            reporter.fail_tool(tool, str(exc))
            return False
        except (httpx.HTTPError, OSError) as exc:
            reporter.fail_tool(tool, f"{type(exc).__name__}: {exc}")
            return False


async def run_updates(
    tools: list[Tool],
    bin_dir: Path,
    reporter: Reporter,
) -> int:
    semaphore = asyncio.Semaphore(CONCURRENCY)
    max_connections = CONCURRENCY * SEGMENTS
    async with make_client(max_connections) as client:
        results = await asyncio.gather(
            *(update_tool(client, semaphore, tool, bin_dir, reporter) for tool in tools)
        )
    return sum(results)
