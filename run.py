#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Seedance Cloak 실행 런처 (소스 실행용)."""

import os
import sys

# 프로젝트 루트를 import 경로에 추가(어디서 실행해도 동작)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
