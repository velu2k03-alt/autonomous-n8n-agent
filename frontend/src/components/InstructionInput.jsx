import { useState } from "react"

const EXAMPLES = [
  "list all workflows in n8n",
  "show me all failed executions",
  "create a webhook workflow that responds with hello world",
  "activate the HTTP Health Check workflow",
]

export default function InstructionInput({ onSubmit, loading }) {
  const [value, setValue] = useState("")
  return (
    <div style={{ marginBottom: 24 }}>
      <h2 style={{ marginBottom: 8, color: "#e2e8f0" }}>Instruction</h2>
      <textarea
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={e => { if (e.key === "Enter" && e.ctrlKey) onSubmit(value) }}
        placeholder="Type a natural language instruction... (Ctrl+Enter to run)"
        style={{
          width: "100%", minHeight: 80, padding: 12, fontSize: 15,
          borderRadius: 8, border: "1px solid #374151",
          background: "#1f2937", color: "#f9fafb", resize: "vertical",
          boxSizing: "border-box", outline: "none",
        }}
      />
      <div style={{ marginTop: 8 }}>
        <span style={{ color: "#6b7280", fontSize: 12 }}>Quick examples: </span>
        {EXAMPLES.map(ex => (
          <button key={ex} onClick={() => setValue(ex)}
            style={{
              margin: "2px 4px", padding: "3px 8px", fontSize: 11,
              borderRadius: 4, cursor: "pointer",
              background: "#374151", color: "#9ca3af", border: "1px solid #4b5563",
            }}>
            {ex}
          </button>
        ))}
      </div>
      <button onClick={() => onSubmit(value)} disabled={loading || !value.trim()}
        style={{
          marginTop: 12, padding: "10px 28px", fontSize: 15, borderRadius: 8,
          background: loading ? "#374151" : "#4f46e5", color: "#fff",
          border: "none", cursor: loading ? "not-allowed" : "pointer", fontWeight: 600,
        }}>
        {loading ? "Agent running..." : "Run Agent"}
      </button>
    </div>
  )
}