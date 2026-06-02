# Local DOCX Agent

DOCX 이력서/입사지원서 양식을 자동으로 채우는 로컬 기반 문서 작성 MVP입니다.

사용자가 개인정보와 이력 정보를 입력하고 DOCX 양식을 업로드하면, 시스템은 문서의 표/셀 구조와 렌더링 이미지를 분석해 어떤 값을 어느 칸에 넣을지 판단합니다. 판단 결과는 JSON 작성 계획으로 저장되고, 실제 DOCX 수정은 Python 코드가 수행합니다.

## 핵심 방향

- 기본 실행 환경은 로컬 Ollama 모델입니다.
- AI는 작성 위치를 판단하고 JSON 계획을 생성합니다.
- Python 코드는 생성된 JSON 계획을 참고해 실제 DOCX 셀에 값을 작성합니다.
- DOCX 내부 구조 분석과 이미지 기반 비전 분석을 함께 사용합니다.
- 무거운 비전 모델 대신 가벼운 비전 모델과 crop 기반 분석을 사용해 로컬 PC 부담을 줄입니다.
- 최종 결과는 DOCX, PDF, 이미지 미리보기로 제공합니다.

## 현재 기능

- DOCX 양식 업로드
- 개인정보, 학력, 경력, 자격증, 어학, 병역 정보 입력 UI
- Ollama 기반 텍스트 모델/비전 모델 사용
- DOCX 표, 셀, 빈칸 후보 구조 분석
- DOCX 이미지 렌더링
- crop 기반 비전 분석
- 텍스트 모델 기반 작성 위치 판단
- `python-docx` 기반 DOCX 작성
- 최종 DOCX/PDF/미리보기 생성
- 선택 가능한 최종 화면 검토
- 실행별 JSON 산출물 저장

## 처리 흐름

```text
사용자 입력 + DOCX 업로드
→ 사용자 입력 JSON 생성
→ DOCX 구조 분석 JSON 생성
→ DOCX를 이미지로 렌더링
→ 렌더링 이미지를 crop하여 비전 모델에 전달
→ 비전 분석 JSON 생성
→ 텍스트 모델이 세 JSON을 참고해 operation_plan.json 생성
→ Python 코드가 operation_plan.json을 참고해서 DOCX 작성
→ 최종 DOCX를 PDF/이미지로 재렌더링
→ DOCX/PDF/미리보기 제공
```

## JSON 산출물 구조

이 프로젝트는 AI에게 문서를 직접 수정하도록 맡기지 않습니다. 각 단계의 결과를 JSON으로 정리한 뒤, 최종 작성 계획을 생성하는 방식으로 동작합니다.

```text
사용자 입력 JSON
+ DOCX 구조 분석 JSON
+ 비전 분석 JSON
→ 텍스트 모델이 세 정보를 참고해 operation_plan.json 생성
→ Python 코드가 operation_plan.json을 참고해서 DOCX 작성
```

주요 산출물은 실행별 output 디렉터리에 저장됩니다.

- `profile.json`: 사용자가 입력한 개인정보와 이력 정보
- `layout.json`: DOCX 내부 표/셀/빈칸 후보 분석 결과
- `original_render.json`: 원본 DOCX 렌더링 결과
- `vision_fields.json`: 비전 모델이 확인한 라벨과 빈칸 위치
- `operation_plan.json`: 최종 작성 지시서
- `write_report.json`: 실제 DOCX 작성 결과
- `final_render.json`: 최종 DOCX 렌더링 결과
- `verification_report.json`: 최종 화면 검토 결과 또는 생략 리포트
- `result.json`: 전체 처리 결과 요약

## 모델

기본 모델은 Ollama를 통해 로컬에서 실행합니다.

```text
텍스트 모델: qwen3:8b
이미지 모델: qwen3-vl:4b
```

텍스트 모델은 사용자 입력값을 어떤 DOCX 셀에 넣을지 판단합니다. 이미지 모델은 렌더링된 DOCX 화면에서 라벨과 빈칸 위치를 분석합니다.

## Crop 기반 비전 분석

무거운 비전 모델은 일반 로컬 컴퓨터에서 실행하기 어렵고 처리 시간도 길어질 수 있습니다. 이 프로젝트는 비교적 가벼운 비전 모델을 사용하면서, 문서 전체 이미지를 한 번에 분석하지 않고 페이지를 상/중/하 영역으로 나누어 전달합니다.

이 방식은 작은 모델이 문서의 세부 라벨과 빈칸을 더 잘 인식하도록 돕고, 로컬 환경에서도 현실적인 처리 속도를 확보하기 위한 구조입니다.

## 요구 사항

- Python 3.10 이상
- Node.js / npm
- Ollama
- LibreOffice 또는 Microsoft Word 렌더링 환경
- Ollama 모델
  - `qwen3:8b`
  - `qwen3-vl:4b`

## 설치

프로젝트 폴더로 이동합니다.

```powershell
cd resume-parser
```

Python 패키지를 설치합니다.

```powershell
pip install -r requirements.txt
```

프론트엔드 패키지를 설치합니다.

```powershell
cd frontend
npm.cmd install
```

Ollama 모델을 설치합니다.

```powershell
ollama pull qwen3:8b
ollama pull qwen3-vl:4b
```

설치된 모델을 확인합니다.

```powershell
ollama list
```

## 실행

백엔드를 실행합니다.

```powershell
cd resume-parser
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

다른 터미널에서 프론트엔드를 실행합니다.

```powershell
cd resume-parser\frontend
npm.cmd run dev
```

브라우저에서 접속합니다.

```text
http://127.0.0.1:5173
```

Ollama 서버가 자동으로 실행되지 않는 환경에서는 별도 터미널에서 실행합니다.

```powershell
ollama serve
```

## 단일 서버 실행

프론트엔드를 빌드하면 FastAPI 서버 하나로 정적 파일까지 제공할 수 있습니다.

```powershell
cd resume-parser\frontend
npm.cmd run build
```

```powershell
cd ..
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

접속 주소:

```text
http://127.0.0.1:8000
```

## 사용 방법

1. 브라우저에서 화면을 엽니다.
2. Ollama 주소와 모델명을 확인합니다.
3. DOCX 양식을 업로드합니다.
4. 개인정보와 이력 정보를 입력합니다.
5. `작성 실행`을 누릅니다.
6. 최종 미리보기를 확인합니다.
7. 필요한 경우 DOCX 또는 PDF를 다운로드합니다.

## 주요 파일

```text
backend/
  main.py              FastAPI 엔트리포인트, 업로드/다운로드/모델 확인
  ai_client.py         Ollama 모델 호출 래퍼
  ollama_client.py     Ollama API 클라이언트
  pipeline.py          전체 처리 파이프라인
  profile_parser.py    입력 정보 정규화
  docx_analyzer.py     DOCX 표/셀/입력 후보 분석
  vision_analyzer.py   렌더링 이미지 기반 비전 분석
  operation_planner.py 작성 위치 판단 및 operation_plan 생성
  record_planner.py    반복 섹션 후보 선택
  docx_writer.py       operation_plan을 DOCX에 적용
  renderer.py          DOCX/PDF/PNG 렌더링
  result_verifier.py   최종 화면 검토

frontend/
  src/main.jsx         React UI
  src/style.css        화면 스타일
```

## 한계 및 개선 방향

현재 MVP는 문서 구조가 복잡하거나 표 병합이 불규칙한 경우 일부 위치 판단이 틀릴 수 있습니다. 또한 지원하지 않는 라벨이나 특정 분야에서만 사용하는 표현이 등장하면 모델이 의미를 정확히 해석하지 못할 수 있습니다.

이를 개선하기 위해 분야별 라벨 사전, 대량의 라벨 예시, 기존 양식 분석 결과를 제공하는 방식이 필요합니다. 향후에는 RAG나 템플릿 캐시를 적용해 한 번 분석한 양식의 구조와 작성 위치를 재사용할 수 있습니다. 동일 양식에서는 다시 비전 분석을 반복하지 않고 더 빠르게 작성하는 방향으로 확장할 수 있습니다.

처리 속도는 로컬 컴퓨터 성능, 비전 모델 크기, DOCX 렌더링 환경에 영향을 받습니다. 현재는 crop 기반 분석으로 작은 비전 모델에서도 문서 세부 영역을 인식할 수 있도록 보완했습니다.
