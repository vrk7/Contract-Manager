import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import PlaybookManager from './components/PlaybookManager';
import FindingsList from './components/FindingsList';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

function App() {
  const [contractText, setContractText] = useState('');
  const [analysisType, setAnalysisType] = useState('risks');
  const [analysisId, setAnalysisId] = useState(null);
  const [status, setStatus] = useState(null);
  const [result, setResult] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const [usage, setUsage] = useState(null);
  const eventSourceRef = useRef(null);
  const [activeTab, setActiveTab] = useState('analyzer');
  const [playbookVersion, setPlaybookVersion] = useState(null);

  const startStream = (id) => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }
    const stream = new EventSource(`${API_BASE}/analysis/${id}/stream`);
    eventSourceRef.current = stream;
    stream.addEventListener('status', (e) => {
      const payload = JSON.parse(e.data);
      setStatus(payload.message || payload.status);
    });
    stream.addEventListener('partial_finding', (e) => {
      const payload = JSON.parse(e.data);
      setResult((prev) => {
        const findings = prev?.findings ? [...prev.findings] : [];
        findings.push(payload.finding);
        return { ...(prev || {}), findings };
      });
    });
    stream.addEventListener('final', (e) => {
      const payload = JSON.parse(e.data);
      setResult(payload.result);
      setWarnings(payload.result.guardrail_warnings || []);
      setUsage(payload.result.usage || null);
      stream.close();
    });
    stream.addEventListener('error', () => stream.close());
  };

  const handleAnalyze = async () => {
    setResult(null);
    setWarnings([]);
    setUsage(null);
    const resp = await axios.post(`${API_BASE}/analyze`, {
      contract_text: contractText,
      analysis_type: analysisType,
      playbook_version_id: playbookVersion || null,
    });
    setAnalysisId(resp.data.analysis_id);
    setStatus('queued');
    startStream(resp.data.analysis_id);
  };

  const riskBadgeClass = (risk) => `badge ${risk}`;

  return (
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
              placeholder="Paste contract text here"
            />
            <div style={{ margin: '0.5rem 0' }}>
              <label className="input-label" htmlFor="analysisType">
                Analysis type
                <select id="analysisType" value={analysisType} onChange={(e) => setAnalysisType(e.target.value)}>
                  <option value="risks">Risks</option>
                  <option value="summary">Summary</option>
                  <option value="obligations">Obligations</option>
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
                <h3>Results</h3>
              </div>
              {result?.overall_risk_score && (
                <span className={riskBadgeClass(result.overall_risk_score)}>Overall: {result.overall_risk_score}</span>
              )}
            </div>
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
            <FindingsList findings={result?.findings || []} />
          </div>
        </div>
      )}

      {activeTab === 'playbook' && (
        <div className="card">
          <PlaybookManager apiBase={API_BASE} onVersionChange={setPlaybookVersion} />
        </div>
      )}
    </div>
  );
}

export default App;
