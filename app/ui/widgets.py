"""재사용 커스텀 위젯 — 글래스 카드 / 토글 스위치 / 실수 슬라이더 / 색상 스와치 / 드롭영역 / 타이틀바."""

from __future__ import annotations

import os

import cv2
import numpy as np
from PySide6.QtCore import (Property, QEasingCurve, QPoint, QPropertyAnimation,
                            QRect, QRectF, QSize, Qt, Signal)
from PySide6.QtGui import (QColor, QFont, QIcon, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QAbstractButton, QColorDialog, QComboBox,
                               QFrame, QHBoxLayout, QLabel, QLayout,
                               QPushButton, QSizePolicy, QSlider, QVBoxLayout,
                               QWidget)

from app.ui import theme

_VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".flv")


# ============================================================
class _NoWheelSlider(QSlider):
    """마우스 휠로 값이 바뀌지 않도록(스크롤 중 실수 방지). 휠은 페이지 스크롤로 전달."""
    def wheelEvent(self, e):
        e.ignore()


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, e):
        e.ignore()


class IconButton(QPushButton):
    """아이콘을 직접 그려주는 버튼(폰트 글리프 의존 X). kind: x/prev/next/refresh."""

    def __init__(self, kind: str, parent=None, color: str = "#e8e9ee"):
        super().__init__(parent)
        self._kind = kind
        self._color = QColor(color)
        self.setText("")

    def paintEvent(self, e):
        super().paintEvent(e)  # 배경/보더/hover 는 QSS 로
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        r = min(w, h) * 0.22
        if self._kind == "x":
            pen = QPen(self._color, 2.0)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(int(cx - r), int(cy - r), int(cx + r), int(cy + r))
            p.drawLine(int(cx - r), int(cy + r), int(cx + r), int(cy - r))
        elif self._kind in ("prev", "next"):
            path = QPainterPath()
            if self._kind == "prev":
                path.moveTo(cx + r, cy - r); path.lineTo(cx - r, cy)
                path.lineTo(cx + r, cy + r)
            else:
                path.moveTo(cx - r, cy - r); path.lineTo(cx + r, cy)
                path.lineTo(cx - r, cy + r)
            path.closeSubpath()
            p.fillPath(path, self._color)
        elif self._kind == "refresh":
            pen = QPen(self._color, 1.7)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), 55 * 16, 250 * 16)
            # 화살촉
            import math
            a = math.radians(55)
            ex, ey = cx + r * math.cos(a), cy - r * math.sin(a)
            p.setPen(Qt.NoPen)
            tri = QPainterPath()
            tri.moveTo(ex + 2.4, ey + 1.0)
            tri.lineTo(ex - 3.0, ey - 1.2)
            tri.lineTo(ex + 1.2, ey - 4.2)
            tri.closeSubpath()
            p.fillPath(tri, self._color)
        p.end()


# ============================================================
class GlassCard(QFrame):
    """반투명 라운드 카드(글래스). 내부 세로 레이아웃 self.v 제공."""

    def __init__(self, parent=None, radius: int = 16, pad: int = 16):
        super().__init__(parent)
        self._radius = radius
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(pad, pad, pad, pad)
        self.v.setSpacing(10)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, self._radius, self._radius)
        p.fillPath(path, QColor(255, 255, 255, 12))
        p.setPen(QPen(QColor(255, 255, 255, 24), 1))
        p.drawPath(path)


class _CardHeader(QWidget):
    clicked = Signal()

    def __init__(self, title: str, desc: str = "", parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        tb = QVBoxLayout(); tb.setSpacing(2)
        t = QLabel(title); t.setObjectName("SectionTitle")
        tb.addWidget(t)
        if desc:
            d = QLabel(desc); d.setObjectName("SectionDesc"); d.setWordWrap(True)
            tb.addWidget(d)
        lay.addLayout(tb, 1)
        self.chev = QLabel("▾")
        self.chev.setStyleSheet(f"color:{theme.FG_MUTED}; font-size:12px;")
        lay.addWidget(self.chev, 0, Qt.AlignVCenter)

    def set_expanded(self, e: bool):
        self.chev.setText("▾" if e else "▸")

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()


class CollapsibleCard(GlassCard):
    """헤더(꺾쇠) 클릭으로 본문을 접었다 펴는 글래스 카드. 본문 레이아웃 self.body."""

    def __init__(self, title: str, desc: str = "", expanded: bool = True, parent=None):
        super().__init__(parent)
        self._expanded = expanded
        self._header = _CardHeader(title, desc)
        self._header.clicked.connect(self.toggle)
        self.v.addWidget(self._header)
        self._bodyw = QWidget()
        self.body = QVBoxLayout(self._bodyw)
        self.body.setContentsMargins(0, 6, 0, 0)
        self.body.setSpacing(10)
        self.v.addWidget(self._bodyw)
        self._apply()

    def toggle(self):
        self.setExpanded(not self._expanded)

    def setExpanded(self, e: bool):
        self._expanded = e
        self._apply()

    def _apply(self):
        self._bodyw.setVisible(self._expanded)
        self._header.set_expanded(self._expanded)


class SectionHeader(QWidget):
    def __init__(self, title: str, desc: str = "", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        t = QLabel(title); t.setObjectName("SectionTitle")
        lay.addWidget(t)
        if desc:
            d = QLabel(desc); d.setObjectName("SectionDesc"); d.setWordWrap(True)
            lay.addWidget(d)


def hline() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {theme.CARD_BORDER}; border: none;")
    return line


# ============================================================
class ToggleSwitch(QAbstractButton):
    """iOS 스타일 애니메이션 토글."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(46, 26)
        self.setCursor(Qt.PointingHandCursor)
        self._offset = 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self.toggled.connect(self._animate)

    def _animate(self, checked):
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def get_offset(self):
        return self._offset

    def set_offset(self, v):
        self._offset = v
        self.update()

    offset = Property(float, get_offset, set_offset)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        track_on = QColor(theme.ACCENT)
        track_off = QColor(255, 255, 255, 34)
        col = QColor(
            int(track_off.red() + (track_on.red() - track_off.red()) * self._offset),
            int(track_off.green() + (track_on.green() - track_off.green()) * self._offset),
            int(track_off.blue() + (track_on.blue() - track_off.blue()) * self._offset),
            int(track_off.alpha() + (255 - track_off.alpha()) * self._offset),
        )
        p.setBrush(col); p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, w, h, h / 2, h / 2)
        d = h - 6
        x = 3 + (w - d - 6) * self._offset
        # 노브: OFF=흰색, ON=어두움(흰 트랙 위 대비)
        on = QColor(theme.ON_ACCENT)
        knob = QColor(
            int(255 + (on.red() - 255) * self._offset),
            int(255 + (on.green() - 255) * self._offset),
            int(255 + (on.blue() - 255) * self._offset),
        )
        p.setBrush(knob)
        p.drawEllipse(QPoint(int(x + d / 2), int(h / 2)), int(d / 2), int(d / 2))


class ToggleRow(QWidget):
    """토글 + 제목/설명 한 줄."""
    toggled = Signal(bool)

    def __init__(self, title: str, desc: str = "", checked: bool = False, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        text = QVBoxLayout(); text.setSpacing(2)
        t = QLabel(title); t.setObjectName("SectionTitle")
        text.addWidget(t)
        if desc:
            d = QLabel(desc); d.setObjectName("SectionDesc"); d.setWordWrap(True)
            text.addWidget(d)
        lay.addLayout(text, 1)
        self.sw = ToggleSwitch()
        self.sw.setChecked(checked)
        self.sw.toggled.connect(self.toggled)
        lay.addWidget(self.sw, 0, Qt.AlignTop)

    def isChecked(self):
        return self.sw.isChecked()

    def setChecked(self, v):
        self.sw.setChecked(v)


# ============================================================
class LabeledSlider(QWidget):
    """라벨 + 값 + 슬라이더(실수 매핑)."""
    changed = Signal(float)

    def __init__(self, label: str, mn: float, mx: float, val: float,
                 steps: int = 100, decimals: int = 2, suffix: str = "", parent=None):
        super().__init__(parent)
        self._mn, self._mx, self._steps = mn, mx, steps
        self._dec, self._suffix = decimals, suffix
        self._default = val

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        top = QHBoxLayout(); top.setSpacing(6)
        self._label = QLabel(label); self._label.setObjectName("Muted")
        self._value = QLabel(); self._value.setObjectName("Value")
        self._reset = IconButton("refresh", color=theme.FG_MUTED)
        self._reset.setCursor(Qt.PointingHandCursor)
        self._reset.setFixedSize(20, 20)
        self._reset.setToolTip("기본값으로 되돌리기")
        self._reset.setStyleSheet(
            "QPushButton{background:transparent;border:none;border-radius:6px;padding:0;}"
            "QPushButton:hover{background:rgba(255,255,255,0.12);}")
        self._reset.clicked.connect(self.reset)
        top.addWidget(self._label); top.addStretch(1)
        top.addWidget(self._value); top.addWidget(self._reset)
        lay.addLayout(top)

        self.slider = _NoWheelSlider(Qt.Horizontal)
        self.slider.setRange(0, steps)
        self.slider.setCursor(Qt.PointingHandCursor)
        self.slider.valueChanged.connect(self._on_change)
        self.slider.setStyleSheet(_slider_qss())
        lay.addWidget(self.slider)
        self.setValueF(val)

    def reset(self):
        self.setValueF(self._default)

    def _on_change(self, i):
        v = self.valueF()
        self._value.setText(f"{v:.{self._dec}f}{self._suffix}")
        self.changed.emit(v)

    def valueF(self) -> float:
        return self._mn + (self._mx - self._mn) * self.slider.value() / self._steps

    def setValueF(self, v: float):
        v = max(self._mn, min(self._mx, v))
        i = round((v - self._mn) / (self._mx - self._mn) * self._steps)
        self.slider.setValue(int(i))
        self._value.setText(f"{self.valueF():.{self._dec}f}{self._suffix}")


def _slider_qss() -> str:
    return f"""
    QSlider::groove:horizontal {{
        height: 6px; border-radius: 3px; background: rgba(255,255,255,0.10);
    }}
    QSlider::sub-page:horizontal {{
        height: 6px; border-radius: 3px;
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {theme.ACCENT}, stop:1 {theme.ACCENT_HOVER});
    }}
    QSlider::handle:horizontal {{
        width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
        background: {theme.FG}; border: 2px solid {theme.BG};
    }}
    QSlider::handle:horizontal:hover {{ background: {theme.ACCENT_HOVER}; }}
    """


# ============================================================
class ColorSwatch(QPushButton):
    colorChanged = Signal(QColor)

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(44, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._pick)

    def color(self) -> QColor:
        return QColor(self._color)

    def bgr(self):
        c = self._color
        return (c.blue(), c.green(), c.red())

    def _pick(self):
        c = QColorDialog.getColor(self._color, self, "격자 색상 선택")
        if c.isValid():
            self._color = c
            self.update()
            self.colorChanged.emit(c)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setBrush(self._color)
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.drawRoundedRect(r, 8, 8)


# ============================================================
class DropArea(QFrame):
    filesDropped = Signal(list)
    EXTS = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".flv",
            ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(150)
        self._hover = False
        self._filename = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        self.icon = QLabel("⬍")
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setStyleSheet("font-size: 30px; color: %s;" % theme.FG_MUTED)
        self.text = QLabel("영상 또는 이미지를 드래그하거나 클릭해서 선택 (여러 개 가능)")
        self.text.setAlignment(Qt.AlignCenter)
        self.text.setObjectName("Muted")
        self.hint = QLabel("동영상 · 이미지  |  여러 파일 일괄 처리 지원")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setStyleSheet("color: %s; font-size: 10px;" % theme.FG_SUBTLE)
        lay.addStretch(1)
        lay.addWidget(self.icon); lay.addWidget(self.text); lay.addWidget(self.hint)
        lay.addStretch(1)

    def set_compact(self, compact: bool):
        """파일이 있으면 슬림한 '추가' 바로, 없으면 큰 안내 영역으로."""
        if compact:
            self.setMinimumHeight(58)
            self.icon.setVisible(False)
            self.hint.setVisible(False)
            self.text.setText("＋  파일 추가 (드래그 또는 클릭)")
            self.text.setStyleSheet(
                "color: %s; font-size: 12px; font-weight: 600;" % theme.FG_MUTED)
        else:
            self.setMinimumHeight(150)
            self.icon.setVisible(True)
            self.hint.setVisible(True)
            self.text.setText("영상 또는 이미지를 드래그하거나 클릭해서 선택 (여러 개 가능)")
            self.text.setObjectName("Muted")
            self.text.setStyleSheet("")
        self.update()

    def _accepts(self, path: str) -> bool:
        return path.lower().endswith(self.EXTS)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            from PySide6.QtWidgets import QFileDialog
            paths, _ = QFileDialog.getOpenFileNames(
                self, "영상/이미지 선택", "",
                "Media (*.mp4 *.mov *.avi *.mkv *.webm *.m4v *.wmv *.flv "
                "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff)")
            if paths:
                self.filesDropped.emit(list(paths))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            for u in e.mimeData().urls():
                if self._accepts(u.toLocalFile()):
                    e.acceptProposedAction()
                    self._hover = True
                    self.update()
                    return

    def dragLeaveEvent(self, e):
        self._hover = False
        self.update()

    def dropEvent(self, e):
        self._hover = False
        self.update()
        paths = [u.toLocalFile() for u in e.mimeData().urls()
                 if self._accepts(u.toLocalFile())]
        if paths:
            self.filesDropped.emit(paths)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        if self._hover:
            p.fillPath(path, QColor(255, 255, 255, 28))
        else:
            p.fillPath(path, QColor(255, 255, 255, 8))
        pen = QPen(QColor(theme.ACCENT) if self._hover else QColor(255, 255, 255, 40),
                   1.4)
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.drawPath(path)


# ============================================================
#  썸네일 카드 그리드 (여러 파일 첨부 시)
# ============================================================
def _load_thumb_bgr(path: str):
    try:
        if path.lower().endswith(_VIDEO_EXTS):
            cap = cv2.VideoCapture(path)
            ok, fr = cap.read()
            cap.release()
            return fr if ok else None
        buf = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)
    except Exception:
        return None


def _rounded_thumb(path: str, w: int, h: int, radius: int = 10) -> QPixmap:
    out = QPixmap(w, h)
    out.fill(Qt.transparent)
    bgr = _load_thumb_bgr(path)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
    p.setClipPath(clip)
    if bgr is not None:
        ih, iw = bgr.shape[:2]
        target = w / h
        ar = iw / ih
        if ar > target:      # 좌우 크롭
            nw = max(1, int(ih * target)); x0 = (iw - nw) // 2
            bgr = bgr[:, x0:x0 + nw]
        else:                # 상하 크롭
            nh = max(1, int(iw / target)); y0 = (ih - nh) // 2
            bgr = bgr[y0:y0 + nh, :]
        bgr = cv2.resize(bgr, (w, h), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        img = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        p.drawPixmap(0, 0, QPixmap.fromImage(img))
    else:
        p.fillRect(0, 0, w, h, QColor(28, 28, 32))
        p.setPen(QColor(theme.FG_SUBTLE))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, "미리보기\n없음")
    p.setClipping(False)
    # 동영상 표시(재생 아이콘)
    if path.lower().endswith(_VIDEO_EXTS):
        cx, cy, r = w / 2, h / 2, 13
        p.setBrush(QColor(0, 0, 0, 120)); p.setPen(Qt.NoPen)
        p.drawEllipse(QPoint(int(cx), int(cy)), r, r)
        tri = QPainterPath()
        tri.moveTo(cx - 4, cy - 6); tri.lineTo(cx - 4, cy + 6); tri.lineTo(cx + 7, cy)
        tri.closeSubpath()
        p.fillPath(tri, QColor(255, 255, 255, 230))
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 45), 1))
    p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), radius, radius)
    p.end()
    return out


class FlowLayout(QLayout):
    """자동 줄바꿈(플로우) 레이아웃."""

    def __init__(self, parent=None, spacing=10):
        super().__init__(parent)
        self._items = []
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._layout(QRect(0, 0, width, 0), test=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, test=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.sizeHint())
        return s

    def _layout(self, rect, test):
        x, y, line_h = rect.x(), rect.y(), 0
        sp = self.spacing()
        for it in self._items:
            sz = it.sizeHint()
            if x + sz.width() > rect.right() and line_h > 0:
                x = rect.x(); y += line_h + sp; line_h = 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), sz))
            x += sz.width() + sp
            line_h = max(line_h, sz.height())
        return y + line_h - rect.y()


class ThumbCard(QFrame):
    removeRequested = Signal(str)

    def __init__(self, path: str, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.path = path
        self.setFixedSize(104, 126)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 2)
        lay.setSpacing(4)
        thumb = QLabel()
        thumb.setFixedSize(104, 100)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setPixmap(pixmap)
        lay.addWidget(thumb)
        name = QLabel()
        name.setObjectName("SectionDesc")
        name.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        name.setFixedWidth(104)
        fm = name.fontMetrics()
        name.setText(fm.elidedText(os.path.basename(path), Qt.ElideMiddle, 100))
        name.setToolTip(os.path.basename(path))
        lay.addWidget(name)

        self.rm = IconButton("x", self, color="#ffffff")
        self.rm.setCursor(Qt.PointingHandCursor)
        self.rm.setFixedSize(22, 22)
        self.rm.move(104 - 24, 4)
        self.rm.setToolTip("제거")
        self.rm.setStyleSheet(
            "QPushButton{background: rgba(0,0,0,0.62); border:none; border-radius:11px;}"
            "QPushButton:hover{background: #ef4444;}")
        self.rm.clicked.connect(lambda: self.removeRequested.emit(self.path))
        self.rm.raise_()


class ThumbGrid(QWidget):
    """첨부 파일들을 둥근 카드 썸네일 그리드로 표시. 삭제 시 changed 방출."""
    changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paths: list[str] = []
        self._cache: dict[str, QPixmap] = {}
        self._flow = FlowLayout(self, spacing=10)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

    def set_files(self, paths):
        self._paths = list(paths)
        self._rebuild()

    def _rebuild(self):
        while self._flow.count():
            it = self._flow.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        for p in self._paths:
            card = ThumbCard(p, self._pixmap(p))
            card.removeRequested.connect(self._remove)
            self._flow.addWidget(card)
        self.updateGeometry()

    def _remove(self, path):
        self._paths = [p for p in self._paths if p != path]
        self._rebuild()
        self.changed.emit(list(self._paths))

    def _pixmap(self, path: str) -> QPixmap:
        if path not in self._cache:
            self._cache[path] = _rounded_thumb(path, 104, 100)
        return self._cache[path]


# ============================================================
class PreviewLabel(QLabel):
    """미리보기 라벨. 수동 그리드 모드에서 드래그로 위치를 옮길 수 있다."""
    dragged = Signal(float, float)   # 이미지 기준 정규화 (cx, cy)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pm_w = 0
        self._pm_h = 0
        self._interactive = False

    def set_interactive(self, on: bool):
        self._interactive = on
        self.setCursor(Qt.SizeAllCursor if on else Qt.ArrowCursor)

    def set_scaled(self, pixmap: QPixmap):
        if pixmap is None or pixmap.isNull():
            self._pm_w = self._pm_h = 0
            super().setPixmap(QPixmap())
            return
        scaled = pixmap.scaled(max(1, self.width()), max(1, self.height()),
                               Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._pm_w, self._pm_h = scaled.width(), scaled.height()
        super().setPixmap(scaled)

    def _emit(self, pos):
        if not self._interactive or self._pm_w <= 0 or self._pm_h <= 0:
            return
        xo = (self.width() - self._pm_w) / 2.0
        yo = (self.height() - self._pm_h) / 2.0
        nx = (pos.x() - xo) / self._pm_w
        ny = (pos.y() - yo) / self._pm_h
        self.dragged.emit(min(1.0, max(0.0, nx)), min(1.0, max(0.0, ny)))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._emit(e.position())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._emit(e.position())


# ============================================================
class TitleBar(QWidget):
    helpRequested = Signal()
    minimizeRequested = Signal()
    closeRequested = Signal()

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self._drag = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 10, 8)
        lay.setSpacing(10)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {theme.ACCENT}; font-size: 13px;")
        lay.addWidget(dot)

        tbox = QVBoxLayout(); tbox.setSpacing(0)
        t = QLabel(title); t.setObjectName("Title")
        tbox.addWidget(t)
        if subtitle:
            s = QLabel(subtitle); s.setObjectName("Subtitle")
            tbox.addWidget(s)
        lay.addLayout(tbox)
        lay.addStretch(1)

        help_btn = QPushButton("  ?  튜토리얼  ")
        help_btn.setObjectName("Ghost")
        help_btn.setCursor(Qt.PointingHandCursor)
        help_btn.clicked.connect(self.helpRequested)
        lay.addWidget(help_btn)

        mini = QPushButton("—"); mini.setObjectName("WinBtn")
        mini.setCursor(Qt.PointingHandCursor)
        mini.clicked.connect(self.minimizeRequested)
        lay.addWidget(mini)

        close = QPushButton("✕"); close.setObjectName("WinBtn")
        close.setProperty("class", "close")
        close.setObjectName("CloseBtn")
        close.setStyleSheet("")  # objectName 스타일 사용
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.closeRequested)
        lay.addWidget(close)

    # 창 이동(frameless)
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self.window().move(e.globalPosition().toPoint() - self._drag)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = None
