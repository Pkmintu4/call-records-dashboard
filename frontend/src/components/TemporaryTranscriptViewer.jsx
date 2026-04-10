import { getCallAudioUrl } from "../lib/api";


function TemporaryTranscriptViewer({ rows }) {
  return (
    <div className="card chart-card temp-transcript-card">
      <div className="chart-header">
        <div>
          <h3>Temporary Transcript + Summary Viewer</h3>
          <p className="chart-subtitle">Latest fetched files with their generated summary and full transcript text.</p>
        </div>
        <span className="card-pill">{rows.length} items</span>
      </div>

      <div className="temp-transcript-list">
        {rows.map((row) => (
          <details key={row.transcript_id} className="temp-transcript-item">
            <summary className="temp-transcript-summary-row">
              <span className="temp-transcript-file">{row.file_name}</span>
              <span className="temp-transcript-meta">
                {new Date(row.created_at).toLocaleString()} | {row.intent_category} | {row.label}
              </span>
            </summary>
            <div className="temp-transcript-body">
              <p className="temp-transcript-generated-summary">
                <strong>Summary:</strong> {row.summary}
              </p>
              {/\.(mp3|wav|m4a|flac|ogg|aac|amr)$/i.test(String(row.file_name || "")) && (
                <audio
                  controls
                  preload="none"
                  className="inline-audio-player"
                  src={getCallAudioUrl(row.transcript_id)}
                >
                  Your browser does not support audio playback.
                </audio>
              )}
              <div className="content-block">{row.content}</div>
            </div>
          </details>
        ))}

        {rows.length === 0 && (
          <p className="empty-state-text">No records yet. Run fetch/ingest to populate transcripts.</p>
        )}
      </div>
    </div>
  );
}

export default TemporaryTranscriptViewer;
