"""
日志模块。
职责类似 Java 项目里的 logback/log4j 配置：
1. 控制台输出，方便开发时看日志
2. app.log 记录系统运行日志
3. operations.log 记录关键业务操作日志
"""

import json
import logging
import os
from collections import deque
from logging.handlers import RotatingFileHandler
from typing import Any
from typing import Dict


LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
APP_LOGGER_NAME = "deploy-web"
OPERATIONS_LOGGER_NAME = "deploy-web.operations"
EVENT_LABELS = {
    "save_md5_remote_settings": "保存远程MD5配置",
    "save_md5_local_settings": "保存本地MD5配置",
    "md5_scan": "统计远程目录MD5",
    "md5_local_scan": "统计本地目录MD5",
    "list_profiles": "读取配置列表",
    "save_profile": "保存环境配置",
    "add_custom_sql": "新增自定义常规SQL",
    "delete_custom_sql": "删除自定义常规SQL",
    "set_active_profile": "切换当前环境",
    "delete_profile": "删除环境配置",
    "test_connection": "测试环境连接",
    "remote_summary": "读取远程目录摘要",
    "upload_dir": "上传目录到服务器",
    "clear_remote_dir": "清空远程目录",
    "generate_script": "生成SQL脚本",
    "run_script": "执行远程脚本",
    "list_remote_logs": "读取远程日志",
    "script_preview": "读取脚本预览",
}


def _ensure_log_dir(log_dir: str) -> str:
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def configure_logging(log_dir: str, max_bytes: int, backup_count: int) -> None:
    """
    初始化日志配置。
    做成幂等的，避免 FastAPI 热加载时重复加 handler。
    """
    log_dir = _ensure_log_dir(log_dir)
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    operations_logger = logging.getLogger(OPERATIONS_LOGGER_NAME)

    if getattr(app_logger, "_deploy_logging_ready", False):
        return

    formatter = logging.Formatter(LOG_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    app_file_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    app_file_handler.setFormatter(formatter)

    operations_file_handler = RotatingFileHandler(
        os.path.join(log_dir, "operations.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    operations_file_handler.setFormatter(formatter)

    app_logger.setLevel(logging.INFO)
    app_logger.handlers = []
    app_logger.addHandler(console_handler)
    app_logger.addHandler(app_file_handler)
    app_logger.propagate = False

    operations_logger.setLevel(logging.INFO)
    operations_logger.handlers = []
    operations_logger.addHandler(console_handler)
    operations_logger.addHandler(operations_file_handler)
    operations_logger.propagate = False

    app_logger._deploy_logging_ready = True
    operations_logger._deploy_logging_ready = True
    app_logger.info(
        "日志模块初始化完成，日志目录=%s，单文件大小上限=%s，保留份数=%s",
        log_dir,
        max_bytes,
        backup_count,
    )


def get_app_logger() -> logging.Logger:
    return logging.getLogger(APP_LOGGER_NAME)


def get_operations_logger() -> logging.Logger:
    return logging.getLogger(OPERATIONS_LOGGER_NAME)


def log_operation(event: str, success: bool, **kwargs: Any) -> None:
    """
    记录关键操作日志。
    输出 JSON 字符串，后续查问题更直观。
    """
    payload = {
        "事件编码": event,
        "操作名称": EVENT_LABELS.get(event, event),
        "执行结果": "成功" if success else "失败",
    }
    payload.update(kwargs)
    get_operations_logger().info(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def tail_log_file(log_dir: str, log_name: str, lines: int) -> Dict[str, Any]:
    """
    读取日志文件的最后 N 行，给页面展示最近日志。
    """
    safe_name = "app.log" if log_name != "operations.log" else "operations.log"
    file_path = os.path.join(log_dir, safe_name)
    if not os.path.exists(file_path):
        return {"log_name": safe_name, "exists": False, "content": ""}

    # deque 只保留最后 N 行，日志接近滚动上限时也不会整文件加载到内存。
    with open(file_path, "r", encoding="utf-8", errors="replace") as log_file:
        recent_lines = deque(log_file, maxlen=max(1, lines))

    return {
        "log_name": safe_name,
        "exists": True,
        "content": "".join(recent_lines),
    }
