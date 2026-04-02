import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

const COLORS = {
  positive: "#34d399",
  neutral: "#f59e0b",
  negative: "#f87171",
};

function SentimentDistributionChart({ data }) {
  const total = data.reduce((sum, item) => sum + (item.count || 0), 0);

  return (
    <div className="card chart-card">
      <div className="chart-header">
        <div>
          <h3>Sentiment Distribution</h3>
          <p className="chart-subtitle">A donut chart makes the positive, neutral, and negative split easy to compare.</p>
        </div>
        <span className="card-pill">{total} calls</span>
      </div>
      <div className="donut-wrap">
        <ResponsiveContainer width="100%" height={240}>
          <PieChart>
            <Pie data={data} dataKey="count" nameKey="label" innerRadius={72} outerRadius={96} paddingAngle={3}>
            {data.map((item) => (
              <Cell key={item.label} fill={COLORS[item.label] || "#2563eb"} />
            ))}
            </Pie>
            <Tooltip />
          </PieChart>
        </ResponsiveContainer>
        <div className="donut-center">
          <strong>{total}</strong>
          <span>calls analysed</span>
        </div>
      </div>

      <div className="pie-legend-list">
        {data.map((item) => {
          const color = COLORS[item.label] || "#2563eb";
          const percentage = total ? ((item.count / total) * 100).toFixed(1) : "0.0";

          return (
            <div key={item.label} className="pie-legend-item">
              <span className="pie-legend-key">
                <span className="pie-legend-dot" style={{ backgroundColor: color }} />
                {item.label.charAt(0).toUpperCase() + item.label.slice(1)}
              </span>
              <span className="pie-legend-value">{item.count} ({percentage}%)</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default SentimentDistributionChart;
