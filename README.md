# Local AI DOCX Agent MVP

로컬 Ollama 모델을 사용해 DOCX 이력서 양식을 자동 작성하는 MVP입니다.

이 프로젝트의 핵심 원칙은 다음과 같습니다.

- AI는 DOCX 파일을 직접 수정하지 않습니다.
- AI는 사용자 정보 분석, 문서 이미지 분석, 작성 계획 생성을 담당합니다.
- 실제 DOCX 수정은 Python 코드가 `python-docx`로 수행합니다.
- 작성 후 DOCX를 다시 이미지로 렌더링하고 비전 모델로 검증합니다.

즉 AI는 판단을 하고, Python은 실제 파일 작업을 수행합니다.

## 현재 상태

현재 MVP에서 안정적으로 되는 부분:

- DOCX 업로드
- 사용자 정보 입력
- DOCX 이미지 렌더링
- 결과 미리보기 표시
- 결과 파일 다운로드
- 실행별 디버그 산출물 저장

현재 불안정한 부분:

- `qwen2.5vl:3b`의 비전 JSON 생성 안정성
- `qwen3:8b`의 operation plan 생성 안정성
- 복잡한 DOCX 표 구조에서 정확한 셀 선택

현재 가장 자주 발생하는 실패는 `operation_plan.json`이 아래처럼 비어 있는 경우입니다.

```json
{
  "operations": [],
  "status": "no_operations"
}
```

이 경우 Python writer가 실패한 것이 아니라, AI가 Python에게 줄 작성 명령을 만들지 못한 상태입니다.

## 기술 스택

- FastAPI
- React
- Ollama
- `qwen3:8b`
- `qwen2.5vl:3b`
- python-docx
- LibreOffice headless
- PyMuPDF

## 설치

### 1. Ollama 설치

Ollama를 설치합니다.

공식 사이트:

```text
https://ollama.com
```

설치 후 PowerShell 또는 터미널에서 모델을 다운로드합니다.

```powershell
ollama pull qwen3:8b
ollama pull qwen2.5vl:3b
```

모델이 설치되었는지 확인합니다.

```powershell
ollama list
```

아래 두 모델이 보여야 합니다.

```text
qwen3:8b
qwen2.5vl:3b
```

### 2. Ollama 서버 실행

대부분의 경우 Ollama는 백그라운드에서 자동 실행됩니다.

수동으로 실행해야 한다면 새 터미널에서 아래 명령어를 실행합니다.

```powershell
ollama serve
```

이 터미널은 Ollama 서버 창이므로, 프로젝트를 실행하는 동안 닫지 않습니다.

참고: 모델 저장 위치를 기본 경로가 아닌 다른 드라이브로 바꾸고 싶은 경우에만 환경 변수를 설정합니다.

```powershell
$env:OLLAMA_MODELS="D:\OllamaModels"
ollama serve
```

일반 사용자는 이 설정이 필요 없습니다.

### 3. Python 패키지 설치

프로젝트 폴더에서 실행합니다.

```powershell
cd <프로젝트_폴더>
pip install -r requirements.txt
```

### 4. 프론트엔드 패키지 설치

```powershell
cd <프로젝트_폴더>\frontend
npm install
```

## 실행 방법

### 방법 A: FastAPI 서버 하나로 실행

프론트엔드를 먼저 빌드합니다.

```powershell
cd <프로젝트_폴더>\frontend
npm run build
```

그 다음 FastAPI 서버를 실행합니다.

```powershell
cd <프로젝트_폴더>
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

브라우저에서 접속합니다.

```text
http://127.0.0.1:8000
```

### 방법 B: 개발 모드로 실행

백엔드 실행:

```powershell
cd <프로젝트_폴더>
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

프론트엔드 실행:

```powershell
cd <프로젝트_폴더>\frontend
npm run dev
```

브라우저에서 접속합니다.

```text
http://127.0.0.1:5173
```

## 기본 실행 순서

1. Ollama 모델 다운로드
2. Ollama 서버 실행
3. Python 패키지 설치
4. 프론트엔드 패키지 설치
5. 프론트엔드 빌드
6. FastAPI 서버 실행
7. 브라우저 접속
8. DOCX 업로드 후 자동 작성 실행

명령어만 모으면 다음과 같습니다.

```powershell
ollama pull qwen3:8b
ollama pull qwen2.5vl:3b
ollama serve
```

다른 터미널:

```powershell
cd <프로젝트_폴더>
pip install -r requirements.txt
cd frontend
npm install
npm run build
cd ..
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

브라우저:

```text
http://127.0.0.1:8000
```

## 프로젝트 구조

```text
ai-agent/
  backend/
    main.py                FastAPI 진입점
    pipeline.py            전체 처리 흐름
    ollama_client.py       Ollama API 호출
    profile_parser.py      사용자 정보 텍스트를 profile JSON으로 변환
    docx_analyzer.py       DOCX 표/셀/입력 후보 분석
    vision_analyzer.py     렌더링 이미지 기반 비전 분석
    operation_planner.py   qwen3 기반 operation plan 생성
    docx_writer.py         operation plan을 DOCX에 적용
    renderer.py            DOCX를 PDF/PNG로 렌더링
    result_verifier.py     최종 결과 이미지 검증
    utils.py               공통 유틸

  frontend/
    src/
      main.jsx             React UI
      style.css            UI 스타일
    dist/                  빌드 결과물

  outputs/
    run_YYYYMMDD_HHMMSS/   실행별 산출물

  data/
    uploads/               업로드된 DOCX 임시 저장

  requirements.txt
  README.md
```

## 처리 흐름

```text
DOCX 업로드
→ 사용자 정보 입력
→ qwen3:8b로 profile.json 생성
→ Python으로 DOCX 구조 분석
→ DOCX를 이미지로 렌더링
→ qwen2.5vl:3b로 이미지 기반 필드 위치 분석
→ qwen3:8b로 operation_plan.json 생성
→ Python이 operation plan을 DOCX에 적용
→ 수정된 DOCX를 다시 이미지로 렌더링
→ qwen2.5vl:3b로 최종 검증
```

## 산출물

실행할 때마다 아래 폴더가 생성됩니다.

```text
outputs/run_YYYYMMDD_HHMMSS/
```

주요 파일:

- `profile.json`
- `layout.json`
- `original_render.json`
- `vision_fields.json`
- `operation_plan.json`
- `write_report.json`
- `verification_report.json`
- `final.docx`
- `final_render.json`
- `result.json`

문제가 생기면 먼저 아래 파일을 확인합니다.

```text
vision_fields.json
operation_plan.json
write_report.json
verification_report.json
```

## 자주 발생하는 문제

### 1. Ollama 연결 실패

에러 예시:

```text
WinError 10061
```

의미:

```text
FastAPI가 Ollama 서버에 연결하지 못했습니다.
```

해결:

```powershell
ollama serve
```

다른 터미널에서 확인:

```powershell
ollama list
```

### 2. 비전 모델 timeout

에러 예시:

```text
qwen2.5vl:3b vision JSON generation failed: timed out
```

의미:

```text
비전 모델이 이미지 분석을 제한 시간 안에 끝내지 못했습니다.
```

확인:

```powershell
ollama ps
```

`PROCESSOR`가 `100% CPU`로 표시되면 GPU 대신 CPU로 실행 중일 수 있고, 매우 느릴 수 있습니다.

### 3. 비전 JSON 파싱 실패

에러 예시:

```text
Expecting ',' delimiter
```

의미:

```text
비전 모델이 JSON처럼 보이는 응답을 했지만 문법이 깨졌습니다.
```

이 경우 `vision_fields.json`이 정상 생성되지 않고, 이후 `operation_plan.json`도 비어 있을 수 있습니다.

### 4. operation plan이 0건인 경우

파일:

```text
operation_plan.json
```

예시:

```json
{
  "operations": [],
  "status": "no_operations"
}
```

의미:

```text
AI가 Python writer에게 줄 작성 작업을 만들지 못했습니다.
```

이 상태에서는 `final.docx`가 채워지지 않습니다.

## 설계 원칙

- AI가 DOCX 파일을 직접 수정하지 않습니다.
- AI는 JSON operation plan만 생성합니다.
- Python만 실제 DOCX를 수정합니다.
- 특정 양식에만 맞춘 rule 기반 하드코딩을 늘리는 방향은 지양합니다.
- 다만 렌더링, 이미지 crop, 후보 추출 같은 보조 처리는 Python이 수행할 수 있습니다.

