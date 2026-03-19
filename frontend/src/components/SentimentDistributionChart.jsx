import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

const COLORS = {
  positive: "#16a34a",
  neutral: "#6b7280",
  negative: "#dc2626",
};

function SentimentDistributionChart({ data }) {
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
    </div>
  );
}

export default SentimentDistributionChart;
