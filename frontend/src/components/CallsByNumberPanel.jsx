function CallsByNumberPanel({ groups, onSelectCall }) {
  return (
    <div className="card chart-card grouped-calls-card">
      <div className="chart-header">
        <div>
          <h3>Combined Calls by Number</h3>
          <p className="chart-subtitle">All calls from the same phone number are grouped together for quick review.</p>
        </div>
        <span className="card-pill">{groups.length} numbers</span>
      </div>

      <div className="grouped-calls-list">
        {groups.map((group) => (
          <details key={`${group.phone_number}-${group.latest_call_at}`} className="grouped-call-item">
            <summary className="grouped-call-summary-row">
              <span className="grouped-call-phone">{group.phone_number}</span>
              <span className="grouped-call-meta">
                {group.call_count} calls | avg score {Number(group.avg_score).toFixed(2)} | {group.dominant_label} | {group.top_intent} | latest {new Date(group.latest_call_at).toLocaleString()}
              </span>
            </summary>

            <div className="grouped-call-body">
              <p className="grouped-call-summary-text">
                <strong>Combined summary:</strong> {group.combined_summary}
              </p>

              <table className="table grouped-call-table">
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Created</th>
                    <th>Label</th>
                    <th>Score</th>
                    <th>Summary</th>
                  </tr>
                </thead>
                <tbody>
                  {group.calls.map((call) => (
                    <tr key={call.transcript_id}>
                      <td>
                        <button className="row-button" onClick={() => onSelectCall(call.transcript_id)}>
                          {call.file_name}
                        </button>
                      </td>
                      <td>{new Date(call.created_at).toLocaleString()}</td>
                      <td>{call.label}</td>
                      <td>{Number(call.score).toFixed(2)}</td>
                      <td>{call.summary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        ))}

        {groups.length === 0 && (
          <p className="empty-state-text">No grouped call data yet. Run ingest to populate grouped numbers.</p>
        )}
      </div>
    </div>
  );
}

export default CallsByNumberPanel;
