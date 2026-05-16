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
  const [contractText, setContractText] = useState<string>('');
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
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }
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

  const riskBadgeClass = (risk: string): string => `badge ${risk}`;

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

  const handleCopyText = () => {
    navigator.clipboard.writeText(contractText);
  };

  return (
    <ErrorBoundary>
    <div className="container">
      <header className="page-header">
        <div>
          <p className="eyebrow">AI-powered contract review</p>
          <h1>Contract Clause Analyzer</h1>
          <p className="lede">Surface risks, summarize obligations, and keep your playbook aligned in one elegant workspace.</p>
        </div>
        <div className="pill-group">
          <span className="pill subtle">Secure by design</span>
          <span className="pill subtle">Real-time analysis</span>
        </div>
      </header>
      <div className="tab-buttons">
        <button className={activeTab === 'analyzer' ? 'active' : ''} onClick={() => setActiveTab('analyzer')}>
          Analyzer
        </button>
        <button className={activeTab === 'playbook' ? 'active' : ''} onClick={() => setActiveTab('playbook')}>
          Playbook
        </button>
      </div>

      {activeTab === 'analyzer' && (
        <div className="grid two-column">
          <div className="card">
            <div className="card-header">
              <div>
                <p className="eyebrow">Step 1</p>
                <h3>Contract Input</h3>
              </div>
              <span className="pill">{analysisType === 'risks' ? 'Risk scan' : analysisType === 'summary' ? 'Summary' : 'Obligations'}</span>
            </div>
            <textarea
              value={contractText}
              onChange={(e) => setContractText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Paste contract text here (Ctrl+Enter to analyze)"
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: '#888', margin: '0.25rem 0' }}>
              <span>{contractText.length.toLocaleString()} characters</span>
              <button onClick={handleCopyText} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '0.75rem', color: '#888' }}>
                Copy
              </button>
            </div>
            <div style={{ margin: '0.5rem 0' }}>
              <label className="input-label" htmlFor="analysisType">
                Analysis type
                <select id="analysisType" value={analysisType} onChange={(e) => setAnalysisType(e.target.value as AnalysisType)}>
                  <option value="risks" title="Identify deviations from your playbook and score their risk level">Risks — identify deviations and score risk</option>
                  <option value="summary" title="Plain-language summary of each clause for non-legal stakeholders">Summary — plain-language clause overview</option>
                  <option value="obligations" title="Extract concrete actions each party is obligated to perform">Obligations — extract required actions</option>
                </select>
              </label>
            </div>
            <button onClick={handleAnalyze} disabled={!contractText}>
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

          <div className="card">
            <div className="card-header">
              <div>
                <p className="eyebrow">Step 2</p>
                <h3>Results {result && <span style={{ fontWeight: 400, fontSize: '0.85rem', color: '#888' }}>({result.findings.length} finding{result.findings.length !== 1 ? 's' : ''})</span>}</h3>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                {result?.overall_risk_score && (
                  <span className={riskBadgeClass(result.overall_risk_score)}>Overall: {result.overall_risk_score}</span>
                )}
                {result && (
                  <button onClick={handleExportJson} style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem' }}>
                    Export JSON
                  </button>
                )}
              </div>
            </div>
            {result?.overall_risk_score && (
              <div className="risk-meter">
                <div className="risk-meter-bar">
                  <div className={`risk-meter-fill ${result.overall_risk_score}`} />
                </div>
                <span className={riskBadgeClass(result.overall_risk_score)}>{result.overall_risk_score}</span>
              </div>
            )}
            {result?.overall_risk_score && (
              <p className="muted">Risk posture calculated from detected clauses and deviations.</p>
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
                  <p className="metric">{usage.total_tokens}</p>
                </div>
                <div>
                  <p className="eyebrow">Estimated cost</p>
                  <p className="metric">${usage.estimated_cost_usd}</p>
                </div>
              </div>
            )}
            <FindingsList findings={result?.findings || []} onClear={() => { setResult(null); setWarnings([]); setUsage(null); setStatus(null); }} />
          </div>
        </div>
      )}

      {activeTab === 'playbook' && (
        <div className="card">
          <PlaybookManager onVersionChange={setPlaybookVersion} />
        </div>
      )}
    </div>
    </ErrorBoundary>
  );
}

export default App;
