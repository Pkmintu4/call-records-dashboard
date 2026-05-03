import React, { useEffect, useState } from "react";
import { getHumanReviewQueue, submitHumanReview } from "../lib/api";

export default function HumanTranscriptReview() {
  const [queue, setQueue] = useState([]);
  const [selected, setSelected] = useState(null);
  const [feedback, setFeedback] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const loadQueue = async () => {
    const rows = await getHumanReviewQueue();
    setQueue(Array.isArray(rows) ? rows : []);
  };

  useEffect(() => {
    loadQueue().catch((err) => setError(err.message || "Failed to load review queue."));
  }, [status]);

  const handleSelect = (item) => {
    setSelected(item);
    setFeedback("");
    setStatus("");
  };

  const handleSubmit = async () => {
    if (!selected || !feedback || !reviewer) return;
    setError("");
    try {
      await submitHumanReview(selected.id, { reviewer, feedback });
      setStatus("Submitted!");
      setSelected(null);
      setFeedback("");
      setReviewer("");
      await loadQueue();
    } catch (err) {
      setError(err.message || "Failed to submit review.");
    }
  };

  return (
    <div style={{ padding: 24 }}>
      <h2>Human Transcript Review</h2>
      {error && <div style={{ color: "crimson", marginBottom: 8 }}>{error}</div>}
      {selected ? (
        <div>
          <h3>Transcript #{selected.id}</h3>
          <pre style={{ background: "#f5f5f5", padding: 12 }}>{selected.text}</pre>
          <input
            placeholder="Your name"
            value={reviewer}
            onChange={(e) => setReviewer(e.target.value)}
            style={{ marginBottom: 8, width: 200 }}
          />
          <br />
          <textarea
            placeholder="Enter your feedback here..."
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            rows={5}
            style={{ width: 400, marginBottom: 8 }}
          />
          <br />
          <button onClick={handleSubmit} disabled={!feedback || !reviewer}>
            Submit Review
          </button>
          <button onClick={() => setSelected(null)} style={{ marginLeft: 8 }}>
            Cancel
          </button>
          {status && <div style={{ color: "green", marginTop: 8 }}>{status}</div>}
        </div>
      ) : (
        <div>
          <h4>Transcripts needing review:</h4>
          <ul>
            {queue.length === 0 && <li>No transcripts pending review.</li>}
            {queue.map((item) => (
              <li key={item.id}>
                Transcript #{item.id} - Language: {item.language || "?"}
                <button style={{ marginLeft: 8 }} onClick={() => handleSelect(item)}>
                  Review
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
