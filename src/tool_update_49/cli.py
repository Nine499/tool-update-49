"""命令行入口。"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .config import ConfigError, load_tools, resolve_config_path
from .ui import make_reporter
from .updater import run_updates


def main(argv: list[str] | None = None) -> int:
    _parser().parse_args(argv)

    try:
        config_path = resolve_config_path()
        tools = load_tools(config_path)
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2

    with make_reporter(tools) as reporter:
        try:
            updated = asyncio.run(run_updates(tools, default_bin_dir(), reporter))
        except KeyboardInterrupt:
            reporter.log("已中断", "warn")
            return 130

    reporter.summary(updated)
    return 0 if updated == len(tools) else 1


def default_bin_dir() -> Path:
    return Path.home() / ".local" / "bin"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tool-update-49",
        description="并发更新 GitHub 发布的开源命令行工具。",
        epilog="工具清单：$SECRETS49/tool-update-49.yaml",
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
