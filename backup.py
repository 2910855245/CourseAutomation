#!/usr/bin/env python3
"""
服务器备份脚本
支持：全量备份 / 仅数据备份 / 仅数据库备份
用法：
    python backup.py                # 全量备份（代码+数据+配置）
    python backup.py --data-only    # 仅备份数据（数据库+账号+日志+配置）
    python backup.py --db-only      # 仅备份数据库
    python backup.py --restore backup_xxx.tar.gz  # 恢复备份
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

# 备份内容定义
BACKUP_ITEMS = {
    "full": {
        "dirs": [
            "api", "infrastructure", "services", "alembic",
            "data", "uploads", "static",
        ],
        "files": [
            "config.py", "run.py", "worker.py", "study_worker.py",
            "wsgi.py", "manage.py",
            "requirements.txt", "pyproject.toml",
            "alembic.ini", "Dockerfile", "docker-compose.yml",
            ".dockerignore", ".env.example",
        ],
        "optional_files": [".env"],
    },
    "data": {
        "dirs": [
            "data/accounts", "data/logs", "data/global_config",
        ],
        "files": [],
        "optional_files": [".env"],
    },
    "db": {
        "dirs": [],
        "files": [],
        "optional_files": [],
    },
}


def get_db_files():
    """获取数据库文件列表（SQLite 包括 WAL 和 SHM）"""
    from config import settings
    db_path = settings.db_path
    if not os.path.isabs(db_path):
        db_path = os.path.join(BASE_DIR, db_path)
    files = [db_path]
    for suffix in ["-wal", "-shm"]:
        p = db_path + suffix
        if os.path.exists(p):
            files.append(p)
    return files


def _should_exclude(name):
    """排除不需要的目录/文件"""
    exclude = {
        "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
        "node_modules", ".git", ".coverage", ".claude",
        "backups", "script",
    }
    return name in exclude


def create_backup(mode="full", output=None):
    """创建备份"""
    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{mode}_{timestamp}"
    if output:
        tar_path = output
    else:
        tar_path = os.path.join(BACKUP_DIR, f"{backup_name}.tar.gz")

    print(f"[备份] 模式: {mode}")
    print(f"[备份] 输出: {tar_path}")

    tmpdir = tempfile.mkdtemp(prefix="backup_")
    backup_root = os.path.join(tmpdir, backup_name)
    os.makedirs(backup_root)

    item_count = 0

    try:
        # 1. 备份目录
        spec = BACKUP_ITEMS[mode]
        for d in spec["dirs"]:
            src = os.path.join(BASE_DIR, d)
            if not os.path.exists(src):
                print(f"  [跳过] 目录不存在: {d}")
                continue
            dst = os.path.join(backup_root, d)
            print(f"  [复制] {d}/")
            shutil.copytree(
                src, dst,
                ignore=shutil.ignore_patterns(
                    *__pycache__patterns(),
                    ".pytest_cache", ".ruff_cache", ".mypy_cache",
                    "node_modules", ".git", ".coverage", ".claude",
                ),
                dirs_exist_ok=True,
            )
            item_count += 1

        # 2. 备份文件
        for f in spec["files"]:
            src = os.path.join(BASE_DIR, f)
            if not os.path.exists(src):
                print(f"  [跳过] 文件不存在: {f}")
                continue
            dst = os.path.join(backup_root, f)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            item_count += 1

        # 3. 可选文件（不报错）
        for f in spec.get("optional_files", []):
            src = os.path.join(BASE_DIR, f)
            if os.path.exists(src):
                dst = os.path.join(backup_root, f)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                item_count += 1

        # 4. 数据库文件（所有模式都备份）
        if mode in ("full", "data", "db"):
            db_dir = os.path.join(backup_root, "data")
            os.makedirs(db_dir, exist_ok=True)
            for db_file in get_db_files():
                if os.path.exists(db_file):
                    fname = os.path.basename(db_file)
                    shutil.copy2(db_file, os.path.join(db_dir, fname))
                    print(f"  [复制] data/{fname}")
                    item_count += 1

        # 5. 写入备份元信息
        meta = {
            "mode": mode,
            "timestamp": timestamp,
            "created_at": datetime.now().isoformat(),
            "item_count": item_count,
            "base_dir": BASE_DIR,
        }
        meta_path = os.path.join(backup_root, "backup_meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        # 6. 打包
        print(f"\n[打包] 正在压缩...")
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(backup_root, arcname=backup_name)

        size_mb = os.path.getsize(tar_path) / (1024 * 1024)
        print(f"[完成] 备份文件: {tar_path}")
        print(f"[完成] 大小: {size_mb:.2f} MB, 共 {item_count} 项")
        return tar_path

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def restore_backup(tar_path):
    """恢复备份"""
    if not os.path.exists(tar_path):
        print(f"[错误] 备份文件不存在: {tar_path}")
        return False

    print(f"[恢复] 正在解压: {tar_path}")
    tmpdir = tempfile.mkdtemp(prefix="restore_")

    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(tmpdir)

        # 找到解压后的根目录
        items = os.listdir(tmpdir)
        if len(items) != 1:
            print("[错误] 备份格式异常")
            return False
        backup_root = os.path.join(tmpdir, items[0])

        # 读取元信息
        meta_path = os.path.join(backup_root, "backup_meta.json")
        if os.path.exists(meta_path):
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            print(f"[恢复] 备份模式: {meta.get('mode')}")
            print(f"[恢复] 备份时间: {meta.get('created_at')}")

        # 恢复文件
        restored = 0
        for root, dirs, files in os.walk(backup_root):
            # 跳过元信息
            dirs[:] = [d for d in dirs if not _should_exclude(d)]
            for fname in files:
                if fname == "backup_meta.json":
                    continue
                src = os.path.join(root, fname)
                rel = os.path.relpath(src, backup_root)
                dst = os.path.join(BASE_DIR, rel)

                # .env 文件需要确认覆盖
                if rel == ".env" and os.path.exists(dst):
                    answer = input(f"  [确认] {rel} 已存在，是否覆盖? (y/N): ")
                    if answer.lower() != "y":
                        print(f"  [跳过] {rel}")
                        continue

                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                restored += 1

        print(f"[完成] 已恢复 {restored} 个文件")
        print("[提示] 请重启服务: python manage.py restart")
        return True

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def list_backups():
    """列出所有备份"""
    if not os.path.exists(BACKUP_DIR):
        print("暂无备份")
        return

    backups = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.endswith(".tar.gz")],
        reverse=True,
    )
    if not backups:
        print("暂无备份")
        return

    print(f"{'文件名':<45} {'大小':>10} {'修改时间':<20}")
    print("-" * 80)
    for f in backups:
        path = os.path.join(BACKUP_DIR, f)
        size = os.path.getsize(path) / (1024 * 1024)
        mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
        print(f"{f:<45} {size:>8.2f}MB {mtime:<20}")


def __pycache__patterns():
    return ["__pycache__"]


def main():
    parser = argparse.ArgumentParser(description="服务器备份/恢复工具")
    parser.add_argument("--data-only", action="store_true", help="仅备份数据（数据库+账号+日志+配置）")
    parser.add_argument("--db-only", action="store_true", help="仅备份数据库")
    parser.add_argument("--restore", metavar="FILE", help="从备份文件恢复")
    parser.add_argument("--list", action="store_true", help="列出所有备份")
    parser.add_argument("-o", "--output", metavar="FILE", help="指定输出文件路径")

    args = parser.parse_args()

    if args.restore:
        restore_backup(args.restore)
    elif args.list:
        list_backups()
    elif args.db_only:
        create_backup(mode="db", output=args.output)
    elif args.data_only:
        create_backup(mode="data", output=args.output)
    else:
        create_backup(mode="full", output=args.output)


if __name__ == "__main__":
    main()
