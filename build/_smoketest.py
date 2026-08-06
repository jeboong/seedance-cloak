#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""개발용 스모크 테스트 — 임포트/엔진/검출/파이프라인(패딩·인코딩) 검증."""

from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np


def test_imports():
    import app.main  # noqa
    import app.ui.main_window  # noqa
    import app.ui.widgets  # noqa
    import app.ui.tutorial  # noqa
    import app.engines.pipeline  # noqa
    print("[ok] imports")


def test_engines():
    from app.engines.cloak import adversarial_cloak
    from app.engines.frequency import freq_perturb
    from app.engines.semantic import semantic_evade
    from app.engines.grid import GridParams, draw_face_grid

    roi = (np.random.rand(80, 64, 3) * 255).astype(np.uint8)
    out, nm = adversarial_cloak(roi, 6.0)
    assert out.shape == roi.shape and out.dtype == np.uint8
    assert nm.shape == roi.shape[:2]
    out2, nm2 = adversarial_cloak(roi, 6.0, nm)  # 시간 일관성 경로
    assert out2.shape == roi.shape

    assert freq_perturb(roi, 0.05).shape == roi.shape
    assert semantic_evade(roi, 0.08).shape == roi.shape

    frame = (np.random.rand(240, 320, 3) * 255).astype(np.uint8)
    p = GridParams(rows=6, cols=6, thickness=2, opacity=0.6, dots=True)
    draw_face_grid(frame, (80, 60, 200, 190), p, angle=8.0)
    assert frame.dtype == np.uint8
    print("[ok] engines (A/B/C/grid)")


def test_detector():
    from app.engines.detector import FaceDetector
    det = FaceDetector()
    frame = (np.random.rand(360, 640, 3) * 255).astype(np.uint8)
    boxes = det.detect(frame)
    print(f"[ok] detector mode={det.mode} ({det.mode_label}), "
          f"random-frame faces={len(boxes)}")


def _make_test_video(path: Path, seconds=2) -> bool:
    from app.engines import ffmpeg_utils as ff
    ffmpeg = ff.find_ffmpeg()
    if not ffmpeg:
        print("[skip] ffmpeg 없음 → 파이프라인 테스트 생략")
        return False
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "lavfi", "-i", f"testsrc=size=320x240:rate=25:duration={seconds}",
           "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)]
    r = subprocess.run(cmd, capture_output=True)
    return r.returncode == 0 and path.exists()


def test_pipeline():
    from PySide6.QtCore import QCoreApplication
    from app.engines.pipeline import RenderConfig, MediaWorker
    from app.engines import ffmpeg_utils as ff

    _ = QCoreApplication.instance() or QCoreApplication(sys.argv)
    tmp = ROOT / "build" / "_stage"
    tmp.mkdir(parents=True, exist_ok=True)
    src = tmp / "test_src.mp4"
    out = tmp / "test_out.mp4"
    if not _make_test_video(src, 2):
        return

    cfg = RenderConfig(methods={"A": True, "B": True, "C": True},
                       use_grid=True, tracking=True,
                       pad_enabled=True, pad_seconds=4.0,
                       quality="balanced")
    w = MediaWorker([(str(src), str(out))], cfg)
    results = {}
    w.status.connect(lambda m: print("   ", m))
    w.done.connect(lambda p: results.__setitem__("done", p))
    w.failed.connect(lambda e: results.__setitem__("fail", e))
    w._run()  # 동기 실행(스레드 없이)

    if "fail" in results:
        print(f"[FAIL] pipeline: {results['fail']}")
        return
    dur = ff.probe_duration(str(out))
    print(f"[ok] video pipeline → {out.name}, duration={dur}")
    assert dur is not None and 3.6 <= dur <= 4.6, f"패딩 후 길이 이상: {dur}"
    print("[ok] 4초 채우기 검증 통과")


def test_image_batch():
    from PySide6.QtCore import QCoreApplication
    from app.engines.pipeline import RenderConfig, MediaWorker
    import cv2

    _ = QCoreApplication.instance() or QCoreApplication(sys.argv)
    tmp = ROOT / "build" / "_stage"
    tmp.mkdir(parents=True, exist_ok=True)
    jobs = []
    for i in range(2):
        img = (np.random.rand(360, 480, 3) * 255).astype(np.uint8)
        sp = tmp / f"img_{i}.png"
        cv2.imwrite(str(sp), img)
        jobs.append((str(sp), str(tmp / f"img_{i}_out.jpg")))

    cfg = RenderConfig(methods={"A": True, "B": False, "C": True},
                       use_grid=True, tracking=True, quality="visually_lossless")
    w = MediaWorker(jobs, cfg)
    res = {}
    w.status.connect(lambda m: print("   ", m))
    w.done.connect(lambda p: res.__setitem__("done", p))
    w.failed.connect(lambda e: res.__setitem__("fail", e))
    w._run()

    if "fail" in res:
        print(f"[FAIL] image batch: {res['fail']}")
        return
    for _, op in jobs:
        assert os.path.exists(op) and os.path.getsize(op) > 0, f"이미지 미생성: {op}"
    print(f"[ok] image batch → {len(jobs)}장 저장, done='{res.get('done')}'")


if __name__ == "__main__":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    test_imports()
    test_engines()
    test_detector()
    test_pipeline()
    test_image_batch()
    print("\n== ALL SMOKE TESTS DONE ==")
