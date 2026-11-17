# tool-update-49

并发更新 GitHub 上发布的命令行工具：查询最新版本、下载（支持 Range 分段并发）、
只解包需要的文件、原子替换到 `~/.local/bin`。

## 安装

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
export SECRETS49=~/secrets49dir
uv tool install .
```

安装后命令名为 `tool-update-49`。改完代码重新安装用：

```bash
uv tool install --force .
```

## 配置

工具清单固定在 `$SECRETS49/tool-update-49.yaml`：

```yaml
tools:
  - name: qdns
    repo: natesales/q
    url: https://github.com/natesales/q/releases/download/v{ver}/q_{ver}_linux_amd64.tar.gz
    files:
      q: qdns
```

- `name`：进度面板里的显示名，必须唯一。
- `repo`：GitHub 仓库，用于查询 latest release 和定位报错。
- `url`：下载地址。含 `{ver}` 时先查 latest release 再替换；不含时直接下载。
- `files`：归档内文件名（大小写不敏感）→ 安装名。URL 文件名以 `.zip` 或
  `.tar.gz` / `.tgz` / `.tar.bz2` / `.tbz2` / `.tar.xz` / `.txz` / `.tar` 结尾时
  按归档处理；否则按裸二进制处理，此时只能有一个映射，且键必须等于 URL 文件名。

安装名在所有工具之间必须唯一，不能包含 `/`、`\`、`.`、`..`。

### GitHub token

可选。匿名访问 `api.github.com` 限制 60 次/小时，带 token 为 5000 次/小时。

优先读 `$SECRETS49/.env` 的 `github-no-403`：

```dotenv
github-no-403=ghp_xxx
```

读不到时回退环境变量 `GITHUB_TOKEN`。token 只会发往 `api.github.com`，
下载 release 资产时不携带。

## 运行

```bash
tool-update-49
```

交互终端里每个工具固定一行，依次显示名称、版本、阶段、进度条、已下载大小和速度；
工具之间的顺序始终与 YAML 一致，不会互相覆盖。非交互环境（重定向、CI）自动改为
逐行日志。

退出码：

| 退出码 | 含义 |
| --- | --- |
| 0 | 全部工具更新成功 |
| 1 | 至少一个工具失败，其余继续 |
| 2 | 配置缺失或格式错误 |
| 130 | 用户中断 |

## 开发

```bash
uv sync
uv run pytest
ruff check src tests
ruff format --check src tests
uv build
```
