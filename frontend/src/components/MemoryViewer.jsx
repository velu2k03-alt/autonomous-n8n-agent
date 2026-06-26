export default function MemoryViewer({ memory, onClearMemory }) {
  if (!memory) return null
  const { execution_memory: em, capability_memory: cm } = memory
  return (
    <div style={{ background: "#111827", border: "1px solid #374151", borderRadius: 8, padding: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h3 style={{ margin: 0, color: "#e2e8f0" }}>Memory State</h3>
        <button onClick={onClearMemory} style={{
          background: "#7f1d1d", color: "#fca5a5", border: "1px solid #991b1b",
          padding: "5px 10px", borderRadius: 6, cursor: "pointer", fontSize: 11, fontWeight: "600",
          transition: "all 0.2s"
        }}
        onMouseOver={e => { e.target.style.background = "#991b1b"; e.target.style.color = "#ffffff" }}
        onMouseOut={e => { e.target.style.background = "#7f1d1d"; e.target.style.color = "#fca5a5" }}>
          Clear Memory
        </button>
      </div>
      <div style={{ marginBottom: 16 }}>
        <h4 style={{ color: "#818cf8", margin: "0 0 8px", fontSize: 13 }}>
          Execution Memory — {em?.count} records
        </h4>
        {em?.recent?.slice(0, 4).map((ex, i) => (
          <div key={i} style={{ display: "flex", gap: 8, padding: "4px 8px", background: "#1f2937",
            borderRadius: 4, marginBottom: 2, fontSize: 12, alignItems: "center" }}>
            <span style={{ color: ex.success ? "#22c55e" : "#ef4444" }}>{ex.success ? "✓" : "✗"}</span>
            <span style={{ flex: 1, color: "#9ca3af", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {ex.instruction}
            </span>
            <span style={{ color: "#6b7280" }}>{ex.total_api_calls} calls</span>
          </div>
        ))}
      </div>
      <div>
        <h4 style={{ color: "#818cf8", margin: "0 0 8px", fontSize: 13 }}>
          Capability Memory — {Object.keys(cm?.tools || {}).length} tools
        </h4>
        {Object.entries(cm?.tools || {}).slice(0, 8).map(([name, d]) => {
          const total = d.success_count + d.failure_count
          const rate = total ? Math.round(d.success_count / total * 100) : 100
          return (
            <div key={name} style={{ display: "flex", justifyContent: "space-between",
              padding: "3px 8px", background: "#1f2937", borderRadius: 4, marginBottom: 2, fontSize: 11 }}>
              <span style={{ color: d.is_synthesised ? "#f59e0b" : "#9ca3af" }}>
                {d.is_synthesised ? "⚡ " : ""}{name}
              </span>
              <span style={{ color: rate > 70 ? "#22c55e" : "#ef4444" }}>{rate}%</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}