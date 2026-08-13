"""
렌더링 파이프라인.

- FrameProcessor : 프레임 1장에 대한 검출→트래킹→엔진 A/B/C→그리드 처리(재사용 코어)
- MediaWorker    : 여러 입력(이미지/동영상 혼합)을 배치로 처리하는 QThread

동영상: 프레임을 rawvideo(bgr24) 로 ffmpeg stdin 에 파이프 → 단일 인코딩(원본 화질 보존),
        짧은 영상 검은화면 패딩(+오디오 무음 패딩), ffmpeg 부재 시 OpenCV 폴백.
이미지: OpenCV 로 로드→처리→저장(품질 프리셋에 따라 PNG 무손실/JPG 품질), 알파 보존.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass, field

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

from app.engines import ffmpeg_utils as ff
from app.engines.cloak import adversarial_cloak
from app.engines.common import blend_into, feather_mask
from app.engines.detector import FaceDetector
from app.engines.frequency import freq_perturb
from app.engines.grid import GridParams, draw_face_grid
from app.engines.semantic import semantic_evade
from app.engines.tracker import FaceTracker

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".flv"}


def is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMAGE_EXTS


def is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS


@dataclass
class RenderConfig:
    methods: dict = field(default_factory=lambda: {"A": True, "B": False, "C": False})
    eps: float = 6.0
    strength: float = 0.05
    use_grid: bool = False
    grid: GridParams = field(default_factory=GridParams)
    tracking: bool = True
    quality: str = ff.DEFAULT_PRESET
    pad_enabled: bool = False
    pad_seconds: float = 4.0
    roi_shape: str = "ellipse"
    detect_score: float = 0.6
    # 수동 그리드(트래킹 OFF + 그리드 ON): 정규화 중심/크기 (0~1)
    man_cx: float = 0.5
    man_cy: float = 0.5
    man_w: float = 0.35
    man_h: float = 0.45


# ============================================================
#  프레임 처리 코어
# ============================================================
class FrameProcessor:
    def __init__(self, cfg: RenderConfig, detector: FaceDetector):
        self.cfg = cfg
        self.detector = detector
        self.tracker = FaceTracker(smooth=0.5, max_age=8)
        self.prev_gray = None
        self.prev_noise: dict[int, np.ndarray] = {}
        self.last_count = 0

    def reset(self):
        self.tracker.reset()
        self.prev_gray = None
        self.prev_noise.clear()

    def process(self, frame: np.ndarray, temporal: bool = True) -> np.ndarray:
        cfg = self.cfg
        H, W = frame.shape[:2]
        auto_grid = cfg.use_grid and cfg.tracking          # 얼굴 추적 그리드
        manual_grid = cfg.use_grid and not cfg.tracking     # 수동 고정 그리드
        any_engine = any(cfg.methods.values())
        need_detect = any_engine or auto_grid

        if need_detect:
            dets = self.detector.detect(frame)
            tracks = self.tracker.update(dets, tracking=cfg.tracking)
            self.last_count = len(tracks)

            cur_gray = None
            use_flow = temporal and cfg.tracking and cfg.methods.get("A")
            if use_flow:
                cur_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            for t in tracks:
                x1, y1, x2, y2 = [int(v) for v in t.box]
                x1 = max(0, min(W - 1, x1)); y1 = max(0, min(H - 1, y1))
                x2 = max(x1 + 1, min(W, x2)); y2 = max(y1 + 1, min(H, y2))
                if x2 - x1 < 8 or y2 - y1 < 8:
                    continue
                box = (x1, y1, x2, y2)
                roi = frame[y1:y2, x1:x2].copy()
                changed = False

                if cfg.methods.get("A"):
                    base_noise = None
                    pn = self.prev_noise.get(t.id) if cfg.tracking else None
                    if (use_flow and pn is not None and pn.shape == roi.shape[:2]
                            and self.prev_gray is not None
                            and self.prev_gray.shape == cur_gray.shape):
                        try:
                            flow = cv2.calcOpticalFlowFarneback(
                                self.prev_gray[y1:y2, x1:x2], cur_gray[y1:y2, x1:x2],
                                None, 0.5, 3, 15, 3, 5, 1.2, 0)
                            rh, rw = roi.shape[:2]
                            gx, gy = np.meshgrid(np.arange(rw, dtype=np.float32),
                                                 np.arange(rh, dtype=np.float32))
                            mx = (gx + flow[..., 0]).astype(np.float32)
                            my = (gy + flow[..., 1]).astype(np.float32)
                            base_noise = cv2.remap(pn, mx, my, cv2.INTER_LINEAR)
                        except Exception:
                            base_noise = None
                    mod, noise = adversarial_cloak(roi, cfg.eps, base_noise)
                    if cfg.tracking:
                        self.prev_noise[t.id] = noise
                    roi = mod
                    changed = True

                if cfg.methods.get("B"):
                    roi = freq_perturb(roi, cfg.strength)
                    changed = True
                if cfg.methods.get("C"):
                    roi = semantic_evade(roi, cfg.strength)
                    changed = True

                if changed:
                    mask = feather_mask(y2 - y1, x2 - x1, cfg.roi_shape, 0.18)
                    blend_into(frame, roi, box, mask)

                if auto_grid:
                    draw_face_grid(frame, box, cfg.grid, t.angle)

            if use_flow:
                self.prev_gray = cur_gray
        else:
            self.last_count = 0

        # 수동 그리드: 사용자가 지정한 위치·크기에 항상 표시(검출 무관)
        if manual_grid:
            bw = max(6.0, cfg.man_w * W)
            bh = max(6.0, cfg.man_h * H)
            cx = cfg.man_cx * W
            cy = cfg.man_cy * H
            box = (int(cx - bw / 2), int(cy - bh / 2),
                   int(cx + bw / 2), int(cy + bh / 2))
            draw_face_grid(frame, box, cfg.grid, 0.0)

        return frame


# ============================================================
#  배치 워커 (이미지/동영상 혼합)
# ============================================================
class MediaWorker(QThread):
    progress = Signal(int)       # 전체 0..100
    status = Signal(str)
    preview = Signal(object)     # RGB ndarray
    done = Signal(str)           # 완료 요약 메시지
    failed = Signal(str)

    def __init__(self, jobs: list[tuple[str, str]], cfg: RenderConfig):
        super().__init__()
        self.jobs = jobs                 # [(input, output), ...]
        self.cfg = cfg
        self._abort = False
        self._n = max(1, len(jobs))

    def abort(self):
        self._abort = True

    def _overall(self, done_files: int, frac: float):
        val = (done_files + max(0.0, min(1.0, frac))) / self._n * 100.0
        self.progress.emit(int(min(100, val)))

    def run(self):
        try:
            self._run()
        except Exception as e:
            self.failed.emit(f"예외: {e}")

    def _run(self):
        cfg = self.cfg
        any_video = any(is_video(i) for i, _ in self.jobs)

        self.status.emit("검출기 로딩...")
        detector = FaceDetector(score_threshold=cfg.detect_score)
        self.status.emit(f"검출기: {detector.mode_label}")
        processor = FrameProcessor(cfg, detector)

        ffmpeg = None
        if any_video:
            self.status.emit("FFmpeg 확인 중...")
            ffmpeg = ff.ensure_ffmpeg(lambda m, p: self.status.emit(m))
            if ffmpeg:
                self.status.emit(
                    f"FFmpeg {ff.ffmpeg_version(ffmpeg)} · 품질: "
                    f"{ff.QUALITY_PRESETS[cfg.quality].label}")
            else:
                self.status.emit("경고: FFmpeg 없음 → OpenCV 폴백(무음/기본화질)")

        ok_count = 0
        outputs: list[str] = []
        for idx, (inp, outp) in enumerate(self.jobs):
            if self._abort:
                self.failed.emit("사용자 중단")
                return
            name = os.path.basename(inp)
            self.status.emit(f"[{idx + 1}/{self._n}] {name}")
            os.makedirs(os.path.dirname(os.path.abspath(outp)), exist_ok=True)

            if is_image(inp):
                ok, err = self._process_image(inp, outp, processor)
            else:
                ok, err = self._render_video(inp, outp, processor, ffmpeg,
                                             lambda fr, i=idx: self._overall(i, fr))
            if not ok:
                self.failed.emit(f"{name}: {err}")
                return
            ok_count += 1
            outputs.append(outp)
            self._overall(idx + 1, 0.0)

        self.progress.emit(100)
        if self._n == 1:
            self.done.emit(outputs[0])
        else:
            folder = os.path.dirname(os.path.abspath(outputs[0]))
            self.done.emit(f"{ok_count}개 파일 완료 → {folder}")

    # ---------------- 이미지 ----------------
    def _process_image(self, inp: str, outp: str, processor: FrameProcessor):
        try:
            data = _imread_unicode(inp)
            if data is None:
                return False, "이미지를 열 수 없습니다."
            alpha = None
            if data.ndim == 2:
                bgr = cv2.cvtColor(data, cv2.COLOR_GRAY2BGR)
            elif data.shape[2] == 4:
                alpha = data[:, :, 3]
                bgr = cv2.cvtColor(data, cv2.COLOR_BGRA2BGR)
            else:
                bgr = data[:, :, :3].copy()

            processor.reset()
            bgr = processor.process(bgr, temporal=False)

            self.preview.emit(cv2.cvtColor(_downscale(bgr, 520), cv2.COLOR_BGR2RGB))

            if alpha is not None:
                out_img = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
                out_img[:, :, 3] = alpha
            else:
                out_img = bgr

            params = _imwrite_params(self.cfg.quality, outp)
            if not _imwrite_unicode(outp, out_img, params):
                return False, "이미지 저장 실패"
            return True, None
        except Exception as e:
            return False, str(e)

    # ---------------- 동영상 ----------------
    def _render_video(self, video: str, out_path: str, processor: FrameProcessor,
                      ffmpeg, on_progress):
        cap = cv2.VideoCapture(video)
        if not cap.isOpened():
            return False, "영상을 열 수 없습니다."
        cfg = self.cfg
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if fps <= 1e-3:
            fps = 30.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if W <= 0 or H <= 0:
            ok, probe = cap.read()
            if not ok:
                cap.release(); return False, "프레임을 읽을 수 없습니다."
            H, W = probe.shape[:2]
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        duration = ff.probe_duration(video)
        if duration is None and total > 1:
            duration = total / fps
        will_pad = bool(cfg.pad_enabled and duration is not None
                        and duration < cfg.pad_seconds - 1e-3)
        target_frames = int(round(cfg.pad_seconds * fps)) if will_pad else 0
        total_est = total if total > 1 else (int(duration * fps) if duration else 0)
        if will_pad:
            total_est = max(total_est, target_frames)

        proc = None
        writer = None
        stderr_file = None
        if ffmpeg:
            audio_src = video if ff.has_audio(video) else None
            cmd = ff.build_render_cmd(
                ffmpeg, W, H, fps, out_path, preset_key=cfg.quality,
                audio_src=audio_src,
                pad_to_seconds=cfg.pad_seconds if will_pad else None)
            stderr_file = tempfile.TemporaryFile()
            try:
                proc = subprocess.Popen(
                    cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                    stderr=stderr_file, creationflags=_CREATE_NO_WINDOW)
            except Exception as e:
                cap.release(); return False, f"FFmpeg 실행 실패: {e}"
        else:
            writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"),
                                     fps, (W, H))
            if not writer.isOpened():
                cap.release(); return False, "출력 파일 생성 실패(코덱)."

        processor.reset()

        def emit(fr):
            data = np.ascontiguousarray(fr)
            if proc is not None:
                proc.stdin.write(data.tobytes())
            else:
                writer.write(data)

        idx = 0
        pipe_broke = False
        try:
            while True:
                if self._abort:
                    _cleanup(cap, proc, writer, stderr_file, kill=True)
                    return False, "사용자 중단"
                ok, frame = cap.read()
                if not ok:
                    break
                if frame.shape[1] != W or frame.shape[0] != H:
                    frame = cv2.resize(frame, (W, H))
                frame = processor.process(frame, temporal=True)
                try:
                    emit(frame)
                except (BrokenPipeError, OSError):
                    # ffmpeg 가 먼저 종료됨(정상 종료일 수 있음) → 아래서 반환코드로 판정
                    pipe_broke = True
                    break
                idx += 1
                if idx % 12 == 0:
                    self.preview.emit(cv2.cvtColor(
                        _downscale(frame, 480), cv2.COLOR_BGR2RGB))
                if total_est and idx % 3 == 0:
                    on_progress(min(0.95, idx / total_est))

            if will_pad and not pipe_broke and idx < target_frames:
                self.status.emit(f"검은화면으로 {cfg.pad_seconds:.0f}초까지 채우는 중...")
                black = np.zeros((H, W, 3), np.uint8)
                while idx < target_frames:
                    if self._abort:
                        _cleanup(cap, proc, writer, stderr_file, kill=True)
                        return False, "사용자 중단"
                    try:
                        emit(black)
                    except (BrokenPipeError, OSError):
                        pipe_broke = True
                        break
                    idx += 1
                    if target_frames and idx % 3 == 0:
                        on_progress(min(0.95, idx / target_frames))

            cap.release()
            if proc is not None:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
                rc = proc.wait()
                err = _ffmpeg_error(stderr_file)
                if stderr_file:
                    stderr_file.close()
                # rc==0 이면 파이프가 끊겼어도(ffmpeg 조기 정상종료) 성공으로 간주
                if rc != 0:
                    return False, f"FFmpeg 인코딩 실패(코드 {rc}):\n{err}"
            else:
                writer.release()

            if not os.path.exists(out_path) or os.path.getsize(out_path) < 1024:
                return False, "출력 파일이 생성되지 않았습니다."
            return True, None
        except Exception as e:
            _cleanup(cap, proc, writer, stderr_file, kill=True)
            return False, f"처리 오류: {e}"


# ============================================================
#  헬퍼
# ============================================================
def _imread_unicode(path: str):
    """한글/유니코드 경로 안전 로드."""
    try:
        buf = np.fromfile(path, dtype=np.uint8)
        if buf.size == 0:
            return None
        return cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
    except Exception:
        return cv2.imread(path, cv2.IMREAD_UNCHANGED)


def _imwrite_unicode(path: str, img, params) -> bool:
    ext = os.path.splitext(path)[1].lower() or ".png"
    try:
        ok, buf = cv2.imencode(ext, img, params)
        if not ok:
            return False
        buf.tofile(path)
        return True
    except Exception:
        try:
            return cv2.imwrite(path, img, params)
        except Exception:
            return False


def _imwrite_params(preset: str, out_path: str) -> list[int]:
    ext = os.path.splitext(out_path)[1].lower()
    if ext in (".jpg", ".jpeg", ".webp"):
        q = {"visually_lossless": 98, "lossless": 100, "high": 95,
             "balanced": 92, "small": 82, "hevc_high": 95}.get(preset, 95)
        flag = cv2.IMWRITE_JPEG_QUALITY if ext in (".jpg", ".jpeg") \
            else cv2.IMWRITE_WEBP_QUALITY
        return [flag, q]
    if ext == ".png":
        return [cv2.IMWRITE_PNG_COMPRESSION, 3]
    return []


def _ffmpeg_error(stderr_file) -> str:
    try:
        if stderr_file is None:
            return "(로그 없음)"
        stderr_file.seek(0)
        data = stderr_file.read()
        if isinstance(data, bytes):
            data = data.decode("utf-8", "ignore")
        lines = [l for l in data.splitlines() if l.strip()
                 and not l.lstrip().startswith("frame=")
                 and "bitrate=" not in l]
        return "\n".join(lines[-6:]) or "(추가 정보 없음)"
    except Exception:
        return "(로그 읽기 실패)"


def _cleanup(cap, proc, writer, stderr_file, kill=False):
    try:
        cap.release()
    except Exception:
        pass
    if proc is not None:
        try:
            proc.kill() if kill else proc.stdin.close()
        except Exception:
            pass
    if writer is not None:
        try:
            writer.release()
        except Exception:
            pass
    if stderr_file is not None:
        try:
            stderr_file.close()
        except Exception:
            pass


def _downscale(frame, max_w):
    h, w = frame.shape[:2]
    if w <= max_w:
        return frame
    s = max_w / float(w)
    return cv2.resize(frame, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)


# 하위호환: 단일 영상 워커 별칭
class Worker(MediaWorker):
    def __init__(self, video: str, out_path: str, cfg: RenderConfig):
        super().__init__([(video, out_path)], cfg)
