import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

function SentimentTrendChart({ data }) {
  return (
    <div className="card">
      <h3>Sentiment Trend</h3>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 12 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="day"
            label={{ value: "Date", position: "insideBottom", offset: -8 }}
          />
          <YAxis
            domain={[-1, 1]}
            label={{ value: "Avg Sentiment Score (-1 to 1)", angle: -90, position: "insideLeft" }}
          />
          <Tooltip formatter={(value) => [Number(value).toFixed(2), "Sentiment Score"]} />
          <Legend verticalAlign="top" height={28} />
          <Line type="monotone" dataKey="avg_score" name="Avg Sentiment" stroke="#2563eb" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default SentimentTrendChart;
