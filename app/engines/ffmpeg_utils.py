"""
FFmpeg 9.0 탐지 / 자동 설치 / 명령 빌더.

동료 배포(exe) 시에는 빌드 스크립트가 ffmpeg.exe·ffprobe.exe 를 exe 옆에 넣어두므로
find_ffmpeg() 가 그것을 최우선으로 잡는다. 소스 실행 시 없으면 gyan.dev 에서
release-essentials(현재 9.0) 를 캐시 폴더로 자동 다운로드한다.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from app.paths import cache_dir, search_dirs

ProgressCb = Optional[Callable[[str, float], None]]

GYAN_ESSENTIALS = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

# Windows 에서 콘솔창 안 뜨게
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _run(cmd: list[str], **kw):
    return subprocess.run(
        cmd, capture_output=True, text=True,
        creationflags=_CREATE_NO_WINDOW, **kw
    )


def _exe(name: str) -> str:
    return name + (".exe" if os.name == "nt" else "")


def _find(name: str) -> Optional[str]:
    # 1) 실행폴더/번들 옆 (bin 포함)
    for d in search_dirs("bin"):
        p = d / _exe(name)
        if p.exists():
            return str(p)
    # 2) 캐시
    p = cache_dir() / "bin" / _exe(name)
    if p.exists():
        return str(p)
    # 3) PATH
    found = shutil.which(name)
    if found:
        return found
    return None


def find_ffmpeg() -> Optional[str]:
    return _find("ffmpeg")


def find_ffprobe() -> Optional[str]:
    return _find("ffprobe")


def ffmpeg_version(path: Optional[str] = None) -> str:
    path = path or find_ffmpeg()
    if not path:
        return "ffmpeg 없음"
    try:
        r = _run([path, "-version"])
        m = re.search(r"ffmpeg version (\S+)", r.stdout)
        return m.group(1) if m else "unknown"
    except Exception:
        return "unknown"


def ensure_ffmpeg(progress: ProgressCb = None) -> Optional[str]:
    """ffmpeg 경로 반환. 없으면 다운로드/추출."""
    found = find_ffmpeg()
    if found:
        return found

    dest_dir = cache_dir() / "bin"
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = cache_dir() / "ffmpeg_dl.zip"

    try:
        if progress:
            progress("FFmpeg 9.0 다운로드 중... (약 110MB, 최초 1회)", 0.0)
        _download(GYAN_ESSENTIALS, zip_path, progress)
        if progress:
            progress("FFmpeg 압축 해제 중...", 0.99)
        _extract_bins(zip_path, dest_dir)
    except Exception:
        return find_ffmpeg()
    finally:
        try:
            zip_path.unlink(missing_ok=True)
        except Exception:
            pass
    return find_ffmpeg()


def _download(url: str, dest: Path, progress: ProgressCb) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "SeedanceCloak/2.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        read = 0
        chunk = 1024 * 256
        with open(dest, "wb") as f:
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                f.write(buf)
                read += len(buf)
                if progress and total:
                    progress("FFmpeg 9.0 다운로드 중...", min(0.98, read / total))


def _extract_bins(zip_path: Path, dest_dir: Path) -> None:
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = info.filename
            base = os.path.basename(name)
            if base.lower() in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
                with z.open(info) as src, open(dest_dir / base, "wb") as dst:
                    shutil.copyfileobj(src, dst)


def has_audio(video: str) -> bool:
    probe = find_ffprobe()
    if not probe:
        return True  # 알 수 없으면 있다고 가정(선택 매핑으로 안전)
    try:
        r = _run([
            probe, "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=index", "-of", "csv=p=0", video,
        ])
        return bool(r.stdout.strip())
    except Exception:
        return True


def probe_duration(video: str) -> Optional[float]:
    probe = find_ffprobe()
    if not probe:
        return None
    try:
        r = _run([
            probe, "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", video,
        ])
        return float(r.stdout.strip())
    except Exception:
        return None


# ============================================================
#  품질 프리셋
# ============================================================
@dataclass(frozen=True)
class QualityPreset:
    key: str
    label: str
    desc: str
    args: tuple = field(default_factory=tuple)


QUALITY_PRESETS: dict[str, QualityPreset] = {
    "visually_lossless": QualityPreset(
        "visually_lossless", "원본 품질 유지 (권장)",
        "육안상 무손실. H.264 CRF14 · slow",
        ("-c:v", "libx264", "-preset", "slow", "-crf", "14", "-pix_fmt", "yuv420p"),
    ),
    "high": QualityPreset(
        "high", "고품질",
        "H.264 CRF18 · medium. 품질/용량 균형 상급",
        ("-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"),
    ),
    "balanced": QualityPreset(
        "balanced", "표준",
        "H.264 CRF20 · fast. 빠른 인코딩",
        ("-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p"),
    ),
    "small": QualityPreset(
        "small", "저용량 (저화질)",
        "H.264 CRF28 · veryfast. 파일 작게",
        ("-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p"),
    ),
    "lossless": QualityPreset(
        "lossless", "완전 무손실 (용량 매우 큼)",
        "H.264 QP0 · yuv444p. 검증/보관용",
        ("-c:v", "libx264", "-preset", "medium", "-qp", "0", "-pix_fmt", "yuv444p"),
    ),
    "hevc_high": QualityPreset(
        "hevc_high", "HEVC 고품질 (H.265)",
        "H.265 CRF20 · medium. 같은 품질에 용량↓ (호환성 주의)",
        ("-c:v", "libx265", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-tag:v", "hvc1"),
    ),
}

DEFAULT_PRESET = "visually_lossless"


def build_render_cmd(
    ffmpeg: str,
    width: int,
    height: int,
    fps: float,
    out_path: str,
    preset_key: str = DEFAULT_PRESET,
    audio_src: Optional[str] = None,
    pad_to_seconds: Optional[float] = None,
    simple: bool = False,
) -> list[str]:
    """
    stdin(rawvideo bgr24) 을 읽어 인코딩하는 ffmpeg 명령을 구성.

    audio_src   : 오디오를 가져올 원본(있을 때만). None 이면 무음 출력.
    pad_to_seconds: 검은화면 패딩으로 최소 길이 보장 시, 오디오도 무음 패딩.
    simple      : 실패 후 재시도용(부가 옵션 제거).
    """
    preset = QUALITY_PRESETS.get(preset_key, QUALITY_PRESETS[DEFAULT_PRESET])

    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-stats"]
    cmd += ["-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}", "-r", f"{fps:.6f}", "-i", "-"]

    use_audio = bool(audio_src)
    if use_audio:
        cmd += ["-i", audio_src]

    cmd += ["-map", "0:v:0"]
    if use_audio:
        cmd += ["-map", "1:a:0?"]

    cmd += list(preset.args)

    if use_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
        if pad_to_seconds:
            # 오디오를 무음으로 무한 패딩 → 영상(패딩 포함) 길이에 맞춰 잘림
            cmd += ["-af", "apad", "-shortest"]
        else:
            cmd += ["-shortest"]

    ext = os.path.splitext(out_path)[1].lower()
    if not simple and ext in (".mp4", ".mov", ".m4v"):
        cmd += ["-movflags", "+faststart"]

    cmd += [out_path]
    return cmd
