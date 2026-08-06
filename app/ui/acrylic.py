"""
Windows 아크릴/블러 배경 (글래스모피즘 질감).

frameless + 반투명 윈도우 뒤에 실시간 블러를 깔아 '유리' 질감을 만든다.
Windows 전용이며, 실패하거나 타 OS 면 조용히 무시(앱은 정상 동작).
"""

from __future__ import annotations

import sys


def _to_abgr(argb: int) -> int:
    a = (argb >> 24) & 0xFF
    r = (argb >> 16) & 0xFF
    g = (argb >> 8) & 0xFF
    b = argb & 0xFF
    return (a << 24) | (b << 16) | (g << 8) | r


def apply_glass(widget, argb: int = 0xC00B0C10, acrylic: bool = True) -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = int(widget.winId())

        class ACCENTPOLICY(ctypes.Structure):
            _fields_ = [
                ("AccentState", ctypes.c_int),
                ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint),
                ("AnimationId", ctypes.c_int),
            ]

        class WINCOMPATTRDATA(ctypes.Structure):
            _fields_ = [
                ("Attribute", ctypes.c_int),
                ("Data", ctypes.POINTER(ACCENTPOLICY)),
                ("SizeOfData", ctypes.c_size_t),
            ]

        ACCENT_ENABLE_BLURBEHIND = 3
        ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
        WCA_ACCENT_POLICY = 19

        accent = ACCENTPOLICY()
        accent.AccentState = (ACCENT_ENABLE_ACRYLICBLURBEHIND if acrylic
                              else ACCENT_ENABLE_BLURBEHIND)
        accent.AccentFlags = 2
        accent.GradientColor = _to_abgr(argb)

        data = WINCOMPATTRDATA()
        data.Attribute = WCA_ACCENT_POLICY
        data.Data = ctypes.pointer(accent)
        data.SizeOfData = ctypes.sizeof(accent)

        set_wca = ctypes.windll.user32.SetWindowCompositionAttribute
        set_wca.argtypes = [wintypes.HWND, ctypes.POINTER(WINCOMPATTRDATA)]
        set_wca(hwnd, ctypes.byref(data))

        _set_round_corners(hwnd)
        return True
    except Exception:
        return False


def _set_round_corners(hwnd: int) -> None:
    try:
        import ctypes
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = 2
        pref = ctypes.c_int(DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(pref), ctypes.sizeof(pref))
    except Exception:
        pass
