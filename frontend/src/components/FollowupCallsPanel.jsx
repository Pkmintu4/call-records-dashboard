import { useState } from "react";
import { resolveFollowupCall, unresolveFollowupCall } from "../lib/api";


function FollowupCallsPanel({ data, onSelectCall, onRefresh }) {
  const [showResolved, setShowResolved] = useState(false);
  const [resolving, setResolving] = useState(new Set());

  if (!data) {
    return null;
  }

  const { frequent_problems = [], followup_calls = [], total = 0 } = data;

  const handleToggleResolve = async (transcriptId, currentlyResolved) => {
    if (resolving.has(transcriptId)) {
      return;
    }

    setResolving((prev) => new Set(prev).add(transcriptId));
    try {
      if (currentlyResolved) {
        await unresolveFollowupCall(transcriptId);
      } else {
        await resolveFollowupCall(transcriptId);
      }
      if (onRefresh) {
        await onRefresh();
      }
    } catch (err) {
      console.error("Failed to toggle follow-up call resolve status:", err);
    } finally {
      setResolving((prev) => {
        const next = new Set(prev);
        next.delete(transcriptId);
        return next;
      });
    }
  };

  const unresolvedCalls = followup_calls.filter((call) => !call.resolved);
  const resolvedCalls = followup_calls.filter((call) => call.resolved);
  const unresolvedCount = unresolvedCalls.length;
  const resolvedCount = resolvedCalls.length;

  return (
    <div className="card chart-card friction-panel" id="followup-calls-panel">
      <div className="chart-header">
        <div>
          <h3>
            <span className="friction-icon">📞</span> Follow-up Needed Tracker
          </h3>
          <p className="chart-subtitle">
            Calls marked as requiring a follow-up. Check the box when the follow-up is complete.
          </p>
        </div>
        <div className="friction-header-actions">
          <span className="card-pill friction-count-pill">
            {unresolvedCount} open
          </span>
          {resolvedCount > 0 && (
            <button
              className={`friction-toggle-resolved ${showResolved ? "friction-toggle-active" : ""}`}
              onClick={() => setShowResolved(!showResolved)}
              type="button"
            >
              {showResolved ? "Hide" : "Show"} {resolvedCount} resolved
            </button>
          )}
        </div>
      </div>

      {/* Frequent Problems Section (from follow-up calls) */}
      {frequent_problems.length > 0 && (
        <div className="friction-frequent-section">
          <h4 className="friction-section-title">
            <span className="friction-fire-icon">🔥</span> Most Frequent Problems in Follow-up Calls
          </h4>
          <div className="friction-frequent-grid">
            {frequent_problems.slice(0, 8).map((problem, index) => {
              return (
                <div
                  key={`${problem.problem_text}-${index}`}
                  className="friction-frequent-card"
                >
                  <div className="friction-frequent-count">
                    <span className="friction-frequent-number">{problem.count}</span>
                    <span className="friction-frequent-label">occurrences</span>
                  </div>
                  <p className="friction-frequent-text">{problem.problem_text}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Divider */}
      <div className="detail-divider"></div>

      {/* All Follow-up Calls List */}
      <div className="friction-list-section">
        <h4 className="friction-section-title">Follow-up Needed Calls</h4>

        {unresolvedCalls.length === 0 && !showResolved && (
          <div className="friction-empty-state">
            <span className="friction-empty-icon">🎉</span>
            <p>All follow-ups have been completed!</p>
          </div>
        )}

        <div className="friction-list">
          {unresolvedCalls.map((call, index) => {
            const isToggling = resolving.has(call.transcript_id);

            return (
              <div key={`unresolved-${call.transcript_id}-${index}`} className="friction-item">
                <label className="friction-checkbox-wrap">
                  <input
                    type="checkbox"
                    checked={false}
                    disabled={isToggling}
                    onChange={() => handleToggleResolve(call.transcript_id, false)}
                    className="friction-checkbox"
                  />
                  <span className="friction-checkmark"></span>
                </label>
                <div className="friction-item-content">
                  <p className="friction-item-text">{call.summary || "No summary available"}</p>
                  <button
                    className="friction-item-source"
                    onClick={() => onSelectCall && onSelectCall(call.transcript_id)}
                    type="button"
                    title="Click to view call details"
                  >
                    📞 {call.file_name}
                  </button>
                </div>
                {isToggling && <span className="friction-spinner"></span>}
              </div>
            );
          })}

          {showResolved && resolvedCalls.length > 0 && (
            <>
              <div className="friction-resolved-divider">
                <span>Resolved ({resolvedCount})</span>
              </div>
              {resolvedCalls.map((call, index) => {
                const isToggling = resolving.has(call.transcript_id);

                return (
                  <div key={`resolved-${call.transcript_id}-${index}`} className="friction-item friction-item-resolved">
                    <label className="friction-checkbox-wrap">
                      <input
                        type="checkbox"
                        checked={true}
                        disabled={isToggling}
                        onChange={() => handleToggleResolve(call.transcript_id, true)}
                        className="friction-checkbox"
                      />
                      <span className="friction-checkmark friction-checkmark-checked"></span>
                    </label>
                    <div className="friction-item-content">
                      <p className="friction-item-text friction-item-text-resolved">{call.summary || "No summary available"}</p>
                      <button
                        className="friction-item-source"
                        onClick={() => onSelectCall && onSelectCall(call.transcript_id)}
                        type="button"
                        title="Click to view call details"
                      >
                        📞 {call.file_name}
                      </button>
                    </div>
                    {isToggling && <span className="friction-spinner"></span>}
                  </div>
                );
              })}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default FollowupCallsPanel;
