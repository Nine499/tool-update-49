"""项目内使用的异常类型与文本清洗工具。"""

from __future__ import annotations


class UpdateError(Exception):
    """可预期的更新失败，消息会直接展示给用户。"""


class RetryableError(UpdateError):
    """值得重试的失败：网络中断、限流、响应截断等。"""


class ConfigError(Exception):
    """工具清单缺失或格式错误。"""


def describe_error(error: object) -> str:
    """把异常变成适合单行展示的文字。"""
    text = one_line(str(error))
    return text or type(error).__name__


def one_line(text: str) -> str:
    """压掉换行和多余空白，避免打乱进度面板。"""
    return " ".join(text.split())
