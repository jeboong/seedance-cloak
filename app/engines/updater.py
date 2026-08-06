"""
자동 업데이트 — GitHub 릴리스의 최신 버전을 확인하고 설치기를 내려받아 실행.

- check_for_update(): 최신 릴리스가 현재 버전보다 높으면 정보 dict 반환, 아니면 None
- download_setup():   설치기(exe)를 임시 폴더로 다운로드
순수 함수라 UI 스레드/일반 스크립트 어디서든 사용 가능.
"""

from __future__ import annotations

import json
import os
import tempfile
import urllib.request
from typing import Callable, Optional

import app as appmod

REPO = "jeboong/seedance-cloak"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"


def _ver(s: str) -> tuple:
    s = (s or "").strip().lstrip("vV")
    out = []
    for part in s.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out) or (0,)


def check_for_update(timeout: int = 8) -> Optional[dict]:
    try:
        req = urllib.request.Request(
            API_LATEST, headers={"User-Agent": "SeedanceCloak",
                                 "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except Exception:
        return None

    tag = data.get("tag_name") or ""
    if not tag:
        return None
    if _ver(tag) <= _ver(appmod.__version__):
        return None

    setup = zip_url = None
    for a in data.get("assets", []):
        name = (a.get("name") or "").lower()
        if name.endswith("-setup.exe"):
            setup = a.get("browser_download_url")
        elif name.endswith(".zip"):
            zip_url = a.get("browser_download_url")
    return {
        "version": tag.lstrip("vV"),
        "tag": tag,
        "setup": setup,
        "zip": zip_url,
        "page": data.get("html_url") or RELEASES_PAGE,
        "notes": data.get("body") or "",
    }


def download_setup(url: str, progress: Optional[Callable[[float], None]] = None,
                   timeout: int = 120) -> str:
    dest = os.path.join(tempfile.gettempdir(), "SeedanceCloak-Setup-latest.exe")
    req = urllib.request.Request(url, headers={"User-Agent": "SeedanceCloak"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        total = int(r.headers.get("Content-Length", 0))
        read = 0
        with open(dest, "wb") as f:
            while True:
                buf = r.read(1024 * 256)
                if not buf:
                    break
                f.write(buf)
                read += len(buf)
                if progress and total:
                    progress(read / total)
    return dest
