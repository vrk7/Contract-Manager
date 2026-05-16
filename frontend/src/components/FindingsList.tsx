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
  onClear?: () => void;
}

interface ParsedRecommendation {
  main: string;
  citations: string[];
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

const riskBorderStyle = (risk: string): React.CSSProperties => ({
  borderLeft: `3px solid ${RISK_COLORS[risk] ?? RISK_COLORS.unknown}`,
});

const parseRecommendation = (text = ''): ParsedRecommendation => {
  const [main, citations] = text.split(/Cite chunks:/i);
  return {
    main: main.replace(/^(Summary:|Action:)/i, '').trim(),
    citations: (citations || '')
      .replace(/\.$/, '')
      .trim()
      .split(/[,;]\s*/)
      .filter(Boolean),
  };
};

export default function FindingsList({ findings, onClear }: FindingsListProps) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [allExpanded, setAllExpanded] = useState(false);

  if (!findings.length) {
    return (
      <div className="empty-state">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
          <polyline points="10 9 9 9 8 9"/>
        </svg>
        <p>Paste a contract and click Start analysis — findings will appear here as they stream in.</p>
      </div>
    );
  }

  const sorted = [...findings].sort(
    (a, b) => RISK_ORDER.indexOf(a.risk_level) - RISK_ORDER.indexOf(b.risk_level)
  );

  const counts = RISK_ORDER.reduce<Record<string, number>>((acc, r) => {
    acc[r] = findings.filter((f) => f.risk_level === r).length;
    return acc;
  }, {});

  const handleToggleAll = () => {
    setAllExpanded((prev) => !prev);
    setExpandedIdx(null);
  };

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
        <div className="chips">
          {RISK_ORDER.filter((r) => counts[r] > 0).map((r) => (
            <span key={r} className={`badge ${r}`}>{counts[r]} {r}</span>
          ))}
        </div>
        <div style={{ display: 'flex', gap: '0.4rem' }}>
          <button onClick={handleToggleAll} className="ghost" style={{ fontSize: '12px', padding: '0.25rem 0.65rem' }}>
            {allExpanded ? 'Collapse all' : 'Expand all'}
          </button>
          {onClear && (
            <button onClick={onClear} className="ghost" style={{ fontSize: '12px', padding: '0.25rem 0.65rem' }}>
              Clear
            </button>
          )}
        </div>
      </div>

      <div className="grid findings-grid">
        {sorted.map((f, idx) => {
          const rec = parseRecommendation(f.recommendation);
          const isExpanded = allExpanded || expandedIdx === idx;

          return (
            <div key={idx} className="card finding-card" style={riskBorderStyle(f.risk_level)}>
              <div
                className="finding-header"
                onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                style={{ cursor: 'pointer', userSelect: 'none' }}
                title={isExpanded ? 'Collapse' : 'Expand'}
              >
                <div>
                  <p className="eyebrow">Clause</p>
                  <strong style={{ fontSize: '14px' }}>{f.clause_type.replace(/_/g, ' ')}</strong>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span className={`badge ${f.risk_level}`}>{f.risk_level}</span>
                  <svg
                    width="14" height="14" viewBox="0 0 24 24" fill="none"
                    stroke="var(--t3)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                    style={{ transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 200ms ease', flexShrink: 0 }}
                  >
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </div>
              </div>

              {isExpanded && (
                <div className="finding-body">
                  <div className="finding-facts">
                    <div>
                      <span className="label">Extracted</span>
                      <p className="fact-value">{f.extracted_value || '—'}</p>
                    </div>
                    <div>
                      <span className="label">Deviation</span>
                      <p className="fact-value">{f.deviation || '—'}</p>
                    </div>
                    <div>
                      <span className="label">Playbook standard</span>
                      <p className="fact-value">{f.playbook_standard || '—'}</p>
                    </div>
                    {f.section && (
                      <div>
                        <span className="label">Section</span>
                        <p className="fact-value">{f.section}</p>
                      </div>
                    )}
                    {f.confidence !== undefined && (
                      <div>
                        <span className="label">Confidence</span>
                        <p className="fact-value">{Math.round(f.confidence * 100)}%</p>
                      </div>
                    )}
                  </div>

                  <div className="recommendation-block">
                    <span className="label">Recommendation</span>
                    <p className="recommendation-text">
                      {rec.main || f.recommendation || 'No recommendation provided.'}
                    </p>
                    {rec.citations.length > 0 && (
                      <div className="chips">
                        {rec.citations.map((id) => (
                          <span key={id} className="chip">{id}</span>
                        ))}
                      </div>
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
                            <p className="chunk-content">
                              {c.content.length > 220 ? `${c.content.slice(0, 220)}…` : c.content}
                            </p>
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
