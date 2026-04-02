function CallDetailPanel({ detail }) {
  if (!detail) {
    return (
      <div className="card chart-card">
        <div className="chart-header">
          <div>
            <h3>Call Analysis</h3>
            <p className="chart-subtitle">Select a call from the table to see full details.</p>
          </div>
        </div>
        <p className="empty-state-text">No call selected</p>
      </div>
    );
  }

  return (
    <div className="card chart-card">
      <div className="chart-header">
        <div>
          <h3>Call Analysis</h3>
          <p className="chart-subtitle">{detail.file_name}</p>
        </div>
        <span className={`sentiment-badge sentiment-${detail.label}`}>
          {detail.label.charAt(0).toUpperCase() + detail.label.slice(1)}
        </span>
      </div>

      <div className="detail-section">
        <div className="detail-grid-2">
          <div className="detail-item">
            <span className="detail-label">Sentiment Score</span>
            <p className="detail-value">{detail.score.toFixed(2)}</p>
          </div>
          <div className="detail-item">
            <span className="detail-label">Summary</span>
            <p className="detail-value-text">{detail.summary || detail.explanation}</p>
          </div>
        </div>
      </div>

      {detail.kpis && (
        <>
          <div className="detail-divider"></div>
          <div className="detail-section">
            <h4 className="section-title">Key Performance Indicators</h4>
            <div className="detail-grid-3">
              <div className="detail-item">
                <span className="detail-label">Admission Probability</span>
                <p className="detail-value">{detail.kpis.admission_probability ?? "-"}%</p>
              </div>
              <div className="detail-item">
                <span className="detail-label">Intent Score</span>
                <p className="detail-value">{detail.kpis.intent_score ?? "-"}/5</p>
              </div>
              <div className="detail-item">
                <span className="detail-label">Visit Intent</span>
                <p className="detail-value">{detail.kpis.visit_intent || "-"}</p>
              </div>
              <div className="detail-item">
                <span className="detail-label">Persuasion</span>
                <p className="detail-value">{detail.kpis.persuasion_score ?? "-"}/5</p>
              </div>
              <div className="detail-item">
                <span className="detail-label">Response Clarity</span>
                <p className="detail-value">{detail.kpis.response_clarity ?? "-"}/5</p>
              </div>
              <div className="detail-item">
                <span className="detail-label">Politeness</span>
                <p className="detail-value">{detail.kpis.politeness_score ?? "-"}/5</p>
              </div>
              <div className="detail-item full-width">
                <span className="detail-label">Lead Source</span>
                <p className="detail-value">{detail.kpis.lead_source || "unknown"}</p>
              </div>
              <div className="detail-item full-width">
                <span className="detail-label">Missed Conversion</span>
                <p className="detail-value">{detail.kpis.missed_conversion_opportunity ? "Yes" : "No"}</p>
              </div>
            </div>
          </div>

          {(detail.kpis.parent_concerns?.length > 0 || detail.kpis.competitor_schools_mentioned?.length > 0 || detail.kpis.key_questions_asked?.length > 0 || detail.kpis.friction_points?.length > 0) && (
            <>
              <div className="detail-divider"></div>
              <div className="detail-section">
                <h4 className="section-title">Conversational Insights</h4>
                {detail.kpis.parent_concerns?.length > 0 && (
                  <div className="insight-group">
                    <strong className="insight-title">Parent Concerns:</strong>
                    <p className="insight-text">{detail.kpis.parent_concerns.join(", ")}</p>
                  </div>
                )}
                {detail.kpis.competitor_schools_mentioned?.length > 0 && (
                  <div className="insight-group">
                    <strong className="insight-title">Competitors Mentioned:</strong>
                    <p className="insight-text">{detail.kpis.competitor_schools_mentioned.join(", ")}</p>
                  </div>
                )}
                {detail.kpis.key_questions_asked?.length > 0 && (
                  <div className="insight-group">
                    <strong className="insight-title">Key Questions:</strong>
                    <p className="insight-text">{detail.kpis.key_questions_asked.join(" | ")}</p>
                  </div>
                )}
                {detail.kpis.friction_points?.length > 0 && (
                  <div className="insight-group">
                    <strong className="insight-title">Friction Points:</strong>
                    <p className="insight-text">{detail.kpis.friction_points.join(" | ")}</p>
                  </div>
                )}
              </div>
            </>
          )}
        </>
      )}

      {detail.keywords.length > 0 && (
        <>
          <div className="detail-divider"></div>
          <div className="detail-section">
            <h4 className="section-title">Key Themes</h4>
            <div className="keywords">
              {detail.keywords.map((keyword) => (
                <span key={keyword} className="keyword">
                  {keyword}
                </span>
              ))}
            </div>
          </div>
        </>
      )}

      <div className="detail-divider"></div>
      <div className="detail-section">
        <h4 className="section-title">Transcript</h4>
        <div className="content-block">{detail.content}</div>
      </div>
    </div>
  );
}

export default CallDetailPanel;
