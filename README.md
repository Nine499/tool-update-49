# tool-update-49

并发更新 GitHub 发布的命令行工具：查最新版本、Range 分段并发下载、只解包需要的文件、原子替换到 `~/.local/bin`。

## 快速开始

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。

1. 准备清单目录（目录必须已存在，内容见「配置」）：

   ```bash
   mkdir -p ~/secrets49dir
   # 把「配置」一节的 YAML 写进 ~/secrets49dir/tool-update-49.yaml
   ```

2. 指定目录并安装：

   ```bash
   export SECRETS49=~/secrets49dir
   uv tool install .
   ```

3. 运行：

   ```bash
   tool-update-49
   ```

安装后命令名为 `tool-update-49`。改完代码重新安装用 `uv tool install --force .`。

## 运行行为

- 最多 3 个工具同时处理；每个工具依次走「查询版本 → 下载 → 解包 → 安装」。
- 下载先发 1 字节 Range 请求探测：服务器支持分段且文件 ≥2MB 时，切成最多 5 段并发下载；
  否则单流下载。
- 单次请求超时 30 秒（连接超时 10 秒）。可重试失败最多尝试 3 次，退避 1 / 2 / 4 秒；
  服务器返回 `Retry-After` 时以其为准，最长等 30 秒。
- 任一工具失败不会中断其他工具。
- 安装时先写同目录临时文件、设为 0755，再用 `os.replace` 原子替换，不会留下写了一半的二进制。
- 进度输出到 stderr：交互终端里是固定行面板，一个工具一行，列为名称、版本、阶段、进度条、
  已下载大小与速度；重定向到文件或 CI 时自动改为逐行日志。

退出码：

| 退出码 | 含义 |
| --- | --- |
| 0 | 全部工具更新成功 |
| 1 | 至少一个工具失败 |
| 2 | 配置错误（环境变量缺失、目录不存在、YAML 或字段不合法） |
| 130 | 用户中断（Ctrl+C） |

## 配置

工具清单固定在 `$SECRETS49/tool-update-49.yaml`。`SECRETS49` 必须指向已存在的目录。

```yaml
tools:
  - name: qdns
    repo: natesales/q
    url: https://github.com/natesales/q/releases/download/v{ver}/q_{ver}_linux_amd64.tar.gz
    files:
      q: qdns
```

顶层只能有 `tools`，且必须是非空列表。每项必须且只能有下面四个字段：

| 字段 | 说明 |
| --- | --- |
| `name` | 面板里的显示名，所有工具之间唯一；不能为空、`.`、`..`，不能含 `/`、`\` 或 NUL |
| `repo` | GitHub 仓库，`owner/repo` 形式，用于查询 latest release |
| `url` | 下载地址，必须是 http 或 https |
| `files` | 归档内文件名 → 安装名，非空映射 |

`url` 的规则：

- 含 `{ver}`：先查 `repo` 的 latest release，取 tag 去掉前导 `v` 后替换。这是唯一支持的占位符。
- 不含 `{ver}`：直接下载，面板里的版本显示为 `latest`。

`files` 的规则：

- 键是归档内的文件名。匹配时只取路径最后一段（忽略目录层级），并忽略大小写。
- 值是安装后的文件名。所有工具之间必须唯一，且不能为空、`.`、`..`，不能含 `/`、`\` 或 NUL。
- 归档格式按 URL 文件名后缀判断：`.zip` 按 zip 处理；`.tar.gz`、`.tgz`、`.tar.bz2`、
  `.tbz2`、`.tar.xz`、`.txz`、`.tar` 按 tar 处理。
- 其他后缀按裸二进制处理：`files` 只能有一个映射，且键必须（忽略大小写）等于 URL 的最后一段文件名。
- 归档里找不到请求的成员时，该工具失败并报「归档中缺少」。

### GitHub token

可选。匿名访问 `api.github.com` 限额 60 次/小时，带 token 为 5000 次/小时。

优先读 `$SECRETS49/.env` 的 `github-no-403`：

```dotenv
github-no-403=ghp_xxx
```

读不到时回退环境变量 `GITHUB_TOKEN`。token 只加在 `api.github.com` 的请求上，
下载 release 资产时不携带。

## 常用命令

| 命令 | 用途 |
| --- | --- |
| `uv sync` | 安装或同步开发依赖 |
| `uv run pytest` | 跑单元测试 |
| `ruff check src tests` | 静态检查 |
| `ruff format --check src tests` | 检查格式 |
| `uv build` | 构建 wheel 和 sdist |
| `uv run tool-update-49 --help` | 从源码运行并查看帮助 |

需要自动修复时用 `ruff check --fix src tests` 和 `ruff format src tests`。

## 项目结构

```text
src/tool_update_49/
  config.py    读取并校验工具清单
  net.py       GitHub token、latest release、HTTP 重试
  download.py  Range 探测与分段并发下载
  archive.py   按 files 从 zip / tar 中只提取需要的成员
  install.py   原子安装到目标目录
  ui.py        交互面板与非 TTY 逐行日志
  updater.py   单工具流程与并发调度
  cli.py       命令行入口与退出码
  errors.py    异常类型与单行文本清洗
tests/         pytest 单元测试
```

## 版本号

格式为 `YYYYMMDD.HHMM.SSMS`，用 `time-version-49` skill 生成。改版本时同时更新
`pyproject.toml` 的 `[project].version` 和 `src/tool_update_49/__init__.py` 的
`__version__`。

## 常见问题

**启动即报「未设置环境变量 SECRETS49」。**
当前 shell 没有导出该变量。执行 `export SECRETS49=~/secrets49dir`，或写进 shell 配置。

**报「找不到工具清单」。**
`SECRETS49` 指向的目录里没有 `tool-update-49.yaml`。确认文件名和位置。

**裸二进制报「files 键必须是下载文件名」。**
URL 没有归档后缀时，`files` 只能写一项，键必须是 URL 最后一段的文件名。例如
`https://example.com/yq_linux_amd64` 对应 `yq_linux_amd64: yq`。

**报「归档中缺少 xxx」。**
`files` 的键要和归档里的文件名一致。程序只比对文件名本身，不比对目录路径，且忽略大小写。

**GitHub API 报 403 限流。**
在 `.env` 里配好 token。错误信息会给出限额恢复时间。

**没有进度条，只有一行行日志。**
输出不是终端（重定向、CI）时的正常降级行为。

## 链接

- Agent / LLM 文档：[AGENTS.md](AGENTS.md)
