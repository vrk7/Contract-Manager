import React, { useState } from 'react';

interface RetrievedChunk {
  chunk_id: string;
  source: string;
  content: string;
}

interface Finding {
  clause_type: string;
  risk_level: string;
  extracted_value?: string;
  deviation?: string;
  playbook_standard?: string;
  recommendation?: string;
  source_text?: string;
  retrieved_chunks?: RetrievedChunk[];
  confidence?: number;
  section?: string;
}

interface FindingsListProps {
  findings: Finding[];
  analysisType?: 'risks' | 'summary' | 'obligations';
  onClear?: () => void;
}

const RISK_COLORS: Record<string, string> = {
  critical:   '#ef4444',
  high:       '#f97316',
  medium:     '#eab308',
  low:        '#22c55e',
  acceptable: '#06b6d4',
  unknown:    '#64748b',
};

const RISK_ORDER = ['critical', 'high', 'medium', 'low', 'acceptable', 'unknown'];

const friendlyLabel = (s: string) =>
  s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

const riskBorderStyle = (risk: string): React.CSSProperties => ({
  borderLeft: `3px solid ${RISK_COLORS[risk] ?? RISK_COLORS.unknown}`,
});

/* ── parsers ── */

interface ParsedRec { main: string; citations: string[] }
const parseRecommendation = (text = ''): ParsedRec => {
  const [main, cites] = text.split(/\(Refs:/i);
  return {
    main: main.replace(/^(Summary:|Action:)/i, '').trim(),
    citations: (cites || '').replace(/\)$/, '').trim().split(/[,;]\s*/).filter(Boolean),
  };
};

interface ObligationMeta { party: string; deadline: string; consequence: string }
const parseObligationMeta = (text = ''): ObligationMeta => ({
  party:       text.match(/Party:\s*([^.]+)/)?.[1]?.trim() ?? '',
  deadline:    text.match(/Deadline:\s*([^.]+)/)?.[1]?.trim() ?? '',
  consequence: text.match(/Consequence:\s*([^.]+)/)?.[1]?.trim() ?? '',
});

const parseObligationItems = (text = ''): string[] => {
  const [main] = text.split(/\(Refs:/i);
  return main.trim().split(/;\s*/).map((s) => s.trim()).filter(Boolean);
};

/* ─────────────────────────────────────────────────────────
   RISKS VIEW — accordion cards sorted by severity
───────────────────────────────────────────────────────── */
function RisksView({ findings, onClear }: { findings: Finding[]; onClear?: () => void }) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [allExpanded, setAllExpanded] = useState(false);

  const sorted = [...findings].sort(
    (a, b) => RISK_ORDER.indexOf(a.risk_level) - RISK_ORDER.indexOf(b.risk_level),
  );
  const counts = RISK_ORDER.reduce<Record<string, number>>((acc, r) => {
    acc[r] = findings.filter((f) => f.risk_level === r).length;
    return acc;
  }, {});

  return (
    <>
      <div className="findings-toolbar">
        <div className="chips">
          {RISK_ORDER.filter((r) => counts[r] > 0).map((r) => (
            <span key={r} className={`badge ${r}`}>{counts[r]} {r}</span>
          ))}
        </div>
        <div style={{ display: 'flex', gap: '0.4rem' }}>
          <button onClick={() => { setAllExpanded((p) => !p); setExpandedIdx(null); }} className="ghost" style={{ fontSize: '12px', padding: '0.25rem 0.65rem' }}>
            {allExpanded ? 'Collapse all' : 'Expand all'}
          </button>
          {onClear && <button onClick={onClear} className="ghost" style={{ fontSize: '12px', padding: '0.25rem 0.65rem' }}>Clear</button>}
        </div>
      </div>

      <div className="grid findings-grid">
        {sorted.map((f, idx) => {
          const rec = parseRecommendation(f.recommendation);
          const isExpanded = allExpanded || expandedIdx === idx;
          return (
            <div key={idx} className="card finding-card" style={riskBorderStyle(f.risk_level)}>
              <div className="finding-header" title={isExpanded ? 'Collapse' : 'Expand'} onClick={() => setExpandedIdx(isExpanded ? null : idx)} style={{ cursor: 'pointer', userSelect: 'none' }}>
                <div>
                  <p className="eyebrow">Clause</p>
                  <strong style={{ fontSize: '14px' }}>{friendlyLabel(f.clause_type)}</strong>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span className={`badge ${f.risk_level}`}>{f.risk_level}</span>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--t3)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                    style={{ transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 200ms ease', flexShrink: 0 }}>
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </div>
              </div>

              {isExpanded && (
                <div className="finding-body">
                  <div className="finding-facts">
                    <div><span className="label">Extracted</span><p className="fact-value">{f.extracted_value || '—'}</p></div>
                    <div><span className="label">Deviation</span><p className="fact-value">{f.deviation || '—'}</p></div>
                    <div><span className="label">Playbook standard</span><p className="fact-value">{f.playbook_standard || '—'}</p></div>
                    {f.section && <div><span className="label">Section</span><p className="fact-value">{f.section}</p></div>}
                    {f.confidence !== undefined && <div><span className="label">Confidence</span><p className="fact-value">{Math.round(f.confidence * 100)}%</p></div>}
                  </div>

                  <div className="recommendation-block">
                    <span className="label">Recommendation</span>
                    <p className="recommendation-text">{rec.main || f.recommendation || 'No recommendation provided.'}</p>
                    {rec.citations.length > 0 && (
                      <div className="chips">{rec.citations.map((id) => <span key={id} className="chip">{id}</span>)}</div>
                    )}
                  </div>

                  <div className="source-section">
                    <span className="label">Source text</span>
                    <pre className="source-text">{f.source_text || 'Not provided.'}</pre>
                  </div>

                  {(f.retrieved_chunks || []).length > 0 && (
                    <div className="retrieved-section">
                      <span className="label">Retrieved evidence</span>
                      <ul className="chunk-list">
                        {f.retrieved_chunks!.map((c) => (
                          <li key={c.chunk_id} className="chunk-item">
                            <div className="chunk-meta">
                              <span className="chip ghost">Chunk {c.chunk_id}</span>
                              <small className="chunk-source">{c.source}</small>
                            </div>
                            <p className="chunk-content">{c.content.length > 220 ? `${c.content.slice(0, 220)}…` : c.content}</p>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}

/* ─────────────────────────────────────────────────────────
   SUMMARY VIEW — prose cards, always open
───────────────────────────────────────────────────────── */
function SummaryView({ findings, onClear }: { findings: Finding[]; onClear?: () => void }) {
  return (
    <>
      <div className="findings-toolbar">
        <p className="eyebrow" style={{ margin: 0 }}>{findings.length} clause{findings.length !== 1 ? 's' : ''} summarised</p>
        {onClear && <button onClick={onClear} className="ghost" style={{ fontSize: '12px', padding: '0.25rem 0.65rem' }}>Clear</button>}
      </div>

      <div className="summary-list">
        {findings.map((f, idx) => {
          const rec = parseRecommendation(f.recommendation);
          return (
            <div key={idx} className="summary-card">
              <div className="summary-card-top">
                <div className="summary-clause-label">
                  <span className="summary-clause-icon">§</span>
                  <span className="summary-clause-name">{friendlyLabel(f.clause_type)}</span>
                </div>
                <span className={`badge ${f.risk_level}`}>{f.risk_level}</span>
              </div>

              <p className="summary-prose">{rec.main || f.recommendation || '—'}</p>

              <div className="summary-meta">
                {f.extracted_value && (
                  <span className="summary-meta-item">
                    <span className="label" style={{ display: 'inline', marginRight: '0.3rem' }}>Value</span>
                    {f.extracted_value}
                  </span>
                )}
                {f.section && (
                  <span className="summary-meta-item">
                    <span className="label" style={{ display: 'inline', marginRight: '0.3rem' }}>Section</span>
                    {f.section}
                  </span>
                )}
                {rec.citations.length > 0 && (
                  <span className="summary-meta-item">
                    <span className="label" style={{ display: 'inline', marginRight: '0.3rem' }}>Refs</span>
                    {rec.citations.join(', ')}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

/* ─────────────────────────────────────────────────────────
   OBLIGATIONS VIEW — checklist per clause
───────────────────────────────────────────────────────── */
function ObligationsView({ findings, onClear }: { findings: Finding[]; onClear?: () => void }) {
  const [checked, setChecked] = useState<Record<string, boolean>>({});

  const toggle = (key: string) =>
    setChecked((prev) => ({ ...prev, [key]: !prev[key] }));

  const totalItems = findings.reduce((sum, f) => sum + parseObligationItems(f.recommendation).length, 0);
  const doneItems = Object.values(checked).filter(Boolean).length;

  return (
    <>
      <div className="findings-toolbar">
        <div className="oblig-progress">
          <div className="oblig-progress-bar">
            <div className="oblig-progress-fill" style={{ width: totalItems ? `${(doneItems / totalItems) * 100}%` : '0%' }} />
          </div>
          <span className="oblig-progress-label">{doneItems} / {totalItems} done</span>
        </div>
        {onClear && <button onClick={onClear} className="ghost" style={{ fontSize: '12px', padding: '0.25rem 0.65rem' }}>Clear</button>}
      </div>

      <div className="oblig-list">
        {findings.map((f, fIdx) => {
          const meta = parseObligationMeta(f.deviation);
          const items = parseObligationItems(f.recommendation);

          return (
            <div key={fIdx} className="oblig-group">
              <div className="oblig-group-header">
                <span className="oblig-clause-name">{friendlyLabel(f.clause_type)}</span>
                <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap', alignItems: 'center' }}>
                  {meta.party && <span className="oblig-badge party">{meta.party}</span>}
                  {meta.deadline && <span className="oblig-badge deadline">⏱ {meta.deadline}</span>}
                  {f.section && <span className="oblig-badge section">{f.section}</span>}
                </div>
              </div>

              <ul className="oblig-items">
                {items.map((item, iIdx) => {
                  const key = `${fIdx}-${iIdx}`;
                  const done = !!checked[key];
                  return (
                    <li key={key} className={`oblig-item${done ? ' done' : ''}`} onClick={() => toggle(key)}>
                      <span className={`oblig-checkbox${done ? ' checked' : ''}`}>
                        {done && (
                          <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
                            <polyline points="2,6 5,9 10,3" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        )}
                      </span>
                      <span className="oblig-item-text">{item}</span>
                    </li>
                  );
                })}
              </ul>

              {meta.consequence && (
                <div className="oblig-consequence">
                  <span className="oblig-consequence-icon">⚠</span>
                  <span><strong>Consequence:</strong> {meta.consequence}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}

/* ─────────────────────────────────────────────────────────
   ROOT EXPORT
───────────────────────────────────────────────────────── */
export default function FindingsList({ findings, analysisType = 'risks', onClear }: FindingsListProps) {
  if (!findings.length) {
    const emptyMessages = {
      risks: 'Paste a contract and click Start analysis — risk findings will stream in.',
      summary: 'Paste a contract and click Start analysis — clause summaries will appear here.',
      obligations: 'Paste a contract and click Start analysis — obligations will be listed as a checklist.',
    };
    return (
      <div className="empty-state">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
          <polyline points="10 9 9 9 8 9"/>
        </svg>
        <p>{emptyMessages[analysisType]}</p>
      </div>
    );
  }

  if (analysisType === 'summary') return <SummaryView findings={findings} onClear={onClear} />;
  if (analysisType === 'obligations') return <ObligationsView findings={findings} onClear={onClear} />;
  return <RisksView findings={findings} onClear={onClear} />;
}
