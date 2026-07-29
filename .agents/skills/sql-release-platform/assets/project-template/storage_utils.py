"""JSON 配置文件的安全读写工具。

类比 Java 项目中的 Repository 基础设施：业务模块只关心 Python 字典，
这里统一负责 UTF-8、临时文件和原子替换，避免程序中断时留下半个 JSON 文件。
"""

import json
import os
import tempfile
from contextlib import suppress
from typing import Any
from typing import Dict


def read_json_object(file_path: str) -> Dict[str, Any]:
    """读取 JSON 对象，并为损坏或格式错误的配置提供明确错误。"""
    try:
        with open(file_path, "r", encoding="utf-8") as json_file:
            data = json.load(json_file)
    except json.JSONDecodeError as exc:
        raise ValueError("配置文件 JSON 格式错误: %s" % file_path) from exc

    if not isinstance(data, dict):
        raise ValueError("配置文件根节点必须是 JSON 对象: %s" % file_path)
    return data


def write_json_object_atomic(file_path: str, data: Dict[str, Any]) -> None:
    """先写同目录临时文件，再原子替换目标文件。"""
    absolute_path = os.path.abspath(file_path)
    parent_dir = os.path.dirname(absolute_path)
    os.makedirs(parent_dir, exist_ok=True)

    file_descriptor, temporary_path = tempfile.mkstemp(
        prefix=".%s." % os.path.basename(absolute_path),
        suffix=".tmp",
        dir=parent_dir,
    )
    try:
        # 运行配置中可能包含密码，默认只允许当前系统用户读写。
        os.chmod(temporary_path, 0o600)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as json_file:
            json.dump(data, json_file, ensure_ascii=False, indent=2)
            json_file.write("\n")
            json_file.flush()
            os.fsync(json_file.fileno())
        os.replace(temporary_path, absolute_path)
    except Exception:
        with suppress(OSError):
            os.close(file_descriptor)
        with suppress(OSError):
            os.remove(temporary_path)
        raise
