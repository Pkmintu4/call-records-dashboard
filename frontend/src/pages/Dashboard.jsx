import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Legend,
} from "recharts";

import CallDetailPanel from "../components/CallDetailPanel";
import CallSentimentTable from "../components/CallSentimentTable";
import SentimentDistributionChart from "../components/SentimentDistributionChart";
import SentimentTrendChart from "../components/SentimentTrendChart";
import { getCallDetail, getCalls, getDistribution, getOverallKpiTrend, getOverallKpis, getTrend, ingestNow } from "../lib/api";

const CONVERSION_COLORS = ["#16a34a", "#f59e0b", "#dc2626"];

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

  const parentSegments = overallKpis?.parent_psychology_segments || [];
  const competitorMentions = overallKpis?.competitor_intelligence || [];
  const conversionData = [
    { name: "High", value: overallKpis?.conversion_prediction?.high || 0 },
    { name: "Medium", value: overallKpis?.conversion_prediction?.medium || 0 },
    { name: "Low", value: overallKpis?.conversion_prediction?.low || 0 },
  ];
  const conversionTotal = conversionData.reduce((sum, item) => sum + item.value, 0);
  const staffPerformanceData = [
    { metric: "Persuasion", score: overallKpis?.staff_performance?.persuasion || 0 },
    { metric: "Clarity", score: overallKpis?.staff_performance?.response_clarity || 0 },
    { metric: "Politeness", score: overallKpis?.staff_performance?.politeness || 0 },
  ];
  const avgStaffScore =
    staffPerformanceData.reduce((acc, item) => acc + item.score, 0) / (staffPerformanceData.length || 1);
  const topCompetitor = competitorMentions[0];

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
        <>
          <div className="kpi-cards-grid">
            <div className="card kpi-card">
              <p className="kpi-label">Total Calls Analysed</p>
              <p className="kpi-value">{overallKpis.total_calls}</p>
            </div>
            <div className="card kpi-card">
              <p className="kpi-label">Avg Admission Probability</p>
              <p className="kpi-value">{overallKpis.avg_admission_probability}%</p>
            </div>
            <div className="card kpi-card">
              <p className="kpi-label">Avg Staff Performance</p>
              <p className="kpi-value">{avgStaffScore.toFixed(1)}/5</p>
            </div>
            <div className="card kpi-card">
              <p className="kpi-label">Top Mentioned Competitor</p>
              <p className="kpi-value small">{topCompetitor ? `${topCompetitor.key} (${topCompetitor.count})` : "No data"}</p>
            </div>
          </div>

          <div className="kpi-grid">
            <div className="card">
              <h3>Parent Psychology Segments</h3>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={parentSegments.slice(0, 8)} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="key" tick={{ fontSize: 11 }} interval={0} angle={-15} textAnchor="end" height={55} />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#2563eb" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="card">
              <h3>Competitor Intelligence</h3>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={competitorMentions.slice(0, 6)} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="key" tick={{ fontSize: 11 }} interval={0} angle={-15} textAnchor="end" height={55} />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#7c3aed" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="card">
              <h3>Conversion Prediction Split</h3>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie
                    data={conversionData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={52}
                    outerRadius={82}
                    paddingAngle={2}
                    label
                  >
                    {conversionData.map((item, index) => (
                      <Cell key={item.name} fill={CONVERSION_COLORS[index % CONVERSION_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>

              <div className="pie-legend-list">
                {conversionData.map((item, index) => {
                  const color = CONVERSION_COLORS[index % CONVERSION_COLORS.length];
                  const percentage = conversionTotal ? ((item.value / conversionTotal) * 100).toFixed(1) : "0.0";

                  return (
                    <div key={item.name} className="pie-legend-item">
                      <span className="pie-legend-key">
                        <span className="pie-legend-dot" style={{ backgroundColor: color }} />
                        {item.name}
                      </span>
                      <span className="pie-legend-value">{item.value} ({percentage}%)</span>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="card">
              <h3>Staff Performance Radar</h3>
              <ResponsiveContainer width="100%" height={220}>
                <RadarChart data={staffPerformanceData} outerRadius={80}>
                  <PolarGrid />
                  <PolarAngleAxis dataKey="metric" />
                  <PolarRadiusAxis domain={[0, 5]} />
                  <Radar dataKey="score" stroke="#059669" fill="#059669" fillOpacity={0.45} />
                  <Tooltip />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="kpi-grid">
          <div className="card">
            <h3>Admission Probability Trend</h3>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={overallKpiTrend} margin={{ top: 8, right: 8, left: 8, bottom: 16 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="day"
                  label={{ value: "Date", position: "insideBottom", offset: -10 }}
                />
                <YAxis
                  domain={[0, 100]}
                  label={{ value: "Admission Probability (%)", angle: -90, position: "insideLeft" }}
                />
                <Tooltip formatter={(value) => [`${Number(value).toFixed(1)}%`, "Probability"]} />
                <Legend verticalAlign="top" height={28} />
                <Line
                  type="monotone"
                  dataKey="avg_admission_probability"
                  name="Avg Admission Probability"
                  stroke="#7c3aed"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="card">
            <h3>Staff Score Trend</h3>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={overallKpiTrend} margin={{ top: 8, right: 8, left: 8, bottom: 16 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="day"
                  label={{ value: "Date", position: "insideBottom", offset: -10 }}
                />
                <YAxis
                  domain={[0, 5]}
                  label={{ value: "Score (0-5)", angle: -90, position: "insideLeft" }}
                />
                <Tooltip formatter={(value) => [`${Number(value).toFixed(2)}/5`, "Score"]} />
                <Legend verticalAlign="top" height={28} />
                <Line type="monotone" dataKey="avg_persuasion" name="Persuasion" stroke="#2563eb" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="avg_clarity" name="Response Clarity" stroke="#059669" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="avg_politeness" name="Politeness" stroke="#ea580c" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          </div>
        </>
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
