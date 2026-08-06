#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Seedance Cloak → 단일 실행 파일(exe) 빌드 스크립트.

수행 내용:
  1) FFmpeg 9.0(gyan release-essentials) 다운로드 → ffmpeg.exe/ffprobe.exe 추출
  2) YuNet 얼굴검출 모델 다운로드(엑세만 232KB, exe 에 번들)
  3) PyInstaller 로 onefile GUI exe 생성
  4) dist/SeedanceCloak/ 에 exe + ffmpeg.exe + ffprobe.exe 배치
  5) 배포용 zip 생성

사용:
  python build/build_exe.py                # 전체(ffmpeg 번들)
  python build/build_exe.py --no-ffmpeg    # ffmpeg 제외(최초 실행 시 자동 다운로드)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
STAGE = BUILD / "_stage"
DIST = ROOT / "dist"
APP_NAME = "SeedanceCloak"

GYAN = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
YUNET_NAME = "face_detection_yunet_2023mar.onnx"
YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
             "face_detection_yunet/face_detection_yunet_2023mar.onnx")


def log(msg): print(f"[build] {msg}", flush=True)


def _dl(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        log(f"이미 있음: {dest.name}")
        return
    log(f"다운로드: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "SeedanceBuild/2.0"})
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        read = 0
        while True:
            buf = r.read(1024 * 256)
            if not buf:
                break
            f.write(buf); read += len(buf)
            if total:
                pct = read / total * 100
                print(f"\r        {read//1_000_000}MB / {total//1_000_000}MB "
                      f"({pct:4.1f}%)", end="", flush=True)
        print()


def fetch_ffmpeg() -> tuple[Path, Path]:
    STAGE.mkdir(parents=True, exist_ok=True)
    zip_path = STAGE / "ffmpeg.zip"
    _dl(GYAN, zip_path)
    log("FFmpeg 압축 해제…")
    ffmpeg = STAGE / "ffmpeg.exe"
    ffprobe = STAGE / "ffprobe.exe"
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            base = os.path.basename(info.filename).lower()
            if base in ("ffmpeg.exe", "ffprobe.exe"):
                with z.open(info) as src, open(STAGE / base, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    if not ffmpeg.exists():
        raise SystemExit("ffmpeg.exe 추출 실패")
    return ffmpeg, ffprobe


def fetch_model() -> Path:
    model = STAGE / YUNET_NAME
    _dl(YUNET_URL, model)
    return model


def check_env():
    try:
        import PySide6  # noqa
    except Exception:
        raise SystemExit("PySide6 가 필요합니다: pip install PySide6")
    try:
        import cv2  # noqa
    except Exception:
        raise SystemExit("opencv 가 필요합니다: pip install opencv-contrib-python")
    # opencv 중복 설치 경고
    try:
        import importlib.metadata as md
        names = {d.metadata["Name"].lower() for d in md.distributions()}
        if "opencv-python" in names and "opencv-contrib-python" in names:
            log("⚠ opencv-python 과 opencv-contrib-python 이 함께 설치됨. "
                "가능하면 깨끗한 venv 에서 opencv-contrib-python 만 설치 권장.")
    except Exception:
        pass


def _kill_running():
    if os.name != "nt":
        return
    for name in (f"{APP_NAME}.exe", f"{APP_NAME}-Setup.exe"):
        subprocess.run(["taskkill", "/IM", name, "/F"],
                       capture_output=True, text=True)
    time.sleep(1.0)


def _clean_dir(p: Path, tries: int = 6):
    for _ in range(tries):
        if not p.exists():
            return
        try:
            shutil.rmtree(p)
            return
        except Exception:
            time.sleep(1.0)
    shutil.rmtree(p, ignore_errors=True)


def run_pyinstaller(model: Path, ffmpeg: Path | None, ffprobe: Path | None):
    _kill_running()
    pkg = DIST / APP_NAME
    _clean_dir(DIST)                    # 잠긴 파일 대비 재시도 정리
    pkg.mkdir(parents=True, exist_ok=True)

    workdir = BUILD / "_work"
    spec = BUILD / "_spec"
    add_data = f"{model}{os.pathsep}models"

    # 이동 없이 곧바로 배포 폴더로 빌드 → 파일 잠금/충돌 회피
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", APP_NAME,
        "--distpath", str(pkg),
        "--workpath", str(workdir),
        "--specpath", str(spec),
        "--paths", str(ROOT),
        "--add-data", add_data,
        "--collect-submodules", "app",
        str(ROOT / "run.py"),
    ]
    log("PyInstaller 실행…")
    log(" ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit("PyInstaller 실패")

    exe = pkg / f"{APP_NAME}.exe"
    if not exe.exists():
        raise SystemExit("exe 생성 확인 실패")
    if ffmpeg and ffmpeg.exists():
        shutil.copy2(ffmpeg, pkg / "ffmpeg.exe")
    if ffprobe and ffprobe.exists():
        shutil.copy2(ffprobe, pkg / "ffprobe.exe")

    # 사용 안내 동봉
    readme = pkg / "사용법.txt"
    readme.write_text(
        "Seedance Cloak\n"
        "================\n\n"
        "1) SeedanceCloak.exe 를 더블클릭하세요.\n"
        "2) 영상을 드래그&드롭 → 옵션 선택 → 실행.\n"
        "3) ffmpeg.exe/ffprobe.exe 는 exe 와 같은 폴더에 두세요(동봉됨).\n\n"
        "문의: 사내 담당자\n", encoding="utf-8")

    log(f"배포 폴더: {pkg}")
    return pkg


def make_zip(pkg: Path) -> Path:
    import app as appmod
    zip_base = DIST / f"{APP_NAME}_v{appmod.__version__}"
    zip_path = Path(str(zip_base) + ".zip")   # 버전의 점(2.0.0) 때문에 with_suffix 금지
    if zip_path.exists():
        zip_path.unlink()
    log("zip 패키징…")
    shutil.make_archive(str(zip_base), "zip", root_dir=DIST, base_dir=APP_NAME)
    log(f"완료: {zip_path}")
    return zip_path


def build_installer(zip_path: Path) -> Path:
    """앱 zip 을 내장한 원클릭 설치기(exe) 빌드."""
    log("원클릭 설치기 빌드…")
    payload = STAGE / "payload.zip"
    shutil.copy2(zip_path, payload)
    workdir = BUILD / "_work_inst"
    spec = BUILD / "_spec_inst"
    add = f"{payload}{os.pathsep}."
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile", "--windowed", "--name", f"{APP_NAME}-Setup",
        "--distpath", str(DIST), "--workpath", str(workdir),
        "--specpath", str(spec), "--add-data", add,
        str(BUILD / "installer_main.py"),
    ]
    log(" ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit("설치기 빌드 실패")
    setup = DIST / f"{APP_NAME}-Setup.exe"
    if not setup.exists():
        raise SystemExit("설치기 exe 확인 실패")
    log(f"설치기 생성: {setup}")
    return setup


def main():
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    check_env()
    bundle_ffmpeg = "--no-ffmpeg" not in sys.argv
    make_setup = "--no-installer" not in sys.argv

    model = fetch_model()
    ffmpeg = ffprobe = None
    if bundle_ffmpeg:
        ffmpeg, ffprobe = fetch_ffmpeg()
    else:
        log("ffmpeg 번들 생략(최초 실행 시 자동 다운로드).")

    pkg = run_pyinstaller(model, ffmpeg, ffprobe)
    zip_path = make_zip(pkg)
    if make_setup:
        build_installer(zip_path)
    log("빌드 성공 ✅")


if __name__ == "__main__":
    main()
