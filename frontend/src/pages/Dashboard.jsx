import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import CallDetailPanel from "../components/CallDetailPanel";
import CallSentimentTable from "../components/CallSentimentTable";
import SentimentDistributionChart from "../components/SentimentDistributionChart";
import SentimentTrendChart from "../components/SentimentTrendChart";
import { getCallDetail, getCalls, getDistribution, getOverallKpiTrend, getOverallKpis, getTrend, ingestNow } from "../lib/api";

function Dashboard() {
  const [trend, setTrend] = useState([]);
  const [distribution, setDistribution] = useState([]);
  const [calls, setCalls] = useState([]);
  const [overallKpis, setOverallKpis] = useState(null);
  const [overallKpiTrend, setOverallKpiTrend] = useState([]);
  const [selectedCall, setSelectedCall] = useState(null);
  const [folderInput, setFolderInput] = useState("/content/drive/MyDrive/Cube ACR/outputss");
  const [limitInput, setLimitInput] = useState(30);
  const [loadingIngest, setLoadingIngest] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const loadAll = async () => {
    const [trendData, distributionData, callsData, overallData, overallTrendData] = await Promise.all([
      getTrend(),
      getDistribution(),
      getCalls(),
      getOverallKpis(),
      getOverallKpiTrend(),
    ]);
    setTrend(trendData);
    setDistribution(distributionData);
    setCalls(callsData);
    setOverallKpis(overallData);
    setOverallKpiTrend(overallTrendData);
  };

  useEffect(() => {
    const savedFolder = localStorage.getItem("driveFolderInput");
    const savedLimit = localStorage.getItem("driveBatchLimit");
    if (savedFolder) {
      setFolderInput(savedFolder);
    }
    if (savedLimit && !Number.isNaN(Number(savedLimit))) {
      setLimitInput(Number(savedLimit));
    }

    loadAll().catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    localStorage.setItem("driveFolderInput", folderInput);
  }, [folderInput]);

  useEffect(() => {
    localStorage.setItem("driveBatchLimit", String(limitInput));
  }, [limitInput]);

  const runIngest = async (modeLabel) => {
    setError("");
    setStatus("");
    setLoadingIngest(true);
    try {
      const result = await ingestNow({ folder: folderInput, limit: Number(limitInput) || undefined });
      setStatus(
        `${modeLabel}: processed ${result.processed}, attempted ${result.attempted}, skipped ${result.skipped}, ` +
          `too short ${result.skipped_too_short}, folder ${result.folder_id || "env default"}.`
      );
      await loadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingIngest(false);
    }
  };

  const handleIngest = async () => {
    await runIngest("Fetch from Drive");
  };

  const handleNextBatch = async () => {
    await runIngest("Next batch");
  };

  const handleSelectCall = async (id) => {
    setError("");
    try {
      const detail = await getCallDetail(id);
      setSelectedCall(detail);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="container">
      <div className="header">
        <h1 className="title">Call Recordings Sentiment Dashboard</h1>
        <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" }}>
          <input
            style={{ minWidth: "340px", padding: "8px", borderRadius: "8px", border: "1px solid #d1d5db" }}
            value={folderInput}
            onChange={(event) => setFolderInput(event.target.value)}
            placeholder="Drive folder URL, ID, or /content/drive/MyDrive/... path"
          />
          <input
            type="number"
            min={1}
            max={500}
            style={{ width: "90px", padding: "8px", borderRadius: "8px", border: "1px solid #d1d5db" }}
            value={limitInput}
            onChange={(event) => setLimitInput(event.target.value)}
            title="Batch size"
          />
          <button className="button" onClick={handleIngest} disabled={loadingIngest}>
            {loadingIngest ? "Fetching..." : "Fetch from Drive"}
          </button>
          <button className="button" onClick={handleNextBatch} disabled={loadingIngest}>
            {loadingIngest ? "Running..." : "Run Next Batch"}
          </button>
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      {status && <div className="status">{status}</div>}

      {overallKpis && (
        <div className="kpi-grid">
          <div className="card">
            <h3>Parent Psychology Segmentation</h3>
            <p className="meta"><strong>Total Calls:</strong> {overallKpis.total_calls}</p>
            <p className="meta">
              {(overallKpis.parent_psychology_segments || [])
                .slice(0, 4)
                .map((item) => `${item.key}: ${item.count}`)
                .join(" | ") || "No data"}
            </p>
          </div>
          <div className="card">
            <h3>Competitor Intelligence</h3>
            <p className="meta">
              {(overallKpis.competitor_intelligence || [])
                .slice(0, 5)
                .map((item) => `${item.key} (${item.count})`)
                .join(", ") || "No competitors mentioned"}
            </p>
          </div>
          <div className="card">
            <h3>Admission & Conversion Prediction</h3>
            <p className="meta"><strong>Avg Admission Probability:</strong> {overallKpis.avg_admission_probability}%</p>
            <p className="meta">
              <strong>Conversion Buckets:</strong> High {overallKpis.conversion_prediction?.high || 0} | Medium {overallKpis.conversion_prediction?.medium || 0} | Low {overallKpis.conversion_prediction?.low || 0}
            </p>
          </div>
          <div className="card">
            <h3>Staff Performance Scoring</h3>
            <p className="meta"><strong>Persuasion:</strong> {overallKpis.staff_performance?.persuasion || 0}/5</p>
            <p className="meta"><strong>Response Clarity:</strong> {overallKpis.staff_performance?.response_clarity || 0}/5</p>
            <p className="meta"><strong>Politeness:</strong> {overallKpis.staff_performance?.politeness || 0}/5</p>
          </div>
          <div className="card">
            <h3>Admission Probability Trend</h3>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={overallKpiTrend} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="day" />
                <YAxis domain={[0, 100]} />
                <Tooltip />
                <Line type="monotone" dataKey="avg_admission_probability" stroke="#7c3aed" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="card">
            <h3>Staff Score Trend</h3>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={overallKpiTrend} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="day" />
                <YAxis domain={[0, 5]} />
                <Tooltip />
                <Line type="monotone" dataKey="avg_persuasion" stroke="#2563eb" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="avg_clarity" stroke="#059669" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="avg_politeness" stroke="#ea580c" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div className="grid">
        <SentimentTrendChart data={trend} />
        <SentimentDistributionChart data={distribution} />
      </div>

      <div className="grid">
        <CallSentimentTable rows={calls} onSelect={handleSelectCall} />
        <CallDetailPanel detail={selectedCall} />
      </div>
    </div>
  );
}

export default Dashboard;
