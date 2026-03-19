function CallSentimentTable({ rows, onSelect }) {
  return (
    <div className="card">
      <h3>Per-Call Sentiment</h3>
      <table className="table">
        <thead>
          <tr>
            <th>File</th>
            <th>Summary</th>
            <th>Label</th>
            <th>Score</th>
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
              <td>{row.summary}</td>
              <td>{row.label}</td>
              <td>{row.score.toFixed(2)}</td>
              <td>{new Date(row.created_at).toLocaleString()}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={5}>No records yet. Click “Fetch from Drive”.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export default CallSentimentTable;
