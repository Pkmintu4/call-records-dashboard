import { useState } from "react";
import { resolveFrictionPoint, unresolveFrictionPoint } from "../lib/api";


function FrictionPointsPanel({ data, onSelectCall, onRefresh }) {
  const [showResolved, setShowResolved] = useState(false);
  const [resolving, setResolving] = useState(new Set());

  if (!data) {
    return null;
  }

  const { frequent_problems = [], friction_points = [], total = 0 } = data;

  const handleToggleResolve = async (transcriptId, frictionText, currentlyResolved) => {
    const key = `${transcriptId}::${frictionText}`;
    if (resolving.has(key)) {
      return;
    }

    setResolving((prev) => new Set(prev).add(key));
    try {
      if (currentlyResolved) {
        await unresolveFrictionPoint(transcriptId, frictionText);
      } else {
        await resolveFrictionPoint(transcriptId, frictionText);
      }
      if (onRefresh) {
        await onRefresh();
      }
    } catch (err) {
      console.error("Failed to toggle friction point resolve status:", err);
    } finally {
      setResolving((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  };

  const unresolvedPoints = friction_points.filter((fp) => !fp.resolved);
  const resolvedPoints = friction_points.filter((fp) => fp.resolved);
  const unresolvedCount = unresolvedPoints.length;
  const resolvedCount = resolvedPoints.length;

  return (
    <div className="card chart-card friction-panel" id="friction-points-panel">
      <div className="chart-header">
        <div>
          <h3>
            <span className="friction-icon">⚡</span> Friction Points Tracker
          </h3>
          <p className="chart-subtitle">
            All friction points from call recordings — resolve issues to remove them from this view.
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

      {/* Frequent Problems Section */}
      {frequent_problems.length > 0 && (
        <div className="friction-frequent-section">
          <h4 className="friction-section-title">
            <span className="friction-fire-icon">🔥</span> Most Frequent Problems
          </h4>
          <div className="friction-frequent-grid">
            {frequent_problems.slice(0, 8).map((problem, index) => {
              const allResolved = problem.resolved_count >= problem.count;
              return (
                <div
                  key={`${problem.friction_text}-${index}`}
                  className={`friction-frequent-card ${allResolved ? "friction-frequent-resolved" : ""}`}
                >
                  <div className="friction-frequent-count">
                    <span className="friction-frequent-number">{problem.count}</span>
                    <span className="friction-frequent-label">occurrences</span>
                  </div>
                  <p className="friction-frequent-text">{problem.friction_text}</p>
                  {problem.resolved_count > 0 && (
                    <span className="friction-frequent-resolved-badge">
                      ✓ {problem.resolved_count} resolved
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Divider */}
      <div className="detail-divider"></div>

      {/* All Friction Points List */}
      <div className="friction-list-section">
        <h4 className="friction-section-title">All Friction Points</h4>

        {unresolvedPoints.length === 0 && !showResolved && (
          <div className="friction-empty-state">
            <span className="friction-empty-icon">🎉</span>
            <p>All friction points have been resolved!</p>
          </div>
        )}

        <div className="friction-list">
          {unresolvedPoints.map((fp, index) => {
            const key = `${fp.transcript_id}::${fp.friction_text}`;
            const isToggling = resolving.has(key);

            return (
              <div key={`unresolved-${fp.transcript_id}-${index}`} className="friction-item">
                <label className="friction-checkbox-wrap">
                  <input
                    type="checkbox"
                    checked={false}
                    disabled={isToggling}
                    onChange={() => handleToggleResolve(fp.transcript_id, fp.friction_text, false)}
                    className="friction-checkbox"
                  />
                  <span className="friction-checkmark"></span>
                </label>
                <div className="friction-item-content">
                  <p className="friction-item-text">{fp.friction_text}</p>
                  <button
                    className="friction-item-source"
                    onClick={() => onSelectCall && onSelectCall(fp.transcript_id)}
                    type="button"
                    title="Click to view call analysis"
                  >
                    📞 {fp.file_name}
                  </button>
                </div>
                {isToggling && <span className="friction-spinner"></span>}
              </div>
            );
          })}

          {showResolved && resolvedPoints.length > 0 && (
            <>
              <div className="friction-resolved-divider">
                <span>Resolved ({resolvedCount})</span>
              </div>
              {resolvedPoints.map((fp, index) => {
                const key = `${fp.transcript_id}::${fp.friction_text}`;
                const isToggling = resolving.has(key);

                return (
                  <div key={`resolved-${fp.transcript_id}-${index}`} className="friction-item friction-item-resolved">
                    <label className="friction-checkbox-wrap">
                      <input
                        type="checkbox"
                        checked={true}
                        disabled={isToggling}
                        onChange={() => handleToggleResolve(fp.transcript_id, fp.friction_text, true)}
                        className="friction-checkbox"
                      />
                      <span className="friction-checkmark friction-checkmark-checked"></span>
                    </label>
                    <div className="friction-item-content">
                      <p className="friction-item-text friction-item-text-resolved">{fp.friction_text}</p>
                      <button
                        className="friction-item-source"
                        onClick={() => onSelectCall && onSelectCall(fp.transcript_id)}
                        type="button"
                        title="Click to view call analysis"
                      >
                        📞 {fp.file_name}
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

export default FrictionPointsPanel;
