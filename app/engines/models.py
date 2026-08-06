"""
얼굴 검출 모델(YuNet ONNX) 탐지 및 자동 다운로드.

우선순위:
  1) 실행폴더/번들 리소스에 이미 존재하면 그걸 사용 (오프라인 OK)
  2) 없으면 캐시 폴더(%LOCALAPPDATA%/SeedanceCloak/models)로 자동 다운로드
"""

from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Callable, Optional

from app.paths import cache_dir, search_dirs

YUNET_NAME = "face_detection_yunet_2023mar.onnx"
YUNET_URLS = [
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
    "face_detection_yunet_2023mar.onnx",
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx",
]

ProgressCb = Optional[Callable[[str, float], None]]


def find_yunet() -> Optional[Path]:
    for d in search_dirs("models"):
        p = d / YUNET_NAME
        if p.exists() and p.stat().st_size > 100_000:
            return p
    return None


def ensure_yunet(progress: ProgressCb = None) -> Optional[Path]:
    """YuNet 모델 경로를 반환. 없으면 다운로드 시도. 실패하면 None."""
    found = find_yunet()
    if found:
        return found

    dest = cache_dir() / "models" / YUNET_NAME
    for url in YUNET_URLS:
        try:
            if progress:
                progress("얼굴 검출 모델(YuNet) 다운로드 중...", 0.0)
            _download(url, dest, progress)
            if dest.exists() and dest.stat().st_size > 100_000:
                return dest
        except Exception:
            continue
    return None


def _download(url: str, dest: Path, progress: ProgressCb) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "SeedanceCloak/2.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        read = 0
        chunk = 1024 * 64
        with open(tmp, "wb") as f:
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                f.write(buf)
                read += len(buf)
                if progress and total:
                    progress("얼굴 검출 모델 다운로드 중...", read / total)
    tmp.replace(dest)
