#!/usr/bin/env python3
"""使用 Skill 内置的安全模板创建全新的 SQL 发布执行台项目。"""

import argparse
import shutil
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="从 Skill 模板创建 SQL 发布执行台项目")
    parser.add_argument("--destination", required=True, help="新项目目录，必须不存在或为空")
    return parser.parse_args()


def main():
    args = parse_args()
    skill_root = Path(__file__).resolve().parent.parent
    template_dir = skill_root / "assets" / "project-template"
    destination = Path(args.destination).expanduser().resolve()

    if not template_dir.is_dir():
        print("创建失败：Skill 中缺少项目模板：%s" % template_dir, file=sys.stderr)
        return 1

    if destination.exists() and any(destination.iterdir()):
        print("创建失败：目标目录不是空目录：%s" % destination, file=sys.stderr)
        return 2

    destination.mkdir(parents=True, exist_ok=True)
    for source in template_dir.iterdir():
        target = destination / source.name
        if source.is_dir():
            shutil.copytree(str(source), str(target))
        else:
            shutil.copy2(str(source), str(target))

    print("创建成功：%s" % destination)
    print("下一步：cd %s && ./start.sh" % destination)
    return 0


if __name__ == "__main__":
    sys.exit(main())
