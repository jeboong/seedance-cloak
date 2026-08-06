#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UI 부팅/스크린샷 테스트 — 오프스크린으로 메인 윈도우 렌더 검증."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PySide6.QtCore import QSettings, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import app as appmod  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.theme import build_qss, dark_palette  # noqa: E402

QApplication.setOrganizationName("SeedanceCloak")
QApplication.setApplicationName("app")
QSettings("SeedanceCloak", "app").setValue("tutorial_seen", True)

qapp = QApplication(sys.argv)
qapp.setStyle("Fusion")
qapp.setPalette(dark_palette())
qapp.setStyleSheet(build_qss())

STAGE = ROOT / "build" / "_stage"
STAGE.mkdir(parents=True, exist_ok=True)
MOV = ROOT / "REP_0350_A0007C009.mov"


def sample_inputs():
    files = []
    if MOV.exists():
        files.append(str(MOV))
        cap = cv2.VideoCapture(str(MOV))
        for i in range(3):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i * 20)
            ok, fr = cap.read()
            if ok:
                sp = STAGE / f"sample_{i}.png"
                cv2.imwrite(str(sp), fr)
                files.append(str(sp))
        cap.release()
    if not files:
        for i in range(4):
            img = (np.random.rand(360, 480, 3) * 255).astype(np.uint8)
            sp = STAGE / f"rand_{i}.png"
            cv2.imwrite(str(sp), img)
            files.append(str(sp))
    return files


ok = {"v": False}
try:
    win = MainWindow()
    win.resize(1080, 900)
    win.set_inputs(sample_inputs())
    win.show()
    win.repaint()
    ok["v"] = True
    print("[ok] MainWindow 생성/표시 성공")
    print(f"     size={win.width()}x{win.height()} inputs={len(win.inputs)}")

    def _grab():
        win._render_preview()
        out = ROOT / "build" / "_preview.png"
        win.grab().save(str(out))
        print("[ok] 스크린샷 저장:", out)
        qapp.quit()
    QTimer.singleShot(2200, _grab)
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"[FAIL] {e}")
    QTimer.singleShot(300, qapp.quit)

qapp.exec()
print("[done] UI 테스트:", "PASS" if ok["v"] else "FAIL")
