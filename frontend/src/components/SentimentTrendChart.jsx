import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const GRID_STROKE = "rgba(148, 163, 184, 0.2)";
const AXIS_TICK = { fill: "#94a3b8", fontSize: 12 };

function SentimentTrendChart({ data }) {
  return (
    <div className="card chart-card">
      <div className="chart-header">
        <div>
          <h3>Sentiment Trend</h3>
          <p className="chart-subtitle">The shaded line shows whether call mood is moving up or down over time.</p>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 12 }}>
          <defs>
            <linearGradient id="sentimentFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.28} />
              <stop offset="95%" stopColor="#60a5fa" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" />
          <XAxis dataKey="day" tickLine={false} axisLine={false} tick={AXIS_TICK} />
          <YAxis domain={[-1, 1]} tickLine={false} axisLine={false} tick={AXIS_TICK} />
          <Tooltip formatter={(value) => [Number(value).toFixed(2), "Sentiment score"]} />
          <Area type="monotone" dataKey="avg_score" stroke="#60a5fa" strokeWidth={3} fill="url(#sentimentFill)" dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export default SentimentTrendChart;
