import { getCallAudioUrl } from "../lib/api";


const SPEAKER_COLORS = {
  "speaker 1": "#4a9eff",
  "speaker 2": "#34d399",
  "speaker 3": "#f59e0b",
  "speaker 4": "#a78bfa",
};

function getSpeakerColor(label) {
  const normalized = (label || "").toLowerCase().trim();
  for (const [key, color] of Object.entries(SPEAKER_COLORS)) {
    if (normalized.startsWith(key)) return color;
  }
  return "#94a3b8";
}

function renderDiarizedTranscript(content) {
  if (!content) return null;

  const lines = content.split("\n").filter((l) => l.trim());
  const speakerRegex = /^(Speaker\s*\d+)\s*:\s*/i;

  const hasSpeakerLabels = lines.some((line) => speakerRegex.test(line.trim()));
  if (!hasSpeakerLabels) {
    return <div className="content-block">{content}</div>;
  }

  return (
    <div className="diarized-transcript">
      {lines.map((line, i) => {
        const match = line.trim().match(speakerRegex);
        if (match) {
          const speakerLabel = match[1];
          const text = line.trim().slice(match[0].length);
          const color = getSpeakerColor(speakerLabel);
          return (
            <div key={i} className="speaker-turn">
              <span className="speaker-label" style={{ color, borderColor: color }}>
                {speakerLabel}
              </span>
              <span className="speaker-text">{text}</span>
            </div>
          );
        }
        return (
          <div key={i} className="speaker-turn">
            <span className="speaker-text">{line.trim()}</span>
          </div>
        );
      })}
    </div>
  );
}


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

  const hasAudioFile = /\.(mp3|wav|m4a|flac|ogg|aac|amr)$/i.test(String(detail.file_name || ""));
  const sentimentLabel = String(detail.label || "neutral").toLowerCase();
  const sentimentScore = Number.isFinite(Number(detail.score)) ? Number(detail.score) : null;
  const isDiarized = (detail.content || "").match(/speaker\s*\d+\s*:/i);

  return (
    <div className="card chart-card">
      <div className="chart-header">
        <div>
          <h3>Call Analysis</h3>
          <p className="chart-subtitle">{detail.file_name}</p>
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          {isDiarized && (
            <span className="diarized-badge">🎙 Diarized</span>
          )}
          <span className={`sentiment-badge sentiment-${sentimentLabel}`}>
            {sentimentLabel.charAt(0).toUpperCase() + sentimentLabel.slice(1)}
          </span>
        </div>
      </div>

      <div className="detail-section">
        <div className="detail-grid-2">
          <div className="detail-item">
            <span className="detail-label">Sentiment Score</span>
            <p className="detail-value">{sentimentScore === null ? "-" : sentimentScore.toFixed(2)}</p>
          </div>
          <div className="detail-item">
            <span className="detail-label">Intent Category</span>
            <p className="detail-value">{detail.intent_category || "Inquiry"}</p>
          </div>
          <div className="detail-item">
            <span className="detail-label">Summary</span>
            <p className="detail-value-text">{detail.summary || detail.explanation}</p>
          </div>
        </div>
      </div>

      {detail.kpis && (
        <>
          {/* Speaker Identification */}
          {(detail.kpis.speaker_1_role || detail.kpis.speaker_2_role) && (
            <>
              <div className="detail-divider"></div>
              <div className="detail-section">
                <h4 className="section-title">Speaker Identification</h4>
                <div className="detail-grid-3">
                  <div className="detail-item">
                    <span className="detail-label" style={{ color: SPEAKER_COLORS["speaker 1"] }}>Speaker 1 Role</span>
                    <p className="detail-value" style={{ textTransform: "capitalize" }}>
                      {detail.kpis.speaker_1_role || "unknown"}
                    </p>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label" style={{ color: SPEAKER_COLORS["speaker 2"] }}>Speaker 2 Role</span>
                    <p className="detail-value" style={{ textTransform: "capitalize" }}>
                      {detail.kpis.speaker_2_role || "unknown"}
                    </p>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">Talk Balance</span>
                    <p className="detail-value">{detail.kpis.speaker_talk_balance || "balanced"}</p>
                  </div>
                </div>
              </div>
            </>
          )}

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
        {hasAudioFile && (
          <audio
            controls
            preload="none"
            className="inline-audio-player"
            src={getCallAudioUrl(detail.transcript_id)}
          >
            Your browser does not support audio playback.
          </audio>
        )}
        {renderDiarizedTranscript(detail.content)}
      </div>
    </div>
  );
}

export default CallDetailPanel;
