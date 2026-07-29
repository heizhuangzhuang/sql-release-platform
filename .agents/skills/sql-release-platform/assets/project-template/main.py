"""
FastAPI 主入口。
类比 Java Web：Controller + Service 都在这个文件里（为了简化示例）。
"""

import base64
import hashlib
import json
import os
import posixpath
import shlex
import shutil
import stat
import time
import uuid
from datetime import datetime
from threading import RLock
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

import paramiko
from fastapi import Body
from fastapi import FastAPI
from fastapi import File
from fastapi import Form
from fastapi import Query
from fastapi import Request
from fastapi import UploadFile
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from config import ConnectionProfile
from config import profile_store
from config import settings
from logging_setup import configure_logging
from logging_setup import get_app_logger
from logging_setup import log_operation
from logging_setup import tail_log_file
from storage_utils import read_json_object
from storage_utils import write_json_object_atomic


configure_logging(settings.log_dir, settings.log_max_bytes, settings.log_backup_count)
logger = get_app_logger()

app = FastAPI()
templates = Jinja2Templates(directory="templates")

SYSTEM_LOG_LINES = 120
REMOTE_COMMAND_LOG_LIMIT = 2000
FILE_READ_BUFFER_SIZE = 1024 * 1024
LOG_DIR_NAME = "log"
LOG_HISTORY_DIR_NAME = "history"
LOG_SKIP_DIR_NAMES = set([LOG_DIR_NAME])
MD5_SETTINGS_FILE = "md5_settings.json"
CUSTOM_SQL_KEY_PREFIX = "custom:"
MAX_CUSTOM_SQL_OPTIONS = 30
MD5_SETTINGS_LOCK = RLock()

SCRIPT_BLOCKS: Dict[str, Dict[str, str]] = {
    "batchetl1_tmp": {
        "title": "db_pbatchetl001db_1_tmp.sql",
        "log_file": "./log/batchetl01_tmp_execute_sql.txt",
        "command": "/pgsoft/pg14.7/bin/psql -h localhost -p 5432 -U outbound -d pbatchetl001db -f ./db_pbatchetl001db_1_tmp.sql &>> ./log/batchetl01_tmp_execute_sql.txt",
    },
    "batchetl2_tmp": {
        "title": "db_pbatchetl001db_2_tmp.sql",
        "log_file": "./log/batchetl02_tmp_execute_sql.txt",
        "command": "/pgsoft/pg14.7/bin/psql -h localhost -p 5432 -U outbound -d pbatchetl001db -f ./db_pbatchetl001db_2_tmp.sql &>> ./log/batchetl02_tmp_execute_sql.txt",
    },
    "data1_tmp": {
        "title": "db_pdata001db_1_tmp.sql",
        "log_file": "./log/data01_tmp_execute_sql.txt",
        "command": "/pgsoft/pg14.7/bin/psql -h localhost -p 5432 -U outbound -d pdata001db -f ./db_pdata001db_1_tmp.sql &>> ./log/data01_tmp_execute_sql.txt",
    },
    "pmigrel88": {
        "title": "db_pmigrel00ldb_88.sql",
        "log_file": "./log/pmigrel00ldb88_execute_sql.txt",
        "sql_file": "db_pmigrel00ldb_88.sql",
        "database": "pmighis001db",
        "connection_type": "configured_database",
    },
    "pmigrel98": {
        "title": "db_pmigrel00ldb_98.sql",
        "log_file": "./log/pmigrel00ldb98_execute_sql.txt",
        "sql_file": "db_pmigrel00ldb_98.sql",
        "database": "pmighis001db",
        "connection_type": "configured_database",
    },
    "batchetl1": {
        "title": "db_pbatchetl001db_1.sql",
        "log_file": "./log/batchetl01_execute_sql.txt",
        "command": "/pgsoft/pg14.7/bin/psql -h localhost -p 5432 -U outbound -d pbatchetl001db -f ./db_pbatchetl001db_1.sql &>> ./log/batchetl01_execute_sql.txt",
    },
    "batchetl2": {
        "title": "db_pbatchetl001db_2.sql",
        "log_file": "./log/batchetl02_execute_sql.txt",
        "command": "/pgsoft/pg14.7/bin/psql -h localhost -p 5432 -U outbound -d pbatchetl001db -f ./db_pbatchetl001db_2.sql &>> ./log/batchetl02_execute_sql.txt",
    },
    "batchetl3": {
        "title": "db_pbatchetl001db_3.sql",
        "log_file": "./log/batchetl03_execute_sql.txt",
        "command": "/pgsoft/pg14.7/bin/psql -h localhost -p 5432 -U outbound -d pbatchetl001db -f ./db_pbatchetl001db_3.sql &>> ./log/batchetl03_execute_sql.txt",
    },
    "batchetl4": {
        "title": "db_pbatchetl001db_4.sql",
        "log_file": "./log/batchetl04_execute_sql.txt",
        "command": "/pgsoft/pg14.7/bin/psql -h localhost -p 5432 -U outbound -d pbatchetl001db -f ./db_pbatchetl001db_4.sql &>> ./log/batchetl04_execute_sql.txt",
    },
    "data": {
        "title": "pdata001db",
        "log_file": "./log/data_execute_sql.txt",
        "command": "/pgsoft/pg14.7/bin/psql -h localhost -p 5432 -U outbound -d pdata001db -f ./db_pdata001db.sql &>> ./log/data_execute_sql.txt",
    },
    "other": {
        "title": "pother001db",
        "log_file": "./log/otherexecute_sql.txt",
        "command": "/pgsoft/pg14.7/bin/psql -h localhost -p 5432 -U outbound -d pother001db -f ./db_pother001db.sql &>> ./log/otherexecute_sql.txt",
    },
    "pub": {
        "title": "ppub001db",
        "log_file": "./log/pubexecute_sql.txt",
        "command": "/pgsoft/pg14.7/bin/psql -h localhost -p 5432 -U outbound -d ppub001db -f ./db_ppub001db.sql &>> ./log/pubexecute_sql.txt",
    },
    "history": {
        "title": "phistory001db",
        "log_file": "./log/histexecute_sql.txt",
        "command": "/pgsoft/pg14.7/bin/psql -h localhost -p 5432 -U outbound -d phist001db -f ./db_phist001db.sql &>> ./log/histexecute_sql.txt",
    },
    "grant": {
        "title": "pgrant001db",
        "log_file": "./log/grant_execute_sql.txt",
        "command": "/pgsoft/pg14.7/bin/psql -h localhost -p 5432 -U outbound -d pgrant001db -f ./db_pgrant001db.sql &>> ./log/grant_execute_sql.txt",
    },
    "install01": {
        "title": "pinstall001db",
        "log_file": "./log/install01execute_sql.txt",
        "command": "/pgsoft/pg14.7/bin/psql -h localhost -p 5432 -U outbound -d pinstall001db -f ./db_pinstall001db.sql &>> ./log/install01execute_sql.txt",
    },
    "install02": {
        "title": "pinstall002db",
        "log_file": "./log/install02execute_sql.txt",
        "command": "/pgsoft/pg14.7/bin/psql -h localhost -p 5432 -U outbound -d pinstall002db -f ./db_pinstall002db.sql &>> ./log/install02execute_sql.txt",
    },
    "mainnf": {
        "title": "pmainnf001db",
        "log_file": "./log/mainnf001dbexecute_sql.txt",
        "command": "/pgsoft/pg14.7/bin/psql -h localhost -p 5432 -U appdb -d pmainnf001db -f ./db_pmainnf001db.sql &>> ./log/mainnf001dbexecute_sql.txt",
    },
    "test": {
        "title": "测试脚本",
        "log_file": "./log/测试脚本log",
        "command": "printf '测试通过啦！！\\n' > ./log/测试脚本log",
    },
}

SCRIPT_ORDER = [
    "batchetl1_tmp",
    "batchetl2_tmp",
    "data1_tmp",
    "pmigrel88",
    "pmigrel98",
    "batchetl1",
    "batchetl2",
    "batchetl3",
    "batchetl4",
    "data",
    "other",
    "pub",
    "history",
    "grant",
    "install01",
    "install02",
    "mainnf",
    "test",
]


def _get_active_profile() -> ConnectionProfile:
    return profile_store.get_active_profile()


def _profile_summary(profile: ConnectionProfile) -> str:
    return (
        "name={name}, host={host}, port={port}, user={user}, remote_dir={remote_dir}, script_name={script_name}, default_local_dir={default_local_dir}, db_host={db_host}, db_port={db_port}, db_user={db_user}"
    ).format(
        name=profile.name,
        host=profile.ssh_host,
        port=profile.ssh_port,
        user=profile.ssh_user,
        remote_dir=profile.remote_dir,
        script_name=profile.script_name,
        default_local_dir=profile.default_local_dir or "-",
        db_host=profile.db_host or "-",
        db_port=profile.db_port,
        db_user=profile.db_user or "-",
    )


def _profile_to_dict(profile: ConnectionProfile) -> Dict[str, Any]:
    return {
        "name": profile.name,
        "ssh_host": profile.ssh_host,
        "ssh_port": profile.ssh_port,
        "ssh_user": profile.ssh_user,
        "ssh_password": profile.ssh_password or "",
        "remote_dir": profile.remote_dir,
        "script_name": profile.script_name,
        "default_local_dir": profile.default_local_dir,
        "db_host": profile.db_host,
        "db_port": profile.db_port,
        "db_user": profile.db_user,
        "db_password": profile.db_password or "",
        "custom_sql_options": profile.custom_sql_options,
    }


def _connect_ssh(profile: ConnectionProfile) -> paramiko.SSHClient:
    profile.validate()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    logger.info("开始建立 SSH 连接，目标环境信息：%s", _profile_summary(profile))
    client.connect(
        hostname=profile.ssh_host,
        port=profile.ssh_port,
        username=profile.ssh_user,
        password=profile.ssh_password,
        timeout=10,
    )
    logger.info("SSH 连接成功：%s", _profile_summary(profile))
    return client


def _remote_path(profile: ConnectionProfile, filename: str) -> str:
    return "%s/%s" % (profile.remote_dir.rstrip("/"), filename)


def _write_remote_file(sftp: paramiko.SFTPClient, remote_path: str, data: bytes) -> None:
    with sftp.open(remote_path, "wb") as remote_file:
        remote_file.write(data)


def _normalize_rel_path(path: str) -> str:
    path = path.replace("\\", "/")
    path = posixpath.normpath(path)
    path = path.lstrip("./")
    while path.startswith("../"):
        path = path[3:]
    return path


def _strip_top_level_dir(path: str) -> str:
    if "/" not in path:
        return path
    _, child_path = path.split("/", 1)
    return child_path


def _ensure_remote_dir(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    parts = remote_dir.strip("/").split("/")
    current = ""
    for part in parts:
        current = "%s/%s" % (current, part) if current else "/%s" % part
        try:
            sftp.stat(current)
        except IOError:
            sftp.mkdir(current)


def _remove_remote_entry(sftp: paramiko.SFTPClient, remote_path: str) -> int:
    try:
        entry_stat = sftp.stat(remote_path)
    except IOError:
        return 0

    if stat.S_ISDIR(entry_stat.st_mode):
        removed = 0
        for entry in sftp.listdir_attr(remote_path):
            child_path = posixpath.join(remote_path, entry.filename)
            removed += _remove_remote_entry(sftp, child_path)
        sftp.rmdir(remote_path)
        return removed + 1

    sftp.remove(remote_path)
    return 1


def _should_skip_clear_entry(entry_name: str) -> bool:
    return entry_name in LOG_SKIP_DIR_NAMES


def _clear_remote_dir(sftp: paramiko.SFTPClient, remote_dir: str) -> int:
    _ensure_remote_dir(sftp, remote_dir)
    removed = 0
    for entry in sftp.listdir_attr(remote_dir):
        if _should_skip_clear_entry(entry.filename):
            logger.info("清理目录时跳过保留目录：%s", entry.filename)
            continue
        child_path = posixpath.join(remote_dir, entry.filename)
        removed += _remove_remote_entry(sftp, child_path)
    return removed


def _count_remote_entries(sftp: paramiko.SFTPClient, remote_dir: str) -> Dict[str, int]:
    _ensure_remote_dir(sftp, remote_dir)
    total_files = 0
    total_dirs = 0

    for entry in sftp.listdir_attr(remote_dir):
        if _should_skip_clear_entry(entry.filename):
            logger.info("统计目录内容时跳过保留目录：%s", entry.filename)
            continue
        child_path = posixpath.join(remote_dir, entry.filename)
        if stat.S_ISDIR(entry.st_mode):
            total_dirs += 1
            child_counts = _count_remote_entries(sftp, child_path)
            total_files += child_counts["total_files"]
            total_dirs += child_counts["total_dirs"]
        else:
            total_files += 1

    return {"total_files": total_files, "total_dirs": total_dirs}


def _list_remote_top_entries(sftp: paramiko.SFTPClient, remote_dir: str) -> List[Dict[str, Any]]:
    _ensure_remote_dir(sftp, remote_dir)
    entries = []
    for entry in sftp.listdir_attr(remote_dir):
        is_dir = stat.S_ISDIR(entry.st_mode)
        entries.append(
            {
                "name": entry.filename,
                "type": "dir" if is_dir else "file",
                "size": 0 if is_dir else entry.st_size,
                "modified_at": datetime.fromtimestamp(entry.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "protected": _should_skip_clear_entry(entry.filename),
            }
        )

    return sorted(entries, key=lambda item: (item["type"] != "dir", item["name"].lower()))


def _run_remote_command(client: paramiko.SSHClient, command: str) -> Dict[str, Any]:
    logger.info("开始执行远程命令：%s", command)
    stdin, stdout, stderr = client.exec_command(command)
    output = _decode_text_bytes(stdout.read())
    error = _decode_text_bytes(stderr.read())
    exit_status = stdout.channel.recv_exit_status()
    logger.info(
        "远程命令执行完成：退出码=%s，标准输出=%r，错误输出=%r",
        exit_status,
        _summarize_for_log(output),
        _summarize_for_log(error),
    )
    return {"exit_status": exit_status, "stdout": output, "stderr": error}


def _summarize_for_log(value: str, limit: int = REMOTE_COMMAND_LOG_LIMIT) -> str:
    """限制后台日志中的远程输出长度，完整内容仍通过接口返回。"""
    if len(value) <= limit:
        return value
    omitted = len(value) - limit
    return "%s\n...（后台日志已省略 %s 个字符）" % (value[:limit], omitted)


def _decode_text_bytes(raw_bytes: bytes) -> str:
    """
    统一做文本解码。
    类比 Java 里把 InputStream 按多个 Charset 依次尝试解码。

    为什么这样做：
    - 脚本文件一般是 UTF-8
    - 远程 Linux 上的日志、命令输出在中文环境里，可能是 GB18030/GBK
    - 直接固定用 UTF-8，会把中文日志读成乱码
    """
    if not raw_bytes:
        return ""

    encodings = ["utf-8", "gb18030", "gbk"]
    for encoding in encodings:
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue

    # 最后兜底，避免接口直接报错。
    return raw_bytes.decode("utf-8", errors="replace")


def _decode_base64_text(value: str) -> str:
    if not value:
        return ""
    try:
        return base64.b64decode(value.encode("ascii")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _load_md5_settings() -> Dict[str, Any]:
    with MD5_SETTINGS_LOCK:
        if not os.path.exists(MD5_SETTINGS_FILE):
            return _default_md5_settings()

        data = read_json_object(MD5_SETTINGS_FILE)
        data.setdefault("remote", {})
        data["remote"].setdefault("connection", {})
        data["remote"].setdefault("paths", [])
        data["remote"].setdefault("paths_by_profile", {})
        data["remote"].setdefault("suffixes", "")
        data.setdefault("local", {})
        data["local"].setdefault("paths", [])
        data["local"].setdefault("suffixes", "")
        return data


def _default_md5_settings() -> Dict[str, Any]:
    return {
        "remote": {
            "connection": {},
            "paths": [],
            "paths_by_profile": {},
            "suffixes": "",
        },
        "local": {
            "paths": [],
            "suffixes": "",
        },
    }


def _write_md5_settings(data: Dict[str, Any]) -> None:
    with MD5_SETTINGS_LOCK:
        write_json_object_atomic(MD5_SETTINGS_FILE, data)


def _update_md5_settings(section_name: str, values: Dict[str, Any]) -> Dict[str, Any]:
    """在同一把锁内完成读取和写入，避免两个保存请求互相覆盖。"""
    with MD5_SETTINGS_LOCK:
        data = _load_md5_settings()
        data[section_name].update(values)
        _write_md5_settings(data)
        return data


def _normalize_unique_text_values(raw_values: Any) -> List[str]:
    """把页面数组整理成去空白、去重复且保持原顺序的字符串列表。"""
    if not isinstance(raw_values, list):
        return []

    values = []
    seen = set()
    for item in raw_values:
        value = str(item).strip()
        if value and value not in seen:
            seen.add(value)
            values.append(value)
    return values


def _md5_connection_from_payload(payload: Dict[str, Any], fallback_paths: List[str]) -> ConnectionProfile:
    connection = payload.get("connection") or payload.get("profile") or {}
    if not isinstance(connection, dict):
        connection = {}

    remote_dir = ""
    if fallback_paths:
        remote_dir = fallback_paths[0]
    remote_dir = str(connection.get("remote_dir", remote_dir)).strip() or "/"

    return ConnectionProfile(
        name=str(connection.get("name", "md5-remote")).strip() or "md5-remote",
        ssh_host=str(connection.get("ssh_host", "")).strip(),
        ssh_port=int(connection.get("ssh_port", 22) or 22),
        ssh_user=str(connection.get("ssh_user", "")).strip(),
        ssh_password=str(connection.get("ssh_password", "")).strip() or None,
        remote_dir=remote_dir,
        script_name="md5",
        default_local_dir="",
    )


def _md5_saved_or_default_connection(paths: List[str]) -> ConnectionProfile:
    settings_data = _load_md5_settings()
    connection = settings_data["remote"].get("connection") or {}
    if connection.get("ssh_host") and connection.get("ssh_user") and connection.get("ssh_password"):
        return _md5_connection_from_payload({"connection": connection}, paths)

    active_profile = _get_active_profile()
    return ConnectionProfile(
        name=active_profile.name,
        ssh_host=active_profile.ssh_host,
        ssh_port=active_profile.ssh_port,
        ssh_user=active_profile.ssh_user,
        ssh_password=active_profile.ssh_password,
        remote_dir=paths[0] if paths else active_profile.remote_dir,
        script_name="md5",
        default_local_dir="",
    )


def _normalize_md5_suffixes(raw_value: Any) -> List[str]:
    if isinstance(raw_value, list):
        parts = raw_value
    else:
        value = str(raw_value or "")
        parts = value.replace("，", ",").replace("\n", ",").split(",")

    suffixes = []
    for item in parts:
        suffix = str(item).strip()
        if not suffix:
            continue
        suffix = suffix.lstrip("*")
        if not suffix.startswith("."):
            suffix = "." + suffix
        if any(char in suffix for char in ("/", "\\", "'", '"', " ", "\t")):
            continue
        if suffix not in suffixes:
            suffixes.append(suffix)
    return suffixes


def _suffixes_to_text(suffixes: List[str]) -> str:
    return ",".join(suffixes)


def _file_matches_suffix(path: str, suffixes: List[str]) -> bool:
    if not suffixes:
        return True
    lower_path = path.lower()
    return any(lower_path.endswith(suffix.lower()) for suffix in suffixes)


def _parse_manual_local_paths(raw_value: str) -> List[str]:
    if not raw_value:
        return []

    try:
        data = json.loads(raw_value)
        parts = data if isinstance(data, list) else [str(data)]
    except json.JSONDecodeError:
        parts = raw_value.replace("，", ",").replace("\n", ",").split(",")

    paths = []
    for item in parts:
        path = str(item).strip()
        if path and path not in paths:
            paths.append(path)
    return paths


def _md5_file_from_disk(file_path: str) -> Dict[str, Any]:
    md5 = hashlib.md5()
    size = 0
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(FILE_READ_BUFFER_SIZE)
            if not chunk:
                break
            size += len(chunk)
            md5.update(chunk)

    stat_result = os.stat(file_path)
    return {
        "md5": md5.hexdigest(),
        "size": size,
        "created_at": datetime.fromtimestamp(stat_result.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
        "time_source": "本地文件创建时间/状态时间",
    }


def _scan_manual_local_path(path: str, suffixes: List[str]) -> Dict[str, Any]:
    group = {
        "path": path,
        "files": [],
        "errors": [],
        "total_files": 0,
        "total_size": 0,
    }

    if not os.path.isdir(path):
        group["errors"].append("路径不存在或不是目录")
        return group

    for root, _, files in os.walk(path):
        for file_name in files:
            full_path = os.path.join(root, file_name)
            if not _file_matches_suffix(full_path, suffixes):
                continue
            try:
                file_info = _md5_file_from_disk(full_path)
            except OSError as exc:
                group["errors"].append("%s 读取失败: %s" % (full_path, exc))
                continue

            relative_path = os.path.relpath(full_path, path)
            group["files"].append(
                {
                    "relative_path": relative_path,
                    "full_path": full_path,
                    "md5": file_info["md5"],
                    "size": file_info["size"],
                    "created_at": file_info["created_at"],
                    "time_source": file_info["time_source"],
                }
            )
            group["total_files"] += 1
            group["total_size"] += file_info["size"]

    return group


def _build_find_filter(suffixes: List[str]) -> str:
    if not suffixes:
        return ""

    parts = []
    for suffix in suffixes:
        parts.append("-name %s" % shlex.quote("*" + suffix))
    return "\\( %s \\)" % " -o ".join(parts)


def _build_md5_scan_command(paths: List[str], suffixes: List[str]) -> str:
    path_args = " ".join(shlex.quote(path) for path in paths)
    find_filter = _build_find_filter(suffixes)
    script = r"""
for target in "$@"; do
  target_b64=$(printf '%s' "$target" | base64 | tr -d '\n')
  if [ ! -d "$target" ]; then
    err_b64=$(printf '%s' "路径不存在或不是目录" | base64 | tr -d '\n')
    printf '__PATH_ERROR__\t%s\t%s\n' "$target_b64" "$err_b64"
    continue
  fi

  find "$target" -type f __FIND_FILTER__ -print0 2>/dev/null | while IFS= read -r -d '' file; do
    md5=$(md5sum "$file" 2>/dev/null | awk '{print $1}')
    size=$(stat -c '%s' "$file" 2>/dev/null || echo 0)
    created_at=$(stat -c '%w' "$file" 2>/dev/null || echo "-")
    time_source="创建时间"

    if [ -z "$created_at" ] || [ "$created_at" = "-" ]; then
      created_at=$(stat -c '%y' "$file" 2>/dev/null || echo "-")
      time_source="修改时间"
    fi

    rel_path="${file#$target/}"
    rel_b64=$(printf '%s' "$rel_path" | base64 | tr -d '\n')
    full_b64=$(printf '%s' "$file" | base64 | tr -d '\n')
    time_b64=$(printf '%s' "$created_at" | base64 | tr -d '\n')
    source_b64=$(printf '%s' "$time_source" | base64 | tr -d '\n')

    if [ -z "$md5" ]; then
      md5="读取失败"
    fi

    printf '__FILE__\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$target_b64" "$rel_b64" "$full_b64" "$md5" "$size" "$time_b64" "$source_b64"
  done
done
"""
    script = script.replace("__FIND_FILTER__", find_filter)
    return "bash -lc {script} -- {paths}".format(script=shlex.quote(script), paths=path_args)


def _parse_md5_scan_output(output: str, paths: List[str]) -> List[Dict[str, Any]]:
    result_map: Dict[str, Dict[str, Any]] = {}
    for path in paths:
        result_map[path] = {
            "path": path,
            "files": [],
            "errors": [],
            "total_files": 0,
            "total_size": 0,
        }

    for line in output.splitlines():
        parts = line.split("\t")
        if not parts:
            continue

        if parts[0] == "__PATH_ERROR__" and len(parts) >= 3:
            path = _decode_base64_text(parts[1])
            message = _decode_base64_text(parts[2]) or "路径读取失败"
            bucket = result_map.setdefault(
                path,
                {
                    "path": path,
                    "files": [],
                    "errors": [],
                    "total_files": 0,
                    "total_size": 0,
                },
            )
            bucket["errors"].append(message)
            continue

        if parts[0] != "__FILE__" or len(parts) < 8:
            continue

        path = _decode_base64_text(parts[1])
        rel_path = _decode_base64_text(parts[2])
        full_path = _decode_base64_text(parts[3])
        md5_value = parts[4]
        try:
            size = int(parts[5])
        except ValueError:
            size = 0

        created_at = _decode_base64_text(parts[6])
        time_source = _decode_base64_text(parts[7]) or "创建时间"
        bucket = result_map.setdefault(
            path,
            {
                "path": path,
                "files": [],
                "errors": [],
                "total_files": 0,
                "total_size": 0,
            },
        )
        bucket["files"].append(
            {
                "relative_path": rel_path,
                "full_path": full_path,
                "md5": md5_value,
                "size": size,
                "created_at": created_at,
                "time_source": time_source,
            }
        )
        bucket["total_files"] += 1
        bucket["total_size"] += size

    return [result_map[path] for path in result_map]


def _backup_log_lines(log_file: str) -> List[str]:
    history_dir = "./%s/%s" % (LOG_DIR_NAME, LOG_HISTORY_DIR_NAME)
    # shell 里的 date +%Y%m%d_%H%M%S 也包含 %，如果继续用 Python 的 % 格式化，
    # Python 会把它误判为占位符，导致“生成脚本”接口直接抛异常。
    history_target = "{history_dir}/$(basename {log_file})_$(date +%Y%m%d_%H%M%S)".format(
        history_dir=history_dir,
        log_file=shlex.quote(log_file),
    )
    return [
        "if [ -f {log_file} ]; then".format(log_file=shlex.quote(log_file)),
        "  mv {log_file} {history_target}".format(
            log_file=shlex.quote(log_file),
            history_target=history_target,
        ),
        "fi",
    ]


def _build_configured_database_command(block: Dict[str, str], profile: ConnectionProfile) -> str:
    """根据当前环境生成远程数据库命令，不把数据库密码写入系统日志。"""
    profile.validate_database()
    return (
        "PGPASSWORD={password} /pgsoft/pg14.7/bin/psql "
        "-h {host} -p {port} -U {user} -d {database} -f {sql_file} &>> {log_file}"
    ).format(
        password=shlex.quote(profile.db_password or ""),
        host=shlex.quote(profile.db_host),
        port=profile.db_port,
        user=shlex.quote(profile.db_user),
        database=shlex.quote(block["database"]),
        sql_file=shlex.quote("./" + block["sql_file"]),
        log_file=shlex.quote(block["log_file"]),
    )


def _build_script_block(option_key: str, profile: ConnectionProfile) -> List[str]:
    block = SCRIPT_BLOCKS[option_key]
    lines = ['echo "执行%s"' % block["title"]]
    lines.extend(_backup_log_lines(block["log_file"]))
    if block.get("connection_type") == "configured_database":
        lines.append(_build_configured_database_command(block, profile))
    else:
        lines.append(block["command"])
    return lines


def _validate_custom_filename(value: Any, suffix: str, field_name: str) -> str:
    filename = str(value or "").strip()
    if not filename:
        raise ValueError("%s不能为空" % field_name)
    if len(filename) > 180:
        raise ValueError("%s不能超过 180 个字符" % field_name)
    if filename != posixpath.basename(filename) or "\\" in filename:
        raise ValueError("%s只能填写文件名，不能包含目录路径" % field_name)
    if "\n" in filename or "\r" in filename or "\x00" in filename:
        raise ValueError("%s包含不允许的字符" % field_name)
    if not filename.lower().endswith(suffix):
        raise ValueError("%s必须以 %s 结尾" % (field_name, suffix))
    return filename


def _validate_custom_text(value: Any, field_name: str) -> str:
    text_value = str(value or "").strip()
    if not text_value:
        raise ValueError("%s不能为空" % field_name)
    if len(text_value) > 128:
        raise ValueError("%s不能超过 128 个字符" % field_name)
    if "\n" in text_value or "\r" in text_value or "\x00" in text_value:
        raise ValueError("%s包含不允许的字符" % field_name)
    return text_value


def _normalize_custom_sql_option(item: Any, create_id: bool = False) -> Dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("自定义 SQL 配置格式不正确")

    option_id = str(item.get("id", "")).strip()
    if create_id and not option_id:
        option_id = uuid.uuid4().hex[:12]
    if not option_id or len(option_id) > 40 or not option_id.replace("-", "").isalnum():
        raise ValueError("自定义 SQL 配置 ID 不正确")

    sql_file = _validate_custom_filename(item.get("sql_file"), ".sql", "SQL 文件名")
    database = _validate_custom_text(item.get("database"), "数据库名")
    pg_host_value = item.get("pg_host")
    if not pg_host_value and not create_id:
        pg_host_value = "localhost"
    pg_host = _validate_custom_text(pg_host_value, "PG 地址")
    try:
        pg_port = int(item.get("pg_port", 5432))
    except (TypeError, ValueError) as exc:
        raise ValueError("PG 端口必须是数字") from exc
    if pg_port < 1 or pg_port > 65535:
        raise ValueError("PG 端口必须在 1 到 65535 之间")
    db_user = _validate_custom_text(item.get("db_user"), "数据库用户")
    db_password = str(item.get("db_password", ""))
    if create_id and not db_password:
        raise ValueError("PG 密码不能为空")
    if len(db_password) > 256 or "\n" in db_password or "\r" in db_password or "\x00" in db_password:
        raise ValueError("PG 密码包含不允许的字符或长度超过 256")
    default_log_file = "%s_execute_sql.txt" % os.path.splitext(sql_file)[0]
    log_file = _validate_custom_filename(item.get("log_file") or default_log_file, ".txt", "日志文件名")
    return {
        "id": option_id,
        "sql_file": sql_file,
        "database": database,
        "pg_host": pg_host,
        "pg_port": pg_port,
        "db_user": db_user,
        "db_password": db_password,
        "log_file": log_file,
    }


def _normalize_custom_sql_options(items: Any) -> List[Dict[str, Any]]:
    if items is None:
        return []
    if not isinstance(items, list):
        raise ValueError("自定义 SQL 配置必须是列表")
    if len(items) > MAX_CUSTOM_SQL_OPTIONS:
        raise ValueError("每个环境最多配置 %s 个自定义 SQL" % MAX_CUSTOM_SQL_OPTIONS)

    normalized = []
    seen_ids = set()
    seen_sql_files = set()
    seen_log_files = set()
    static_sql_files = set()
    for block in SCRIPT_BLOCKS.values():
        if block.get("sql_file"):
            static_sql_files.add(block["sql_file"].lower())
        for command_part in block.get("command", "").split():
            if command_part.startswith("./") and command_part.lower().endswith(".sql"):
                static_sql_files.add(posixpath.basename(command_part).lower())
    static_log_files = set(posixpath.basename(block["log_file"]).lower() for block in SCRIPT_BLOCKS.values())
    for item in items:
        option = _normalize_custom_sql_option(item)
        sql_name = option["sql_file"].lower()
        log_name = option["log_file"].lower()
        if option["id"] in seen_ids:
            raise ValueError("自定义 SQL 配置 ID 重复")
        if sql_name in seen_sql_files or sql_name in static_sql_files:
            raise ValueError("SQL 文件名已经存在: %s" % option["sql_file"])
        if log_name in seen_log_files or log_name in static_log_files:
            raise ValueError("日志文件名已经存在: %s" % option["log_file"])
        seen_ids.add(option["id"])
        seen_sql_files.add(sql_name)
        seen_log_files.add(log_name)
        normalized.append(option)
    return normalized


def _custom_sql_key(option_id: str) -> str:
    return CUSTOM_SQL_KEY_PREFIX + option_id


def _build_custom_script_block(option: Dict[str, Any]) -> List[str]:
    log_path = "./%s/%s" % (LOG_DIR_NAME, option["log_file"])
    password_prefix = ""
    if option.get("db_password"):
        password_prefix = "PGPASSWORD=%s " % shlex.quote(option["db_password"])
    command = (
        "{password_prefix}/pgsoft/pg14.7/bin/psql -h {pg_host} -p {pg_port} -U {db_user} "
        "-d {database} -f {sql_file} &>> {log_file}"
    ).format(
        password_prefix=password_prefix,
        pg_host=shlex.quote(option["pg_host"]),
        pg_port=option["pg_port"],
        db_user=shlex.quote(option["db_user"]),
        database=shlex.quote(option["database"]),
        sql_file=shlex.quote("./" + option["sql_file"]),
        log_file=shlex.quote(log_path),
    )
    lines = ['echo "执行%s"' % option["sql_file"]]
    lines.extend(_backup_log_lines(log_path))
    lines.append(command)
    return lines


def _build_script_content(
    selected: Any,
    profile: ConnectionProfile,
    custom_options: List[Dict[str, Any]],
) -> str:
    """组装完整脚本，类比 Java Service 中可独立单元测试的业务方法。"""
    lines = [
        "#!/usr/bin/env bash",
        "set -e",
        "mkdir -p ./%s ./%s/%s" % (LOG_DIR_NAME, LOG_DIR_NAME, LOG_HISTORY_DIR_NAME),
    ]
    for key in SCRIPT_ORDER:
        if key == "test":
            continue
        if key in selected:
            lines.extend(_build_script_block(key, profile))
    for custom_option in custom_options:
        if _custom_sql_key(custom_option["id"]) in selected:
            lines.extend(_build_custom_script_block(custom_option))
    if "test" in selected:
        lines.extend(_build_script_block("test", profile))
    return "\n".join(lines) + "\n"


def _mask_database_password_in_script(content: str, profile: ConnectionProfile) -> str:
    """脚本预览隐藏数据库密码；真实远程脚本保持可执行。"""
    passwords = [profile.db_password]
    passwords.extend(option.get("db_password") for option in profile.custom_sql_options)
    for password in passwords:
        if password:
            password_assignment = "PGPASSWORD=%s" % shlex.quote(str(password))
            content = content.replace(password_assignment, "PGPASSWORD='******'")
    return content


def _json_error(message: str, status_code: int) -> JSONResponse:
    return JSONResponse({"ok": False, "message": message}, status_code=status_code)


def _log_failure(event: str, reason: str, profile: ConnectionProfile = None, **kwargs: Any) -> None:
    payload = {"失败原因": reason}
    payload.update(kwargs)
    if profile is not None:
        payload["环境名称"] = profile.name
        payload["远程目录"] = profile.remote_dir
        payload["脚本名称"] = profile.script_name
    log_operation(event, False, **payload)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start_time = time.monotonic()
    logger.info("收到 HTTP 请求：方法=%s，请求路径=%s", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        logger.exception(
            "HTTP 请求处理失败：方法=%s，请求路径=%s，耗时=%s毫秒",
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = int((time.monotonic() - start_time) * 1000)
    logger.info(
        "HTTP 请求处理完成：方法=%s，请求路径=%s，状态码=%s，耗时=%s毫秒",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/md5", response_class=HTMLResponse)
def md5_page(request: Request):
    return templates.TemplateResponse("md5.html", {"request": request})


@app.get("/md5/remote", response_class=HTMLResponse)
def md5_remote_page(request: Request):
    return templates.TemplateResponse("md5_remote.html", {"request": request})


@app.get("/md5/local", response_class=HTMLResponse)
def md5_local_page(request: Request):
    return templates.TemplateResponse("md5_local.html", {"request": request})


@app.get("/md5-defaults")
def md5_defaults():
    settings_data = _load_md5_settings()
    remote_settings = settings_data["remote"]
    saved_paths = remote_settings.get("paths") or []
    saved_suffixes = remote_settings.get("suffixes", "")
    saved_connection = remote_settings.get("connection") or {}

    try:
        active_profile = _get_active_profile()
    except ValueError:
        active_profile = None

    if not saved_connection and active_profile is not None:
        saved_connection = {
            "name": active_profile.name,
            "ssh_host": active_profile.ssh_host,
            "ssh_port": active_profile.ssh_port,
            "ssh_user": active_profile.ssh_user,
            "ssh_password": active_profile.ssh_password or "",
            "remote_dir": active_profile.remote_dir,
        }

    if not saved_paths and active_profile is not None:
        saved_paths = remote_settings.get("paths_by_profile", {}).get(active_profile.name, [])

    if not saved_paths:
        if saved_connection.get("remote_dir"):
            saved_paths = [saved_connection["remote_dir"]]
        elif active_profile is not None:
            saved_paths = [active_profile.remote_dir]

    return {
        "ok": True,
        "profile": {
            "name": saved_connection.get("name", ""),
            "ssh_host": saved_connection.get("ssh_host", ""),
            "ssh_port": saved_connection.get("ssh_port", 22),
            "ssh_user": saved_connection.get("ssh_user", ""),
            "ssh_password": saved_connection.get("ssh_password", ""),
            "remote_dir": saved_connection.get("remote_dir", saved_paths[0] if saved_paths else ""),
        },
        "paths": saved_paths,
        "suffixes": saved_suffixes,
    }


@app.post("/md5-remote-settings")
def save_md5_remote_settings(payload: Dict[str, Any] = Body(...)):
    raw_paths = payload.get("paths", [])
    if not isinstance(raw_paths, list):
        return _json_error("paths 必须是数组", 400)

    paths = _normalize_unique_text_values(raw_paths)
    suffixes = _normalize_md5_suffixes(payload.get("suffixes", ""))
    try:
        profile = _md5_connection_from_payload(payload, paths)
        profile.validate()
    except ValueError as exc:
        _log_failure("save_md5_remote_settings", str(exc))
        return _json_error(str(exc), 400)

    if not paths:
        paths = [profile.remote_dir]

    _update_md5_settings(
        "remote",
        {
            "connection": {
                "name": profile.name,
                "ssh_host": profile.ssh_host,
                "ssh_port": profile.ssh_port,
                "ssh_user": profile.ssh_user,
                "ssh_password": profile.ssh_password or "",
                "remote_dir": profile.remote_dir,
            },
            "paths": paths,
            "suffixes": _suffixes_to_text(suffixes),
        },
    )
    log_operation(
        "save_md5_remote_settings",
        True,
        环境名称=profile.name,
        路径数量=len(paths),
        文件后缀=_suffixes_to_text(suffixes),
    )
    return {
        "ok": True,
        "message": "MD5 远程配置已保存",
        "profile": _profile_to_dict(profile),
        "paths": paths,
        "suffixes": _suffixes_to_text(suffixes),
    }


@app.get("/md5-local-settings")
def md5_local_settings():
    settings_data = _load_md5_settings()
    return {
        "ok": True,
        "paths": settings_data["local"].get("paths", []),
        "suffixes": settings_data["local"].get("suffixes", ""),
    }


@app.post("/md5-local-settings")
def save_md5_local_settings(payload: Dict[str, Any] = Body(...)):
    suffixes = _normalize_md5_suffixes(payload.get("suffixes", ""))
    raw_paths = payload.get("paths", [])
    paths = _normalize_unique_text_values(raw_paths)

    _update_md5_settings(
        "local",
        {
            "paths": paths,
            "suffixes": _suffixes_to_text(suffixes),
        },
    )
    log_operation(
        "save_md5_local_settings",
        True,
        路径数量=len(paths),
        文件后缀=_suffixes_to_text(suffixes),
    )
    return {
        "ok": True,
        "message": "MD5 本地配置已保存",
        "paths": paths,
        "suffixes": _suffixes_to_text(suffixes),
    }


@app.post("/md5-scan")
def md5_scan(payload: Dict[str, Any] = Body(...)):
    raw_paths = payload.get("paths", [])
    if not isinstance(raw_paths, list):
        return _json_error("paths 必须是数组", 400)

    paths = _normalize_unique_text_values(raw_paths)

    if not paths:
        return _json_error("请至少填写一个远程路径", 400)
    if len(paths) > 20:
        return _json_error("一次最多统计 20 个路径", 400)

    suffixes = _normalize_md5_suffixes(payload.get("suffixes", ""))
    try:
        if payload.get("connection") or payload.get("profile"):
            profile = _md5_connection_from_payload(payload, paths)
        else:
            profile = _md5_saved_or_default_connection(paths)
        client = _connect_ssh(profile)
    except ValueError as exc:
        _log_failure("md5_scan", str(exc))
        return _json_error(str(exc), 400)
    except Exception as exc:
        logger.exception("MD5 统计前，建立 SSH 连接失败")
        _log_failure("md5_scan", str(exc))
        return _json_error("SSH 连接失败: %s" % exc, 500)

    try:
        command = _build_md5_scan_command(paths, suffixes)
        logger.info(
            "开始执行 MD5 统计：环境=%s，路径=%s，文件后缀=%s",
            profile.name,
            ",".join(paths),
            _suffixes_to_text(suffixes) or "全部",
        )
        result = _run_remote_command(client, command)
    except Exception as exc:
        logger.exception("MD5 统计执行失败：%s", _profile_summary(profile))
        _log_failure("md5_scan", str(exc), profile, 路径=",".join(paths))
        return _json_error("MD5 统计失败: %s" % exc, 500)
    finally:
        client.close()

    if result["exit_status"] != 0:
        _log_failure(
            "md5_scan",
            result["stderr"] or "远程命令执行失败",
            profile,
            路径=",".join(paths),
        )
        return JSONResponse(
            {
                "ok": False,
                "message": result["stderr"] or "远程命令执行失败",
                "output": result["stdout"],
                "exit_status": result["exit_status"],
            },
            status_code=500,
        )

    scan_results = _parse_md5_scan_output(result["stdout"], paths)
    total_files = sum(item["total_files"] for item in scan_results)
    total_size = sum(item["total_size"] for item in scan_results)
    logger.info(
        "MD5 统计完成：环境=%s，路径数=%s，文件总数=%s",
        profile.name,
        len(paths),
        total_files,
    )
    log_operation(
        "md5_scan",
        True,
        环境名称=profile.name,
        路径数量=len(paths),
        文件后缀=_suffixes_to_text(suffixes) or "全部",
        文件总数=total_files,
        文件总大小=total_size,
    )
    return {
        "ok": True,
        "profile_name": profile.name,
        "results": scan_results,
        "total_files": total_files,
        "total_size": total_size,
        "suffixes": _suffixes_to_text(suffixes),
    }


@app.post("/md5-local-scan")
def md5_local_scan(
    files: Optional[List[UploadFile]] = File(default=None),
    group_names: List[str] = Form(default=[]),
    modified_ats: List[str] = Form(default=[]),
    suffixes: str = Form(default=""),
    manual_paths: str = Form(default="[]"),
):
    files = files or []
    normalized_suffixes = _normalize_md5_suffixes(suffixes)
    manual_path_values = _parse_manual_local_paths(manual_paths)
    if not files and not manual_path_values:
        return _json_error("请选择本地目录，或手动填写本地目录路径", 400)

    groups: Dict[str, Dict[str, Any]] = {}
    group_order: List[str] = []
    total_size = 0
    total_files = 0

    manual_results = []
    for path in manual_path_values:
        group = _scan_manual_local_path(path, normalized_suffixes)
        manual_results.append(group)
        total_files += group["total_files"]
        total_size += group["total_size"]

    for index, upload in enumerate(files):
        file_name = upload.filename or ""
        if not file_name or not _file_matches_suffix(file_name, normalized_suffixes):
            continue

        group_name = group_names[index] if index < len(group_names) else ""
        group_name = str(group_name).strip() or "本地选择目录"
        if group_name not in groups:
            groups[group_name] = {
                "path": group_name,
                "files": [],
                "errors": [],
                "total_files": 0,
                "total_size": 0,
            }
            group_order.append(group_name)

        md5 = hashlib.md5()
        size = 0
        while True:
            chunk = upload.file.read(FILE_READ_BUFFER_SIZE)
            if not chunk:
                break
            size += len(chunk)
            md5.update(chunk)

        modified_at = modified_ats[index] if index < len(modified_ats) else ""
        groups[group_name]["files"].append(
            {
                "relative_path": _normalize_rel_path(file_name),
                "full_path": _normalize_rel_path(file_name),
                "md5": md5.hexdigest(),
                "size": size,
                "created_at": modified_at or "-",
                "time_source": "本地文件修改时间",
            }
        )
        groups[group_name]["total_files"] += 1
        groups[group_name]["total_size"] += size
        total_files += 1
        total_size += size

    results = manual_results + [groups[name] for name in group_order]
    log_operation(
        "md5_local_scan",
        True,
        路径数量=len(results),
        文件总数=total_files,
        文件总大小=total_size,
        文件后缀=_suffixes_to_text(normalized_suffixes) or "全部",
    )
    return {
        "ok": True,
        "results": results,
        "total_files": total_files,
        "total_size": total_size,
        "suffixes": _suffixes_to_text(normalized_suffixes),
    }


@app.get("/config-profiles")
def list_config_profiles():
    data = profile_store.list_profiles()
    profiles = [_profile_to_dict(profile) for profile in profile_store.get_profiles()]
    total = len(profiles)
    logger.info("已读取环境配置列表：当前环境=%s，配置总数=%s", data.get("active"), total)
    log_operation("list_profiles", True, 当前环境=data.get("active"), 配置总数=total)
    return {"ok": True, "active": data.get("active"), "profiles": profiles}


@app.post("/config-profiles")
def save_config_profile(payload: Dict[str, Any] = Body(...)):
    try:
        profile = ConnectionProfile(
            name=str(payload.get("name", "")).strip(),
            ssh_host=str(payload.get("ssh_host", "")).strip(),
            ssh_port=int(payload.get("ssh_port", 22)),
            ssh_user=str(payload.get("ssh_user", "")).strip(),
            ssh_password=str(payload.get("ssh_password", "")).strip() or None,
            remote_dir=str(payload.get("remote_dir", "")).strip(),
            script_name=str(payload.get("script_name", "224.sh")).strip() or "224.sh",
            default_local_dir=str(payload.get("default_local_dir", "")).strip(),
            db_host=str(payload.get("db_host", "")).strip(),
            db_port=int(payload.get("db_port", 5432)),
            db_user=str(payload.get("db_user", "")).strip(),
            db_password=str(payload.get("db_password", "")).strip() or None,
            custom_sql_options=_normalize_custom_sql_options(payload.get("custom_sql_options", [])),
        )
        profile_store.save_profile(profile)
        logger.info("环境配置保存成功：%s", _profile_summary(profile))
        log_operation("save_profile", True, 环境名称=profile.name, 远程目录=profile.remote_dir)
        return {
            "ok": True,
            "message": "配置已保存",
            "profile": _profile_to_dict(profile),
        }
    except ValueError as exc:
        _log_failure("save_profile", str(exc))
        return _json_error(str(exc), 400)


@app.post("/custom-sql-options")
def add_custom_sql_option(payload: Dict[str, Any] = Body(...)):
    try:
        profile = _get_active_profile()
        current_options = _normalize_custom_sql_options(profile.custom_sql_options)
        if len(current_options) >= MAX_CUSTOM_SQL_OPTIONS:
            raise ValueError("每个环境最多配置 %s 个自定义 SQL" % MAX_CUSTOM_SQL_OPTIONS)
        new_option = _normalize_custom_sql_option(payload, create_id=True)
        profile.custom_sql_options = _normalize_custom_sql_options(current_options + [new_option])
        profile_store.save_profile(profile)
    except ValueError as exc:
        _log_failure("add_custom_sql", str(exc))
        return _json_error(str(exc), 400)

    logger.info(
        "自定义 SQL 新增成功：环境=%s，SQL文件=%s，PG地址=%s，PG端口=%s，数据库=%s，数据库用户=%s，日志文件=%s",
        profile.name,
        new_option["sql_file"],
        new_option["pg_host"],
        new_option["pg_port"],
        new_option["database"],
        new_option["db_user"],
        new_option["log_file"],
    )
    log_operation(
        "add_custom_sql",
        True,
        环境名称=profile.name,
        SQL文件=new_option["sql_file"],
        PG地址=new_option["pg_host"],
        PG端口=new_option["pg_port"],
        数据库=new_option["database"],
        日志文件=new_option["log_file"],
    )
    return {
        "ok": True,
        "message": "自定义常规 SQL 已加入当前环境",
        "profile_name": profile.name,
        "option": new_option,
    }


@app.delete("/custom-sql-options/{option_id}")
def delete_custom_sql_option(option_id: str):
    try:
        profile = _get_active_profile()
        current_options = _normalize_custom_sql_options(profile.custom_sql_options)
        target = None
        remaining = []
        for option in current_options:
            if option["id"] == option_id:
                target = option
            else:
                remaining.append(option)
        if target is None:
            raise ValueError("自定义 SQL 配置不存在")
        profile.custom_sql_options = remaining
        profile_store.save_profile(profile)
    except ValueError as exc:
        _log_failure("delete_custom_sql", str(exc))
        return _json_error(str(exc), 400)

    logger.info("自定义 SQL 删除成功：环境=%s，SQL文件=%s", profile.name, target["sql_file"])
    log_operation(
        "delete_custom_sql",
        True,
        环境名称=profile.name,
        SQL文件=target["sql_file"],
        日志文件=target["log_file"],
    )
    return {
        "ok": True,
        "message": "自定义常规 SQL 已删除",
        "profile_name": profile.name,
    }


@app.post("/config-profiles/active")
def set_active_profile(payload: Dict[str, Any] = Body(...)):
    profile_name = str(payload.get("name", "")).strip()
    try:
        profile_store.set_active(profile_name)
        logger.info("当前环境切换成功：环境名称=%s", profile_name)
        log_operation("set_active_profile", True, 环境名称=profile_name)
        return {"ok": True, "message": "当前配置已切换"}
    except ValueError as exc:
        _log_failure("set_active_profile", str(exc), profile_name=profile_name)
        return _json_error(str(exc), 400)


@app.delete("/config-profiles/{profile_name}")
def delete_profile(profile_name: str):
    try:
        profile_store.delete_profile(profile_name)
        logger.info("环境配置删除成功：环境名称=%s", profile_name)
        log_operation("delete_profile", True, 环境名称=profile_name)
        return {"ok": True, "message": "配置已删除"}
    except ValueError as exc:
        _log_failure("delete_profile", str(exc), profile_name=profile_name)
        return _json_error(str(exc), 400)


@app.post("/connection-test")
def test_connection():
    try:
        profile = _get_active_profile()
        client = _connect_ssh(profile)
    except ValueError as exc:
        _log_failure("test_connection", str(exc))
        return _json_error(str(exc), 400)
    except Exception as exc:
        logger.exception("环境连接测试失败，SSH 会话建立前发生异常")
        _log_failure("test_connection", str(exc))
        return JSONResponse(
            {"ok": False, "connected": False, "message": "连接失败: %s" % exc},
            status_code=500,
        )

    try:
        logger.info("环境连接测试成功：%s", _profile_summary(profile))
        log_operation("test_connection", True, 环境名称=profile.name, 远程目录=profile.remote_dir)
        return {
            "ok": True,
            "connected": True,
            "message": "当前环境连接正常",
            "profile_name": profile.name,
        }
    finally:
        client.close()


@app.get("/remote-summary")
def remote_summary():
    try:
        profile = _get_active_profile()
        client = _connect_ssh(profile)
    except ValueError as exc:
        _log_failure("remote_summary", str(exc))
        return _json_error(str(exc), 400)
    except Exception as exc:
        logger.exception("读取远程目录摘要失败，建立 SSH 连接时发生异常")
        _log_failure("remote_summary", str(exc))
        return _json_error("SSH 连接失败: %s" % exc, 500)

    try:
        sftp = client.open_sftp()
        try:
            counts = _count_remote_entries(sftp, profile.remote_dir)
            entries = _list_remote_top_entries(sftp, profile.remote_dir)
            logger.info(
                "远程目录摘要：环境=%s，目录=%s，文件数=%s，子目录数=%s，顶层条目数=%s",
                profile.name,
                profile.remote_dir,
                counts["total_files"],
                counts["total_dirs"],
                len(entries),
            )
            log_operation(
                "remote_summary",
                True,
                环境名称=profile.name,
                远程目录=profile.remote_dir,
                文件总数=counts["total_files"],
                子目录总数=counts["total_dirs"],
                顶层条目数=len(entries),
            )
            return {
                "ok": True,
                "profile_name": profile.name,
                "remote_dir": profile.remote_dir,
                "script_name": profile.script_name,
                "total_files": counts["total_files"],
                "total_dirs": counts["total_dirs"],
                "entries": entries,
            }
        finally:
            sftp.close()
    except Exception as exc:
        logger.exception("读取远程目录摘要失败：%s", _profile_summary(profile))
        _log_failure("remote_summary", str(exc), profile)
        return _json_error("读取远程目录信息失败: %s" % exc, 500)
    finally:
        client.close()


@app.get("/system-logs")
def system_logs(log_name: str = Query("app.log"), lines: int = Query(SYSTEM_LOG_LINES)):
    safe_lines = max(20, min(lines, 300))
    if log_name not in ("app.log", "operations.log"):
        return _json_error("日志类型不存在", 400)

    logger.info("读取系统日志文件：文件名=%s，行数=%s", log_name, safe_lines)
    log_data = tail_log_file(settings.log_dir, log_name, safe_lines)
    return {
        "ok": True,
        "log_name": log_data["log_name"],
        "exists": log_data["exists"],
        "content": log_data["content"],
        "log_dir": settings.log_dir,
        "lines": safe_lines,
    }


@app.post("/upload")
def upload_file(files: List[UploadFile] = File(...)):
    if not files:
        _log_failure("upload_dir", "未选择文件或目录")
        return _json_error("未选择文件或目录", 400)

    try:
        profile = _get_active_profile()
        client = _connect_ssh(profile)
    except ValueError as exc:
        _log_failure("upload_dir", str(exc))
        return _json_error(str(exc), 400)
    except Exception as exc:
        logger.exception("上传目录前，建立 SSH 连接失败")
        _log_failure("upload_dir", str(exc))
        return _json_error("SSH 连接失败: %s" % exc, 500)

    uploaded = 0
    try:
        sftp = client.open_sftp()
        try:
            logger.info(
                "开始上传目录内容：环境=%s，目标目录=%s，待上传文件数=%s",
                profile.name,
                profile.remote_dir,
                len(files),
            )
            _ensure_remote_dir(sftp, profile.remote_dir)
            for upload in files:
                raw_name = upload.filename or ""
                if not raw_name:
                    continue

                rel_path = _normalize_rel_path(raw_name)
                rel_path = _strip_top_level_dir(rel_path)
                if not rel_path:
                    continue

                remote_path = _remote_path(profile, rel_path)
                remote_dir = posixpath.dirname(remote_path)
                _ensure_remote_dir(sftp, remote_dir)

                upload.file.seek(0)
                with sftp.open(remote_path, "wb") as remote_file:
                    shutil.copyfileobj(upload.file, remote_file)
                uploaded += 1
                logger.info("文件上传完成：本地条目=%s，远程路径=%s", raw_name, remote_path)
        finally:
            sftp.close()
    except Exception as exc:
        logger.exception("上传目录失败：%s", _profile_summary(profile))
        _log_failure("upload_dir", str(exc), profile)
        return _json_error("上传失败: %s" % exc, 500)
    finally:
        client.close()

    logger.info("目录上传结束：环境=%s，成功上传文件数=%s", profile.name, uploaded)
    log_operation(
        "upload_dir",
        True,
        环境名称=profile.name,
        远程目录=profile.remote_dir,
        上传文件数=uploaded,
    )
    return {
        "ok": True,
        "message": "已上传 %s 个文件到 %s" % (uploaded, profile.remote_dir),
        "uploaded_files": uploaded,
        "remote_dir": profile.remote_dir,
    }


@app.post("/clear-dir")
def clear_remote_dir():
    try:
        profile = _get_active_profile()
        client = _connect_ssh(profile)
    except ValueError as exc:
        _log_failure("clear_remote_dir", str(exc))
        return _json_error(str(exc), 400)
    except Exception as exc:
        logger.exception("清空远程目录前，建立 SSH 连接失败")
        _log_failure("clear_remote_dir", str(exc))
        return _json_error("SSH 连接失败: %s" % exc, 500)

    try:
        sftp = client.open_sftp()
        try:
            logger.info(
                "开始清空远程目录：环境=%s，目标目录=%s",
                profile.name,
                profile.remote_dir,
            )
            removed = _clear_remote_dir(sftp, profile.remote_dir)
        finally:
            sftp.close()
    except Exception as exc:
        logger.exception("清空远程目录失败：%s", _profile_summary(profile))
        _log_failure("clear_remote_dir", str(exc), profile)
        return _json_error("清除目录失败: %s" % exc, 500)
    finally:
        client.close()

    logger.info("远程目录清空完成：环境=%s，删除条目数=%s", profile.name, removed)
    log_operation(
        "clear_remote_dir",
        True,
        环境名称=profile.name,
        远程目录=profile.remote_dir,
        删除条目数=removed,
    )
    return {
        "ok": True,
        "message": "目录已清空，log 目录和历史备份已保留",
        "removed": removed,
        "remote_dir": profile.remote_dir,
    }


@app.post("/generate")
def generate_script(options: List[str] = Form(default=[])):
    if not options:
        _log_failure("generate_script", "请至少选择一个选项")
        return _json_error("请至少选择一个选项", 400)

    try:
        profile = _get_active_profile()
        custom_options = _normalize_custom_sql_options(profile.custom_sql_options)
    except ValueError as exc:
        _log_failure("generate_script", str(exc))
        return _json_error(str(exc), 400)

    custom_options_by_key = {_custom_sql_key(item["id"]): item for item in custom_options}
    allowed_options = set(SCRIPT_BLOCKS.keys()) | set(custom_options_by_key.keys())
    unknown_options = sorted(set(options) - allowed_options)
    if unknown_options:
        message = "存在无法识别的 SQL 选项: %s" % ", ".join(unknown_options)
        _log_failure("generate_script", message, profile)
        return _json_error(message, 400)

    selected = set(options)
    try:
        content = _build_script_content(selected, profile, custom_options)
    except ValueError as exc:
        logger.warning("生成脚本参数校验失败：环境=%s，原因=%s", profile.name, exc)
        _log_failure("generate_script", str(exc), profile, 选中项=",".join(sorted(selected)))
        return _json_error(str(exc), 400)
    try:
        client = _connect_ssh(profile)
    except ValueError as exc:
        _log_failure("generate_script", str(exc), profile, 选中项=",".join(sorted(selected)))
        return _json_error(str(exc), 400)
    except Exception as exc:
        logger.exception("生成脚本前，建立 SSH 连接失败")
        _log_failure("generate_script", str(exc))
        return _json_error("SSH 连接失败: %s" % exc, 500)

    try:
        sftp = client.open_sftp()
        try:
            _ensure_remote_dir(sftp, profile.remote_dir)
            remote_path = _remote_path(profile, profile.script_name)
            logger.info(
                "开始生成脚本：环境=%s，脚本路径=%s，选中项=%s",
                profile.name,
                remote_path,
                ",".join(sorted(selected)),
            )
            _write_remote_file(sftp, remote_path, content.encode("utf-8"))
        finally:
            sftp.close()

        chmod_command = "cd {remote_dir} && chmod +x {script_name}".format(
            remote_dir=shlex.quote(profile.remote_dir),
            script_name=shlex.quote("./" + profile.script_name),
        )
        chmod_result = _run_remote_command(client, chmod_command)
        if chmod_result["exit_status"] != 0:
            _log_failure(
                "generate_script",
                chmod_result["stderr"] or "chmod 执行失败",
                profile,
                选中项=",".join(sorted(selected)),
            )
            return _json_error(chmod_result["stderr"] or "chmod 执行失败", 500)
    except Exception as exc:
        logger.exception("生成脚本失败：%s", _profile_summary(profile))
        _log_failure("generate_script", str(exc), profile, 选中项=",".join(sorted(selected)))
        return _json_error("生成脚本失败: %s" % exc, 500)
    finally:
        client.close()

    logger.info(
        "脚本生成成功：环境=%s，脚本=%s，选中项=%s",
        profile.name,
        remote_path,
        ",".join(sorted(selected)),
    )
    log_operation(
        "generate_script",
        True,
        环境名称=profile.name,
        远程目录=profile.remote_dir,
        脚本名称=profile.script_name,
        选中项=",".join(sorted(selected)),
    )
    return {"ok": True, "message": "脚本已生成: %s" % remote_path}


@app.post("/run")
def run_script():
    try:
        profile = _get_active_profile()
        remote_path = _remote_path(profile, profile.script_name)
        client = _connect_ssh(profile)
    except ValueError as exc:
        _log_failure("run_script", str(exc))
        return _json_error(str(exc), 400)
    except Exception as exc:
        logger.exception("执行脚本前，建立 SSH 连接失败")
        _log_failure("run_script", str(exc))
        return _json_error("SSH 连接失败: %s" % exc, 500)

    try:
        command = "cd {remote_dir} && bash {script_name}".format(
            remote_dir=shlex.quote(profile.remote_dir),
            script_name=shlex.quote("./" + profile.script_name),
        )
        logger.info(
            "准备执行脚本：环境=%s，脚本路径=%s，执行命令=%s",
            profile.name,
            remote_path,
            command,
        )
        result = _run_remote_command(client, command)
    except Exception as exc:
        logger.exception("执行脚本失败：%s", _profile_summary(profile))
        _log_failure("run_script", str(exc), profile)
        return _json_error("脚本执行失败: %s" % exc, 500)
    finally:
        client.close()

    if result["exit_status"] != 0:
        _log_failure(
            "run_script",
            result["stderr"] or "脚本执行失败",
            profile,
            执行命令=command,
            退出码=result["exit_status"],
        )
        return JSONResponse(
            {
                "ok": False,
                "message": result["stderr"] or "脚本执行失败",
                "output": result["stdout"],
                "command": command,
                "exit_status": result["exit_status"],
            },
            status_code=500,
        )

    log_operation(
        "run_script",
        True,
        环境名称=profile.name,
        远程目录=profile.remote_dir,
        脚本名称=profile.script_name,
        执行命令=command,
        退出码=result["exit_status"],
    )
    return {
        "ok": True,
        "message": "脚本执行完成",
        "output": result["stdout"],
        "command": command,
        "exit_status": result["exit_status"],
    }


@app.get("/logs")
def list_logs(scope: str = Query("current")):
    log_scope = scope if scope in ("current", "history") else "current"
    try:
        profile = _get_active_profile()
        client = _connect_ssh(profile)
    except ValueError as exc:
        _log_failure("list_remote_logs", str(exc))
        return _json_error(str(exc), 400)
    except Exception as exc:
        logger.exception("读取远程日志前，建立 SSH 连接失败")
        _log_failure("list_remote_logs", str(exc))
        return _json_error("SSH 连接失败: %s" % exc, 500)

    try:
        sftp = client.open_sftp()
        try:
            log_dir = _remote_path(profile, LOG_DIR_NAME)
            if log_scope == "history":
                log_dir = posixpath.join(log_dir, LOG_HISTORY_DIR_NAME)

            try:
                entries = sftp.listdir_attr(log_dir)
            except FileNotFoundError:
                log_operation(
                    "list_remote_logs",
                    True,
                    环境名称=profile.name,
                    日志范围=log_scope,
                    日志文件数=0,
                )
                return {"ok": True, "scope": log_scope, "log_dir": log_dir, "logs": []}

            files = []
            for entry in entries:
                if not stat.S_ISDIR(entry.st_mode):
                    files.append(entry)

            files = sorted(files, key=lambda entry: entry.st_mtime, reverse=True)
            logs = []
            for entry in files:
                path = posixpath.join(log_dir, entry.filename)
                try:
                    with sftp.open(path, "rb") as log_file:
                        content = _decode_text_bytes(log_file.read())
                except IOError as exc:
                    content = "读取失败: %s" % exc

                logs.append(
                    {
                        "name": entry.filename,
                        "content": content,
                        "modified_at": datetime.fromtimestamp(entry.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

            logger.info(
                "远程日志读取完成：环境=%s，日志范围=%s，日志目录=%s，日志文件数=%s",
                profile.name,
                log_scope,
                log_dir,
                len(logs),
            )
            log_operation(
                "list_remote_logs",
                True,
                环境名称=profile.name,
                日志范围=log_scope,
                日志目录=log_dir,
                日志文件数=len(logs),
            )
            return {"ok": True, "scope": log_scope, "log_dir": log_dir, "logs": logs}
        finally:
            sftp.close()
    except Exception as exc:
        logger.exception("读取远程日志失败：%s", _profile_summary(profile))
        _log_failure("list_remote_logs", str(exc), profile)
        return _json_error("读取日志失败: %s" % exc, 500)
    finally:
        client.close()


@app.get("/script-preview")
def script_preview():
    try:
        profile = _get_active_profile()
        client = _connect_ssh(profile)
    except ValueError as exc:
        _log_failure("script_preview", str(exc))
        return _json_error(str(exc), 400)
    except Exception as exc:
        logger.exception("读取脚本预览前，建立 SSH 连接失败")
        _log_failure("script_preview", str(exc))
        return _json_error("SSH 连接失败: %s" % exc, 500)

    try:
        sftp = client.open_sftp()
        try:
            script_path = _remote_path(profile, profile.script_name)
            try:
                script_stat = sftp.stat(script_path)
            except IOError:
                log_operation("script_preview", True, 环境名称=profile.name, 是否存在=False)
                return {"ok": True, "exists": False, "content": "", "modified_at": ""}

            with sftp.open(script_path, "rb") as script_file:
                content = _decode_text_bytes(script_file.read())
            content = _mask_database_password_in_script(content, profile)

            modified_at = datetime.fromtimestamp(script_stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            logger.info(
                "脚本预览读取成功：环境=%s，脚本=%s，更新时间=%s",
                profile.name,
                script_path,
                modified_at,
            )
            log_operation(
                "script_preview",
                True,
                环境名称=profile.name,
                是否存在=True,
                脚本名称=profile.script_name,
                更新时间=modified_at,
            )
            return {
                "ok": True,
                "exists": True,
                "script_name": profile.script_name,
                "content": content,
                "modified_at": modified_at,
            }
        finally:
            sftp.close()
    except Exception as exc:
        logger.exception("读取脚本预览失败：%s", _profile_summary(profile))
        _log_failure("script_preview", str(exc), profile)
        return _json_error("读取脚本失败: %s" % exc, 500)
    finally:
        client.close()
