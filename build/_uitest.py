#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UI 부팅 테스트 — 메인 윈도우 생성/표시가 예외 없이 되는지 오프스크린 검증."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import app as appmod  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.theme import build_qss, dark_palette  # noqa: E402

QApplication.setOrganizationName("SeedanceCloak")
QApplication.setApplicationName("app")
QSettings("SeedanceCloak", "app").setValue("tutorial_seen", True)  # 튜토리얼 스킵

qapp = QApplication(sys.argv)
qapp.setStyle("Fusion")
qapp.setPalette(dark_palette())
qapp.setStyleSheet(build_qss())

ok = {"v": False}
try:
    win = MainWindow()
    win.resize(680, 1240)          # 더 많은 카드가 보이도록
    win.grid_enable.setChecked(True)   # 그리드 옵션 펼치기
    win.pad_enable.setChecked(True)    # 4초 채우기 슬라이더 활성화
    win.drop.set_files(["sample_interview.mp4", "portrait_01.png", "portrait_02.jpg"])
    win.meta.setText("동영상 1 · 이미지 2   |   여러 파일 일괄 처리")
    win.show()
    win.repaint()
    ok["v"] = True
    print("[ok] MainWindow 생성/표시 성공")
    print(f"     size={win.width()}x{win.height()} title={appmod.__app_name__}")

    def _grab():
        out = ROOT / "build" / "_preview.png"
        win.grab().save(str(out))
        print("[ok] 스크린샷 저장:", out)
        qapp.quit()
    QTimer.singleShot(700, _grab)
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"[FAIL] {e}")
    QTimer.singleShot(300, qapp.quit)

qapp.exec()
print("[done] UI 부팅 테스트 종료:", "PASS" if ok["v"] else "FAIL")
