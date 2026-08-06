"""테마 — 모노크롬 Black & White 미니멀 (shadcn zinc 다크)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

# ---- 팔레트 (shadcn zinc, 다크 기본) ----
BG            = "#09090b"
FG            = "#fafafa"
FG_MUTED      = "#a1a1aa"
FG_SUBTLE     = "#71717a"
CARD          = "rgba(255, 255, 255, 0.035)"
CARD_BORDER   = "rgba(255, 255, 255, 0.10)"
CARD_HOVER    = "rgba(255, 255, 255, 0.06)"
INPUT_BG      = "rgba(255, 255, 255, 0.04)"
INPUT_BORDER  = "rgba(255, 255, 255, 0.14)"

# 강조색 = 흰색(모노크롬). 포커스/토글/슬라이더/프라이머리에 사용
ACCENT        = "#fafafa"
ACCENT_HOVER  = "#e4e4e7"
ACCENT_SOFT   = "rgba(255, 255, 255, 0.12)"
ON_ACCENT     = "#09090b"   # 흰색 위 글자/노브 색(대비)
SUCCESS       = "#e4e4e7"
DANGER        = "#ef4444"
WARN          = "#e4e4e7"

# 아크릴 배경(ARGB) — 거의 검정 유리
ACRYLIC_ARGB  = 0xE00A0A0B


def dark_palette() -> QPalette:
    """Fusion 기본(밝은) 팔레트를 다크로 교체 — 메시지박스/팝업까지 어둡게."""
    p = QPalette()
    bg = QColor("#09090b")
    base = QColor("#101012")
    text = QColor("#fafafa")
    subtle = QColor("#71717a")
    disabled = QColor("#52525b")
    p.setColor(QPalette.Window, bg)
    p.setColor(QPalette.WindowText, text)
    p.setColor(QPalette.Base, base)
    p.setColor(QPalette.AlternateBase, QColor("#151517"))
    p.setColor(QPalette.Text, text)
    p.setColor(QPalette.Button, QColor("#151517"))
    p.setColor(QPalette.ButtonText, text)
    p.setColor(QPalette.BrightText, QColor("#ffffff"))
    p.setColor(QPalette.ToolTipBase, base)
    p.setColor(QPalette.ToolTipText, text)
    p.setColor(QPalette.Highlight, QColor("#fafafa"))
    p.setColor(QPalette.HighlightedText, QColor("#09090b"))
    p.setColor(QPalette.PlaceholderText, subtle)
    p.setColor(QPalette.Link, QColor("#e4e4e7"))
    for grp in (QPalette.Disabled,):
        p.setColor(grp, QPalette.Text, disabled)
        p.setColor(grp, QPalette.WindowText, disabled)
        p.setColor(grp, QPalette.ButtonText, disabled)
    return p


def build_qss() -> str:
    return f"""
    * {{
        font-family: 'Segoe UI Variable', 'Segoe UI', 'Malgun Gothic', sans-serif;
        color: {FG};
        outline: none;
    }}
    QToolTip {{
        background: #18181b; color: {FG};
        border: 1px solid {CARD_BORDER}; border-radius: 8px; padding: 6px 8px;
    }}

    QLabel#Title      {{ font-size: 15px; font-weight: 700; letter-spacing: 0.2px; }}
    QLabel#Subtitle   {{ color: {FG_MUTED}; font-size: 11px; }}
    QLabel#SectionTitle {{ font-size: 12.5px; font-weight: 700; }}
    QLabel#SectionDesc  {{ color: {FG_MUTED}; font-size: 10.5px; }}
    QLabel#Muted        {{ color: {FG_MUTED}; font-size: 11px; }}
    QLabel#Value        {{ color: {FG}; font-weight: 700; }}

    /* 입력류 */
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {INPUT_BG};
        border: 1px solid {INPUT_BORDER};
        border-radius: 9px;
        padding: 8px 10px;
        selection-background-color: {ACCENT};
        selection-color: {ON_ACCENT};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {FG};
    }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox::down-arrow {{
        image: none; border-left: 4px solid transparent;
        border-right: 4px solid transparent; border-top: 5px solid {FG_MUTED};
        margin-right: 10px;
    }}
    QComboBox QAbstractItemView {{
        background: #101012; border: 1px solid {CARD_BORDER};
        border-radius: 10px; padding: 4px;
        selection-background-color: {ACCENT_SOFT};
        outline: none;
    }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; height: 0; }}

    /* 스크롤바 */
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
    QScrollBar::handle:vertical {{
        background: rgba(255,255,255,0.16); border-radius: 5px; min-height: 40px;
    }}
    QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.30); }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* 진행바 */
    QProgressBar {{
        background: rgba(255,255,255,0.07);
        border: none; border-radius: 7px; height: 12px; text-align: center;
        font-size: 9px; color: {ON_ACCENT};
    }}
    QProgressBar::chunk {{ border-radius: 7px; background: {FG}; }}

    /* 기본 버튼 */
    QPushButton {{
        background: {INPUT_BG}; border: 1px solid {INPUT_BORDER};
        border-radius: 10px; padding: 9px 14px; font-weight: 600; color: {FG};
    }}
    QPushButton:hover {{ background: {CARD_HOVER}; border: 1px solid {FG}; }}
    QPushButton:disabled {{ color: {FG_SUBTLE}; border-color: rgba(255,255,255,0.06); }}

    /* 프라이머리 = 흰색 배경 + 검정 글자 (shadcn default) */
    QPushButton#Primary {{
        background: {ACCENT}; border: none; color: {ON_ACCENT};
        font-size: 13.5px; font-weight: 700; padding: 13px; border-radius: 12px;
    }}
    QPushButton#Primary:hover {{ background: {ACCENT_HOVER}; }}
    QPushButton#Primary:disabled {{ background: rgba(255,255,255,0.30); color: rgba(9,9,11,0.55); }}

    QPushButton#Ghost {{ background: transparent; border: 1px solid {CARD_BORDER}; color: {FG}; }}
    QPushButton#Ghost:hover {{ background: {CARD_HOVER}; border: 1px solid {FG}; }}

    QPushButton#WinBtn {{
        background: transparent; border: none; border-radius: 8px;
        padding: 0; font-size: 15px; color: {FG_MUTED}; min-width: 34px; min-height: 30px;
    }}
    QPushButton#WinBtn:hover {{ background: rgba(255,255,255,0.12); color: {FG}; }}
    QPushButton#CloseBtn:hover {{ background: rgba(255,255,255,0.20); color: {FG}; }}

    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{
        width: 18px; height: 18px; border-radius: 6px;
        border: 1px solid {INPUT_BORDER}; background: {INPUT_BG};
    }}
    QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}

    QTextEdit {{
        background: rgba(0,0,0,0.35); border: 1px solid {CARD_BORDER};
        border-radius: 10px; padding: 8px; color: {FG_MUTED};
        font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 10.5px;
    }}
    """
