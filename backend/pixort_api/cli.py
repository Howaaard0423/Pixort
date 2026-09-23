"""Command line entry point: ``python run.py`` (or ``python -m pixort_api``)."""

from __future__ import annotations

import argparse
import logging
import sys
import webbrowser
from pathlib import Path

from . import settings
from .app import Application
from .server import create_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pixort-api",
        description="Pixort 后端 API 服务（前后端分离架构）",
    )
    parser.add_argument("--host", default=settings.HOST, help="监听地址（默认 %(default)s）")
    parser.add_argument("--port", type=int, default=settings.PORT, help="监听端口（默认 %(default)s）")
    parser.add_argument("--data-root", type=Path, default=None, help="数据库与图片所在目录")
    parser.add_argument("--frontend", type=Path, default=None, help="前端静态目录")
    parser.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    parser.add_argument("--quiet", action="store_true", help="不打印每个请求的日志")
    parser.add_argument("--verbose", action="store_true", help="打印调试日志")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # A redirected stream (a .bat wrapper, CI, the packaged EXE piped to a file)
    # would otherwise block-buffer the banner and fall back to the ANSI code
    # page, so pin it to UTF-8 and flush per line.  A real console is left
    # alone: there the Windows console encoding handles Chinese correctly.
    try:
        if not sys.stdout.isatty():
            sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        if not sys.stderr.isatty():
            sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except (AttributeError, ValueError):  # pragma: no cover - exotic streams
        pass

    if args.data_root is not None:
        settings.DATA_ROOT = args.data_root.expanduser().resolve()
        settings.DB_PATH = settings.DATA_ROOT / "illustration_manager.db"
        settings.ILLUSTRATIONS_DIR = settings.DATA_ROOT / "illustrations"
        settings.ARCHIVE_DIR = settings.DATA_ROOT / "archive_illustrations"
    if args.frontend is not None:
        settings.FRONTEND_DIR = args.frontend.expanduser().resolve()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    if not args.verbose:
        # expected 4xx responses are not worth a full traceback in the log
        logging.getLogger("pixort.api").setLevel(logging.WARNING)

    application = Application(frontend_dir=settings.FRONTEND_DIR)
    try:
        server = create_server(args.host, args.port, application=application, quiet=args.quiet)
    except OSError as exc:
        print(f"无法绑定 {args.host}:{args.port} —— {exc}", file=sys.stderr)
        return 1

    host, port = server.server_address[:2]
    display_host = "localhost" if host in ("0.0.0.0", "::") else host
    url = f"http://{display_host}:{port}/"
    print("Pixort API 已启动")
    print(f"  界面      {url}")
    print(f"  接口      {url}api/health")
    print(f"  数据目录  {settings.DATA_ROOT}")
    print(f"  数据库    {settings.DB_PATH}")
    print("按 Ctrl+C 停止服务")

    if args.open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止服务…")
    finally:
        server.shutdown()
        server.server_close()
    return 0
