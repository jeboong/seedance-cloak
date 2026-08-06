"""메인 윈도우 — 2단(좌: 컨트롤 / 우: 라이브 미리보기) 글래스 다크 UI + 파이프라인 연동."""

from __future__ import annotations

import os

import cv2
from PySide6.QtCore import (QRectF, QSettings, Qt, QThread, QTimer, Signal)
from PySide6.QtGui import (QColor, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPixmap)
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QProgressBar, QPushButton,
                               QScrollArea, QSizeGrip, QSizePolicy, QSlider,
                               QSplitter, QTextEdit, QVBoxLayout, QWidget)

import app
from app.engines import ffmpeg_utils as ff
from app.engines import updater
from app.engines.detector import FaceDetector
from app.engines.grid import GridParams
from app.engines.pipeline import (FrameProcessor, MediaWorker, RenderConfig,
                                   _imread_unicode, is_image, is_video)
from app.ui import theme
from app.ui.acrylic import apply_glass
from app.ui.tutorial import TutorialDialog
from app.ui.widgets import (CollapsibleCard, ColorSwatch, DropArea, GlassCard,
                            IconButton, LabeledSlider, NoWheelComboBox,
                            SectionHeader, ThumbGrid, TitleBar, ToggleRow,
                            ToggleSwitch, hline)


# ============================================================
class _CheckThread(QThread):
    result = Signal(object)

    def run(self):
        self.result.emit(updater.check_for_update())


class _DownloadThread(QThread):
    progress = Signal(float)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            path = updater.download_setup(self.url, lambda f: self.progress.emit(f))
            self.done.emit(path)
        except Exception as e:
            self.failed.emit(str(e))


# ============================================================
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.inputs: list[str] = []
        self._jobs: list[tuple[str, str]] = []
        self.worker = None
        self._running = False
        self._glass = False
        self._detector = None
        self._last_preview_rgb = None
        self._checker = None
        self._downloader = None
        # 미리보기 프레임 상태
        self._preview_cap = None
        self._preview_total = 0
        self._preview_idx = 0
        self._preview_base = None      # 현재 미리보기 대상 프레임(BGR, 원본해상도)
        self.settings = QSettings("SeedanceCloak", "app")

        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(940, 680)
        self.resize(1040, 880)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._root = _Root()
        outer.addWidget(self._root)

        root = QVBoxLayout(self._root)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.titlebar = TitleBar(app.__app_name__,
                                 f"Reference Cloak · v{app.__version__}")
        self.titlebar.helpRequested.connect(self.show_tutorial)
        self.titlebar.minimizeRequested.connect(self.showMinimized)
        self.titlebar.closeRequested.connect(self.close)
        root.addWidget(self.titlebar)

        self._build_banner()
        root.addWidget(self.banner)

        # 좌: 스크롤 컨트롤 / 우: 미리보기 — 가운데 분리바(splitter)로 폭 조절
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setMinimumWidth(400)
        scroll.viewport().setStyleSheet("background: transparent;")
        content = QWidget()
        content.setAttribute(Qt.WA_StyledBackground, True)
        content.setStyleSheet("background: transparent;")
        scroll.setWidget(content)
        self.v = QVBoxLayout(content)
        self.v.setContentsMargins(18, 6, 12, 18)
        self.v.setSpacing(14)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        splitter.setStyleSheet(
            "QSplitter::handle{background: rgba(255,255,255,0.06);}"
            "QSplitter::handle:hover{background: rgba(255,255,255,0.18);}")
        splitter.addWidget(scroll)
        splitter.addWidget(self._build_preview_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([520, 520])
        root.addWidget(splitter, 1)

        self._build_dropcard()
        self._build_grid_card()       # 1순위
        self._build_engines_card()    # 2순위(접힘)
        self._build_general_card()
        self._build_output_card()
        self._build_run_card()
        self.v.addStretch(1)

        grip_row = QHBoxLayout()
        grip_row.addStretch(1)
        grip = QSizeGrip(self._root)
        grip.setStyleSheet("background: transparent;")
        grip_row.addWidget(grip, 0, Qt.AlignRight | Qt.AlignBottom)
        root.addLayout(grip_row)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._render_preview)
        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.timeout.connect(self._do_seek)
        self._pending_seek = 0
        self._frame_guard = False
        self._wire_preview()

        QTimer.singleShot(350, self._maybe_first_run)
        QTimer.singleShot(1200, self._start_update_check)

    # ------------------------------------------------------------ 배너/미리보기
    def _build_banner(self):
        self.banner = QFrame()
        self.banner.setVisible(False)
        self.banner.setStyleSheet(
            f"QFrame{{background: rgba(255,255,255,0.06);"
            f"border-bottom:1px solid {theme.CARD_BORDER};}}")
        lay = QHBoxLayout(self.banner)
        lay.setContentsMargins(16, 8, 12, 8)
        self.banner_label = QLabel("새 버전이 있습니다.")
        self.banner_label.setObjectName("Muted")
        lay.addWidget(self.banner_label, 1)
        self.banner_pb = QProgressBar()
        self.banner_pb.setFixedWidth(140)
        self.banner_pb.setVisible(False)
        lay.addWidget(self.banner_pb)
        self.btn_update = QPushButton("지금 업데이트")
        self.btn_update.setObjectName("Ghost")
        self.btn_update.setCursor(Qt.PointingHandCursor)
        self.btn_update.clicked.connect(self._do_update)
        lay.addWidget(self.btn_update)
        self.btn_later = QPushButton("나중에")
        self.btn_later.setObjectName("Ghost")
        self.btn_later.setCursor(Qt.PointingHandCursor)
        self.btn_later.clicked.connect(lambda: self.banner.setVisible(False))
        lay.addWidget(self.btn_later)

    def _build_preview_panel(self) -> QWidget:
        card = GlassCard(pad=14)
        card.setMinimumWidth(340)
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        card.v.addWidget(SectionHeader(
            "미리보기",
            "설정이 아래 프레임에 실시간 반영됩니다. 슬라이더/버튼으로 프레임을 이동하세요."))

        self.preview = QLabel("영상/이미지를 첨부하면\n여기에서 미리 볼 수 있어요")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(320, 260)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview.setStyleSheet(
            f"background: rgba(0,0,0,0.35); border:1px solid {theme.CARD_BORDER};"
            f"border-radius:12px; color:{theme.FG_SUBTLE}; font-size:11px;")
        card.v.addWidget(self.preview, 1)

        # 프레임 이동 컨트롤(동영상일 때만 표시)
        self._frame_row = QWidget()
        fr = QHBoxLayout(self._frame_row)
        fr.setContentsMargins(0, 0, 0, 0)
        fr.setSpacing(8)
        self.btn_prev = IconButton("prev")
        self.btn_next = IconButton("next")
        for b in (self.btn_prev, self.btn_next):
            b.setObjectName("Ghost")
            b.setFixedSize(34, 28)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip("1프레임 이동")
        self.btn_prev.clicked.connect(lambda: self._step_frame(-1))
        self.btn_next.clicked.connect(lambda: self._step_frame(1))
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setRange(0, 0)
        self.frame_slider.valueChanged.connect(self._on_frame_slider)
        self.frame_slider.setStyleSheet(
            "QSlider::groove:horizontal{height:6px;border-radius:3px;"
            "background:rgba(255,255,255,0.10);}"
            f"QSlider::sub-page:horizontal{{height:6px;border-radius:3px;background:{theme.ACCENT};}}"
            f"QSlider::handle:horizontal{{width:14px;height:14px;margin:-5px 0;"
            f"border-radius:7px;background:{theme.FG};border:2px solid {theme.BG};}}")
        fr.addWidget(self.btn_prev)
        fr.addWidget(self.frame_slider, 1)
        fr.addWidget(self.btn_next)
        card.v.addWidget(self._frame_row)
        self._frame_row.setVisible(False)

        self.preview_caption = QLabel("")
        self.preview_caption.setObjectName("SectionDesc")
        self.preview_caption.setWordWrap(True)
        card.v.addWidget(self.preview_caption)
        return card

    # ------------------------------------------------------------------ cards
    def _build_dropcard(self):
        card = GlassCard()
        card.v.addWidget(SectionHeader(
            "영상·이미지 첨부",
            "얼굴이 있는 영상/이미지를 넣으면 얼굴만 처리합니다. 여러 개 일괄 처리 가능."))
        self.drop = DropArea()
        self.drop.filesDropped.connect(self.set_inputs)
        card.v.addWidget(self.drop)
        self.thumbs = ThumbGrid()
        self.thumbs.changed.connect(self._on_thumbs_changed)
        self.thumbs.setVisible(False)
        card.v.addWidget(self.thumbs)
        self.meta = QLabel("첨부된 파일 없음")
        self.meta.setObjectName("Muted")
        card.v.addWidget(self.meta)
        self.v.addWidget(card)

    def _build_grid_card(self):
        card = GlassCard()
        head = QHBoxLayout()
        head.addWidget(SectionHeader(
            "얼굴 그리드", "얼굴 크기·위치에 맞춰 격자를 씌웁니다."), 1)
        self.grid_enable = ToggleSwitch()
        self.grid_enable.setChecked(True)
        self.grid_enable.toggled.connect(self._toggle_grid_controls)
        head.addWidget(self.grid_enable, 0, Qt.AlignTop)
        card.v.addLayout(head)

        self._grid_box = QWidget()
        gb = QVBoxLayout(self._grid_box)
        gb.setContentsMargins(0, 4, 0, 0)
        gb.setSpacing(10)

        self.sl_rows = LabeledSlider("가로 칸 수", 1, 20, 6, 19, 0, " 칸")
        self.sl_cols = LabeledSlider("세로 칸 수", 1, 20, 6, 19, 0, " 칸")
        self.sl_thick = LabeledSlider("선 두께", 1, 8, 2, 7, 0, " px")
        self.sl_opacity = LabeledSlider("투명도(불투명도)", 0.05, 1.0, 0.6, 95, 2)
        self.sl_margin = LabeledSlider("영역 여백", 0.0, 0.4, 0.06, 40, 2)
        self.sl_dotr = LabeledSlider("교차점 점 크기", 1, 8, 3, 7, 0, " px")
        for w in (self.sl_rows, self.sl_cols, self.sl_thick,
                  self.sl_opacity, self.sl_margin, self.sl_dotr):
            gb.addWidget(w)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("색상")); row1.addSpacing(6)
        self.color = ColorSwatch(QColor(255, 255, 255))
        row1.addWidget(self.color)
        row1.addSpacing(16)
        row1.addWidget(QLabel("모양")); row1.addSpacing(6)
        self.shape = NoWheelComboBox()
        self.shape.addItem("타원(얼굴형)", "ellipse")
        self.shape.addItem("사각형", "rect")
        row1.addWidget(self.shape, 1)
        gb.addLayout(row1)

        self.grid_align = ToggleRow("얼굴 기울기 정렬", "눈 위치 기준으로 격자를 회전", True)
        self.grid_dots = ToggleRow("교차점 점 표시", "", False)
        gb.addWidget(self.grid_align)
        gb.addWidget(self.grid_dots)

        card.v.addWidget(self._grid_box)
        self.v.addWidget(card)

    def _build_engines_card(self):
        card = CollapsibleCard(
            "회피 엔진 (A · B · C)",
            "얼굴 검출·매칭을 방해하는 처리. 필요할 때 펼쳐서 사용하세요.",
            expanded=False)
        self.eng_a = ToggleRow("A · Adversarial Cloak",
                               "검출기를 속이는 미세 노이즈 (권장)", False)
        self.eng_b = ToggleRow("B · Frequency Perturb",
                               "얼굴 임베딩/매칭 회피 (인물 매칭 대비)", False)
        self.eng_c = ToggleRow("C · Semantic Evade", "검출 자체 방해 (보험)", False)
        for w in (self.eng_a, self.eng_b, self.eng_c):
            card.body.addWidget(w)
        card.body.addWidget(hline())
        self.sl_eps = LabeledSlider("A 강도 (eps · 낮을수록 품질↑)",
                                    2, 30, 6, steps=28, decimals=0, suffix=" /255")
        self.sl_str = LabeledSlider("B·C 강도 (strength)",
                                    0.01, 0.20, 0.05, steps=19, decimals=2)
        card.body.addWidget(self.sl_eps)
        card.body.addWidget(self.sl_str)
        self.v.addWidget(card)

    def _build_general_card(self):
        card = GlassCard()
        card.v.addWidget(SectionHeader("트래킹 & 품질"))
        self.tracking = ToggleRow(
            "얼굴 트래킹",
            "프레임 간 추적·스무딩으로 격자/노이즈 떨림(플리커) 방지", True)
        card.v.addWidget(self.tracking)
        card.v.addWidget(hline())

        qrow = QVBoxLayout(); qrow.setSpacing(4)
        qrow.addWidget(_muted("렌더링 품질"))
        self.quality = NoWheelComboBox()
        for key, p in ff.QUALITY_PRESETS.items():
            self.quality.addItem(p.label, key)
        self.quality.setCurrentIndex(
            list(ff.QUALITY_PRESETS.keys()).index(ff.DEFAULT_PRESET))
        self.quality.currentIndexChanged.connect(self._update_quality_desc)
        qrow.addWidget(self.quality)
        self.quality_desc = QLabel(); self.quality_desc.setObjectName("SectionDesc")
        self.quality_desc.setWordWrap(True)
        qrow.addWidget(self.quality_desc)
        card.v.addLayout(qrow)
        self._update_quality_desc()
        self.v.addWidget(card)

    def _build_output_card(self):
        card = GlassCard()
        head = QHBoxLayout()
        head.addWidget(SectionHeader(
            "4초 채우기", "짧은 영상 뒤에 검은 화면을 이어붙여 목표 길이를 맞춥니다."), 1)
        self.pad_enable = ToggleSwitch()
        self.pad_enable.toggled.connect(lambda v: self.sl_pad.setEnabled(v))
        head.addWidget(self.pad_enable, 0, Qt.AlignTop)
        card.v.addLayout(head)
        self.sl_pad = LabeledSlider("목표 길이", 1.0, 15.0, 4.0, 28, 1, " 초")
        self.sl_pad.setEnabled(False)
        card.v.addWidget(self.sl_pad)
        card.v.addWidget(hline())

        self.out_label = _muted("저장 경로")
        card.v.addWidget(self.out_label)
        orow = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("저장할 위치/파일명…")
        btn = QPushButton("찾아보기")
        btn.setObjectName("Ghost")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self.pick_output)
        orow.addWidget(self.out_edit, 1); orow.addWidget(btn)
        card.v.addLayout(orow)
        self.v.addWidget(card)

    def _build_run_card(self):
        card = GlassCard()
        self.bar = QProgressBar(); self.bar.setValue(0)
        card.v.addWidget(self.bar)
        self.log = QTextEdit(); self.log.setReadOnly(True); self.log.setFixedHeight(92)
        card.v.addWidget(self.log)

        self.run_btn = QPushButton("실행")
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self._style_run_button(running=False)
        self.run_btn.clicked.connect(self.on_run_clicked)
        card.v.addWidget(self.run_btn)
        self.v.addWidget(card)

    def _style_run_button(self, running: bool):
        # 인라인 스타일로 확실히 밝은 프라이머리 버튼 보장(어두움 문제 방지)
        if running:
            bg, hover, fg = theme.CARD_HOVER, theme.CARD_HOVER, theme.FG
            border = f"1px solid {theme.INPUT_BORDER}"
            self.run_btn.setText("취소")
        else:
            bg, hover, fg = theme.ACCENT, theme.ACCENT_HOVER, theme.ON_ACCENT
            border = "none"
            self.run_btn.setText("실행")
        self.run_btn.setStyleSheet(
            f"QPushButton{{background:{bg};color:{fg};border:{border};"
            f"border-radius:12px;padding:14px;font-weight:700;font-size:14px;}}"
            f"QPushButton:hover{{background:{hover};}}"
            f"QPushButton:disabled{{background:rgba(255,255,255,0.25);"
            f"color:rgba(9,9,11,0.5);}}")

    # ------------------------------------------------------------ 미리보기 로직
    def _wire_preview(self):
        for sl in (self.sl_rows, self.sl_cols, self.sl_thick, self.sl_opacity,
                   self.sl_margin, self.sl_dotr, self.sl_eps, self.sl_str):
            sl.changed.connect(self._schedule_preview)
        for tg in (self.grid_enable, self.grid_align.sw, self.grid_dots.sw,
                   self.eng_a.sw, self.eng_b.sw, self.eng_c.sw, self.tracking.sw):
            tg.toggled.connect(self._schedule_preview)
        self.color.colorChanged.connect(lambda *_: self._schedule_preview())
        self.shape.currentIndexChanged.connect(self._schedule_preview)

    def _schedule_preview(self, *args):
        if self._preview_base is not None:
            self._preview_timer.start(220)

    def _get_detector(self):
        if self._detector is None:
            self._detector = FaceDetector(score_threshold=0.6)
        return self._detector

    def _downscale_for_preview(self, f):
        h, w = f.shape[:2]
        if w > 960:
            s = 960.0 / w
            return cv2.resize(f, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        return f.copy()

    def _render_preview(self):
        base = self._preview_base
        if base is None:
            return
        try:
            src = self._downscale_for_preview(base)
            cfg = self._collect_config()
            proc = FrameProcessor(cfg, self._get_detector())
            out = proc.process(src, temporal=False)
            self._show_preview_rgb(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
            faces = proc.last_count
            bits = [f"얼굴 {faces}명 감지" if faces else "이 프레임에서 얼굴 미검출"]
            if cfg.use_grid:
                bits.append(f"그리드 {int(cfg.grid.rows)}×{int(cfg.grid.cols)}·"
                            f"{'타원' if cfg.grid.shape=='ellipse' else '사각'}")
            eng = [k for k, v in cfg.methods.items() if v]
            if eng:
                bits.append("엔진 " + "·".join(eng))
            if self._preview_total > 1:
                bits.append(f"프레임 {self._preview_idx + 1}/{self._preview_total}")
            self.preview_caption.setText("  ·  ".join(bits))
        except Exception:
            pass

    # ---- 프레임 이동 ----
    def _release_preview_cap(self):
        if self._preview_cap is not None:
            try:
                self._preview_cap.release()
            except Exception:
                pass
        self._preview_cap = None

    def _find_face_frame(self, cap, total):
        """얼굴이 잡히는 프레임을 찾아 (idx, frame) 반환. 없으면 첫 프레임."""
        det = self._get_detector()
        if total and total > 1:
            n = min(14, total)
            step = max(1, total // n)
            candidates = list(range(0, total, step))[:n]
        else:
            candidates = [0]
        first = None
        for idx in candidates:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, fr = cap.read()
            if not ok:
                continue
            if first is None:
                first = (idx, fr)
            try:
                if det.detect(self._downscale_for_preview(fr)):
                    return idx, fr
            except Exception:
                pass
        if first is not None:
            return first
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ok, fr = cap.read()
        return (0, fr if ok else None)

    def _step_frame(self, delta):
        if self._preview_cap is None or self._preview_total <= 1:
            return
        idx = max(0, min(self._preview_total - 1, self._preview_idx + delta))
        self._frame_guard = True
        self.frame_slider.setValue(idx)
        self._frame_guard = False
        self._seek_and_render(idx)

    def _on_frame_slider(self, val):
        if self._frame_guard:
            return
        self._pending_seek = val
        self._seek_timer.start(60)

    def _do_seek(self):
        self._seek_and_render(self._pending_seek)

    def _seek_and_render(self, idx):
        cap = self._preview_cap
        if cap is None:
            return
        idx = max(0, min(self._preview_total - 1, int(idx)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, fr = cap.read()
        if ok:
            self._preview_base = fr
            self._preview_idx = idx
            self._render_preview()

    def _show_preview_rgb(self, rgb):
        self._last_preview_rgb = rgb
        self._repaint_preview()

    def _repaint_preview(self):
        rgb = self._last_preview_rgb
        if rgb is None:
            return
        try:
            h, w, ch = rgb.shape
            img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
            pix = QPixmap.fromImage(img.copy())
            self.preview.setPixmap(pix.scaled(
                self.preview.width(), self.preview.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception:
            pass

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._repaint_preview()

    # ------------------------------------------------------------------ logic
    def _toggle_grid_controls(self, v):
        self._grid_box.setVisible(v)
        self._schedule_preview()

    def _update_quality_desc(self):
        key = self.quality.currentData()
        self.quality_desc.setText(ff.QUALITY_PRESETS[key].desc)

    def set_inputs(self, paths):
        add = [p for p in paths if is_image(p) or is_video(p)]
        if not add:
            return
        merged = list(self.inputs)
        for p in add:
            if p not in merged:
                merged.append(p)
        self._apply_inputs(merged, rebuild_thumbs=True)

    def _on_thumbs_changed(self, paths):
        self._apply_inputs(list(paths), rebuild_thumbs=False)

    def _apply_inputs(self, paths, rebuild_thumbs):
        self.inputs = paths
        has = len(paths) > 0
        if rebuild_thumbs:
            self.thumbs.set_files(paths)
        self.thumbs.setVisible(has)
        self.drop.set_compact(has)
        if has:
            self._update_meta()
            self._set_default_output()
            self._load_preview_source()
        else:
            self.meta.setText("첨부된 파일 없음")
            self._release_preview_cap()
            self._preview_base = None
            self._last_preview_rgb = None
            self._preview_total = 0
            self._frame_row.setVisible(False)
            self.preview.setPixmap(QPixmap())
            self.preview.setText("영상/이미지를 첨부하면\n여기에서 미리 볼 수 있어요")
            self.preview_caption.setText("")
            self.out_edit.clear()

    def _load_preview_source(self):
        self._release_preview_cap()
        self._preview_base = None
        self._last_preview_rgb = None
        self._preview_total = 0
        self._preview_idx = 0
        p = self.inputs[0]
        try:
            if is_video(p):
                cap = cv2.VideoCapture(p)
                total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                self._preview_cap = cap
                self._preview_total = max(0, total)
                idx, frame = self._find_face_frame(cap, total)
                self._preview_idx = idx
                self._preview_base = frame
                self._frame_guard = True
                self.frame_slider.setRange(0, max(0, total - 1) if total > 1 else 0)
                self.frame_slider.setValue(idx)
                self._frame_guard = False
                self._frame_row.setVisible(total > 1)
            else:
                data = _imread_unicode(p)
                if data is not None:
                    if data.ndim == 2:
                        self._preview_base = cv2.cvtColor(data, cv2.COLOR_GRAY2BGR)
                    elif data.shape[2] == 4:
                        self._preview_base = cv2.cvtColor(data, cv2.COLOR_BGRA2BGR)
                    else:
                        self._preview_base = data[:, :, :3].copy()
                self._frame_row.setVisible(False)
        except Exception:
            self._preview_base = None
            self._frame_row.setVisible(False)

        if self._preview_base is not None:
            self._render_preview()
        else:
            self.preview.setText("첫 프레임을 불러오지 못했습니다")

    def _update_meta(self):
        imgs = [p for p in self.inputs if is_image(p)]
        vids = [p for p in self.inputs if is_video(p)]
        parts = []
        if vids:
            parts.append(f"동영상 {len(vids)}")
        if imgs:
            parts.append(f"이미지 {len(imgs)}")
        head = " · ".join(parts) if parts else "없음"
        if len(self.inputs) == 1 and vids:
            try:
                cap = cv2.VideoCapture(self.inputs[0])
                fps = cap.get(cv2.CAP_PROP_FPS) or 0
                n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()
                dur = (n / fps) if fps else 0
                head += f"  |  {w}×{h} · {fps:.1f}fps · {dur:.1f}s"
                if 0 < dur <= 4:
                    head += "   ⚠ 4초 이하 (4초 채우기 권장)"
            except Exception:
                pass
        elif len(self.inputs) == 1 and imgs:
            head = "이미지 · " + os.path.basename(self.inputs[0])
        self.meta.setText(head)

    def _set_default_output(self):
        if len(self.inputs) == 1:
            p = self.inputs[0]
            base, ext = os.path.splitext(p)
            out = base + "_cloaked.mp4" if is_video(p) else base + "_cloaked" + ext
            self.out_edit.setText(out)
            self.out_label.setText("저장 경로 (파일)")
        else:
            folder = os.path.join(
                os.path.dirname(os.path.abspath(self.inputs[0])), "cloaked_output")
            self.out_edit.setText(folder)
            self.out_label.setText("저장 폴더 (여러 파일 일괄)")

    def pick_output(self):
        if len(self.inputs) > 1:
            d = QFileDialog.getExistingDirectory(
                self, "저장 폴더 선택", self.out_edit.text() or "")
            if d:
                self.out_edit.setText(d)
        else:
            cur = self.out_edit.text() or "cloaked.mp4"
            path, _ = QFileDialog.getSaveFileName(
                self, "저장 위치", cur,
                "Media (*.mp4 *.mov *.mkv *.png *.jpg *.jpeg *.webp)")
            if path:
                self.out_edit.setText(path)

    def _build_jobs(self):
        out = self.out_edit.text().strip()
        if len(self.inputs) == 1:
            return [(self.inputs[0], out)]
        jobs = []
        for p in self.inputs:
            stem, ext = os.path.splitext(os.path.basename(p))
            oext = ".mp4" if is_video(p) else ext
            jobs.append((p, os.path.join(out, f"{stem}_cloaked{oext}")))
        return jobs

    def _collect_config(self) -> RenderConfig:
        gp = GridParams(
            rows=int(self.sl_rows.valueF()),
            cols=int(self.sl_cols.valueF()),
            thickness=int(self.sl_thick.valueF()),
            auto_thickness=True,
            color=self.color.bgr(),
            opacity=self.sl_opacity.valueF(),
            margin=self.sl_margin.valueF(),
            shape=self.shape.currentData(),
            align_angle=self.grid_align.isChecked(),
            dots=self.grid_dots.isChecked(),
            dot_radius=int(self.sl_dotr.valueF()),
        )
        return RenderConfig(
            methods={"A": self.eng_a.isChecked(),
                     "B": self.eng_b.isChecked(),
                     "C": self.eng_c.isChecked()},
            eps=self.sl_eps.valueF(),
            strength=self.sl_str.valueF(),
            use_grid=self.grid_enable.isChecked(),
            grid=gp,
            tracking=self.tracking.isChecked(),
            quality=self.quality.currentData(),
            pad_enabled=self.pad_enable.isChecked(),
            pad_seconds=self.sl_pad.valueF(),
        )

    def on_run_clicked(self):
        if self._running:
            if self.worker:
                self.worker.abort()
                self.log_msg("중단 요청…")
            return
        if not self.inputs:
            self._warn("먼저 영상 또는 이미지를 첨부하세요.")
            return
        if not self.out_edit.text().strip():
            self._warn("저장 경로를 지정하세요.")
            return
        cfg = self._collect_config()
        if not any(cfg.methods.values()) and not cfg.use_grid:
            self._warn("회피 엔진(A/B/C) 중 하나를 켜거나 얼굴 그리드를 활성화하세요.")
            return
        self._jobs = self._build_jobs()
        if not self._jobs:
            self._warn("저장 경로를 확인하세요.")
            return

        self._set_running(True)
        self.bar.setValue(0)
        self.log.clear()
        self.log_msg(f"=== 처리 시작 ({len(self._jobs)}개) ===")
        self.worker = MediaWorker(self._jobs, cfg)
        self.worker.progress.connect(self.bar.setValue)
        self.worker.status.connect(self.log_msg)
        self.worker.preview.connect(self.on_preview)
        self.worker.done.connect(self.on_done)
        self.worker.failed.connect(self.on_fail)
        self.worker.start()

    def _set_running(self, running: bool):
        self._running = running
        self._style_run_button(running)

    def on_preview(self, rgb):
        self._show_preview_rgb(rgb)

    def on_done(self, msg):
        self._set_running(False)
        self.bar.setValue(100)
        self.log_msg(f"완료 → {msg}")
        folder = os.path.dirname(os.path.abspath(self._jobs[0][1])) \
            if self._jobs else ""
        box = QMessageBox(self)
        box.setWindowTitle("완료")
        box.setText(f"저장되었습니다:\n{msg}")
        box.setIcon(QMessageBox.Information)
        open_btn = box.addButton("폴더 열기", QMessageBox.ActionRole)
        box.addButton("확인", QMessageBox.AcceptRole)
        box.exec()
        if box.clickedButton() == open_btn and folder:
            self._open_folder(folder)

    def on_fail(self, err):
        self._set_running(False)
        self.log_msg(f"실패: {err}")
        QMessageBox.critical(self, "실패", err)

    def log_msg(self, msg):
        self.log.append(msg)

    def _warn(self, msg):
        QMessageBox.warning(self, "알림", msg)

    @staticmethod
    def _open_folder(folder):
        try:
            if os.name == "nt":
                os.startfile(folder)  # noqa
        except Exception:
            pass

    # ------------------------------------------------------------ 자동 업데이트
    def _start_update_check(self):
        self._checker = _CheckThread()
        self._checker.result.connect(self._on_update_result)
        self._checker.start()

    def _on_update_result(self, info):
        if not info or not info.get("setup"):
            return
        self._update_info = info
        self.banner_label.setText(
            f"새 버전 v{info['version']} 이(가) 있습니다. 지금 업데이트할 수 있어요.")
        self.banner.setVisible(True)

    def _do_update(self):
        info = getattr(self, "_update_info", None)
        if not info or not info.get("setup"):
            return
        self.btn_update.setEnabled(False)
        self.btn_later.setEnabled(False)
        self.banner_pb.setVisible(True)
        self.banner_pb.setValue(0)
        self.banner_label.setText("업데이트 다운로드 중…")
        self._downloader = _DownloadThread(info["setup"])
        self._downloader.progress.connect(lambda f: self.banner_pb.setValue(int(f * 100)))
        self._downloader.done.connect(self._on_update_downloaded)
        self._downloader.failed.connect(self._on_update_failed)
        self._downloader.start()

    def _on_update_downloaded(self, path):
        self.banner_label.setText("설치기를 실행합니다. 앱이 종료됩니다…")
        try:
            os.startfile(path)  # noqa
        except Exception:
            import subprocess
            subprocess.Popen([path])
        QTimer.singleShot(600, self.close)

    def _on_update_failed(self, err):
        self.banner_pb.setVisible(False)
        self.btn_update.setEnabled(True)
        self.btn_later.setEnabled(True)
        self.banner_label.setText(f"업데이트 실패: {err}. 릴리스 페이지에서 수동 설치하세요.")

    # ------------------------------------------------------------------ misc
    def _maybe_first_run(self):
        if not self.settings.value("tutorial_seen", False, type=bool):
            self.show_tutorial()

    def show_tutorial(self):
        dlg = TutorialDialog(self)
        dlg.exec()
        self.settings.setValue("tutorial_seen", True)

    def showEvent(self, e):
        super().showEvent(e)
        if not self._glass:
            self._glass = True
            apply_glass(self, theme.ACRYLIC_ARGB, acrylic=True)


def _muted(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Muted")
    return lbl


class _Root(QWidget):
    """반투명 라운드 배경(아크릴 위에 얹히는 유리 패널)."""

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        p.fillPath(path, QColor(12, 13, 18, 232))
        g = QLinearGradient(0, 0, 0, 120)
        g.setColorAt(0.0, QColor(255, 255, 255, 16))
        g.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, g)
