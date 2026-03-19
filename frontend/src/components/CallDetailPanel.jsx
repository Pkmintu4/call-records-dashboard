function CallDetailPanel({ detail }) {
  if (!detail) {
    return (
      <div className="card">
        <h3>Call Summary</h3>
        <p className="meta">Select a call from the table to see summary and sentiment.</p>
      </div>
    );
  }

  return (
    <div className="card">
      <h3>Call Summary</h3>
      <p className="meta"><strong>File:</strong> {detail.file_name}</p>
      <p className="meta"><strong>Label:</strong> {detail.label}</p>
      <p className="meta"><strong>Score:</strong> {detail.score.toFixed(2)}</p>
      <p className="meta"><strong>Summary:</strong> {detail.summary || detail.explanation}</p>
      {detail.kpis && (
        <>
          <h4>KPI Insights</h4>
          <p className="meta"><strong>Parent Sentiment:</strong> {detail.kpis.sentiment || detail.label}</p>
          <p className="meta"><strong>Intent Score:</strong> {detail.kpis.intent_score ?? "-"}</p>
          <p className="meta"><strong>Visit Intent:</strong> {detail.kpis.visit_intent || "-"}</p>
          <p className="meta"><strong>Lead Source:</strong> {detail.kpis.lead_source || "unknown"}</p>
          <p className="meta"><strong>Admission Probability:</strong> {detail.kpis.admission_probability ?? "-"}%</p>
          <p className="meta"><strong>Persuasion:</strong> {detail.kpis.persuasion_score ?? "-"}/5</p>
          <p className="meta"><strong>Response Clarity:</strong> {detail.kpis.response_clarity ?? "-"}/5</p>
          <p className="meta"><strong>Politeness:</strong> {detail.kpis.politeness_score ?? "-"}/5</p>
          <p className="meta"><strong>Missed Conversion:</strong> {detail.kpis.missed_conversion_opportunity || "no"}</p>
          <p className="meta"><strong>Parent Concerns:</strong> {(detail.kpis.parent_concerns || []).join(", ") || "none"}</p>
          <p className="meta"><strong>Competitors Mentioned:</strong> {(detail.kpis.competitor_schools_mentioned || []).join(", ") || "none"}</p>
          <p className="meta"><strong>Key Questions:</strong> {(detail.kpis.key_questions_asked || []).join(" | ") || "none"}</p>
          <p className="meta"><strong>Friction Points:</strong> {(detail.kpis.friction_points || []).join(" | ") || "none"}</p>
        </>
      )}
      {detail.keywords.length > 0 && (
        <div className="keywords">
          {detail.keywords.map((keyword) => (
            <span key={keyword} className="keyword">
              {keyword}
            </span>
          ))}
        </div>
      )}
      <h4>Transcript</h4>
      <div className="content-block">{detail.content}</div>
    </div>
  );
}

export default CallDetailPanel;
