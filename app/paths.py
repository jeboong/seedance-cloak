"""
경로 유틸리티 — 개발 실행/PyInstaller 프리즈 실행 양쪽을 모두 지원.

- resource_path(): 번들된 읽기전용 리소스(모델, ffmpeg, 아이콘 등) 위치
- app_dir():       실행 파일(exe) 이 있는 폴더 (동료 배포 시 여기에 ffmpeg/모델을 같이 둠)
- cache_dir():     쓰기 가능한 캐시(자동 다운로드 저장소). %LOCALAPPDATA%/SeedanceCloak
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def resource_path(*parts: str) -> Path:
    """PyInstaller onefile 은 sys._MEIPASS 에 리소스를 풀어놓는다."""
    if is_frozen():
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent.parent
    return base.joinpath(*parts)


def app_dir() -> Path:
    """실행 파일이 위치한 폴더. 여기에 ffmpeg.exe / models 를 나란히 두면 우선 사용."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def cache_dir() -> Path:
    """자동 다운로드/설정을 저장할 쓰기 가능한 폴더."""
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    d = Path(root) / "SeedanceCloak"
    d.mkdir(parents=True, exist_ok=True)
    (d / "bin").mkdir(exist_ok=True)
    (d / "models").mkdir(exist_ok=True)
    return d


def search_dirs(sub: str) -> list[Path]:
    """리소스를 찾을 후보 폴더들(우선순위 순)."""
    cands = [
        app_dir() / sub,
        app_dir(),
        resource_path(sub),
        resource_path("assets", sub),
        cache_dir() / sub,
    ]
    # 중복 제거(순서 유지)
    seen: set[str] = set()
    out: list[Path] = []
    for c in cands:
        key = str(c).lower()
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out
