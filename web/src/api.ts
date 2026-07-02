// Typed client for the Flask API. All endpoints are same-origin.

export interface Band {
  typical: number
  good: number
  tough: number
}

export interface Standards {
  four_hour?: Band | null
  initial_assessment?: Band | null
  twelve_hour?: Band | null
  ambulance_handover?: Band | null
  lwbs?: Band | null
  attendances_per_day?: number
}

export interface Finance {
  annual_benefit: number
  annual_cost_low: number
  annual_cost_high: number
  roi: number | null
  payback_years: number | null
  summary: string
  drivers: string[]
  assumptions: string[]
}

export interface GapItem {
  key: string
  label: string
  why: string
  cost: string
  value: number
  unit: string
  benefit: string
  finance?: Finance
}

export interface BenchmarkPosition {
  n_peers: number
  n_band: number
  synthetic: boolean
  four_hour_percentile: number
  twelve_hour_percentile: number
  quartile: number
  summary: string
}

export interface ExecPayload {
  department: { name: string; attendances_per_day: number; calibrated: boolean }
  standards: Standards
  risk: { level: number; label: string; colour: 'green' | 'amber' | 'orange' | 'red' }
  bed_occupancy: number
  bottleneck: string
  recommendation: string
  workforce: { weekly_cost: number; understaffed_hours: number; headline: string }
  invest: GapItem | null
  gap_computed: boolean
  benchmark?: BenchmarkPosition | null
}

export async function getExec(): Promise<ExecPayload> {
  const r = await fetch('/api/exec')
  if (!r.ok) throw new Error(`API ${r.status}`)
  return r.json()
}

export async function downloadReport(): Promise<void> {
  const r = await fetch('/api/report')
  if (!r.ok) throw new Error(`report failed (${r.status})`)
  const blob = await r.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'decision_report.pdf'
  a.click()
  URL.revokeObjectURL(a.href)
}
