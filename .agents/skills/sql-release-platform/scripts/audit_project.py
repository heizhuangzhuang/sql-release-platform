#!/usr/bin/env python3
"""在不连接远程服务器的情况下审计 SQL 发布执行台项目。"""

import argparse
import ast
import io
import re
import sys
import tokenize
from pathlib import Path


REQUIRED_FILES = [
    "main.py",
    "config.py",
    "logging_setup.py",
    "storage_utils.py",
    "requirements.txt",
    "start.sh",
    "start_uvicorn.sh",
    "templates/index.html",
    "templates/md5.html",
    "templates/md5_local.html",
    "templates/md5_remote.html",
    "tests/test_core.py",
    "tests/test_frontend_contract.py",
]

PYTHON_FILES = [
    "main.py",
    "config.py",
    "logging_setup.py",
    "storage_utils.py",
    "tests/test_core.py",
    "tests/test_frontend_contract.py",
]

REQUIRED_ROUTES = [
    "/upload",
    "/clear-dir",
    "/generate",
    "/run",
    "/logs",
    "/script-preview",
    "/connection-test",
    "/custom-sql-options",
    "/md5/local",
    "/md5/remote",
    "/md5-local-scan",
    "/md5-scan",
]

REQUIRED_IGNORES = [
    ".env",
    ".venv/",
    "profiles.json",
    "md5_settings.json",
    "runtime_logs/",
]


def parse_args():
    parser = argparse.ArgumentParser(description="检查 SQL 发布执行台项目结构和基础规范")
    parser.add_argument("--project", required=True, help="项目根目录")
    return parser.parse_args()


def report(ok, message):
    prefix = "通过" if ok else "失败"
    print("[%s] %s" % (prefix, message))
    return ok


def code_without_strings_or_comments(source):
    """保留代码标记，排除字符串和注释，避免把内嵌 Shell 误判成 Python 语法。"""
    tokens = []
    try:
        generated = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in generated:
            if token.type in (tokenize.STRING, tokenize.COMMENT):
                tokens.append((token.type, ""))
            else:
                tokens.append((token.type, token.string))
        return tokenize.untokenize(tokens)
    except (IndentationError, tokenize.TokenError):
        return source


def main():
    args = parse_args()
    root = Path(args.project).expanduser().resolve()
    all_ok = True

    all_ok = report(root.is_dir(), "项目目录存在：%s" % root) and all_ok
    if not root.is_dir():
        return 1

    for relative_path in REQUIRED_FILES:
        exists = (root / relative_path).is_file()
        all_ok = report(exists, "必需文件 %s" % relative_path) and all_ok

    for relative_path in PYTHON_FILES:
        source = root / relative_path
        if not source.is_file():
            continue
        try:
            # 类似 Java 只做编译检查：在内存中解析，不向被检查项目写入 __pycache__。
            ast.parse(
                source.read_text(encoding="utf-8"),
                filename=str(source),
                feature_version=8,
            )
            report(True, "Python 3.8 语法 %s" % relative_path)
        except (SyntaxError, UnicodeError) as exc:
            report(False, "Python 语法 %s：%s" % (relative_path, exc))
            all_ok = False

    main_text = (root / "main.py").read_text(encoding="utf-8") if (root / "main.py").is_file() else ""
    for route in REQUIRED_ROUTES:
        found = ('"%s"' % route) in main_text
        all_ok = report(found, "接口 %s" % route) and all_ok

    modern_patterns = [
        (r"\b(?:list|dict|set|tuple)\s*\[", "发现 Python 3.9+ 内置泛型"),
        (r"\bmatch\s+[^:\n]+:", "发现 Python 3.10+ match 语法"),
        (
            r"\b[A-Za-z_][A-Za-z0-9_]*\s*\|\s*(?:None|[A-Za-z_])",
            "发现 Python 3.10+ 联合类型语法",
        ),
    ]
    python_text = "\n".join(
        (root / relative_path).read_text(encoding="utf-8")
        for relative_path in PYTHON_FILES
        if (root / relative_path).is_file()
    )
    python_code = code_without_strings_or_comments(python_text)
    for pattern, message in modern_patterns:
        compatible = re.search(pattern, python_code) is None
        all_ok = (
            report(
                compatible,
                message if not compatible else "未发现对应的高版本 Python 语法",
            )
            and all_ok
        )

    gitignore = (root / ".gitignore").read_text(encoding="utf-8") if (root / ".gitignore").is_file() else ""
    for ignored in REQUIRED_IGNORES:
        found = ignored in gitignore
        all_ok = report(found, ".gitignore 包含 %s" % ignored) and all_ok

    for template_name in (
        "index.html",
        "md5.html",
        "md5_local.html",
        "md5_remote.html",
    ):
        template_path = root / "templates" / template_name
        if not template_path.is_file():
            continue
        template_text = template_path.read_text(encoding="utf-8")
        element_ids = re.findall(r'\bid=["\']([^"\']+)["\']', template_text)
        duplicate_ids = sorted(set(item for item in element_ids if element_ids.count(item) > 1))
        all_ok = (
            report(
                not duplicate_ids,
                "页面 %s 不存在重复 ID" % template_name
                if not duplicate_ids
                else "页面 %s 存在重复 ID: %s" % (template_name, ", ".join(duplicate_ids)),
            )
            and all_ok
        )

    sensitive_files = [".env", "profiles.json", "md5_settings.json"]
    present_runtime = [name for name in sensitive_files if (root / name).exists()]
    if present_runtime:
        report(
            True,
            "检测到本地运行配置（允许存在，但禁止提交）：%s" % ", ".join(present_runtime),
        )

    if all_ok:
        print("审计完成：基础检查全部通过。未执行 SSH、上传、清理或 SQL。")
        return 0

    print("审计完成：存在失败项，请修复后重新检查。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
