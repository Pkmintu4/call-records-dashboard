import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

const COLORS = {
  positive: "#16a34a",
  neutral: "#6b7280",
  negative: "#dc2626",
};

function SentimentDistributionChart({ data }) {
  const total = data.reduce((sum, item) => sum + (item.count || 0), 0);

  return (
    <div className="card">
      <h3>Sentiment Distribution</h3>
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie data={data} dataKey="count" nameKey="label" outerRadius={95} label>
            {data.map((item) => (
              <Cell key={item.label} fill={COLORS[item.label] || "#2563eb"} />
            ))}
          </Pie>
          <Tooltip />
        </PieChart>
      </ResponsiveContainer>

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
