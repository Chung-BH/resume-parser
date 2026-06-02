import React, { useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileText,
  Image as ImageIcon,
  Plus,
  Play,
  Square,
  Trash2,
} from "lucide-react";
import "./style.css";

const emptyProfile = {
  name: "",
  english_name: "",
  birth_date: "",
  gender: "",
  phone: "",
  email: "",
  address: "",
  job: "",
  education: [{ period: "", school: "", major: "" }],
  careers: [{ period: "", company: "", position: "", role: "" }],
  certificates: [{ name: "", issuer: "", date: "" }],
  languages: [{ language: "", ability: "", test: "", score: "" }],
  military: [{ status: "", branch: "", service_type: "", rank: "", period: "", exemption_reason: "" }],
  extra: { raw: "" },
};

const sampleProfile = {
  ...emptyProfile,
  name: "김철수",
  english_name: "Cheolsu Kim",
  birth_date: "1990-02-23",
  gender: "남",
  phone: "010-1234-5678",
  email: "asd123@naver.com",
  address: "서울특별시 노원구 화랑로 815",
  job: "백엔드 개발자",
  education: [
    { period: "2006-03 ~ 2009-02", school: "일육고등학교", major: "인문계" },
    { period: "2009-03 ~ 2015-02", school: "일육대학교", major: "컴퓨터공학과" },
  ],
  careers: [{ period: "2015-03 ~ 2019-06", company: "넥스트인터", position: "백엔드 개발자", role: "정산 API 개발" }],
  certificates: [
    { name: "정보처리기사", issuer: "한국산업인력공단", date: "2023.06" },
    { name: "SQLD", issuer: "한국데이터산업진흥원", date: "2022.12" },
  ],
  languages: [{ language: "영어", ability: "상", test: "TOEIC", score: "900" }],
  military: [{ status: "군필", branch: "육군", service_type: "현역", rank: "병장", period: "2010-03 ~ 2012-01", exemption_reason: "" }],
  extra: { raw: "컴퓨터 활용능력: MS-WORD 상, MS-EXCEL 중\n보훈여부: 대상 아님" },
};

const sectionConfigs = {
  education: {
    title: "학력",
    empty: { period: "", school: "", major: "" },
    fields: [
      ["period", "기간"],
      ["school", "학교명"],
      ["major", "전공"],
    ],
  },
  careers: {
    title: "경력",
    empty: { period: "", company: "", position: "", role: "" },
    fields: [
      ["period", "근무기간"],
      ["company", "근무처"],
      ["position", "직위"],
      ["role", "직무"],
    ],
  },
  certificates: {
    title: "자격증",
    empty: { name: "", issuer: "", date: "" },
    fields: [
      ["name", "자격증명"],
      ["issuer", "발행처"],
      ["date", "취득일"],
    ],
  },
  languages: {
    title: "어학",
    empty: { language: "", ability: "", test: "", score: "" },
    fields: [
      ["language", "외국어명"],
      ["ability", "활용능력"],
      ["test", "테스트명"],
      ["score", "공인점수"],
    ],
  },
  military: {
    title: "병역",
    empty: { status: "", branch: "", service_type: "", rank: "", period: "", exemption_reason: "" },
    fields: [
      ["status", "구분"],
      ["branch", "군별"],
      ["service_type", "역종"],
      ["rank", "계급"],
      ["period", "복무기간"],
      ["exemption_reason", "면제사유"],
    ],
  },
};

function App() {
  const abortRef = useRef(null);
  const [file, setFile] = useState(null);
  const [profile, setProfile] = useState(sampleProfile);
  const [ollamaUrl, setOllamaUrl] = useState("http://localhost:11434");
  const [textModel, setTextModel] = useState("qwen3:8b");
  const [visionModel, setVisionModel] = useState("qwen3-vl:4b");
  const [useAi, setUseAi] = useState(true);
  const [useFinalVerification, setUseFinalVerification] = useState(true);
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
    form.append("user_text", profileToText(profile));
    form.append("profile_json", JSON.stringify(compactProfile(profile)));
    form.append("ollama_url", ollamaUrl);
    form.append("text_model", textModel);
    form.append("vision_model", visionModel);
    form.append("use_ai", String(useAi));
    form.append("use_final_verification", String(useFinalVerification));

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
        setError("요청을 중단했습니다. 서버에서 진행 중인 작업은 곧 정리됩니다.");
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
          <p className="eyebrow">Document workbench</p>
          <h1>지원서 문서 작성</h1>
          <p className="subtitle">양식을 선택하고 정보를 입력해 결과 문서를 생성합니다.</p>
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
            {loading ? "작성 중" : "작성 실행"}
          </button>
        </div>
      </header>

      {loading && (
        <section className="status-strip">
          <span className="spinner" />
          <div>
            <strong>문서를 작성하고 있습니다.</strong>
            <span>문서 분석과 렌더링을 진행하고 있습니다.</span>
          </div>
        </section>
      )}

      <section className="workspace">
        <aside className="side-panel">
          <Panel title="처리 설정">
            <Input label="Ollama 주소" value={ollamaUrl} onChange={setOllamaUrl} />
            <Input label="텍스트 모델" value={textModel} onChange={setTextModel} />
            <Input label="이미지 모델" value={visionModel} onChange={setVisionModel} />
            <Toggle label="자동 위치 매핑" checked={useAi} onChange={setUseAi} />
            <Toggle label="최종 화면 검토" checked={useFinalVerification} onChange={setUseFinalVerification} />
          </Panel>

          <Panel title="DOCX 업로드">
            <label className={`dropzone ${file ? "has-file" : ""}`}>
              <FileText size={28} />
              <span>{file ? file.name : "DOCX 파일 선택"}</span>
              <small>{file ? "업로드 준비 완료" : "입력할 이력서 양식 .docx를 선택하세요"}</small>
              <input type="file" accept=".docx" onChange={(event) => setFile(event.target.files?.[0] || null)} />
            </label>
          </Panel>
        </aside>

        <section className="main-panel">
          <ProfileForm profile={profile} setProfile={setProfile} />

          {error && <div className="notice error">{error}</div>}
          {result && <ResultView result={result} elapsedMs={elapsedMs} />}
        </section>
      </section>
    </main>
  );
}

function ProfileForm({ profile, setProfile }) {
  function update(key, value) {
    setProfile((current) => ({ ...current, [key]: value }));
  }

  function updateExtra(value) {
    setProfile((current) => ({ ...current, extra: { ...current.extra, raw: value } }));
  }

  return (
    <div className="profile-form">
      <Panel title="인적사항">
        <div className="form-grid two">
          <Input label="성명" value={profile.name} onChange={(value) => update("name", value)} />
          <Input label="영문 이름" value={profile.english_name} onChange={(value) => update("english_name", value)} />
          <Input label="생년월일" value={profile.birth_date} onChange={(value) => update("birth_date", value)} />
          <Input label="성별" value={profile.gender} onChange={(value) => update("gender", value)} />
          <Input label="연락처" value={profile.phone} onChange={(value) => update("phone", value)} />
          <Input label="이메일" value={profile.email} onChange={(value) => update("email", value)} />
          <Input label="주소" value={profile.address} onChange={(value) => update("address", value)} wide />
          <Input label="지원직무" value={profile.job} onChange={(value) => update("job", value)} />
        </div>
      </Panel>

      {Object.entries(sectionConfigs).map(([key, config]) => (
        <RepeatingSection key={key} sectionKey={key} config={config} profile={profile} setProfile={setProfile} />
      ))}

      <Panel title="기타 정보">
        <label className="field">
          <span>위 항목에 없는 내용</span>
          <textarea
            className="extra-textarea"
            value={profile.extra?.raw || ""}
            onChange={(event) => updateExtra(event.target.value)}
            placeholder="예: 보훈여부, 컴퓨터 활용능력, 수상, 연수, 봉사활동, 자기소개 등"
          />
        </label>
      </Panel>
    </div>
  );
}

function RepeatingSection({ sectionKey, config, profile, setProfile }) {
  const rows = profile[sectionKey] || [];

  function updateRow(index, key, value) {
    setProfile((current) => ({
      ...current,
      [sectionKey]: current[sectionKey].map((row, rowIndex) => (rowIndex === index ? { ...row, [key]: value } : row)),
    }));
  }

  function addRow() {
    setProfile((current) => ({ ...current, [sectionKey]: [...current[sectionKey], { ...config.empty }] }));
  }

  function removeRow(index) {
    setProfile((current) => ({
      ...current,
      [sectionKey]: current[sectionKey].filter((_, rowIndex) => rowIndex !== index),
    }));
  }

  return (
    <Panel title={config.title}>
      <div className="rows-stack">
        {rows.map((row, index) => (
          <div className="entry-row" key={`${sectionKey}-${index}`}>
            <div className={`form-grid compact columns-${Math.min(config.fields.length, 4)}`}>
              {config.fields.map(([key, label]) => (
                <Input key={key} label={label} value={row[key] || ""} onChange={(value) => updateRow(index, key, value)} />
              ))}
            </div>
            <button className="icon-btn" type="button" onClick={() => removeRow(index)} title={`${config.title} 행 삭제`}>
              <Trash2 size={16} />
            </button>
          </div>
        ))}
      </div>
      <button className="btn secondary add-row" type="button" onClick={addRow}>
        <Plus size={15} />
        {config.title} 추가
      </button>
    </Panel>
  );
}

function ResultView({ result, elapsedMs }) {
  return (
    <div className="result-stack">
      <VerificationSummary report={result.verification_report} />

      <Panel title="결과 파일">
        {elapsedMs !== null && <p className="elapsed">총 소요 시간: {formatElapsed(elapsedMs)}</p>}
        <div className="download-row">
          {result.final_docx_url && <DownloadLink href={result.final_docx_url} label="DOCX 다운로드" />}
          {result.final_pdf_url && <DownloadLink href={result.final_pdf_url} label="PDF 다운로드" />}
        </div>
        {result.warnings?.length > 0 && <p className="warning-text">{result.warnings.join(" / ")}</p>}
      </Panel>

      <Panel title="최종 문서">
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

      {result.logs?.length > 0 && (
        <details className="panel details-panel process-details">
          <summary>처리 단계</summary>
          <pre className="log-box">{result.logs.join("\n")}</pre>
        </details>
      )}
    </div>
  );
}

function VerificationSummary({ report }) {
  if (!report) return null;
  const confidence = Number(report.overall_confidence || 0);
  const percent = Math.round(confidence * 100);
  const skipped = report.status === "skipped";
  const needsReview = Boolean(report.needs_user_confirmation);

  return (
    <section className={`verify-card ${needsReview || skipped ? "review" : "pass"}`}>
      {needsReview ? <AlertTriangle size={22} /> : <CheckCircle2 size={22} />}
      <div>
        <div className="verify-header">
          <h2>{skipped ? "최종 확인 생략" : "검토 결과"}</h2>
          {!skipped && <span>신뢰도 {percent}%</span>}
          <span>{report.status}</span>
        </div>
        <p>{report.summary || "검토 요약이 없습니다."}</p>
        {skipped ? (
          <strong>최종 확인을 끈 상태라 미리보기에서 직접 확인하세요.</strong>
        ) : (
          needsReview && <strong>신뢰도가 낮거나 의심 항목이 있어 최종 확인이 필요합니다.</strong>
        )}
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

function Input({ label, value, onChange, wide = false, type = "text", placeholder = "" }) {
  return (
    <label className={`field ${wide ? "wide" : ""}`}>
      <span>{label}</span>
      <input type={type} value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function Toggle({ label, checked, onChange }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
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

function compactProfile(profile) {
  const compact = { ...profile, extra: { raw: profile.extra?.raw || "" } };
  for (const key of Object.keys(sectionConfigs)) {
    compact[key] = (profile[key] || []).filter((row) => Object.values(row).some((value) => String(value || "").trim()));
  }
  return compact;
}

function profileToText(profile) {
  const p = compactProfile(profile);
  const lines = [
    `이름: ${p.name}`,
    `영문 이름: ${p.english_name}`,
    `생년월일: ${p.birth_date}`,
    `성별: ${p.gender}`,
    `연락처: ${p.phone}`,
    `이메일: ${p.email}`,
    `주소: ${p.address}`,
    `지원직무: ${p.job}`,
  ];
  for (const [key, config] of Object.entries(sectionConfigs)) {
    lines.push("", config.title);
    for (const row of p[key]) {
      lines.push(`- ${config.fields.map(([field]) => row[field]).filter(Boolean).join(" / ")}`);
    }
  }
  if (p.extra?.raw) lines.push("", "기타 정보", p.extra.raw);
  return lines.join("\n");
}

function formatElapsed(ms) {
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}초`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}분 ${rest}초`;
}

createRoot(document.getElementById("root")).render(<App />);
