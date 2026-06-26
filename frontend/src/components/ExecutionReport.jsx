const STATUS_COLOR = { success: "#22c55e", failed: "#ef4444", skipped: "#f59e0b", pending: "#6b7280" }

export default function ExecutionReport({ report }) {
  if (!report) return null

  // Helper to color confidence score
  const getConfidenceColor = (score) => {
    if (score >= 0.85) return "#22c55e"
    if (score >= 0.6) return "#f59e0b"
    return "#ef4444"
  }

  return (
    <div style={{ background: "#111827", border: "1px solid #374151", borderRadius: 8, padding: 20, marginBottom: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 style={{ margin: 0, color: "#e2e8f0" }}>Execution Report</h3>
        <div style={{ display: "flex", gap: 8 }}>
          {report.rollback_occurred && (
            <span style={{
              padding: "4px 12px", borderRadius: 4, fontSize: 13, fontWeight: 600,
              background: "#7f1d1d", color: "#fca5a5", border: "1px solid #ef4444"
            }}>
              ⎌ ROLLED BACK
            </span>
          )}
          <span style={{
            padding: "4px 12px", borderRadius: 4, fontSize: 13, fontWeight: 600,
            background: report.success ? "#064e3b" : "#7f1d1d",
            color: report.success ? "#22c55e" : "#ef4444",
          }}>
            {report.success ? "✓ SUCCESS" : "✗ FAILED"}
          </span>
        </div>
      </div>
      <p style={{ color: "#9ca3af", margin: "0 0 16px", fontSize: 14 }}>{report.instruction}</p>
      
      <div style={{ display: "flex", flexWrap: "wrap", gap: 20, marginBottom: 16 }}>
        {[
          ["API Calls", report.total_api_calls],
          ["Duration", `${report.total_duration_seconds?.toFixed(2)}s`],
          ["Steps", report.steps?.length || 0],
          ["Synthesised", report.synthesis_occurred ? "Yes ⚡" : "No"],
          ["Rollback", report.rollback_occurred ? "Triggered ⎌" : "No"],
          ["Compacted", report.compaction_occurred ? "Yes 📦" : "No"]
        ].map(([label, val]) => (
          <div key={label} style={{ textAlign: "center", minWidth: 80 }}>
            <div style={{ fontSize: 18, fontWeight: "bold", color: "#818cf8" }}>{val}</div>
            <div style={{ fontSize: 11, color: "#6b7280" }}>{label}</div>
          </div>
        ))}
      </div>

      {report.steps?.map(step => (
        <div key={step.id} style={{
          display: "flex", flexDirection: "column", gap: 4, padding: "10px 14px",
          marginBottom: 6, background: "#1f2937", borderRadius: 6,
          borderLeft: `3px solid ${STATUS_COLOR[step.status] || "#6b7280"}`,
        }}>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12 }}>
            <span style={{ color: STATUS_COLOR[step.status], fontWeight: "bold", minWidth: 64, fontSize: 11 }}>
              {step.status?.toUpperCase()}
            </span>
            <span style={{ flex: 1, color: "#d1d5db", fontSize: 13, fontWeight: 500 }}>{step.description}</span>
            
            {/* Specialist Badge */}
            {step.assigned_agent && (
              <span style={{
                background: "#312e81", color: "#c7d2fe", padding: "2px 8px",
                borderRadius: 4, fontSize: 11, fontWeight: "500"
              }}>
                🕵️‍♂️ {step.assigned_agent}
              </span>
            )}

            {/* Confidence Badge */}
            {step.confidence_score !== undefined && (
              <span style={{
                border: `1px solid ${getConfidenceColor(step.confidence_score)}`,
                color: getConfidenceColor(step.confidence_score),
                padding: "2px 6px", borderRadius: 4, fontSize: 11, fontWeight: "500",
                display: "inline-flex", alignItems: "center", gap: 4
              }} title={step.confidence_reason}>
                🎯 {Math.round(step.confidence_score * 100)}% Conf.
              </span>
            )}

            {/* Rollback Registered Badge */}
            {step.rollback_registered && (
              <span style={{
                background: "#0f172a", color: "#38bdf8", border: "1px solid #0284c7",
                padding: "2px 6px", borderRadius: 4, fontSize: 11, fontWeight: "500"
              }}>
                ⎌ Revertable
              </span>
            )}

            <span style={{ color: "#818cf8", fontSize: 11, fontFamily: "monospace" }}>{step.tool}</span>
            <span style={{ color: "#6b7280", fontSize: 11 }}>{step.duration_seconds?.toFixed(2)}s</span>
          </div>

          {/* Confidence Reason */}
          {step.confidence_reason && (
            <div style={{ fontSize: 11, color: "#9ca3af", marginLeft: 76, fontStyle: "italic" }}>
              Reason: {step.confidence_reason}
            </div>
          )}

          {step.params && Object.keys(step.params).length > 0 && (
            <div style={{ fontSize: 12, color: "#9ca3af", marginLeft: 76, fontFamily: "monospace", wordBreak: "break-all" }}>
              <span style={{ color: "#4b5563" }}>params:</span> {JSON.stringify(step.params)}
            </div>
          )}

          {/* Show actual result data — this is what proves real API calls */}
          {step.result_summary && step.status === "success" && (
            <div style={{
              marginTop: 6, marginLeft: 76,
              padding: "4px 10px", background: "#064e3b",
              borderRadius: 4, fontSize: 12, color: "#6ee7b7",
              fontFamily: "monospace", wordBreak: "break-all"
            }}>
              → {step.result_summary}
            </div>
          )}

          {/* Show error message for failed steps */}
          {step.error && step.status === "failed" && (
            <div style={{
              marginTop: 6, marginLeft: 76,
              padding: "4px 10px", background: "#450a0a",
              borderRadius: 4, fontSize: 12, color: "#fca5a5",
              fontFamily: "monospace", wordBreak: "break-all"
            }}>
              ✗ {step.error}
            </div>
          )}
        </div>
      ))}

      {/* Memory Compaction Summary */}
      {report.compaction_occurred && report.compaction_summary && (
        <div style={{
          marginTop: 12, padding: 12, background: "#1e1b4b", border: "1px solid #4338ca",
          borderRadius: 6, color: "#c7d2fe", fontSize: 13
        }}>
          <div style={{ fontWeight: "bold", marginBottom: 4 }}>📦 Episodic Memory Compaction Triggered:</div>
          <div>{report.compaction_summary}</div>
        </div>
      )}

      {/* Rollback Logs if occurred */}
      {report.rollback_occurred && report.rollback_log && report.rollback_log.length > 0 && (
        <div style={{
          marginTop: 12, padding: 12, background: "#450a0a", border: "1px solid #991b1b",
          borderRadius: 6, color: "#fca5a5", fontSize: 13
        }}>
          <div style={{ fontWeight: "bold", marginBottom: 4 }}>⎌ Rollback Compensating Log:</div>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {report.rollback_log.map((log, idx) => (
              <li key={idx}>{log}</li>
            ))}
          </ul>
        </div>
      )}

      {report.failure_reason && (
        <div style={{ marginTop: 12, padding: 10, background: "#450a0a", borderRadius: 6, color: "#fca5a5", fontSize: 13 }}>
          {report.failure_reason}
        </div>
      )}

      {report.final_result && (
        <div style={{ marginTop: 20, borderTop: "1px solid #374151", paddingTop: 16 }}>
          <h4 style={{ color: "#818cf8", margin: "0 0 8px", fontSize: 13, fontWeight: "600" }}>Final Result Output:</h4>
          <pre style={{
            background: "#1f2937", padding: 12, borderRadius: 6, fontSize: 12,
            fontFamily: "monospace", color: "#34d399", margin: 0, overflowX: "auto",
            maxHeight: 300, border: "1px solid #1f2937"
          }}>
            {typeof report.final_result === "object" ? JSON.stringify(report.final_result, null, 2) : String(report.final_result)}
          </pre>
        </div>
      )}
    </div>
  )
}