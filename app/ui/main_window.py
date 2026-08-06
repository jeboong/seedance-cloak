"""메인 윈도우 — 글래스모피즘 다크 UI 조립 + 렌더 파이프라인 연동."""

from __future__ import annotations

import os

import cv2
from PySide6.QtCore import QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QScrollArea,
                               QSizeGrip, QVBoxLayout, QWidget)

import app
from app.engines import ffmpeg_utils as ff
from app.engines.grid import GridParams
from app.engines.pipeline import (RenderConfig, MediaWorker, is_image,
                                  is_video)
from app.ui import theme
from app.ui.acrylic import apply_glass
from app.ui.tutorial import TutorialDialog
from app.ui.widgets import (ColorSwatch, DropArea, GlassCard, LabeledSlider,
                            SectionHeader, TitleBar, ToggleRow, ToggleSwitch,
                            hline)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.inputs: list[str] = []
        self._jobs: list[tuple[str, str]] = []
        self.worker = None
        self._running = False
        self._glass = False
        self.settings = QSettings("SeedanceCloak", "app")

        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(600, 680)
        self.resize(660, 900)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._root = _Root()
        outer.addWidget(self._root)

        root = QVBoxLayout(self._root)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.titlebar = TitleBar(
            f"{app.__app_name__}", f"Reference Cloak · v{app.__version__}")
        self.titlebar.helpRequested.connect(self.show_tutorial)
        self.titlebar.minimizeRequested.connect(self.showMinimized)
        self.titlebar.closeRequested.connect(self.close)
        root.addWidget(self.titlebar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.viewport().setStyleSheet("background: transparent;")
        content = QWidget()
        content.setAttribute(Qt.WA_StyledBackground, True)
        content.setStyleSheet("background: transparent;")
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self.v = QVBoxLayout(content)
        self.v.setContentsMargins(18, 6, 18, 18)
        self.v.setSpacing(14)

        self._build_dropcard()
        self._build_engines_card()
        self._build_grid_card()
        self._build_general_card()
        self._build_output_card()
        self._build_run_card()

        grip_row = QHBoxLayout()
        grip_row.addStretch(1)
        grip = QSizeGrip(self._root)
        grip.setStyleSheet("background: transparent;")
        grip_row.addWidget(grip, 0, Qt.AlignRight | Qt.AlignBottom)
        root.addLayout(grip_row)

        QTimer.singleShot(350, self._maybe_first_run)

    # ------------------------------------------------------------------ cards
    def _build_dropcard(self):
        card = GlassCard()
        card.v.addWidget(SectionHeader(
            "영상·이미지 첨부",
            "얼굴이 있는 영상/이미지를 넣으면 얼굴만 처리합니다. 여러 개를 한 번에 처리(배치)할 수 있어요."))
        self.drop = DropArea()
        self.drop.filesDropped.connect(self.set_inputs)
        card.v.addWidget(self.drop)
        self.meta = QLabel("첨부된 파일 없음")
        self.meta.setObjectName("Muted")
        card.v.addWidget(self.meta)
        self.v.addWidget(card)

    def _build_engines_card(self):
        card = GlassCard()
        card.v.addWidget(SectionHeader(
            "회피 엔진", "여러 개를 함께 켤 수 있습니다. 강도는 아래 슬라이더로 조절."))
        self.eng_a = ToggleRow("A · Adversarial Cloak",
                               "검출기를 속이는 미세 노이즈 (권장)", True)
        self.eng_b = ToggleRow("B · Frequency Perturb",
                               "얼굴 임베딩/매칭 회피 (인물 매칭 대비)", False)
        self.eng_c = ToggleRow("C · Semantic Evade",
                               "검출 자체 방해 (보험)", False)
        for w in (self.eng_a, self.eng_b, self.eng_c):
            card.v.addWidget(w)
        card.v.addWidget(hline())
        self.sl_eps = LabeledSlider("A 강도 (eps · 낮을수록 품질↑)",
                                    2, 30, 6, steps=28, decimals=0, suffix=" /255")
        self.sl_str = LabeledSlider("B·C 강도 (strength)",
                                    0.01, 0.20, 0.05, steps=19, decimals=2)
        card.v.addWidget(self.sl_eps)
        card.v.addWidget(self.sl_str)
        self.v.addWidget(card)

    def _build_grid_card(self):
        card = GlassCard()
        head = QHBoxLayout()
        sh = SectionHeader("얼굴 그리드 (신규)",
                           "얼굴 크기·위치에 맞춰 격자를 씌웁니다.")
        head.addWidget(sh, 1)
        self.grid_enable = ToggleSwitch()
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
        self.shape = QComboBox()
        self.shape.addItem("타원(얼굴형)", "ellipse")
        self.shape.addItem("사각형", "rect")
        row1.addWidget(self.shape, 1)
        gb.addLayout(row1)

        self.grid_align = ToggleRow("얼굴 기울기 정렬",
                                    "눈 위치 기준으로 격자를 회전", True)
        self.grid_dots = ToggleRow("교차점 점 표시", "", False)
        gb.addWidget(self.grid_align)
        gb.addWidget(self.grid_dots)

        card.v.addWidget(self._grid_box)
        self._grid_box.setVisible(False)
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
        self.quality = QComboBox()
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
        prow = QHBoxLayout()
        self.preview = QLabel("처리 중 미리보기가 여기에 표시됩니다")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(190)
        self.preview.setStyleSheet(
            f"background: rgba(0,0,0,0.30); border:1px solid {theme.CARD_BORDER};"
            f"border-radius:12px; color:{theme.FG_SUBTLE}; font-size:11px;")
        prow.addWidget(self.preview)
        card.v.addLayout(prow)

        from PySide6.QtWidgets import QProgressBar, QTextEdit
        self.bar = QProgressBar(); self.bar.setValue(0)
        card.v.addWidget(self.bar)
        self.log = QTextEdit(); self.log.setReadOnly(True); self.log.setFixedHeight(96)
        card.v.addWidget(self.log)

        self.run_btn = QPushButton("실행")
        self.run_btn.setObjectName("Primary")
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self.run_btn.clicked.connect(self.on_run_clicked)
        card.v.addWidget(self.run_btn)
        self.v.addWidget(card)

    # ------------------------------------------------------------------ logic
    def _toggle_grid_controls(self, v):
        self._grid_box.setVisible(v)

    def _update_quality_desc(self):
        key = self.quality.currentData()
        self.quality_desc.setText(ff.QUALITY_PRESETS[key].desc)

    def set_inputs(self, paths):
        paths = [p for p in paths if is_image(p) or is_video(p)]
        if not paths:
            return
        self.inputs = paths
        self.drop.set_files(paths)
        self._update_meta()
        self._set_default_output()

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
            self.out_edit.setPlaceholderText("저장할 위치/파일명…")
        else:
            folder = os.path.join(
                os.path.dirname(os.path.abspath(self.inputs[0])), "cloaked_output")
            self.out_edit.setText(folder)
            self.out_label.setText("저장 폴더 (여러 파일 일괄)")
            self.out_edit.setPlaceholderText("결과를 저장할 폴더…")

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
        if running:
            self.run_btn.setText("취소")
            self.run_btn.setObjectName("Ghost")
        else:
            self.run_btn.setText("실행")
            self.run_btn.setObjectName("Primary")
        self.run_btn.setStyleSheet("")
        self.run_btn.style().unpolish(self.run_btn)
        self.run_btn.style().polish(self.run_btn)

    def on_preview(self, rgb):
        try:
            h, w, ch = rgb.shape
            img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
            pix = QPixmap.fromImage(img.copy())
            self.preview.setPixmap(pix.scaled(
                self.preview.width(), self.preview.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception:
            pass

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

    # ------------------------------------------------------------------ misc
    def _maybe_first_run(self):
        if not self.settings.value("tutorial_seen", False, type=bool):
            self.show_tutorial()

    def show_tutorial(self):
        dlg = TutorialDialog(self)
        dlg.exec()
        if dlg.dont_show_again():
            self.settings.setValue("tutorial_seen", True)
        else:
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
        # 아크릴이 적용되면 유리처럼 비치고, 실패해도 충분히 어둡게(대비 확보)
        p.fillPath(path, QColor(12, 13, 18, 232))
        # 상단 미세 광택
        from PySide6.QtGui import QLinearGradient
        g = QLinearGradient(0, 0, 0, 120)
        g.setColorAt(0.0, QColor(255, 255, 255, 16))
        g.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, g)
