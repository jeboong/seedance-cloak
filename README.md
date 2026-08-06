# Seedance Cloak v2

영상 속 **얼굴만** 골라 (1) 검출·매칭을 회피하는 미세 처리를 하거나 (2) 얼굴에 맞춘 **격자(그리드)** 를 씌우는 데스크톱 도구입니다. 배경 화질은 그대로 유지합니다.

- 글래스모피즘 다크 UI (PySide6, frameless + Windows 아크릴 블러)
- YuNet 고정밀 얼굴 검출 + 프레임 간 트래킹/스무딩(플리커 방지)
- 4가지 엔진: A(Adversarial) · B(Frequency) · C(Semantic) · D(Face Grid)
- **FFmpeg 9.0** 번들, raw 프레임 단일 인코딩으로 원본 화질 보존
- 짧은 영상(≤목표초) 뒤에 검은 화면을 이어붙이는 **4초 채우기**
- 회사 동료 배포용 **단일 exe** 패키징

> ⚠️ 이 도구는 본인이 권리를 가진 영상의 프라이버시 보호/워크플로 용도로만 사용하세요.

---

## 1. 빠른 시작 (소스 실행)

```bat
run.bat
```

또는 수동으로:

```bat
python -m pip install -r requirements.txt
python run.py
```

- Python 3.10+ 권장 (개발/테스트: 3.11)
- FFmpeg 가 PATH 에 없어도, 최초 실행 시 자동으로 FFmpeg 9.0 을 내려받아 캐시에 설치합니다.
- 얼굴 검출 모델(YuNet, 232KB)도 없으면 자동 다운로드됩니다.

## 2. exe 로 빌드해서 동료에게 배포

```bat
build.bat
```

빌드가 끝나면 다음이 생성됩니다.

```
dist/
  SeedanceCloak/
    SeedanceCloak.exe     ← 더블클릭 실행
    ffmpeg.exe            ← 함께 배포(동봉)
    ffprobe.exe
    사용법.txt
  SeedanceCloak_v2.0.0.zip  ← 이 zip 만 전달하면 됨
```

동료는 zip 을 풀고 `SeedanceCloak.exe` 를 더블클릭하면 끝입니다. (별도 설치 불필요)

- `build.bat --no-ffmpeg` : FFmpeg 를 번들하지 않고 exe 크기를 줄입니다(최초 실행 시 자동 다운로드).
- 깨끗한 결과물을 원하면 `opencv-python` 과 `opencv-contrib-python` 중 **contrib 하나만** 설치된 venv 에서 빌드하세요.

## 3. 기능 요약

| 엔진 | 이름 | 용도 |
|---|---|---|
| A | Adversarial Cloak | 검출기를 속이는 미세 노이즈(권장, 기본 ON) |
| B | Frequency Perturb | 얼굴 임베딩/매칭 회피(YCrCb 기반, 색 변형 최소화) |
| C | Semantic Evade | 그레인·경계 소프트닝·미세 워프로 검출 자체 방해 |
| D | Face Grid | 얼굴에 맞춘 격자 오버레이(격자 수/두께/색/투명도/모양/정렬/점) |

- **트래킹 ON**: 얼굴을 프레임 간 추적·스무딩 → 격자/노이즈 떨림 제거
- **렌더링 품질**: 원본 품질 유지(권장) · 고품질 · 표준 · 저용량 · 완전 무손실 · HEVC
- **4초 채우기**: 짧은 영상 뒤에 검은 화면 + 무음 오디오로 목표 길이 강제 확보

자세한 사용법은 [TUTORIAL.md](TUTORIAL.md) 를 참고하세요. (앱 내 "튜토리얼" 버튼으로도 볼 수 있습니다.)

## 4. 구조

```
app/
  main.py                 # 진입점(QApplication)
  paths.py                # 리소스/캐시 경로(소스·exe 공용)
  engines/
    detector.py           # YuNet/res10/Haar 얼굴 검출 + 랜드마크
    tracker.py            # IOU 트래킹 + EMA 스무딩
    cloak.py              # A. Adversarial
    frequency.py          # B. Frequency (YCrCb)
    semantic.py           # C. Semantic
    grid.py               # D. Face Grid
    common.py             # 페더 블렌딩
    ffmpeg_utils.py       # FFmpeg 9.0 탐지/설치/명령·품질 프리셋
    models.py             # YuNet 모델 탐지/다운로드
    pipeline.py           # Worker(QThread): 전체 렌더 파이프라인
  ui/
    theme.py, acrylic.py, widgets.py, tutorial.py, main_window.py
build/
  build_exe.py            # exe 빌드 스크립트
run.py, run.bat, build.bat, requirements.txt
```

## 5. 문제 해결

- **실행이 안 돼요**: `run.bat` 로 실행하면 필요한 패키지를 자동 설치합니다. (v1 의 PyQt5 의존성 문제는 v2 에서 PySide6 로 이관되어 해결됨)
- **소리가 사라져요 / 인코딩 실패**: exe 와 같은 폴더에 `ffmpeg.exe`, `ffprobe.exe` 가 있는지 확인하세요.
- **얼굴을 잘 못 잡아요**: 강도를 낮추고 트래킹을 켜세요. 매우 작은 얼굴은 원본 해상도가 낮으면 검출이 어렵습니다.
- **처리가 느려요**: 품질을 '표준/저용량'으로, 엔진 A 단독 사용을 권장합니다.
