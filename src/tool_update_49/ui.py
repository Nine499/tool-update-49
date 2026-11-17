"""进度面板与日志输出。"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, TextIO

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from .config import Tool

NAME_WIDTH = 10
VERSION_WIDTH = 10
PHASE_WIDTH = 8
BAR_WIDTH = 18
DETAIL_WIDTH = 30
LEVEL_STYLE = {"info": "cyan", "ok": "green", "warn": "yellow", "error": "red"}
LEVEL_LABEL = {"info": "·", "ok": "✓", "warn": "!", "error": "✗"}


class Reporter(Protocol):
    """更新流程只依赖这几个回调。"""

    def start_tool(self, tool: Tool) -> None: ...
    def set_version(self, tool: Tool, version: str) -> None: ...
    def set_phase(self, tool: Tool, phase: str) -> None: ...
    def begin_download(self, tool: Tool, total: int | None) -> None: ...
    def advance(self, tool: Tool, size: int) -> None: ...
    def finish_tool(self, tool: Tool, installed: list[Path]) -> None: ...
    def fail_tool(self, tool: Tool, message: str) -> None: ...
    def log(self, message: str, level: str = "info") -> None: ...
    def summary(self, updated: int) -> None: ...
    def __enter__(self) -> Reporter: ...
    def __exit__(self, *exc_info: object) -> None: ...


@dataclass(slots=True)
class _Row:
    name: str
    version: str = ""
    phase: str = "等待"
    state: str = "pending"
    completed: int = 0
    total: int | None = None
    speed: float = 0.0
    detail: str = ""
    last_time: float = 0.0
    last_bytes: int = 0


class RichReporter:
    """交互终端里的固定行面板：一个工具一行，顺序不变。"""

    def __init__(self, tools: list[Tool], console: Console) -> None:
        self._console = console
        self._rows = {tool.name: _Row(name=tool.name) for tool in tools}
        self._ordered = list(self._rows.values())
        self._finished = 0
        self._failed = 0
        self._started = False
        self._live = Live(
            self,
            console=console,
            refresh_per_second=10,
            transient=False,
        )

    def __enter__(self) -> RichReporter:
        self._live.start()
        self._started = True
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._started = False
        self._live.stop()

    def __rich__(self) -> RenderableType:
        table = Table.grid(padding=(0, 1))
        table.add_column(width=NAME_WIDTH, no_wrap=True, overflow="ellipsis")
        table.add_column(width=VERSION_WIDTH, no_wrap=True, overflow="ellipsis")
        table.add_column(width=PHASE_WIDTH, no_wrap=True, overflow="ellipsis")
        table.add_column(width=BAR_WIDTH, no_wrap=True)
        table.add_column(width=DETAIL_WIDTH, no_wrap=True, overflow="ellipsis")
        for row in self._ordered:
            table.add_row(*self._cells(row))
        return Group(self._header(), Text(""), table)

    def start_tool(self, tool: Tool) -> None:
        row = self._rows[tool.name]
        row.state = "running"
        row.phase = "查询版本" if tool.needs_version else "准备"
        row.detail = "处理中"
        self._refresh()

    def set_version(self, tool: Tool, version: str) -> None:
        self._rows[tool.name].version = version
        self._refresh()

    def set_phase(self, tool: Tool, phase: str) -> None:
        row = self._rows[tool.name]
        row.phase = phase
        row.detail = "处理中"
        if phase != "下载":
            row.total = None
            row.completed = 0
            row.speed = 0.0
        self._refresh()

    def begin_download(self, tool: Tool, total: int | None) -> None:
        row = self._rows[tool.name]
        row.phase = "下载"
        row.total = total
        row.completed = 0
        row.speed = 0.0
        row.detail = ""
        row.last_time = time.monotonic()
        row.last_bytes = 0
        self._refresh()

    def advance(self, tool: Tool, size: int) -> None:
        row = self._rows[tool.name]
        row.completed += size
        now = time.monotonic()
        elapsed = now - row.last_time
        if elapsed >= 0.2:
            instant = (row.completed - row.last_bytes) / elapsed
            row.speed = instant if row.speed == 0 else row.speed * 0.7 + instant * 0.3
            row.last_time = now
            row.last_bytes = row.completed

    def finish_tool(self, tool: Tool, installed: list[Path]) -> None:
        row = self._rows[tool.name]
        row.state = "done"
        row.phase = "完成"
        row.completed = 1
        row.total = 1
        row.speed = 0.0
        row.detail = "已安装 " + ", ".join(path.name for path in installed)
        self._finished += 1
        self._refresh()

    def fail_tool(self, tool: Tool, message: str) -> None:
        row = self._rows[tool.name]
        row.state = "failed"
        row.phase = "失败"
        row.detail = message
        self._finished += 1
        self._failed += 1
        self.log(f"{tool.name}: {message}", "error")
        self._refresh()

    def log(self, message: str, level: str = "info") -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        style = LEVEL_STYLE.get(level, "white")
        label = LEVEL_LABEL.get(level, "·")
        self._console.print(
            Text.assemble(
                (stamp, "dim"),
                " ",
                (label, style),
                " ",
                (_one_line(message), style),
            )
        )

    def summary(self, updated: int) -> None:
        total = len(self._ordered)
        if updated == total:
            self._console.print(
                Text(f"✓ 全部完成：{total} 个工具已更新", style="bold green")
            )
            return
        failed = [row.name for row in self._ordered if row.state == "failed"]
        self._console.print(
            Text.assemble(
                ("完成 ", "bold"),
                f"{updated}/{total}",
                ("，失败 ", "red"),
                f"{len(failed)}",
                (f"（{', '.join(failed)}）" if failed else "", "red"),
            )
        )

    def _refresh(self) -> None:
        if self._started:
            self._live.refresh()

    def _header(self) -> Text:
        header = Text.assemble(
            ("tool-update-49", "bold cyan"),
            "  ",
            ("·", "dim"),
            f"  已完成 {self._finished}/{len(self._ordered)}",
        )
        if self._failed:
            header.append(f"  ·  失败 {self._failed}", style="red")
        return header

    def _cells(self, row: _Row) -> tuple[RenderableType, ...]:
        phase_style = {
            "pending": "dim",
            "running": "cyan",
            "done": "green",
            "failed": "red",
        }.get(row.state, "white")
        return (
            Text(row.name, style="bold"),
            Text(row.version or "—", style="dim"),
            Text(row.phase, style=phase_style),
            _bar(row),
            _detail(row),
        )


class PlainReporter:
    """非交互终端里的逐行日志，不做动态刷新。"""

    def __init__(self, total: int, stream: TextIO | None = None) -> None:
        self._total = total
        self._stream = stream if stream is not None else sys.stderr
        self._versions: dict[str, str] = {}
        self._finished = 0
        self._failed = 0

    def __enter__(self) -> PlainReporter:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def start_tool(self, tool: Tool) -> None:
        self._print(f"→ {tool.name} 开始")

    def set_version(self, tool: Tool, version: str) -> None:
        self._versions[tool.name] = version

    def set_phase(self, tool: Tool, phase: str) -> None:
        if phase in {"解包", "安装"}:
            self._print(f"  {tool.name}: {phase}")

    def begin_download(self, tool: Tool, total: int | None) -> None:
        version = self._versions.get(tool.name, "")
        label = f"v{version} " if version and version != "latest" else ""
        size = f"（{format_bytes(total)}）" if total is not None else ""
        self._print(f"  {tool.name}: 下载 {label}{size}")

    def advance(self, tool: Tool, size: int) -> None:
        return None

    def finish_tool(self, tool: Tool, installed: list[Path]) -> None:
        self._finished += 1
        paths = ", ".join(str(path) for path in installed)
        self._print(f"✓ {tool.name} 已安装: {paths}")

    def fail_tool(self, tool: Tool, message: str) -> None:
        self._finished += 1
        self._failed += 1
        self._print(f"✗ {tool.name}: {_one_line(message)}")

    def log(self, message: str, level: str = "info") -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        label = LEVEL_LABEL.get(level, "·")
        self._print(f"{stamp} {label} {_one_line(message)}")

    def summary(self, updated: int) -> None:
        if updated == self._total:
            self._print(f"✓ 全部完成：{self._total} 个工具已更新")
            return
        self._print(
            f"完成 {updated}/{self._total}，失败 {self._failed}，"
            f"已处理 {self._finished}/{self._total}"
        )

    def _print(self, message: str) -> None:
        print(message, file=self._stream, flush=True)


def make_reporter(tools: list[Tool]) -> Reporter:
    console = Console(stderr=True, highlight=False)
    if console.is_terminal:
        return RichReporter(tools, console)
    return PlainReporter(len(tools))


def format_bytes(value: float) -> str:
    if value < 1024:
        return f"{value:.0f} B"
    value /= 1024
    for unit in ("KB", "MB", "GB", "TB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def _bar(row: _Row) -> ProgressBar:
    if row.state == "done":
        return ProgressBar(
            total=1, completed=1, width=BAR_WIDTH, finished_style="green"
        )
    if row.state == "failed":
        return ProgressBar(
            total=1,
            completed=1,
            width=BAR_WIDTH,
            complete_style="red",
            finished_style="red",
        )
    if row.total is not None:
        return ProgressBar(
            total=max(row.total, 1),
            completed=min(row.completed, row.total),
            width=BAR_WIDTH,
            complete_style="cyan",
            finished_style="green",
        )
    if row.state == "running":
        return ProgressBar(total=None, width=BAR_WIDTH, pulse=True)
    return ProgressBar(total=1, completed=0, width=BAR_WIDTH)


def _detail(row: _Row) -> Text:
    if row.state == "failed":
        return Text(row.detail or "失败", style="red")
    if row.state == "done":
        return Text(row.detail or "已安装", style="green")
    if row.phase == "下载":
        if row.total is None:
            text = f"{format_bytes(row.completed)}  {format_bytes(row.speed)}/s"
        else:
            text = (
                f"{format_bytes(row.completed)} / {format_bytes(row.total)}  "
                f"{format_bytes(row.speed)}/s"
            )
        return Text(text, style="dim")
    if row.state == "running":
        return Text(row.detail or "处理中", style="dim")
    return Text("")


def _one_line(text: str) -> str:
    return " ".join(text.split())
