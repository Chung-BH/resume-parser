# Local AI DOCX Agent

DOCX 이력서/입사지원서 양식을 자동으로 채우는 로컬 AI 기반 MVP입니다.

사용자가 개인정보와 이력 정보를 직접 입력하고 DOCX 양식을 업로드하면, 시스템은 문서의 표/셀 구조와 렌더링 이미지를 분석해서 어떤 값을 어느 칸에 넣을지 결정합니다. AI는 문서를 직접 수정하지 않고 JSON 계획만 생성하며, 실제 DOCX 수정은 Python 코드가 수행합니다.

## 핵심 방향

- AI는 DOCX 파일을 직접 수정하지 않습니다.
- AI는 위치 판단과 검증에 필요한 JSON만 생성합니다.
- 실제 문서 작성은 `python-docx`가 검증된 operation plan을 적용하는 방식으로 수행합니다.
- 원본 DOCX는 항상 이미지로 렌더링하고, 비전 모델이 라벨과 빈칸 위치를 분석합니다.
- 최종 DOCX도 이미지/PDF로 렌더링합니다.
- 최종 비전 검증은 UI 토글로 켜거나 끌 수 있습니다.
- 기본 사용은 로컬 Ollama 모델입니다.
- OpenAI GPT 프리셋은 샘플 데이터로 모델 품질을 비교하기 위한 선택 옵션입니다.

## 현재 기능

- DOCX 업로드
- 개인정보/학력/경력/자격증/어학/병역 정보 입력 UI
- 로컬 Ollama 모델 프리셋
- OpenAI GPT 모델 프리셋
- DOCX 표/셀/입력 후보 구조 분석
- 원본 DOCX 이미지 렌더링
- 비전 모델 기반 라벨/빈칸 위치 분석
- 텍스트 모델 기반 작성 위치 결정
- `python-docx` 기반 DOCX 작성
- 최종 DOCX/PDF/미리보기 이미지 생성
- 선택 가능한 최종 비전 검증
- 실행별 디버깅 JSON 저장
- 결과 파일 다운로드 API 제한
- 로컬 개발 주소 기준 CORS 제한

## 처리 흐름

```text
사용자 입력 + DOCX 업로드
→ 입력 정보 정규화
→ DOCX 표/셀/입력 후보 분석
→ 원본 DOCX를 이미지로 렌더링
→ 비전 모델이 라벨과 빈칸 위치 확인
→ 텍스트 모델이 입력값을 넣을 칸 결정
→ Python이 DOCX에 실제 값 작성
→ 최종 DOCX를 다시 이미지/PDF로 렌더링
→ 최종 비전 검증 사용 여부 확인
→ DOCX/PDF/미리보기 제공
```

최종 비전 검증을 끄면 원본 비전 분석은 그대로 실행되고, 마지막 결과 검증 호출만 건너뜁니다. 따라서 위치 판단 품질은 유지하면서 최종 검증 시간을 줄일 수 있습니다.

## 모델 선택

UI의 `모델 설정`에서 프리셋을 선택할 수 있습니다.

### 로컬 Ollama

```text
텍스트 판단 모델: qwen3:8b
비전 분석/검증 모델: qwen3-vl:4b
```

개인정보가 들어간 실제 문서는 이 모드를 권장합니다. 입력 데이터와 렌더링 이미지는 로컬 PC 안에서 처리됩니다.

### OpenAI GPT

```text
텍스트 판단 모델: gpt-5-mini
비전 분석/검증 모델: gpt-5-mini
```

모델 비교 실험용입니다. OpenAI API를 사용하면 입력 정보, DOCX 구조 일부, 원본/최종 렌더링 이미지, crop 이미지, 검증 프롬프트가 OpenAI 서버로 전송될 수 있습니다. 실제 개인정보 대신 샘플 데이터를 사용하는 것을 권장합니다.

OpenAI 프리셋을 쓰려면 백엔드 실행 전에 환경변수를 설정합니다.

```powershell
$env:OPENAI_API_KEY="sk-..."
```

Git Bash에서는 다음과 같이 설정합니다.

```bash
export OPENAI_API_KEY="sk-..."
```

## 요구 사항

- Windows PowerShell 또는 Git Bash
- Python 3.10 이상
- Node.js / npm
- Ollama
- LibreOffice 또는 Microsoft Word 렌더링 환경
- 로컬 모델
  - `qwen3:8b`
  - `qwen3-vl:4b`

`backend/renderer.py`는 DOCX를 PDF/PNG로 렌더링합니다. 우선 LibreOffice를 사용하고, 실패하면 Microsoft Word 변환을 시도합니다. 둘 다 실패하면 구조 기반 미리보기 이미지를 생성하지만, 이 경우 실제 렌더링이 아니므로 비전 분석 품질이 낮아질 수 있습니다.

## 설치

### 1. 프로젝트 폴더로 이동

```powershell
cd resume-parser
```

### 2. Python 패키지 설치

```powershell
pip install -r requirements.txt
```

### 3. 프론트엔드 패키지 설치

Windows에서는 `npm` 실행 정책 문제를 피하기 위해 `npm.cmd` 사용을 권장합니다.

```powershell
cd frontend
npm.cmd install
```

### 4. Ollama 모델 설치

```powershell
ollama pull qwen3:8b
ollama pull qwen3-vl:4b
```

설치 확인:

```powershell
ollama list
```

GPU 사용 여부 확인:

```powershell
ollama ps
```

`PROCESSOR`가 `100% GPU`로 보이면 GPU를 사용 중입니다.

## 실행 방법

개발 중에는 백엔드와 프론트엔드를 따로 실행하는 방식을 권장합니다.

### 1. 백엔드 실행

새 PowerShell에서:

```powershell
cd resume-parser
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

OpenAI GPT 프리셋도 테스트하려면 백엔드 실행 전에:

```powershell
$env:OPENAI_API_KEY="sk-..."
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

### 2. 프론트엔드 실행

다른 PowerShell 또는 Git Bash에서:

```powershell
cd resume-parser\frontend
npm.cmd run dev
```

브라우저에서 접속:

```text
http://127.0.0.1:5173
```

### 3. Ollama 서버

대부분의 경우 Ollama는 백그라운드에서 자동 실행됩니다.

수동 실행이 필요하면 새 PowerShell에서:

```powershell
ollama serve
```

모델 저장 위치를 D 드라이브로 쓰는 경우:

```powershell
$env:OLLAMA_MODELS="D:\OllamaModels"
ollama serve
```

## 단일 서버로 실행

프론트엔드를 빌드한 뒤 FastAPI 하나로 서빙할 수도 있습니다.

```powershell
cd resume-parser\frontend
npm.cmd run build
```

```powershell
cd ..
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

접속:

```text
http://127.0.0.1:8000
```

## 사용 방법

1. 브라우저에서 앱을 엽니다.
2. `모델 설정`에서 `로컬 Ollama` 또는 `OpenAI GPT`를 선택합니다.
3. 필요한 경우 `최종 비전 검증 사용` 토글을 조정합니다.
4. DOCX 양식을 업로드합니다.
5. 개인정보, 학력, 경력, 자격증, 어학, 병역 정보를 입력합니다.
6. `자동 작성 실행`을 누릅니다.
7. 결과 미리보기를 확인합니다.
8. 필요한 경우 DOCX 또는 PDF를 다운로드합니다.

## 최종 비전 검증 옵션

`최종 비전 검증 사용`은 마지막 결과 검증 단계만 제어합니다.

토글이 켜져 있으면:

```text
최종 DOCX 렌더링 이미지
→ 비전 모델이 작성값, 위치, 누락, 겹침, 잘림 여부 검증
→ verification_report.json 생성
```

토글이 꺼져 있으면:

```text
최종 DOCX 렌더링 이미지 생성
→ 비전 모델 검증 호출 생략
→ write_report 기준으로 skipped/uncertain 검증 리포트 생성
```

원본 문서의 비전 분석은 항상 실행됩니다. 즉, 이 토글을 꺼도 라벨/빈칸 위치 판단에는 비전 분석 결과가 계속 사용됩니다.

## 보안과 개인정보

### 로컬 Ollama 사용 시

입력 정보와 렌더링 이미지는 로컬 PC에서 처리됩니다. 실제 개인정보가 들어간 문서는 이 방식을 권장합니다.

### OpenAI GPT 사용 시

OpenAI API로 다음 데이터가 전송될 수 있습니다.

- 입력 폼의 개인정보
- DOCX 구조 분석 일부
- 원본 DOCX 렌더링 이미지와 crop 이미지
- 최종 작성 결과 이미지
- 검증 프롬프트와 기대 필드 값

따라서 GPT 프리셋은 샘플 데이터로 비교 실험할 때 사용하는 것을 권장합니다.

### CORS 제한

백엔드는 로컬 개발과 단일 서버 실행 주소만 허용합니다.

```text
http://127.0.0.1:5173
http://localhost:5173
http://127.0.0.1:8000
http://localhost:8000
```

외부 웹페이지에서 임의로 API를 호출하는 위험을 줄이기 위한 설정입니다.

### 다운로드 API 제한

`/api/file`은 `outputs` 폴더 안의 결과 파일만 내려줍니다.

허용 확장자:

```text
.docx
.pdf
.png
.jpg
.jpeg
```

코드 파일, 업로드 원본, 프로젝트 내부 파일은 다운로드할 수 없습니다.

### API 응답 제한

프론트엔드 응답에는 화면에 필요한 값만 내려줍니다.

- `logs`
- `warnings`
- `verification_report`
- `final_docx_url`
- `final_pdf_url`
- `preview_urls`

디버깅용 내부 JSON은 브라우저 응답으로 보내지 않고 `outputs/run_...` 폴더에만 저장합니다.

## 프로젝트 구조

```text
ai-agent/
  backend/
    main.py              FastAPI 엔트리포인트, 업로드/다운로드/CORS/모델 준비 확인
    pipeline.py          전체 처리 파이프라인
    ai_client.py         Ollama/OpenAI 모델 라우터
    ollama_client.py     Ollama API 호출, 이미지 인코딩, JSON 추출/복구
    profile_parser.py    입력 텍스트/profile JSON 정규화
    docx_analyzer.py     DOCX 표/셀/입력 후보 분석
    vision_analyzer.py   원본 렌더링 이미지 기반 비전 분석
    operation_planner.py 입력값을 넣을 DOCX 위치 결정
    record_planner.py    학력/경력/자격증/어학/병역 반복 행 계획
    docx_writer.py       operation plan을 DOCX에 적용
    renderer.py          DOCX를 PDF/PNG로 렌더링
    result_verifier.py   최종 렌더링 이미지 검증 또는 검증 생략 리포트 생성
    schemas.py           profile/operation schema
    utils.py             공통 유틸

  frontend/
    src/
      main.jsx           React UI
      style.css          스타일
    dist/                빌드 결과

  tests/
    test_record_planner.py

  data/
    uploads/             업로드된 DOCX 임시 저장

  outputs/
    run_.../             실행별 결과물

  requirements.txt
  README.md
```

## 실행별 JSON 산출물

실행할 때마다 `outputs` 아래에 실행 폴더가 생성됩니다.

```text
outputs/run_YYYYMMDD_HHMMSS_xxxxxxxx/
```

주요 파일:

```text
template.docx
profile.json
layout.json
original_render.json
vision_fields.json
operation_plan.json
write_report.json
verification_report.json
final.docx
final_render.json
result.json
```

각 파일의 역할:

- `template.docx`: 업로드된 원본 DOCX의 실행용 복사본
- `profile.json`: 사용자 입력을 표준 profile schema로 정규화한 값
- `layout.json`: DOCX 표/행/셀/라벨/입력 후보 구조
- `original_render.json`: 원본 DOCX의 PDF/PNG 렌더링 결과
- `vision_fields.json`: 비전 모델이 본 라벨, 빈칸, 상대 위치 정보
- `operation_plan.json`: AI가 생성한 DOCX 작성 계획
- `write_report.json`: Python이 실제로 작성한 셀과 값
- `final.docx`: 최종 작성된 DOCX
- `final_render.json`: 최종 DOCX의 PDF/PNG 렌더링 결과
- `verification_report.json`: 최종 비전 검증 결과 또는 검증 생략 리포트
- `result.json`: 내부 디버깅용 통합 결과

문제가 생겼을 때 먼저 볼 파일:

- `vision_fields.json`
- `operation_plan.json`
- `write_report.json`
- `verification_report.json`

## 테스트

백엔드 문법 확인:

```powershell
cd resume-parser
python -m compileall -q backend
```

record planner 테스트:

```powershell
python -m unittest tests.test_record_planner
```

프론트엔드 빌드:

```powershell
cd resume-parser\frontend
npm.cmd run build
```

## 자주 발생하는 문제

### PowerShell에서 npm 실행 오류

오류 예:

```text
npm : 이 시스템에서 스크립트를 실행할 수 없으므로 ...
```

해결:

```powershell
npm.cmd run dev
npm.cmd run build
```

### Ollama 서버 연결 실패

확인:

```powershell
ollama list
```

수동 실행:

```powershell
ollama serve
```

### Ollama 모델 없음

오류 예:

```text
Ollama에 필요한 모델이 없습니다
```

해결:

```powershell
ollama pull qwen3:8b
ollama pull qwen3-vl:4b
```

### 비전 모델이 너무 느림

확인:

```powershell
ollama ps
```

`PROCESSOR`가 `100% CPU`이면 GPU가 아니라 CPU로 돌고 있을 수 있습니다.

속도가 중요하면 `최종 비전 검증 사용`을 끌 수 있습니다. 이 경우 원본 비전 분석은 계속 실행되고 마지막 검증 호출만 생략됩니다.

### OpenAI GPT 프리셋에서 API Key 오류

백엔드 실행 전에 환경변수를 설정합니다.

```powershell
$env:OPENAI_API_KEY="sk-..."
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

### 검증 confidence가 낮음

가능한 원인:

- 비전 모델이 최종 이미지를 제대로 읽지 못함
- 값은 들어갔지만 위치 검증이 불확실함
- 일부 필드가 작성되지 않음
- 표가 복잡해서 행/열 판단이 흔들림
- 최종 비전 검증을 꺼서 `skipped` 상태로 리포트가 생성됨

확인할 파일:

```text
outputs/run_.../operation_plan.json
outputs/run_.../write_report.json
outputs/run_.../verification_report.json
```

## 현재 설계상 한계

- 모든 DOCX 양식을 완벽하게 처리하지는 못합니다.
- 복잡한 병합 셀, 여러 페이지, 표가 중첩된 양식에서는 위치 판단이 흔들릴 수 있습니다.
- 현재 최종 검증은 속도를 위해 주로 첫 페이지 중심입니다.
- OpenAI GPT 비교는 개인정보가 없는 샘플 데이터 사용을 권장합니다.
- AI가 위치를 판단하지만, 실제 작성은 항상 Python의 검증된 operation만 적용합니다.
- `기타 정보`는 profile과 user text에는 포함되지만, 현재 정형 필드 자동 매핑 대상은 아닙니다.

## 개발 메모

- 일반 사용자 UI에는 디버그 JSON을 표시하지 않습니다.
- 디버그 JSON은 `outputs/run_...` 폴더에 저장됩니다.
- 반복 섹션은 `record_planner.py`가 행/열 후보를 좁히고, AI가 같은 record group 안에서 최종 선택합니다.
- 어학/컴퓨터처럼 한 표 안에 여러 섹션이 붙어 있는 경우, 컴퓨터 칸을 어학 칸으로 착각하지 않도록 후보 필터링을 둡니다.
- 자격증/경력/어학/병역처럼 행 단위 데이터는 같은 record group 안에서만 작성하도록 제한합니다.
- LibreOffice 변환 timeout이 발생해도 전체 `soffice.exe` 프로세스를 이름 기준으로 종료하지 않고, 현재 변환 명령의 프로세스 트리만 timeout 처리합니다.
