import React, { useRef, useState } from 'react';
import ErrorBoundary from './components/ErrorBoundary';
import FindingsList from './components/FindingsList';
import PlaybookManager from './components/PlaybookManager';
import { api, streamUrl } from './api';

type AnalysisType = 'risks' | 'summary' | 'obligations';

interface GuardrailWarning {
  type: string;
  message: string;
}

interface Usage {
  total_tokens: number;
  estimated_cost_usd: string;
}

interface Finding {
  clause_type: string;
  risk_level: string;
  extracted_value?: string;
  deviation?: string;
  playbook_standard?: string;
  recommendation?: string;
  source_text?: string;
  retrieved_chunks?: Array<{
    chunk_id: string;
    source: string;
    content: string;
  }>;
}

interface AnalysisResult {
  findings: Finding[];
  overall_risk_score?: string;
  guardrail_warnings?: GuardrailWarning[];
  usage?: Usage;
}

interface StatusEvent {
  message?: string;
  status?: string;
}

interface PartialFindingEvent {
  finding: Finding;
}

interface FinalEvent {
  result: AnalysisResult;
}

function App() {
  const [contractText, setContractText] = useState<string>(() => {
    try { return localStorage.getItem('contract_draft') ?? ''; } catch { return ''; }
  });
  const [analysisType, setAnalysisType] = useState<AnalysisType>('risks');
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [warnings, setWarnings] = useState<GuardrailWarning[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const [activeTab, setActiveTab] = useState<'analyzer' | 'playbook'>('analyzer');
  const [playbookVersion, setPlaybookVersion] = useState<string | null>(null);

  const startStream = (id: string, attempt = 0) => {
    if (eventSourceRef.current) eventSourceRef.current.close();
    const stream = new EventSource(streamUrl(`/analysis/${id}/stream`));
    eventSourceRef.current = stream;
    reconnectAttemptsRef.current = attempt;

    stream.addEventListener('status', (e: MessageEvent) => {
      const payload = JSON.parse(e.data) as StatusEvent;
      setStatus(payload.message || payload.status || null);
    });
    stream.addEventListener('partial_finding', (e: MessageEvent) => {
      const payload = JSON.parse(e.data) as PartialFindingEvent;
      setResult((prev) => {
        const findings = prev?.findings ? [...prev.findings] : [];
        findings.push(payload.finding);
        return { ...(prev || { findings: [] }), findings };
      });
    });
    stream.addEventListener('final', (e: MessageEvent) => {
      const payload = JSON.parse(e.data) as FinalEvent;
      setResult(payload.result);
      setWarnings(payload.result.guardrail_warnings || []);
      setUsage(payload.result.usage || null);
      reconnectAttemptsRef.current = 0;
      stream.close();
    });
    stream.addEventListener('error', () => {
      stream.close();
      const maxRetries = 3;
      if (attempt < maxRetries) {
        const delay = Math.min(1000 * 2 ** attempt, 8000);
        setStatus(`Connection lost — retrying in ${delay / 1000}s (${attempt + 1}/${maxRetries})`);
        setTimeout(() => startStream(id, attempt + 1), delay);
      } else {
        setStatus('Stream disconnected. Please refresh and try again.');
      }
    });
  };

  const isLoading = !!status && status !== 'Stream disconnected. Please refresh and try again.' && !result;

  const handleAnalyze = async () => {
    setResult(null);
    setWarnings([]);
    setUsage(null);
    const resp = await api.post<{ analysis_id: string }>('/analyze', {
      contract_text: contractText,
      analysis_type: analysisType,
      playbook_version_id: playbookVersion || null,
    });
    setAnalysisId(resp.data.analysis_id);
    setStatus('queued');
    startStream(resp.data.analysis_id);
  };

  const riskBadgeClass = (risk: string) => `badge ${risk}`;

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && contractText) {
      e.preventDefault();
      handleAnalyze();
    }
  };

  const handleExportJson = () => {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `analysis-${analysisId || 'result'}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <ErrorBoundary>
      {/* ── Sticky nav ── */}
      <nav className="nav">
        <div className="nav-brand">
          <div className="nav-logo">CA</div>
          <span className="nav-wordmark">Clause Analyzer</span>
        </div>
        <div className="nav-tabs">
          <button
            className={`nav-tab${activeTab === 'analyzer' ? ' active' : ''}`}
            onClick={() => setActiveTab('analyzer')}
          >
            Analyzer
          </button>
          <button
            className={`nav-tab${activeTab === 'playbook' ? ' active' : ''}`}
            onClick={() => setActiveTab('playbook')}
          >
            Playbook
          </button>
        </div>
        <div className="nav-end">
          <span className="pill subtle">Secure</span>
          <span className="pill subtle">Real-time</span>
        </div>
      </nav>

      <div className="container">
        {activeTab === 'analyzer' && (
          <>
            <header className="page-header">
              <div>
                <p className="eyebrow">AI-powered contract review</p>
                <h1>Contract Clause Analyzer</h1>
                <p className="lede">
                  Surface risks, summarize obligations, and keep your playbook aligned — in one elegant workspace.
                </p>
              </div>
            </header>

            <div className="grid two-column">
              {/* ── Input card ── */}
              <div className="card">
                <div className="card-header">
                  <div>
                    <p className="eyebrow">Step 1</p>
                    <h3>Contract Input</h3>
                  </div>
                  <span className="pill">
                    {analysisType === 'risks' ? 'Risk scan' : analysisType === 'summary' ? 'Summary' : 'Obligations'}
                  </span>
                </div>

                <textarea
                  value={contractText}
                  onChange={(e) => {
                    setContractText(e.target.value);
                    try { localStorage.setItem('contract_draft', e.target.value); } catch { /* quota */ }
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder="Paste contract text here — Ctrl+Enter to analyze"
                />

                <div className="char-row">
                  <span>{contractText.length.toLocaleString()} characters</span>
                  <button onClick={() => navigator.clipboard.writeText(contractText)}>Copy</button>
                </div>

                <div style={{ margin: '0.75rem 0' }}>
                  <label className="input-label" htmlFor="analysisType">
                    Analysis type
                    <select
                      id="analysisType"
                      value={analysisType}
                      onChange={(e) => setAnalysisType(e.target.value as AnalysisType)}
                    >
                      <option value="risks">Risks — identify deviations and score risk</option>
                      <option value="summary">Summary — plain-language clause overview</option>
                      <option value="obligations">Obligations — extract required actions</option>
                    </select>
                  </label>
                </div>

                <button onClick={handleAnalyze} disabled={!contractText} style={{ width: '100%' }}>
                  Start analysis
                </button>

                {(analysisId || status) && (
                  <div className="meta-row">
                    {analysisId && (
                      <span className="pill subtle">
                        <strong>ID:</strong> {analysisId}
                      </span>
                    )}
                    {status && (
                      <span className="pill success">
                        <strong>Status:</strong> {status}
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* ── Results card ── */}
              <div className="card">
                <div className="card-header">
                  <div>
                    <p className="eyebrow">Step 2</p>
                    <h3>
                      Results{' '}
                      {result && (
                        <span style={{ fontWeight: 400, fontSize: '0.82rem', color: 'var(--t3)' }}>
                          ({result.findings.length} finding{result.findings.length !== 1 ? 's' : ''})
                        </span>
                      )}
                    </h3>
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    {result?.overall_risk_score && (
                      <span className={riskBadgeClass(result.overall_risk_score)}>
                        Overall: {result.overall_risk_score}
                      </span>
                    )}
                    {result && (
                      <button
                        onClick={handleExportJson}
                        className="ghost"
                        style={{ fontSize: '12px', padding: '0.28rem 0.7rem' }}
                      >
                        Export JSON
                      </button>
                    )}
                  </div>
                </div>

                {result?.overall_risk_score && (
                  <>
                    <div className="risk-meter">
                      <div className="risk-meter-bar">
                        <div className={`risk-meter-fill ${result.overall_risk_score}`} />
                      </div>
                      <span className={riskBadgeClass(result.overall_risk_score)}>
                        {result.overall_risk_score}
                      </span>
                    </div>
                    <p className="muted" style={{ marginBottom: '1rem' }}>
                      Risk posture calculated from detected clauses and deviations.
                    </p>
                  </>
                )}

                {warnings.map((w, idx) => (
                  <div className="warning" key={idx}>
                    <strong>{w.type}</strong>: {w.message}
                  </div>
                ))}

                {usage && (
                  <div className="usage">
                    <div>
                      <p className="eyebrow">Tokens</p>
                      <p className="metric">{usage.total_tokens.toLocaleString()}</p>
                    </div>
                    <div>
                      <p className="eyebrow">Est. cost</p>
                      <p className="metric">${usage.estimated_cost_usd}</p>
                    </div>
                  </div>
                )}

                {isLoading && !result?.findings?.length && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.5rem' }}>
                    {[1, 2, 3].map((i) => (
                      <div key={i} className="skeleton" />
                    ))}
                  </div>
                )}

                <FindingsList
                  findings={result?.findings || []}
                  onClear={() => {
                    setResult(null);
                    setWarnings([]);
                    setUsage(null);
                    setStatus(null);
                  }}
                />
              </div>
            </div>
          </>
        )}

        {activeTab === 'playbook' && (
          <>
            <header className="page-header">
              <div>
                <p className="eyebrow">Governance</p>
                <h1>Playbook</h1>
                <p className="lede">Edit, version, and reindex your contract playbook standards.</p>
              </div>
            </header>
            <div className="card">
              <PlaybookManager onVersionChange={setPlaybookVersion} />
            </div>
          </>
        )}
      </div>
    </ErrorBoundary>
  );
}

export default App;
