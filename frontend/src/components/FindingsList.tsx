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
}

interface ParsedRecommendation {
  main: string;
  citations: string[];
}

const RISK_COLORS: Record<string, string> = {
  critical: '#e53e3e',
  high: '#dd6b20',
  medium: '#d69e2e',
  low: '#38a169',
  acceptable: '#319795',
  unknown: '#718096',
};

const riskColor = (risk: string): string => `badge ${risk}`;

const riskBorderStyle = (risk: string): React.CSSProperties => ({
  borderLeft: `4px solid ${RISK_COLORS[risk] ?? RISK_COLORS.unknown}`,
});

const parseRecommendation = (text: string = ''): ParsedRecommendation => {
  const [main, citations] = text.split(/Cite chunks:/i);
  const cleanedMain = main.replace(/^(Summary:|Action:)/i, '').trim();
  const cleanedCitations = (citations || '').replace(/\.$/, '').trim();
  const citationList = cleanedCitations
    ? cleanedCitations.split(/[,;]\s*/).filter(Boolean)
    : [];
  return {
    main: cleanedMain,
    citations: citationList,
  };
};

interface FindingsListProps {
  findings: Finding[];
  onClear?: () => void;
}

export default function FindingsList({ findings, onClear }: FindingsListProps) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [allExpanded, setAllExpanded] = useState(false);

  if (!findings.length) {
    return <p style={{ color: '#475569' }}>No findings yet. Paste a contract and click Start analysis.</p>;
  }

  const RISK_ORDER = ['critical', 'high', 'medium', 'low', 'acceptable', 'unknown'];
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
        <div className="chips">
          {RISK_ORDER.filter((r) => counts[r] > 0).map((r) => (
            <span key={r} className={`badge ${r}`}>{counts[r]} {r}</span>
          ))}
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button onClick={handleToggleAll} className="ghost" style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem', boxShadow: 'none' }}>
            {allExpanded ? 'Collapse all' : 'Expand all'}
          </button>
          {onClear && (
            <button onClick={onClear} className="ghost" style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem', boxShadow: 'none' }}>
              Clear
            </button>
          )}
        </div>
      </div>
    <div className="grid findings-grid">
      {sorted.map((f, idx) => {
        const recommendation = parseRecommendation(f.recommendation);
        const isExpanded = allExpanded || expandedIdx === idx;
        return (
          <div key={idx} className="card finding-card" style={riskBorderStyle(f.risk_level)}>
            <div
              className="finding-header"
              onClick={() => setExpandedIdx(isExpanded ? null : idx)}
              style={{ cursor: 'pointer', userSelect: 'none' }}
              title={isExpanded ? 'Click to collapse' : 'Click to expand'}
            >
              <div>
                <p className="eyebrow">Clause</p>
                <strong>{f.clause_type.replace(/_/g, ' ')}</strong>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span className={riskColor(f.risk_level)}>{f.risk_level}</span>
                <span style={{ fontSize: '0.75rem', color: '#888' }}>{isExpanded ? '▲' : '▼'}</span>
              </div>
            </div>
            {isExpanded && <div className="finding-body">
              <div className="finding-facts">
                <div className="fact">
                  <p className="label">Extracted</p>
                  <p className="fact-value">{f.extracted_value || '—'}</p>
                </div>
                <div className="fact">
                  <p className="label">Deviation</p>
                  <p className="fact-value">{f.deviation || '—'}</p>
                </div>
                <div className="fact">
                  <p className="label">Playbook standard</p>
                  <p className="fact-value">{f.playbook_standard || '—'}</p>
                </div>
                {f.section && (
                  <div className="fact">
                    <p className="label">Section</p>
                    <p className="fact-value">{f.section}</p>
                  </div>
                )}
                {f.confidence !== undefined && (
                  <div className="fact">
                    <p className="label">Confidence</p>
                    <p className="fact-value">{Math.round(f.confidence * 100)}%</p>
                  </div>
                )}
              </div>

              <div className="recommendation-block">
                <p className="label">Recommendation</p>
                <p className="recommendation-text">
                  {recommendation.main || f.recommendation || 'No recommendation provided.'}
                </p>
                {recommendation.citations.length > 0 && (
                  <div className="chips">
                    {recommendation.citations.map((id) => (
                      <span key={id} className="chip">
                        {id}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div className="source-section">
                <p className="label">Source text</p>
                <pre className="source-text">{f.source_text || 'Not provided.'}</pre>
              </div>

              {(f.retrieved_chunks || []).length > 0 && (
                <div className="retrieved-section">
                  <p className="label">Retrieved evidence</p>
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
            </div>}
          </div>
        );
      })}
    </div>
    </>
  );
}
