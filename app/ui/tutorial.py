"""인앱 튜토리얼 — 단계별 사용법 안내(글래스 다이얼로그)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

from app.ui import theme

STEPS = [
    ("Seedance Cloak 에 오신 걸 환영합니다",
     "이 도구는 영상 속 <b>얼굴만</b> 골라 검출·매칭 회피 처리를 하거나, 얼굴에 "
     "격자(그리드)를 씌워 줍니다. 배경 화질은 그대로 유지됩니다.<br><br>"
     "아래 <b>다음</b> 버튼으로 핵심 기능을 60초 만에 훑어보세요."),
    ("1. 영상·이미지 넣기",
     "상단의 큰 영역에 파일을 <b>드래그&드롭</b> 하거나 클릭해서 선택하세요.<br>"
     "동영상(MP4·MOV·MKV…)과 이미지(JPG·PNG·WEBP…) 모두 지원하고, "
     "<b>여러 개를 한 번에</b> 넣으면 자동으로 일괄(배치) 처리합니다."),
    ("2. 회피 엔진 고르기 (A · B · C)",
     "<b>A. Adversarial</b> — 검출기를 속이는 미세 노이즈(권장, 기본 ON).<br>"
     "<b>B. Frequency</b> — 얼굴 임베딩/매칭 회피(유명인·인물 매칭 대비).<br>"
     "<b>C. Semantic</b> — 검출 자체 방해(보험). <br><br>"
     "여러 개를 동시에 켤 수 있고, <b>강도 슬라이더</b>로 세기를 조절합니다. "
     "강도가 낮을수록 화질↑, 높을수록 회피율↑."),
    ("3. 얼굴 그리드 (신규)",
     "얼굴을 자동 인식해 크기·위치에 맞춰 <b>격자</b>를 덧씌웁니다.<br>"
     "격자 수(가로/세로), 선 두께, <b>색상</b>, <b>투명도</b>, 모양(사각/타원), "
     "얼굴 기울기 정렬, 교차점 점까지 세밀하게 조절할 수 있어요."),
    ("4. 트래킹 & 품질",
     "<b>트래킹 ON</b> 이면 얼굴을 프레임 간 추적·스무딩해 격자/노이즈가 "
     "떨리지 않습니다.<br><br>"
     "<b>렌더링 품질</b>: ‘원본 품질 유지(권장)’ 는 육안상 무손실입니다. "
     "저용량·완전 무손실·HEVC 등도 선택 가능."),
    ("5. 4초 채우기 & 저장",
     "<b>4초 채우기</b> 를 켜면 4초 이하의 짧은 영상 뒤에 검은 화면을 이어붙여 "
     "목표 길이(기본 4초)를 강제로 맞춥니다(오디오는 무음 패딩).<br><br>"
     "저장 경로를 확인하고 <b>실행</b> 을 누르면 완료! 처리 중 미리보기와 "
     "진행률이 표시됩니다."),
]


class TutorialDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setFixedSize(520, 380)
        self._i = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._card = _Card()
        root.addWidget(self._card)
        c = QVBoxLayout(self._card)
        c.setContentsMargins(28, 26, 28, 22)
        c.setSpacing(14)

        self.badge = QLabel()
        self.badge.setStyleSheet(
            f"color:{theme.ACCENT_HOVER}; font-weight:700; font-size:11px;")
        self.title = QLabel(); self.title.setObjectName("Title")
        self.title.setStyleSheet("font-size: 18px; font-weight: 800;")
        self.title.setWordWrap(True)
        self.body = QLabel(); self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.RichText)
        self.body.setStyleSheet(f"color:{theme.FG_MUTED}; font-size:12.5px; line-height:1.6;")
        self.body.setAlignment(Qt.AlignTop)

        c.addWidget(self.badge)
        c.addWidget(self.title)
        c.addWidget(self.body, 1)

        self.dots = QLabel(); self.dots.setAlignment(Qt.AlignCenter)
        c.addWidget(self.dots)

        row = QHBoxLayout()
        self.skip = QCheckBox("다시 보지 않기")
        self.skip.setStyleSheet(f"color:{theme.FG_SUBTLE}; font-size:11px;")
        row.addWidget(self.skip)
        row.addStretch(1)
        self.prev = QPushButton("이전"); self.prev.setObjectName("Ghost")
        self.prev.setCursor(Qt.PointingHandCursor)
        self.prev.clicked.connect(self._go_prev)
        self.next = QPushButton("다음"); self.next.setObjectName("Primary")
        self.next.setCursor(Qt.PointingHandCursor)
        self.next.clicked.connect(self._go_next)
        row.addWidget(self.prev); row.addWidget(self.next)
        c.addLayout(row)

        self._render()

    def _render(self):
        title, body = STEPS[self._i]
        self.badge.setText(f"둘러보기 · {self._i + 1} / {len(STEPS)}")
        self.title.setText(title)
        self.body.setText(body)
        self.dots.setText("  ".join(
            ("●" if k == self._i else "○") for k in range(len(STEPS))))
        self.dots.setStyleSheet(f"color:{theme.ACCENT}; font-size:10px; letter-spacing:2px;")
        self.prev.setEnabled(self._i > 0)
        self.next.setText("시작하기" if self._i == len(STEPS) - 1 else "다음")

    def _go_prev(self):
        if self._i > 0:
            self._i -= 1
            self._render()

    def _go_next(self):
        if self._i < len(STEPS) - 1:
            self._i += 1
            self._render()
        else:
            self.accept()

    def dont_show_again(self) -> bool:
        return self.skip.isChecked()

    def showEvent(self, e):
        if self.parent():
            pg = self.parent().frameGeometry()
            self.move(pg.center().x() - self.width() // 2,
                      pg.center().y() - self.height() // 2)
        super().showEvent(e)


class _Card(QWidget):
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 20, 20)
        p.fillPath(path, QColor(16, 16, 18, 252))
        from PySide6.QtGui import QPen
        p.setPen(QPen(QColor(255, 255, 255, 40), 1.2))
        p.drawPath(path)
