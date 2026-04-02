import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  LabelList,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import CallDetailPanel from "../components/CallDetailPanel";
import CallSentimentTable from "../components/CallSentimentTable";
import SentimentDistributionChart from "../components/SentimentDistributionChart";
import SentimentTrendChart from "../components/SentimentTrendChart";
import { getCallDetail, getCalls, getDistribution, getGoogleAuthUrl, getOverallKpiTrend, getOverallKpis, getTrend, ingestNow, getSegmentSentimentBreakdown } from "../lib/api";

const CONVERSION_COLORS = ["#60a5fa", "#f59e0b", "#f87171"];
const PERFORMANCE_COLORS = ["#60a5fa", "#34d399", "#f59e0b"];
const SENTIMENT_STACK_COLORS = {
  positive: "#34d399",
  neutral: "#f59e0b",
  negative: "#f87171",
};
const SEGMENT_SEQUENCE = ["Cold", "Skeptical", "Exploring", "High Intent"];
const GRID_STROKE = "rgba(148, 163, 184, 0.2)";
const AXIS_TICK = { fill: "#94a3b8", fontSize: 12 };

const percentFormatter = (value) => `${Number(value).toFixed(1)}%`;

function Dashboard() {
  const [trend, setTrend] = useState([]);
  const [distribution, setDistribution] = useState([]);
  const [calls, setCalls] = useState([]);
  const [overallKpis, setOverallKpis] = useState(null);
  const [overallKpiTrend, setOverallKpiTrend] = useState([]);
  const [segmentSentimentBreakdown, setSegmentSentimentBreakdown] = useState([]);
  const [selectedCall, setSelectedCall] = useState(null);
  const [folderInput, setFolderInput] = useState("/content/drive/MyDrive/Cube ACR/outputss");
  const [limitInput, setLimitInput] = useState(30);
  const [loadingIngest, setLoadingIngest] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [googleAuthUrl, setGoogleAuthUrl] = useState("");
  const [googleAuthError, setGoogleAuthError] = useState("");

  const loadAll = async () => {
    const [trendData, distributionData, callsData, overallData, overallTrendData, segmentData] = await Promise.all([
      getTrend(),
      getDistribution(),
      getCalls(10),
      getOverallKpis(),
      getOverallKpiTrend(),
      getSegmentSentimentBreakdown(),
    ]);
    setTrend(trendData);
    setDistribution(distributionData);
    setCalls(callsData);
    setOverallKpis(overallData);
    setOverallKpiTrend(overallTrendData);
    setSegmentSentimentBreakdown(segmentData);
  };

  const loadGoogleAuthPrompt = async () => {
    try {
      const response = await getGoogleAuthUrl();
      setGoogleAuthUrl(response.auth_url || "");
      setGoogleAuthError("");
    } catch (err) {
      setGoogleAuthUrl("");
      setGoogleAuthError(err.message || "Failed to load Google auth URL");
    }
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
    loadGoogleAuthPrompt();
  }, []);

  useEffect(() => {
    localStorage.setItem("driveFolderInput", folderInput);
  }, [folderInput]);

  useEffect(() => {
    localStorage.setItem("driveBatchLimit", String(limitInput));
  }, [limitInput]);

  useEffect(() => {
    if (!googleAuthUrl || typeof window === "undefined") {
      return;
    }

    const autoAuthKey = "googleAuthAutoOpenedAt";
    const now = Date.now();
    const lastOpenedAt = Number(window.sessionStorage.getItem(autoAuthKey) || 0);

    // Avoid duplicate tabs caused by rapid remount in dev strict mode.
    if (now - lastOpenedAt < 5000) {
      return;
    }

    window.sessionStorage.setItem(autoAuthKey, String(now));
    const popup = window.open(googleAuthUrl, "_blank", "noopener,noreferrer");
    if (!popup) {
      setGoogleAuthError("Popup blocked. Click Authorize Google to complete refresh-token setup.");
    }
  }, [googleAuthUrl]);

  const runIngest = async (modeLabel) => {
    setError("");
    setStatus("");
    setLoadingIngest(true);
    try {
      const result = await ingestNow({ folder: folderInput, limit: Number(limitInput) || undefined });
      setStatus(
        `${modeLabel}: processed ${result.processed}, attempted ${result.attempted}, skipped ${result.skipped}, ` +
          `too short ${result.skipped_too_short}, non-English ${result.skipped_non_english || 0}, folder ${result.folder_id || "env default"}. Showing top 10 calls in analytics.`
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
  const highIntentLeads = parentSegments.find(seg => seg.key === "high-intent")?.count || 0;
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
  const politenessRating = overallKpis?.staff_performance?.politeness || 0;
  const avgStaffScore =
    staffPerformanceData.reduce((acc, item) => acc + item.score, 0) / (staffPerformanceData.length || 1);
  const staffScore = overallKpis?.staff_performance?.staff_score || avgStaffScore;
  const segmentLookup = new Map(segmentSentimentBreakdown.map((item) => [item.segment, item]));
  const segmentOutcomeData = SEGMENT_SEQUENCE
    .map((segment) => {
      const item = segmentLookup.get(segment);
      if (!item) {
        return null;
      }

      const positiveCount = Number(item.positive) || 0;
      const neutralCount = Number(item.neutral) || 0;
      const negativeCount = Number(item.negative) || 0;
      const total = Number(item.total) || positiveCount + neutralCount + negativeCount;
      const safeTotal = total || 1;

      return {
        segment,
        positive_pct: Number(((positiveCount / safeTotal) * 100).toFixed(1)),
        neutral_pct: Number(((neutralCount / safeTotal) * 100).toFixed(1)),
        negative_pct: Number(((negativeCount / safeTotal) * 100).toFixed(1)),
        positive_count: positiveCount,
        neutral_count: neutralCount,
        negative_count: negativeCount,
        total,
      };
    })
    .filter(Boolean);

  return (
    <div className="container dashboard-shell">
      <div className="header dashboard-header">
        <div>
          <h1 className="title">Call Recordings Sentiment Dashboard</h1>
          <p className="dashboard-intro">A clean view of what is driving admissions, staff quality, and call outcomes.</p>
        </div>
        <div className="dashboard-controls">
          <input
            className="text-input"
            value={folderInput}
            onChange={(event) => setFolderInput(event.target.value)}
            placeholder="Drive folder URL, ID, or /content/drive/MyDrive/... path"
          />
          <input
            className="number-input"
            type="number"
            min={1}
            max={500}
            value={limitInput}
            onChange={(event) => setLimitInput(event.target.value)}
            title="Batch size"
          />
          <button className="button" onClick={handleIngest} disabled={loadingIngest}>
            {loadingIngest ? "Fetching..." : "Fetch from Drive"}
          </button>
          <button className="button button-secondary" onClick={handleNextBatch} disabled={loadingIngest}>
            {loadingIngest ? "Running..." : "Run Next Batch"}
          </button>
        </div>
      </div>

      <div className="auth-notice">
        <div>
          <p className="auth-title">Google Auth Required After Run</p>
          <p className="auth-text">Run Google authorization each time you start the app to refresh Drive access before ingest.</p>
          <p className="auth-hint">The auth page auto-opens once per tab. After approval, copy refresh_token from callback and update GOOGLE_REFRESH_TOKEN in .env.</p>
        </div>
        <div className="auth-actions">
          {googleAuthUrl ? (
            <a className="button auth-button" href={googleAuthUrl} target="_blank" rel="noreferrer">
              Authorize Google
            </a>
          ) : (
            <button className="button auth-button" type="button" onClick={loadGoogleAuthPrompt}>
              Get Google Auth URL
            </button>
          )}
        </div>
      </div>

      {googleAuthError && <div className="error">{googleAuthError}</div>}
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
              <p className="kpi-label">High-Intent Leads</p>
              <p className="kpi-value">{highIntentLeads}</p>
            </div>
            <div className="card kpi-card">
              <p className="kpi-label">Politeness Rating</p>
              <p className="kpi-value kpi-value-success">{politenessRating.toFixed(1)}/5</p>
            </div>
            <div className="card kpi-card">
              <p className="kpi-label">Staff Score</p>
              <p className="kpi-value kpi-value-primary">{staffScore.toFixed(1)}/5</p>
            </div>
          </div>

          <div className="kpi-grid kpi-grid-3">
            <div className="card chart-card">
              <div className="chart-header">
                <div>
                  <h3>Parent Psychology Themes</h3>
                  <p className="chart-subtitle">Longer bars mean a theme appears more often in call notes.</p>
                </div>
                <span className="card-pill">Top 8</span>
              </div>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={parentSegments.slice(0, 8)} layout="vertical" margin={{ top: 8, right: 16, left: 24, bottom: 8 }}>
                  <CartesianGrid horizontal={false} stroke={GRID_STROKE} strokeDasharray="3 3" />
                  <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={false} tick={AXIS_TICK} />
                  <YAxis dataKey="key" type="category" width={120} tickLine={false} axisLine={false} interval={0} tick={AXIS_TICK} />
                  <Tooltip formatter={(value) => [value, "Mentions"]} />
                  <Bar dataKey="count" fill="#60a5fa" radius={[0, 12, 12, 0]} barSize={18} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="card chart-card">
              <div className="chart-header">
                <div>
                  <h3>Conversion Mix</h3>
                  <p className="chart-subtitle">The donut shows how calls split across likely conversion tiers.</p>
                </div>
                <span className="card-pill">{conversionTotal} calls</span>
              </div>
              <div className="donut-wrap">
                <ResponsiveContainer width="100%" height={250}>
                  <PieChart>
                    <Pie data={conversionData} dataKey="value" nameKey="name" innerRadius={66} outerRadius={92} paddingAngle={2}>
                      {conversionData.map((item, index) => (
                        <Cell key={item.name} fill={CONVERSION_COLORS[index % CONVERSION_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value, name) => [value, name]} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="donut-center">
                  <strong>{conversionTotal}</strong>
                  <span>calls analysed</span>
                </div>
              </div>

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

            <div className="card chart-card">
              <div className="chart-header">
                <div>
                  <h3>Staff Performance</h3>
                  <p className="chart-subtitle">Calibrated staff KPIs with added emphasis on politeness quality.</p>
                </div>
                <span className="card-pill">0-5 scale</span>
              </div>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={staffPerformanceData} layout="vertical" margin={{ top: 8, right: 24, left: 8, bottom: 8 }}>
                  <CartesianGrid horizontal={false} stroke={GRID_STROKE} strokeDasharray="3 3" />
                  <XAxis type="number" domain={[0, 5]} allowDecimals={false} tickCount={6} tickLine={false} axisLine={false} tick={AXIS_TICK} />
                  <YAxis dataKey="metric" type="category" width={110} tickLine={false} axisLine={false} tick={AXIS_TICK} />
                  <Tooltip formatter={(value) => [`${Number(value).toFixed(1)}/5`, "Score"]} />
                  <Bar dataKey="score" radius={[0, 12, 12, 0]} barSize={18}>
                    {staffPerformanceData.map((entry, index) => (
                      <Cell key={entry.metric} fill={PERFORMANCE_COLORS[index % PERFORMANCE_COLORS.length]} />
                    ))}
                    <LabelList dataKey="score" position="right" formatter={(value) => `${Number(value).toFixed(1)}`} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="kpi-grid">
            <div className="card chart-card">
              <div className="chart-header">
                <div>
                  <h3>Admission Probability Trend</h3>
                  <p className="chart-subtitle">A smoother line makes the upward movement easy to read.</p>
                </div>
              </div>
              <ResponsiveContainer width="100%" height={250}>
                <AreaChart data={overallKpiTrend} margin={{ top: 8, right: 12, left: 0, bottom: 12 }}>
                  <defs>
                    <linearGradient id="admissionFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.28} />
                      <stop offset="95%" stopColor="#60a5fa" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" />
                  <XAxis dataKey="day" tickLine={false} axisLine={false} tick={AXIS_TICK} />
                  <YAxis domain={[0, 100]} tickFormatter={(value) => `${value}%`} tickLine={false} axisLine={false} tick={AXIS_TICK} />
                  <Tooltip formatter={(value) => [percentFormatter(value), "Admission probability"]} />
                  <Area type="monotone" dataKey="avg_admission_probability" stroke="#60a5fa" strokeWidth={3} fill="url(#admissionFill)" dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="card chart-card">
              <div className="chart-header">
                <div>
                  <h3>Staff Skill Trend</h3>
                  <p className="chart-subtitle">Three lines show how the staff averages changed over time.</p>
                </div>
              </div>
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={overallKpiTrend} margin={{ top: 8, right: 12, left: 0, bottom: 12 }}>
                  <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" />
                  <XAxis dataKey="day" tickLine={false} axisLine={false} tick={AXIS_TICK} />
                  <YAxis domain={[0, 5]} tickCount={6} tickLine={false} axisLine={false} tick={AXIS_TICK} />
                  <Tooltip formatter={(value) => [`${Number(value).toFixed(2)}/5`, "Score"]} />
                  <Line type="monotone" dataKey="avg_persuasion" name="Persuasion" stroke="#60a5fa" strokeWidth={2.5} dot={false} />
                  <Line type="monotone" dataKey="avg_clarity" name="Response Clarity" stroke="#34d399" strokeWidth={2.5} dot={false} />
                  <Line type="monotone" dataKey="avg_politeness" name="Politeness" stroke="#d97706" strokeWidth={2.5} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}

      <div className="kpi-grid-single">
        <div className="card chart-card">
          <div className="chart-header">
            <div>
              <h3>Call Outcome by Segment</h3>
              <p className="chart-subtitle">100% stacked view of sentiment quality across each segment.</p>
            </div>
            <span className="card-pill">100% stacked</span>
          </div>
          {segmentOutcomeData.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={segmentOutcomeData} barCategoryGap="24%" margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                <CartesianGrid vertical={false} stroke={GRID_STROKE} strokeDasharray="3 3" />
                <XAxis dataKey="segment" tickLine={false} axisLine={false} tick={AXIS_TICK} interval={0} />
                <YAxis
                  domain={[0, 100]}
                  ticks={[0, 20, 40, 60, 80, 100]}
                  tickFormatter={(value) => `${value}%`}
                  tickLine={false}
                  axisLine={false}
                  tick={AXIS_TICK}
                />
                <Tooltip
                  cursor={{ fill: "rgba(148, 163, 184, 0.06)" }}
                  contentStyle={{
                    backgroundColor: "rgba(15, 23, 42, 0.95)",
                    border: "1px solid rgba(148, 163, 184, 0.25)",
                    borderRadius: 10,
                  }}
                  labelStyle={{ color: "#e2e8f0", fontWeight: 600 }}
                  itemStyle={{ color: "#cbd5e1" }}
                  formatter={(value, name, item) => {
                    const countBySeries = {
                      Positive: item?.payload?.positive_count ?? 0,
                      Neutral: item?.payload?.neutral_count ?? 0,
                      Negative: item?.payload?.negative_count ?? 0,
                    };
                    return [`${Number(value).toFixed(1)}% (${countBySeries[name]})`, name];
                  }}
                />
                <Legend
                  verticalAlign="top"
                  align="right"
                  iconType="circle"
                  formatter={(value) => <span style={{ color: "#cbd5e1" }}>{value}</span>}
                />
                <Bar dataKey="positive_pct" stackId="sentiment" fill={SENTIMENT_STACK_COLORS.positive} name="Positive" />
                <Bar dataKey="neutral_pct" stackId="sentiment" fill={SENTIMENT_STACK_COLORS.neutral} name="Neutral" />
                <Bar dataKey="negative_pct" stackId="sentiment" fill={SENTIMENT_STACK_COLORS.negative} name="Negative" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty-state-text">No segment data available yet. Run ingest to populate this chart.</div>
          )}
        </div>
      </div>

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
