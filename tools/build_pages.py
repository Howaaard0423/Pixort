"""Assemble the static bundle that GitHub Pages serves.

    python tools/build_pages.py             # 生成 _site/
    python tools/build_pages.py --serve     # 生成后在本机预览

GitHub Pages 只能托管静态文件、跑不了后端，所以发布出去的是同一套前端，
只是把数据源钉在内置示例库上（`window.PIXORT_DEMO = true`，等价于 URL 上带
`?demo=1`）。需要真实数据时，用 `?api=http://后端地址` 覆盖即可。
"""

from __future__ import annotations

import argparse
import functools
import http.server
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "frontend"
TARGET = ROOT / "_site"

ENTRY = '<script type="module" src="js/main.js"></script>'
ENTRY_WITH_DEMO = '<script>window.PIXORT_DEMO = true;</script>\n  ' + ENTRY


def build() -> int:
    if not (SOURCE / "index.html").is_file():
        print(f"找不到前端目录：{SOURCE}", file=sys.stderr)
        return 1
    if TARGET.exists():
        # On Windows a preview server started with ``--serve`` keeps the folder
        # open, and rmtree then fails with a bare WinError 32.  Translate that
        # into something actionable instead of a traceback.
        shutil.rmtree(TARGET, ignore_errors=True)
        if TARGET.exists():
            print(
                f"无法覆盖 {TARGET}：目录正被占用。\n"
                "如果上一个 --serve 预览服务还开着，请先在那边按 Ctrl+C 停掉。",
                file=sys.stderr,
            )
            return 1
    shutil.copytree(SOURCE, TARGET)

    index = TARGET / "index.html"
    html = index.read_text(encoding="utf-8")
    if ENTRY not in html:
        print(f"{index} 里没有找到入口脚本，前端结构可能变了", file=sys.stderr)
        return 1
    index.write_text(html.replace(ENTRY, ENTRY_WITH_DEMO, 1), encoding="utf-8")

    # GitHub Pages runs Jekyll unless it sees this file, and Jekyll would skip
    # any path starting with an underscore.
    (TARGET / ".nojekyll").write_text("", encoding="utf-8")

    files = [path for path in TARGET.rglob("*") if path.is_file()]
    size = sum(path.stat().st_size for path in files)
    print(f"已生成 {TARGET}")
    print(f"  {len(files)} 个文件，共 {size / 1024:.0f} KB")
    return 0


def serve(port: int) -> int:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(TARGET))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"预览地址 http://127.0.0.1:{port}/   （Ctrl+C 停止）")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 GitHub Pages 用的静态站点")
    parser.add_argument("--serve", action="store_true", help="生成后启动本地预览服务")
    parser.add_argument("--port", type=int, default=8123, help="预览端口（默认 %(default)s）")
    args = parser.parse_args(argv)

    code = build()
    if code or not args.serve:
        return code
    return serve(args.port)


if __name__ == "__main__":
    sys.exit(main())
