function CallSentimentTable({ rows, onSelect, title = "Per-Call Sentiment Analytics" }) {
  return (
    <div className="card">
      <h3>{title}</h3>
      <table className="table">
        <thead>
          <tr>
            <th>File</th>
            <th>Detailed Insight</th>
            <th>Admission %</th>
            <th>Intent</th>
            <th>Visit</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.transcript_id}>
              <td>
                <button className="row-button" onClick={() => onSelect(row.transcript_id)}>
                  {row.file_name}
                </button>
              </td>
              <td>{row.detailed_insight || row.summary}</td>
              <td>{row.admission_probability}%</td>
              <td>{row.intent_category || "Inquiry"} ({row.intent_score}/5)</td>
              <td>{row.visit_intent}</td>
              <td>{new Date(row.created_at).toLocaleString()}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={6}>No records yet. Click “Fetch from Drive”.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export default CallSentimentTable;
