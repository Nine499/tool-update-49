# tool-update-49 项目规则

Agent / LLM 文档见 `AGENTS.md`，改代码前先读。

## 版本号

- 所有版本号必须用 `time-version-49` skill 生成，格式 `YYYYMMDD.HHMM.SSMS`。
- 改版本时同时更新两处，保持一致：
  - `pyproject.toml` 的 `[project].version`
  - `src/tool_update_49/__init__.py` 的 `__version__`
- 禁止手写、递增或沿用旧版本号。

## 安装与验证

- 禁止运行 `uv tool install`，全局安装由用户手动执行。
- 需要验证安装时，只把命令交给用户：`uv tool install --force .`。
- 改完代码后运行：

```bash
uv sync
ruff check src tests
ruff format --check src tests
uv run pytest
uv build
uv run tool-update-49 --help
```

## 项目结构

- `config.py`：读取并校验 `$SECRETS49/tool-update-49.yaml`。
- `net.py`：GitHub token、latest release、HTTP 重试。
- `download.py`：Range 探测、分段并发下载。
- `archive.py` / `install.py`：只提取需要的成员、原子安装。
- `ui.py`：交互终端固定行面板；非 TTY 自动切换逐行日志。
- `updater.py`：单工具流程与并发调度。
- `cli.py`：入口、退出码。

## 配置

- 工具清单固定在 `$SECRETS49/tool-update-49.yaml`，字段为 `name` / `repo` / `url` / `files`。
- 归档按 URL 文件名后缀判断；裸二进制只能有一个映射，键必须等于 URL 文件名。
- token 读 `$SECRETS49/.env` 的 `github-no-403`，回退 `GITHUB_TOKEN`；只发给 `api.github.com`。

## Git

- 远程地址：`git@github.com:Nine499/tool-update-49.git`（`origin`）。
- 不提交、不推送，除非用户明确要求。

## 代码约定

- 人类可读优先，一个函数只做一件事；面向用户的错误消息用简体中文。
- 新增依赖用 `uv add`，装进本项目，不做全局安装。
