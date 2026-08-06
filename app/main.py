"""앱 진입점 — QApplication 설정 + 메인 윈도우 표시."""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

import app as appmod
from app.ui.main_window import MainWindow
from app.ui.theme import build_qss, dark_palette


def main() -> int:
    QApplication.setApplicationName(appmod.__app_name__)
    QApplication.setOrganizationName("SeedanceCloak")
    QApplication.setApplicationVersion(appmod.__version__)

    qapp = QApplication(sys.argv)
    qapp.setStyle("Fusion")
    qapp.setPalette(dark_palette())
    qapp.setStyleSheet(build_qss())
    # 한글이 깨지지 않도록 폴백 폰트 체인을 명시(Segoe UI -> Malgun Gothic)
    font = QFont()
    font.setFamilies(["Segoe UI Variable", "Segoe UI", "Malgun Gothic",
                      "Apple SD Gothic Neo", "sans-serif"])
    font.setPointSize(10)
    qapp.setFont(font)

    win = MainWindow()
    win.show()
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
