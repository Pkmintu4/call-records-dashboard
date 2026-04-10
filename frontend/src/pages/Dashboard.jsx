import { useEffect, useRef, useState } from "react";
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
import CallsByNumberPanel from "../components/CallsByNumberPanel";
import CallSentimentTable from "../components/CallSentimentTable";
import SentimentDistributionChart from "../components/SentimentDistributionChart";
import SentimentTrendChart from "../components/SentimentTrendChart";
import TemporaryTranscriptViewer from "../components/TemporaryTranscriptViewer";
import {
  getCallDetail,
  getCallsByNumber,
  getCalls,
  getCallAudioUrl,
  getDistribution,
  getGoogleAuthUrl,
  getIngestStatus,
  getOverallKpiTrend,
  getOverallKpis,
  getSegmentSentimentBreakdown,
  getTranscriptSummaries,
  getTrend,
  ingestNow,
  getDbTables,
  getDbTableRows,
  getDbTableExportUrl,
  searchGlobal,
} from "../lib/api";

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
  const [transcriptSummaries, setTranscriptSummaries] = useState([]);
  const [callsByNumber, setCallsByNumber] = useState([]);
  const [selectedCall, setSelectedCall] = useState(null);
  const [folderInput, setFolderInput] = useState("");
  const [limitInput, setLimitInput] = useState(30);
  const [forceReprocess, setForceReprocess] = useState(false);
  const [audioOnly, setAudioOnly] = useState(true);
  const [loadingIngest, setLoadingIngest] = useState(false);
  const [ingestProgress, setIngestProgress] = useState(null);
  const [lastIngestResult, setLastIngestResult] = useState(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [googleAuthUrl, setGoogleAuthUrl] = useState("");
  const [googleAuthRequired, setGoogleAuthRequired] = useState(false);
  const [googleAuthMessage, setGoogleAuthMessage] = useState("");
  const [googleAuthError, setGoogleAuthError] = useState("");
  const [dbTables, setDbTables] = useState([]);
  const [selectedDbTable, setSelectedDbTable] = useState(null);
  const [dbTableRows, setDbTableRows] = useState([]);
  const [dbTableColumns, setDbTableColumns] = useState([]);
  const [dbTableLimit, setDbTableLimit] = useState(200);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [searchLimit, setSearchLimit] = useState(50);
  const [searchOffset, setSearchOffset] = useState(0);
  const ingestPollRef = useRef(null);

  const stopIngestPolling = () => {
    if (!ingestPollRef.current) {
      return;
    }

    window.clearInterval(ingestPollRef.current);
    ingestPollRef.current = null;
  };

  const parseApiErrorDetail = (rawMessage) => {
    const fallback = String(rawMessage || "Request failed");
    try {
      const parsed = JSON.parse(fallback);
      const detail = parsed?.detail;
      if (typeof detail === "string") {
        return { message: detail, statusPayload: null };
      }
      if (detail && typeof detail === "object") {
        return {
          message: String(detail.message || fallback),
          statusPayload: detail.status && typeof detail.status === "object" ? detail.status : null,
        };
      }
    } catch {
      // Fallback to raw text below.
    }
    return { message: fallback, statusPayload: null };
  };

  const buildIngestSummary = (modeLabel, result) => (
    `${modeLabel} (${result.audio_only ? "audio-only" : "audio+txt"}): processed ${result.processed}, reprocessed ${result.reprocessed || 0}, attempted ${result.attempted}, skipped total ${result.skipped_total ?? result.skipped}, ` +
      `duplicate ${result.skipped_duplicate || 0}, too short ${result.skipped_too_short || 0}, ` +
      `unsupported language ${result.skipped_unsupported_language || 0}, transcription errors ${result.failed_transcription || 0}, ` +
      `examined ${result.examined || 0}/${result.total_seen || 0}, folder ${result.folder_id || "env default"}. Showing top 10 calls in analytics.`
  );

  const refreshIngestStatus = async () => {
    const current = await getIngestStatus();
    setIngestProgress(current);
    if (current?.last_result && typeof current.last_result === "object") {
      setLastIngestResult(current.last_result);
    }
    const isRunning = Boolean(current?.running);
    setLoadingIngest(isRunning);
    if (!isRunning) {
      stopIngestPolling();
    }
    return current;
  };

  const startIngestPolling = () => {
    if (ingestPollRef.current || typeof window === "undefined") {
      return;
    }

    ingestPollRef.current = window.setInterval(() => {
      refreshIngestStatus().catch(() => {
        // Keep UI responsive even if one poll fails.
      });
    }, 1500);
  };

  const loadAll = async () => {
    const [trendData, distributionData, callsData, overallData, overallTrendData, segmentData, summaryRows, groupedRows, dbTableList] = await Promise.all([
      getTrend(),
      getDistribution(),
      getCalls(10),
      getOverallKpis(),
      getOverallKpiTrend(),
      getSegmentSentimentBreakdown(),
      getTranscriptSummaries(250, 0),
      getCallsByNumber(150, 25),
      getDbTables(),
    ]);
    setTrend(trendData);
    setDistribution(distributionData);
    setCalls(callsData);
    setOverallKpis(overallData);
    setOverallKpiTrend(overallTrendData);
    setSegmentSentimentBreakdown(segmentData);
    setTranscriptSummaries(summaryRows);
    setCallsByNumber(groupedRows);
    setDbTables(dbTableList.tables || []);
  };

  const loadGoogleAuthPrompt = async () => {
    try {
      const response = await getGoogleAuthUrl();
      const authUrl = response.auth_url || "";
      const requiresUserAuth = Boolean(response.requires_user_auth ?? authUrl);

      setGoogleAuthUrl(authUrl);
      setGoogleAuthRequired(requiresUserAuth);
      setGoogleAuthMessage(requiresUserAuth ? "" : (response.message || "Service-account mode active. OAuth setup is not required."));
      setGoogleAuthError("");
    } catch (err) {
      setGoogleAuthUrl("");
      setGoogleAuthRequired(false);
      setGoogleAuthMessage("");
      setGoogleAuthError(err.message || "Failed to load Google auth URL");
    }
  };

  useEffect(() => {
    const savedFolder = localStorage.getItem("driveFolderInput");
    const savedLimit = localStorage.getItem("driveBatchLimit");
    const savedForceReprocess = localStorage.getItem("driveForceReprocess");
    const savedAudioOnly = localStorage.getItem("driveAudioOnly");
    if (savedFolder) {
      const normalized = savedFolder.trim().replaceAll("\\", "/");
      // Ignore stale Colab-style defaults and rely on backend GOOGLE_DRIVE_FOLDER_ID.
      if (!normalized.startsWith("/content/drive/")) {
        setFolderInput(savedFolder);
      }
    }
    if (savedLimit && !Number.isNaN(Number(savedLimit))) {
      setLimitInput(Number(savedLimit));
    }
    if (savedForceReprocess === "true") {
      setForceReprocess(true);
    }
    if (savedAudioOnly === "false") {
      setAudioOnly(false);
    }

    loadAll().catch((err) => setError(err.message));
    loadGoogleAuthPrompt();
    refreshIngestStatus().catch(() => {
      // Ignore first-load ingest status failures.
    });
  }, []);

  const loadDbTablePreview = async (tableName) => {
    try {
      const resp = await getDbTableRows(tableName, dbTableLimit, 0);
      setSelectedDbTable(tableName);
      setDbTableColumns(resp.columns || []);
      setDbTableRows(resp.rows || []);
    } catch (err) {
      setError(err.message || "Failed to load table rows");
    }
  };

  const runGlobalSearch = async (query, limit = searchLimit, offset = 0) => {
    const normalizedQuery = String(query || "").trim();
    if (!normalizedQuery) {
      setSearchQuery("");
      setSearchResults([]);
      setSearchTotal(0);
      setSearchOffset(0);
      return;
    }

    try {
      setError("");
      setSearchQuery(normalizedQuery);
      const resp = await searchGlobal(normalizedQuery, limit, offset);
      setSearchResults(resp.rows || []);
      setSearchTotal(resp.total_rows || 0);
      setSearchLimit(resp.limit || limit);
      setSearchOffset(resp.offset || offset);
    } catch (err) {
      setError(err.message || "Search failed");
    }
  };

  useEffect(() => {
    return () => {
      stopIngestPolling();
    };
  }, []);

  useEffect(() => {
    localStorage.setItem("driveFolderInput", folderInput);
  }, [folderInput]);

  useEffect(() => {
    localStorage.setItem("driveBatchLimit", String(limitInput));
  }, [limitInput]);

  useEffect(() => {
    localStorage.setItem("driveForceReprocess", String(forceReprocess));
  }, [forceReprocess]);

  useEffect(() => {
    localStorage.setItem("driveAudioOnly", String(audioOnly));
  }, [audioOnly]);

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

  const runIngest = async (modeLabel, options = {}) => {
    setError("");
    setStatus("");
    setLoadingIngest(true);
    startIngestPolling();

    const explicitLimit = Number(options.limitOverride);
    const activeLimit = Number.isFinite(explicitLimit) && explicitLimit > 0
      ? explicitLimit
      : (Number(limitInput) || undefined);

    try {
      const result = await ingestNow({
        folder: folderInput,
        limit: activeLimit,
        forceReprocess,
        audioOnly,
      });
      setLastIngestResult(result);
      setStatus(buildIngestSummary(modeLabel, result));
      await Promise.all([loadAll(), refreshIngestStatus()]);
    } catch (err) {
      const parsed = parseApiErrorDetail(err.message);
      if (parsed.statusPayload) {
        setIngestProgress(parsed.statusPayload);
      }

      if (parsed.message.toLowerCase().includes("ingest is already running")) {
        setStatus("Ingest is already running in another request. Live processing progress is shown below.");
        await refreshIngestStatus().catch(() => {
          // Keep the conflict hint visible even if status fetch fails once.
        });
        startIngestPolling();
      } else {
        setError(parsed.message);
      }
    } finally {
      try {
        await refreshIngestStatus();
      } catch {
        setLoadingIngest(false);
        stopIngestPolling();
      }
    }
  };

  const handleIngest = async () => {
    await runIngest("Fetch from Drive");
  };

  const handleNextBatch = async () => {
    await runIngest("Next batch");
  };

  const handleSmallBatchTest = async () => {
    await runIngest("Small batch test", { limitOverride: 2 });
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

  const progress = ingestProgress?.current || {};
  const progressLimit = Number(ingestProgress?.limit || 0);
  const processedCount = Number(progress.processed || 0);
  const reprocessedCount = Number(progress.reprocessed || 0);
  const attemptedCount = Number(progress.attempted || 0);
  const examinedCount = Number(progress.examined || 0);
  const totalSeenCount = Number(progress.total_seen || 0);
  const processedTargetPct = progressLimit > 0
    ? Math.min(100, Math.round((processedCount / progressLimit) * 100))
    : 0;
  const scannedPct = totalSeenCount > 0
    ? Math.min(100, Math.round((examinedCount / totalSeenCount) * 100))
    : 0;
  const ingestModeLabel = ingestProgress?.mode === "auto" ? "Auto ingest" : "Manual ingest";
  const ingestUpdatedAt = ingestProgress?.updated_at
    ? new Date(ingestProgress.updated_at).toLocaleTimeString()
    : "";
  const progressFolder = progress.folder_id || ingestProgress?.folder || "env default";
  const searchHasResults = searchTotal > 0;
  const searchFrom = searchHasResults ? searchOffset + 1 : 0;
  const searchTo = searchHasResults ? Math.min(searchOffset + searchResults.length, searchTotal) : 0;
  const canSearchPrev = searchOffset > 0;
  const canSearchNext = (searchOffset + searchLimit) < searchTotal;
  const latestBatchResult = lastIngestResult || ingestProgress?.last_result || null;
  const latestSkippedTotal = latestBatchResult
    ? Number(latestBatchResult.skipped_total ?? latestBatchResult.skipped ?? 0)
    : 0;
  const latestBatchTranscripts = Array.isArray(latestBatchResult?.processed_records)
    ? latestBatchResult.processed_records
    : [];

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
          <button className="button button-secondary" onClick={handleSmallBatchTest} disabled={loadingIngest}>
            {loadingIngest ? "Running..." : "Test Small Batch (2)"}
          </button>
          <div
            className={`reprocess-status-badge ${forceReprocess ? "reprocess-status-on" : "reprocess-status-off"}`}
            title="Current duplicate handling mode"
          >
            Force Reprocess: {forceReprocess ? "ON" : "OFF"}
          </div>
          <div
            className={`reprocess-status-badge ${audioOnly ? "reprocess-status-on" : "reprocess-status-off"}`}
            title="Current source filter mode"
          >
            Audio Only: {audioOnly ? "ON" : "OFF"}
          </div>
          <label className="force-reprocess-toggle">
            <input
              type="checkbox"
              checked={forceReprocess}
              onChange={(event) => setForceReprocess(event.target.checked)}
              disabled={loadingIngest}
            />
            <span>Force reprocess duplicates</span>
          </label>
          <label className="force-reprocess-toggle">
            <input
              type="checkbox"
              checked={audioOnly}
              onChange={(event) => setAudioOnly(event.target.checked)}
              disabled={loadingIngest}
            />
            <span>Process only audio files</span>
          </label>
        </div>
      </div>

      {googleAuthRequired && (
        <div className="auth-notice">
          <div>
            <p className="auth-title">Google OAuth Required</p>
            <p className="auth-text">Authorize Google once to fetch a refresh token for OAuth mode.</p>
            <p className="auth-hint">If service-account credentials are configured, this prompt is skipped automatically.</p>
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
      )}

      {!googleAuthRequired && googleAuthMessage && <div className="status">{googleAuthMessage}</div>}

      {googleAuthError && <div className="error">{googleAuthError}</div>}
      {error && <div className="error">{error}</div>}
      {status && <div className="status">{status}</div>}

      {ingestProgress && (
        <div className={`ingest-progress-card ${ingestProgress.running ? "ingest-running" : "ingest-idle"}`}>
          <div className="ingest-progress-head">
            <p className="ingest-progress-title">
              {ingestProgress.running ? `${ingestModeLabel} processing in progress...` : "Ingest idle"}
            </p>
            <span className="card-pill">
              {ingestUpdatedAt ? `Updated ${ingestUpdatedAt}` : "Waiting for updates"}
            </span>
          </div>

          <div className="ingest-progress-grid">
            <div className="ingest-progress-row">
              <div className="ingest-progress-row-label">
                <span>Processed target</span>
                <strong>{processedCount}/{progressLimit > 0 ? progressLimit : "-"}</strong>
              </div>
              <div className="ingest-progress-track">
                <div className="ingest-progress-fill" style={{ width: `${processedTargetPct}%` }} />
              </div>
            </div>

            <div className="ingest-progress-row">
              <div className="ingest-progress-row-label">
                <span>Files scanned</span>
                <strong>{examinedCount}/{totalSeenCount || "-"}</strong>
              </div>
              <div className="ingest-progress-track ingest-progress-track-alt">
                <div className="ingest-progress-fill ingest-progress-fill-alt" style={{ width: `${scannedPct}%` }} />
              </div>
            </div>
          </div>

          <div className="ingest-progress-metrics">
            <span>Attempted: {attemptedCount}</span>
            <span>Reprocessed: {reprocessedCount}</span>
            <span>Duplicate: {Number(progress.skipped_duplicate || 0)}</span>
            <span>Too short: {Number(progress.skipped_too_short || 0)}</span>
            <span>Unsupported language: {Number(progress.skipped_unsupported_language || 0)}</span>
            <span>Transcription errors: {Number(progress.failed_transcription || 0)}</span>
            <span>Folder: {progressFolder}</span>
          </div>

          {ingestProgress.last_error && (
            <div className="ingest-progress-error">Last error: {ingestProgress.last_error}</div>
          )}
        </div>
      )}

      {latestBatchResult && (
        <div className="ingest-result-card">
          <div className="ingest-result-head">
            <p className="ingest-result-title">Last Batch Result</p>
            <span className="card-pill">
              {latestBatchResult.audio_only ? "audio-only" : "audio+txt"}
            </span>
          </div>

          <div className="ingest-result-grid">
            <div><span>Processed</span><strong>{Number(latestBatchResult.processed || 0)}</strong></div>
            <div><span>Reprocessed</span><strong>{Number(latestBatchResult.reprocessed || 0)}</strong></div>
            <div><span>Attempted</span><strong>{Number(latestBatchResult.attempted || 0)}</strong></div>
            <div><span>Examined</span><strong>{Number(latestBatchResult.examined || 0)}</strong></div>
            <div><span>Skipped Total</span><strong>{latestSkippedTotal}</strong></div>
            <div><span>Transcription Errors</span><strong>{Number(latestBatchResult.failed_transcription || 0)}</strong></div>
            <div><span>Skipped Too Large</span><strong>{Number(latestBatchResult.skipped_audio_too_large || 0)}</strong></div>
            <div><span>Skipped Empty</span><strong>{Number(latestBatchResult.skipped_empty || 0)}</strong></div>
          </div>

          <p className="ingest-result-footnote">
            Folder: {latestBatchResult.folder_id || "env default"}
          </p>

          <div className="batch-transcript-wrap">
            <p className="batch-transcript-title">Transcripts From This Test</p>
            {latestBatchTranscripts.length > 0 ? (
              <div className="batch-transcript-list">
                {latestBatchTranscripts.map((item) => (
                  <details key={`${item.transcript_id}-${item.file_name}`} className="batch-transcript-item">
                    <summary className="batch-transcript-summary">
                      <span className="batch-transcript-file">{item.file_name}</span>
                      <span className="batch-transcript-meta">
                        {item.source_type || "audio"} | {item.transcription_language || "unknown"}
                      </span>
                    </summary>
                    <div className="batch-transcript-body">
                      <p className="batch-transcript-intent">Summary: {item.summary || "-"}</p>
                      {item.source_type === "audio" && item.transcript_id ? (
                        <audio
                          controls
                          preload="none"
                          className="batch-audio-player"
                          src={getCallAudioUrl(item.transcript_id)}
                        >
                          Your browser does not support audio playback.
                        </audio>
                      ) : null}
                      <div className="batch-transcript-content">{item.content || "(no transcript text)"}</div>
                    </div>
                  </details>
                ))}
              </div>
            ) : (
              <p className="batch-transcript-empty">No processed transcripts returned in this run.</p>
            )}
          </div>
        </div>
      )}

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

      <div className="kpi-grid-single">
        <CallsByNumberPanel groups={callsByNumber} onSelectCall={handleSelectCall} />
      </div>

      <div className="kpi-grid-single">
        <TemporaryTranscriptViewer rows={transcriptSummaries} />
      </div>

      <div className="kpi-grid-single">
        <div className="card chart-card">
          <div className="chart-header">
            <div>
              <h3>Database Viewer</h3>
              <p className="chart-subtitle">Browse tables and download full CSV exports.</p>
            </div>
            <span className="card-pill">Read-only</span>
          </div>
          <div style={{ padding: 12 }}>
            <div style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                  <input
                    className="text-input"
                    placeholder="Search transcripts, summaries..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') runGlobalSearch(searchQuery); }}
                  />
                  <button className="button" onClick={() => runGlobalSearch(searchQuery)}>Search</button>
                  <input
                    className="number-input"
                    type="number"
                    min={1}
                    max={200}
                    value={searchLimit}
                    onChange={(e) => setSearchLimit(Math.max(1, Math.min(200, Number(e.target.value) || 50)))}
                    title="Search page size"
                  />
                  <span style={{ color: '#94a3b8' }}>{searchTotal} matches</span>
                </div>

                {searchQuery && (
                  <div style={{ border: "1px solid rgba(71, 85, 105, 0.35)", borderRadius: 10, padding: 10, marginBottom: 10 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                      <strong>Search Results</strong>
                      <span style={{ color: "#94a3b8" }}>
                        Showing {searchFrom}-{searchTo} of {searchTotal}
                      </span>
                    </div>

                    {searchResults.length === 0 ? (
                      <div className="empty-state-text">No matches found for "{searchQuery}".</div>
                    ) : (
                      <div style={{ maxHeight: 260, overflowY: "auto" }}>
                        <table className="db-preview-table">
                          <thead>
                            <tr>
                              <th>ID</th>
                              <th>File</th>
                              <th>Created</th>
                              <th>Label</th>
                              <th>Summary</th>
                              <th>Open</th>
                            </tr>
                          </thead>
                          <tbody>
                            {searchResults.map((row) => (
                              <tr key={row.transcript_id}>
                                <td>{row.transcript_id}</td>
                                <td>{row.file_name}</td>
                                <td>{new Date(row.created_at).toLocaleString()}</td>
                                <td>{row.label}</td>
                                <td>{row.summary}</td>
                                <td>
                                  <button className="button button-small" onClick={() => handleSelectCall(row.transcript_id)}>
                                    View
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                      <button
                        className="button button-small"
                        disabled={!canSearchPrev}
                        onClick={() => runGlobalSearch(searchQuery, searchLimit, Math.max(0, searchOffset - searchLimit))}
                      >
                        Previous
                      </button>
                      <button
                        className="button button-small"
                        disabled={!canSearchNext}
                        onClick={() => runGlobalSearch(searchQuery, searchLimit, searchOffset + searchLimit)}
                      >
                        Next
                      </button>
                    </div>
                  </div>
                )}

                {dbTables.length === 0 ? (
                  <div className="empty-state-text">No tables discovered yet.</div>
                ) : (
                  <div className="db-table-list">
                    {dbTables.map((tbl) => (
                      <div key={tbl.name} className="db-table-item">
                        <strong>{tbl.name}</strong>
                        <span style={{ marginLeft: 8, color: '#94a3b8' }}>{tbl.row_count} rows</span>
                        <div style={{ float: 'right' }}>
                          <button className="button button-small" onClick={() => loadDbTablePreview(tbl.name)}>View top {dbTableLimit}</button>
                          <a className="button button-small button-secondary" style={{ marginLeft: 8 }} href={getDbTableExportUrl(tbl.name)}>
                            Download CSV
                          </a>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
            </div>

            {selectedDbTable && (
              <div>
                <h4 style={{ marginTop: 8 }}>Preview: {selectedDbTable}</h4>
                <div style={{ marginBottom: 8 }}>
                  <label>Rows to fetch: </label>
                  <input type="number" min={1} max={2000} value={dbTableLimit} onChange={(e) => setDbTableLimit(Number(e.target.value) || 200)} />
                  <button className="button" style={{ marginLeft: 8 }} onClick={() => loadDbTablePreview(selectedDbTable)}>Refresh</button>
                </div>
                <div style={{ overflowX: 'auto', maxHeight: 360 }}>
                  <table className="db-preview-table">
                    <thead>
                      <tr>
                        {dbTableColumns.map((col) => (
                          <th key={col}>{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {dbTableRows.map((row, idx) => (
                        <tr key={idx}>
                          {dbTableColumns.map((col) => (
                            <td key={col}>{String(row[col] ?? '')}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
