#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""데모 생성 — REP_0350_A0007C009.mov 앞부분에 그리드를 적용해 GIF/짧은 mp4 로 저장."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication  # noqa: E402

from app.engines import ffmpeg_utils as ff  # noqa: E402
from app.engines.grid import GridParams  # noqa: E402
from app.engines.pipeline import MediaWorker, RenderConfig  # noqa: E402

NO_WINDOW = 0x08000000


def main():
    mov = ROOT / "REP_0350_A0007C009.mov"
    if not mov.exists():
        sys.exit(f"데모 영상 없음: {mov}")

    ffmpeg = ff.find_ffmpeg()
    if not ffmpeg:
        ffmpeg = ff.ensure_ffmpeg(lambda m, p: print(m))
    stage = ROOT / "build" / "_stage"
    stage.mkdir(parents=True, exist_ok=True)

    dur = ff.probe_duration(str(mov)) or 4.0
    t = min(4.0, dur)
    src = stage / "demo_src.mp4"
    print(f"[demo] 앞 {t:.1f}s 트리밍…")
    subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                    "-t", f"{t}", "-i", str(mov), "-an",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)],
                   check=True, creationflags=NO_WINDOW)

    out = stage / "demo_grid.mp4"
    _ = QCoreApplication.instance() or QCoreApplication(sys.argv)
    grid = GridParams(rows=8, cols=8, thickness=2, opacity=0.85,
                      shape="ellipse", align_angle=True, color=(255, 255, 255))
    cfg = RenderConfig(methods={"A": False, "B": False, "C": False},
                       use_grid=True, grid=grid, tracking=True, quality="high")
    w = MediaWorker([(str(src), str(out))], cfg)
    res = {}
    w.status.connect(lambda m: print("  ", m))
    w.done.connect(lambda p: res.__setitem__("done", p))
    w.failed.connect(lambda e: res.__setitem__("fail", e))
    print("[demo] 그리드 렌더링…")
    w._run()
    if "fail" in res:
        sys.exit("렌더 실패: " + res["fail"])

    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    gif = docs / "demo_grid.gif"
    print("[demo] GIF 변환…")
    vf = ("fps=12,scale=460:-1:flags=lanczos,split[s0][s1];"
          "[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer")
    subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(out), "-vf", vf, "-loop", "0", str(gif)],
                   check=True, creationflags=NO_WINDOW)

    kb = gif.stat().st_size // 1024
    print(f"[demo] 완료: {gif} ({kb} KB), mp4: {out}")


if __name__ == "__main__":
    main()
