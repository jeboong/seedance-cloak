#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Seedance Cloak — 원클릭 설치기 (관리자 권한 불필요).

동작:
  1) 더블클릭하면 즉시 설치 시작(추가 클릭 없음)
  2) %LOCALAPPDATA%\\Programs\\SeedanceCloak 에 앱 압축 해제(UAC 없음)
  3) 바탕화면 + 시작메뉴 바로가기 생성
  4) 제거용 uninstall.bat 생성
  5) 앱 자동 실행 후 설치기 종료

앱 본체(zip)는 이 exe 안에 payload.zip 으로 번들되어 있다.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
import zipfile
from pathlib import Path
from tkinter import ttk

APP_NAME = "SeedanceCloak"
APP_TITLE = "Seedance Cloak"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def _folder(kind: str) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"[Environment]::GetFolderPath('{kind}')"],
            capture_output=True, text=True, creationflags=NO_WINDOW)
        p = r.stdout.strip()
        if p:
            return p
    except Exception:
        pass
    return ""


def _make_shortcut(lnk: str, target: str, workdir: str):
    ps = (
        f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
        f"$s.TargetPath='{target}';"
        f"$s.WorkingDirectory='{workdir}';"
        f"$s.IconLocation='{target},0';"
        f"$s.Description='{APP_TITLE}';"
        f"$s.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   capture_output=True, text=True, creationflags=NO_WINDOW)


class Installer:
    def __init__(self):
        # 테스트 훅(운영 기본값에는 영향 없음)
        self.test_mode = bool(os.environ.get("SEEDANCE_INSTALLER_TEST"))
        self.install_root_override = os.environ.get("SEEDANCE_INSTALL_ROOT")

        self.root = tk.Tk()
        self.root.title(f"{APP_TITLE} 설치")
        if self.test_mode:
            self.root.withdraw()
        self.root.configure(bg="#09090b")
        self.root.resizable(False, False)
        w, h = 460, 236
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass

        pad = tk.Frame(self.root, bg="#09090b")
        pad.pack(fill="both", expand=True, padx=26, pady=22)

        tk.Label(pad, text=APP_TITLE, bg="#09090b", fg="#fafafa",
                 font=("Segoe UI", 18, "bold")).pack(anchor="w")
        tk.Label(pad, text="Reference Cloak · 설치 프로그램", bg="#09090b",
                 fg="#a1a1aa", font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 18))

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("W.Horizontal.TProgressbar", troughcolor="#1b1b1f",
                        background="#fafafa", borderwidth=0, thickness=10)
        self.pb = ttk.Progressbar(pad, style="W.Horizontal.TProgressbar",
                                  length=408, maximum=100)
        self.pb.pack(anchor="w", pady=(2, 10))

        self.status = tk.Label(pad, text="설치를 준비하는 중...", bg="#09090b",
                               fg="#e4e4e7", font=("Segoe UI", 10))
        self.status.pack(anchor="w")

        self.sub = tk.Label(pad, text="", bg="#09090b", fg="#71717a",
                            font=("Segoe UI", 9))
        self.sub.pack(anchor="w", pady=(4, 0))

        self.btn = None
        self.root.after(400, self.start)

    def set_status(self, msg, sub=""):
        self.status.config(text=msg)
        if sub:
            self.sub.config(text=sub)
        self.root.update_idletasks()

    def start(self):
        t = threading.Thread(target=self._install_safe, daemon=True)
        t.start()

    def _install_safe(self):
        try:
            self._install()
        except Exception as e:
            self.root.after(0, lambda: self._fail(str(e)))

    def _install(self):
        if self.install_root_override:
            install_root = Path(self.install_root_override)
        else:
            install_root = Path(os.environ.get("LOCALAPPDATA",
                                str(Path.home()))) / "Programs"
        app_dir = install_root / APP_NAME
        install_root.mkdir(parents=True, exist_ok=True)

        payload = resource_path("payload.zip")
        if not payload.exists():
            raise FileNotFoundError("설치 페이로드를 찾을 수 없습니다.")

        self.root.after(0, lambda: self.set_status(
            "기존 버전 정리 중...", str(app_dir)))
        import shutil
        shutil.rmtree(app_dir, ignore_errors=True)

        self.root.after(0, lambda: self.set_status("파일 설치 중...",
                                                   str(install_root)))
        with zipfile.ZipFile(payload) as z:
            members = z.infolist()
            total = max(1, len(members))
            for i, m in enumerate(members):
                z.extract(m, str(install_root))
                if i % 3 == 0 or i == total - 1:
                    pct = (i + 1) / total * 92
                    self.root.after(0, lambda v=pct: self.pb.config(value=v))
            self.root.update_idletasks()

        exe = app_dir / f"{APP_NAME}.exe"
        if not exe.exists():
            raise FileNotFoundError("설치된 실행 파일을 찾을 수 없습니다.")

        # 바로가기
        self.root.after(0, lambda: self.set_status("바로가기 만드는 중...", ""))
        desktop = _folder("Desktop") or str(Path.home() / "Desktop")
        programs = _folder("Programs")
        if not self.test_mode:
            _make_shortcut(str(Path(desktop) / f"{APP_TITLE}.lnk"),
                           str(exe), str(app_dir))
            if programs:
                _make_shortcut(str(Path(programs) / f"{APP_TITLE}.lnk"),
                               str(exe), str(app_dir))
        self.root.after(0, lambda: self.pb.config(value=97))

        # 제거 스크립트
        try:
            (app_dir / "uninstall.bat").write_text(
                "@echo off\r\n"
                "echo Seedance Cloak 제거 중...\r\n"
                f'del /q "{Path(desktop) / (APP_TITLE + ".lnk")}" 2>nul\r\n'
                + (f'del /q "{Path(programs) / (APP_TITLE + ".lnk")}" 2>nul\r\n'
                   if programs else "")
                + 'cd /d "%~dp0.."\r\n'
                f'rmdir /s /q "{APP_NAME}"\r\n'
                "echo 완료.\r\n", encoding="utf-8")
        except Exception:
            pass

        self.root.after(0, lambda: self.pb.config(value=100))
        self.root.after(0, lambda: self.set_status(
            "설치 완료! 앱을 실행합니다...", str(app_dir)))
        if not self.test_mode:
            try:
                subprocess.Popen([str(exe)], cwd=str(app_dir))
            except Exception:
                pass
        else:
            print("[installer-test] installed to", app_dir, flush=True)
        self.root.after(800 if self.test_mode else 1200, self.root.destroy)

    def _fail(self, msg):
        self.set_status("설치 중 문제가 발생했습니다.", msg)
        if self.btn is None:
            self.btn = tk.Button(self.root, text="닫기", command=self.root.destroy,
                                 bg="#fafafa", fg="#09090b", relief="flat",
                                 font=("Segoe UI", 10, "bold"), padx=16, pady=4)
            self.btn.pack(pady=8)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Installer().run()
