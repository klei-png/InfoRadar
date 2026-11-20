"""用户管理命令行工具（在 backend/ 目录下运行）

用法：
  uv run python -m src.manage_user add 用户名 密码        新增用户
  uv run python -m src.manage_user passwd 用户名 新密码   重置密码
  uv run python -m src.manage_user list                  列出用户
  uv run python -m src.manage_user del 用户名            删除用户
"""
import argparse
import logging
import sys

from src.api.auth import hash_password
from src.db.connection import get_conn
from src.db.repository import create_user, ensure_user_table, get_user_by_username

logger = logging.getLogger("manage_user")


def cmd_add(args):
    conn = get_conn()
    try:
        ensure_user_table(conn)
        if get_user_by_username(conn, args.username) is not None:
            sys.exit(f"用户 {args.username!r} 已存在")
        uid = create_user(conn, args.username, args.password)
        print(f"用户已创建: {args.username} (id={uid})")
    finally:
        conn.close()


def cmd_passwd(args):
    conn = get_conn()
    try:
        if get_user_by_username(conn, args.username) is None:
            sys.exit(f"用户 {args.username!r} 不存在")
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE users SET password_hash = %s WHERE username = %s",
                (hash_password(args.password), args.username),
            )
        conn.commit()
        print(f"密码已重置: {args.username}")
    finally:
        conn.close()


def cmd_list(args):
    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, username, created_at FROM users ORDER BY id"
            )
            for uid, name, created in cursor.fetchall():
                print(f"{uid:>4}  {name:<20}  {created}")
    finally:
        conn.close()


def cmd_del(args):
    conn = get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE username = %s", (args.username,))
            if cursor.rowcount == 0:
                sys.exit(f"用户 {args.username!r} 不存在")
        conn.commit()
        print(f"用户已删除: {args.username}")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="InforRadar 用户管理")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="新增用户")
    p.add_argument("username")
    p.add_argument("password")

    p = sub.add_parser("passwd", help="重置密码")
    p.add_argument("username")
    p.add_argument("password")

    sub.add_parser("list", help="列出用户")

    p = sub.add_parser("del", help="删除用户")
    p.add_argument("username")

    args = parser.parse_args()
    {"add": cmd_add, "passwd": cmd_passwd,
     "list": cmd_list, "del": cmd_del}[args.cmd](args)


if __name__ == "__main__":
    main()
