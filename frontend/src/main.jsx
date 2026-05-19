import React, { useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileText,
  Image as ImageIcon,
  Play,
  Square,
} from "lucide-react";
import "./style.css";

const sampleText = `이름: 김철수
영문 이름: Cheolsu Kim
생년월일: 1990-02-23
성별: 남
연락처: 010-1234-5678
이메일: asd123@naver.com
주소: 서울특별시 노원구 화랑로 815
지원직무: 백엔드 개발자

학력
- 2006-03 ~ 2009-02 / 일육고등학교 / 인문계
- 2009-03 ~ 2015-02 / 일육대학교 / 컴퓨터공학과

경력
- 2015-03 ~ 2019-06 / 넥스트인터 / 백엔드 개발자 / 정산 API 개발

자격증
- 정보처리기사 / 한국산업인력공단 / 2023.06
- SQLD / 한국데이터산업진흥원 / 2022.12`;

function App() {
  const abortRef = useRef(null);
  const [file, setFile] = useState(null);
  const [userText, setUserText] = useState(sampleText);
  const [ollamaUrl, setOllamaUrl] = useState("http://localhost:11434");
  const [textModel, setTextModel] = useState("qwen3:8b");
  const [visionModel, setVisionModel] = useState("qwen2.5vl:3b");
  const [useAi, setUseAi] = useState(true);
  const [useVision, setUseVision] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [elapsedMs, setElapsedMs] = useState(null);

  async function run() {
    if (!file || loading) return;
    const controller = new AbortController();
    abortRef.current = controller;
    const startedAt = performance.now();

    setLoading(true);
    setError("");
    setResult(null);
    setElapsedMs(null);

    const form = new FormData();
    form.append("file", file);
    form.append("user_text", userText);
    form.append("ollama_url", ollamaUrl);
    form.append("text_model", textModel);
    form.append("vision_model", visionModel);
    form.append("use_ai", String(useAi));
    form.append("use_vision", String(useVision));

    try {
      const response = await fetch("/api/process", {
        method: "POST",
        body: form,
        signal: controller.signal,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "처리에 실패했습니다.");
      setElapsedMs(Math.round(performance.now() - startedAt));
      setResult(payload);
    } catch (err) {
      setElapsedMs(Math.round(performance.now() - startedAt));
      if (err.name === "AbortError") {
        setError("요청을 중단했습니다. 서버에서 진행 중이던 작업은 곧 정리됩니다.");
      } else {
        setError(err.message);
      }
    } finally {
      abortRef.current = null;
      setLoading(false);
    }
  }

  function stopRequest() {
    abortRef.current?.abort();
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Local AI DOCX workflow</p>
          <h1>DOCX 자동 작성 MVP</h1>
          <p className="subtitle">
            AI는 JSON 작업 계획만 만들고, 실제 DOCX 수정은 Python이 수행합니다.
          </p>
        </div>
        <div className="topbar-actions">
          {loading && (
            <button className="btn secondary" onClick={stopRequest}>
              <Square size={15} />
              중단
            </button>
          )}
          <button className="btn primary" onClick={run} disabled={!file || loading}>
            <Play size={16} />
            {loading ? "처리 중" : "자동 작성 실행"}
          </button>
        </div>
      </header>

      {loading && (
        <section className="status-strip">
          <span className="spinner" />
          <div>
            <strong>문서를 처리하고 있습니다.</strong>
            <span>qwen2.5vl 검증은 오래 걸릴 수 있습니다. 필요하면 중단을 누르세요.</span>
          </div>
        </section>
      )}

      <section className="workspace">
        <aside className="side-panel">
          <Panel title="모델 설정">
            <Input label="Ollama URL" value={ollamaUrl} onChange={setOllamaUrl} />
            <Input label="텍스트/추론 모델" value={textModel} onChange={setTextModel} />
            <Input label="비전 분석/검증 모델" value={visionModel} onChange={setVisionModel} />
            <Toggle label="qwen3 사용" checked={useAi} onChange={setUseAi} />
            <Toggle label="qwen2.5vl 이미지 분석/검증 사용" checked={useVision} onChange={setUseVision} />
          </Panel>

          <Panel title="DOCX 업로드">
            <label className={`dropzone ${file ? "has-file" : ""}`}>
              <FileText size={28} />
              <span>{file ? file.name : "DOCX 파일 선택"}</span>
              <small>{file ? "업로드 준비 완료" : "이력서 양식 .docx를 선택하세요"}</small>
              <input type="file" accept=".docx" onChange={(e) => setFile(e.target.files?.[0] || null)} />
            </label>
          </Panel>
        </aside>

        <section className="main-panel">
          <Panel title="사용자 정보">
            <textarea
              className="profile-textarea"
              value={userText}
              onChange={(e) => setUserText(e.target.value)}
            />
          </Panel>

          {error && <div className="notice error">{error}</div>}
          {result && <ResultView result={result} elapsedMs={elapsedMs} />}
        </section>
      </section>
    </main>
  );
}

function ResultView({ result, elapsedMs }) {
  return (
    <div className="result-stack">
      <VerificationSummary report={result.verification_report} />

      <Panel title="결과 다운로드">
        {elapsedMs !== null && <p className="elapsed">총 소요 시간: {formatElapsed(elapsedMs)}</p>}
        <div className="download-row">
          {result.final_docx_url && <DownloadLink href={result.final_docx_url} label="DOCX 다운로드" />}
          {result.final_pdf_url && <DownloadLink href={result.final_pdf_url} label="PDF 다운로드" />}
        </div>
        {result.warnings?.length > 0 && <p className="warning-text">{result.warnings.join(" / ")}</p>}
      </Panel>

      <Panel title="최종 미리보기">
        {result.preview_urls?.length ? (
          <div className="preview-list">
            {result.preview_urls.map((url, index) => (
              <img key={url || index} src={url} alt={`preview ${index + 1}`} />
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <ImageIcon size={17} />
            미리보기 이미지가 없습니다.
          </div>
        )}
      </Panel>

      <Details title="자동 검증 리포트 JSON" value={result.verification_report} />
      <Details title="Operation Plan JSON" value={result.operation_plan} />

      <Panel title="처리 로그">
        <pre className="log-box">{(result.logs || []).join("\n")}</pre>
      </Panel>
    </div>
  );
}

function VerificationSummary({ report }) {
  if (!report) return null;
  const confidence = Number(report.overall_confidence || 0);
  const percent = Math.round(confidence * 100);
  const needsReview = Boolean(report.needs_user_confirmation);

  return (
    <section className={`verify-card ${needsReview ? "review" : "pass"}`}>
      {needsReview ? <AlertTriangle size={22} /> : <CheckCircle2 size={22} />}
      <div>
        <div className="verify-header">
          <h2>자동 검증 결과</h2>
          <span>confidence {percent}%</span>
          <span>{report.status}</span>
        </div>
        <p>{report.summary || "검증 요약이 없습니다."}</p>
        {needsReview && <strong>confidence가 낮거나 의심 항목이 있어 최종 확인이 필요합니다.</strong>}
      </div>
    </section>
  );
}

function Panel({ title, children }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function Details({ title, value }) {
  return (
    <details className="panel details-panel">
      <summary>{title}</summary>
      <pre className="json-box">{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

function Input({ label, value, onChange }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

function Toggle({ label, checked, onChange }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

function DownloadLink({ href, label }) {
  return (
    <a className="btn download" href={href}>
      <Download size={16} />
      {label}
    </a>
  );
}

function formatElapsed(ms) {
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}초`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}분 ${rest}초`;
}

createRoot(document.getElementById("root")).render(<App />);
