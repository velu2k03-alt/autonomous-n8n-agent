const STATUS_COLOR = { success: "#22c55e", failed: "#ef4444", skipped: "#f59e0b", pending: "#6b7280" }

export default function ExecutionReport({ report }) {
  if (!report) return null
  return (
    <div style={{ background: "#111827", border: "1px solid #374151", borderRadius: 8, padding: 20, marginBottom: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 style={{ margin: 0, color: "#e2e8f0" }}>Execution Report</h3>
        <span style={{
          padding: "4px 12px", borderRadius: 4, fontSize: 13, fontWeight: 600,
          background: report.success ? "#064e3b" : "#7f1d1d",
          color: report.success ? "#22c55e" : "#ef4444",
        }}>
          {report.success ? "✓ SUCCESS" : "✗ FAILED"}
        </span>
      </div>
      <p style={{ color: "#9ca3af", margin: "0 0 16px", fontSize: 14 }}>{report.instruction}</p>
      <div style={{ display: "flex", gap: 28, marginBottom: 16 }}>
        {[["API Calls", report.total_api_calls], ["Duration", `${report.total_duration_seconds?.toFixed(2)}s`],
          ["Steps", report.steps?.length], ["Synthesised", report.synthesis_occurred ? "Yes ⚡" : "No"]
        ].map(([label, val]) => (
          <div key={label} style={{ textAlign: "center" }}>
            <div style={{ fontSize: 20, fontWeight: "bold", color: "#818cf8" }}>{val}</div>
            <div style={{ fontSize: 11, color: "#6b7280" }}>{label}</div>
          </div>
        ))}
      </div>
      {report.steps?.map(step => (
        <div key={step.id} style={{
          display: "flex", alignItems: "center", gap: 12, padding: "7px 12px",
          marginBottom: 3, background: "#1f2937", borderRadius: 6,
          borderLeft: `3px solid ${STATUS_COLOR[step.status] || "#6b7280"}`,
        }}>
          <span style={{ color: STATUS_COLOR[step.status], fontWeight: "bold", minWidth: 64, fontSize: 11 }}>
            {step.status?.toUpperCase()}
          </span>
          <span style={{ flex: 1, color: "#d1d5db", fontSize: 13 }}>{step.description}</span>
          <span style={{ color: "#6b7280", fontSize: 11 }}>{step.tool}</span>
          <span style={{ color: "#6b7280", fontSize: 11 }}>{step.duration_seconds?.toFixed(2)}s</span>
        </div>
      ))}
      {report.failure_reason && (
        <div style={{ marginTop: 12, padding: 10, background: "#450a0a", borderRadius: 6, color: "#fca5a5", fontSize: 13 }}>
          {report.failure_reason}
        </div>
      )}
    </div>
  )
}