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

      {/* Add a BEFORE / AFTER section to show API call reduction */}
      {data?.runs?.length >= 2 && (() => {
        const first = data.runs[0]
        const last = data.runs[data.runs.length - 1]
        const improved = last.total_api_calls < first.total_api_calls
        const pct = first.total_api_calls > 0
          ? Math.round((first.total_api_calls - last.total_api_calls) / first.total_api_calls * 100)
          : 0
        return (
          <div style={{
            marginTop: 16, padding: 12,
            background: improved ? "#064e3b" : "#1f2937",
            borderRadius: 6, display: "flex",
            justifyContent: "space-around", alignItems: "center"
          }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 28, fontWeight: "bold", color: "#ef4444" }}>
                {first.total_api_calls}
              </div>
              <div style={{ fontSize: 11, color: "#9ca3af" }}>calls — Run 1</div>
            </div>
            <div style={{ color: "#6b7280", fontSize: 20 }}>→</div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 28, fontWeight: "bold", color: "#22c55e" }}>
                {last.total_api_calls}
              </div>
              <div style={{ fontSize: 11, color: "#9ca3af" }}>calls — Run {data.runs.length}</div>
            </div>
            {improved && (
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: 24, fontWeight: "bold", color: "#818cf8" }}>
                  -{pct}%
                </div>
                <div style={{ fontSize: 11, color: "#9ca3af" }}>improvement</div>
              </div>
            )}
          </div>
        )
      })()}
    </div>
  )
}