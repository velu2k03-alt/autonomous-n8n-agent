import { useState, useEffect } from "react"
import InstructionInput from "./components/InstructionInput"
import ExecutionReport from "./components/ExecutionReport"
import LearningChart from "./components/LearningChart"
import MemoryViewer from "./components/MemoryViewer"

const API = "/api"

export default function App() {
  const [loading, setLoading] = useState(false)
  const [report, setReport] = useState(null)
  const [memory, setMemory] = useState(null)
  const [learning, setLearning] = useState(null)
  const [error, setError] = useState(null)

  const loadSideData = () =>
    Promise.all([
      fetch(`${API}/memory`).then(r => r.json()).then(setMemory),
      fetch(`${API}/learning`).then(r => r.json()).then(setLearning),
    ]).catch(console.error)

  useEffect(() => { loadSideData() }, [])

  const handleSubmit = async (instruction) => {
    if (!instruction.trim()) return
    setLoading(true); setError(null); setReport(null)
    try {
      const res = await fetch(`${API}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instruction }),
      })
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail || "Agent error") }
      setReport(await res.json())
      await loadSideData()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleClearMemory = async () => {
    if (!window.confirm("Are you sure you want to clear the agent's memory? This will reset all learned strategies, execution counts, and synthesised tools.")) return
    try {
      const res = await fetch(`${API}/memory`, { method: "DELETE" })
      if (!res.ok) throw new Error("Failed to clear memory")
      setReport(null)
      await loadSideData()
    } catch (e) {
      alert("Error clearing memory: " + e.message)
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: "#0f172a", color: "#f9fafb",
      fontFamily: "system-ui, -apple-system, sans-serif", padding: "32px 24px" }}>
      <div style={{ maxWidth: 920, margin: "0 auto" }}>
        <h1 style={{ margin: "0 0 4px", fontSize: 24 }}>n8n Platform Intelligence Agent</h1>
        <p style={{ color: "#6b7280", marginBottom: 32, fontSize: 14 }}>
          Autonomous agent that manages n8n workflows via natural language
        </p>
        <InstructionInput onSubmit={handleSubmit} loading={loading} />
        {error && (
          <div style={{ padding: 14, marginBottom: 24, background: "#450a0a",
            borderRadius: 8, color: "#fca5a5", fontSize: 14 }}>
            Error: {error}
          </div>
        )}
        <ExecutionReport report={report} />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
          <LearningChart data={learning} />
          <MemoryViewer memory={memory} onClearMemory={handleClearMemory} />
        </div>
      </div>
    </div>
  )
}