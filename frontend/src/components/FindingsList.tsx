import React from 'react';

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
}

interface FindingsListProps {
  findings: Finding[];
}

interface ParsedRecommendation {
  main: string;
  citations: string[];
}

const riskColor = (risk: string): string => `badge ${risk}`;

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

export default function FindingsList({ findings }: FindingsListProps) {
  if (!findings.length) {
    return <p>No findings yet.</p>;
  }

  return (
    <div className="grid findings-grid">
      {findings.map((f, idx) => {
        const recommendation = parseRecommendation(f.recommendation);
        return (
          <div key={idx} className="card finding-card">
            <div className="finding-header">
              <div>
                <p className="eyebrow">Clause</p>
                <strong>{f.clause_type}</strong>
              </div>
              <span className={riskColor(f.risk_level)}>{f.risk_level}</span>
            </div>
            <div className="finding-body">
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
            </div>
          </div>
        );
      })}
    </div>
  );
}
