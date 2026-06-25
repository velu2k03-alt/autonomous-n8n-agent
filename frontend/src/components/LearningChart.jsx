import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from "recharts"

export default function LearningChart({ data }) {
  if (!data?.runs?.length) return (
    <div style={{ background: "#111827", border: "1px solid #374151", borderRadius: 8, padding: 20 }}>
      <h3 style={{ margin: 0, color: "#e2e8f0" }}>Learning Signal</h3>
      <p style={{ color: "#6b7280", fontSize: 13 }}>Run at least 2 instructions to see the trend.</p>
    </div>
  )
  const chartData = data.runs.map((r, i) => ({ run: `R${i + 1}`, calls: r.total_api_calls }))
  return (
    <div style={{ background: "#111827", border: "1px solid #374151", borderRadius: 8, padding: 20 }}>
      <h3 style={{ margin: "0 0 4px", color: "#e2e8f0" }}>Learning Signal — API Calls Per Run</h3>
      <p style={{ color: "#6b7280", fontSize: 12, margin: "0 0 16px" }}>
        Should decrease as agent learns optimal step sequences
      </p>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis dataKey="run" stroke="#6b7280" fontSize={11} />
          <YAxis stroke="#6b7280" fontSize={11} />
          <Tooltip contentStyle={{ background: "#1f2937", border: "1px solid #374151", color: "#f9fafb" }} />
          <Line type="monotone" dataKey="calls" stroke="#818cf8" strokeWidth={2} dot={{ fill: "#818cf8" }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}