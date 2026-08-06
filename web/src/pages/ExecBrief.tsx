import { useEffect, useState } from 'react'
import { Band, ExecPayload, downloadReport, getExec } from '../api'

function rag4h(v: number) {
  return v >= 78 ? 'green' : v >= 72 ? 'amber' : 'red'
}

interface DataStatus {
  source?: { kind?: string; label?: string; as_of?: string }
  assumed?: string[]
  warnings?: string[]
}

// Data-provenance banner: where the numbers come from and what is still an
// assumption - the same banner the Flask surfaces show (advisory, never blocks).
function ProvenanceBanner() {
  const [status, setStatus] = useState<DataStatus | null>(null)
  useEffect(() => {
    fetch('/api/data-status')
      .then((r) => r.json())
      .then(setStatus)
      .catch(() => {})
  }, [])
  if (!status) return null
  const demo = status.source?.kind === 'demo'
  const style = {
    margin: '10px 0 0',
    padding: '8px 12px',
    borderRadius: 6,
    fontSize: 13,
    background: demo ? '#fff4e5' : '#eef6ee',
    border: demo ? '1px solid #ffb81c' : '1px solid #007f3b',
    color: demo ? '#3b3b3b' : '#212b32',
  }
  const assumed = status.assumed?.length ? ` Still assumptions: ${status.assumed.join(', ')}.` : ''
  return (
    <div role="status" aria-live="polite" style={style}>
      <b>{demo ? 'Demonstration data.' : 'Your data:'}</b>{' '}
      {demo ? (status.warnings ?? []).join(' ') : status.source?.label}
      <span style={{ color: '#b25900' }}>{assumed}</span>
    </div>
  )
}

function Tile(props: { cls: string; k: string; v: string; band?: Band | null; suffix: string }) {
  const spread = props.band ? `good week ${props.band.good}${props.suffix}, tough week ${props.band.tough}${props.suffix}` : ''
  return (
    <div className={`tile ${props.cls}`}>
      <div className="k">{props.k}</div>
      <div className="v">{props.v}</div>
      <div className="s">{spread}</div>
    </div>
  )
}

export default function ExecBrief() {
  const [data, setData] = useState<ExecPayload | null>(null)
  const [error, setError] = useState('')
  const [reportNote, setReportNote] = useState('')
  const [building, setBuilding] = useState(false)

  useEffect(() => {
    getExec().then(setData).catch((e) => setError(String(e)))
  }, [])

  if (error) return <div className="loading">Could not load the brief: {error}</div>
  if (!data)
    return (
      <div className="loading">
        <span className="spin" /> Preparing your brief...
      </div>
    )

  const s = data.standards
  const onReport = async () => {
    setBuilding(true)
    setReportNote('Building your report - this takes about a minute...')
    try {
      await downloadReport()
      setReportNote('Done - check your downloads.')
    } catch (e) {
      setReportNote(`Could not build the report: ${e}`)
    }
    setBuilding(false)
  }

  return (
    <>
      <ProvenanceBanner />
      <p className="sub">
        {data.department.name}, about {data.department.attendances_per_day} attendances a day ,{' '}
        {data.department.calibrated ? 'calibrated from your data' : 'synthetic until calibrated'}
      </p>
      <div className={`risk ${data.risk.colour}`}>
        {data.risk.label} - hospital about {data.bed_occupancy}% full
      </div>

      <div className="card">
        <h2>Standards this week</h2>
        <p className="sub">A typical week at your current set-up, with the good-week / tough-week spread.</p>
        <div className="tiles">
          <Tile cls={rag4h(s.four_hour?.typical ?? 0)} k="4-hour standard" v={`${s.four_hour?.typical ?? '-'}%`} band={s.four_hour} suffix="%" />
          <Tile cls={(s.initial_assessment?.typical ?? 0) >= 80 ? 'green' : 'amber'} k="Seen within 15 min" v={`${s.initial_assessment?.typical ?? '-'}%`} band={s.initial_assessment} suffix="%" />
          <Tile cls={(s.twelve_hour?.typical ?? 0) <= 1 ? 'green' : (s.twelve_hour?.typical ?? 0) <= 3 ? 'amber' : 'red'} k="12-hour waits" v={`${s.twelve_hour?.typical ?? '-'}%`} band={s.twelve_hour} suffix="%" />
          <Tile cls={(s.ambulance_handover?.typical ?? 0) >= 85 ? 'green' : 'amber'} k="Handover ≤ 45 min" v={`${s.ambulance_handover?.typical ?? '-'}%`} band={s.ambulance_handover} suffix="%" />
          {s.lwbs && <Tile cls={(s.lwbs.typical ?? 0) <= 5 ? 'green' : 'amber'} k="Walked out unseen" v={`${s.lwbs.typical ?? '-'}%`} band={s.lwbs} suffix="%" />}
        </div>
      </div>

      <div className="card">
        <h2>The pinch point</h2>
        <div className="drives" dangerouslySetInnerHTML={{ __html: data.bottleneck }} />
        <div className="drives action" dangerouslySetInnerHTML={{ __html: data.recommendation }} />
      </div>

      <div className="card">
        <h2>Workforce</h2>
        <p className="sub">
          Weekly pay-bill about <b>£{data.workforce.weekly_cost.toLocaleString()}</b>. {data.workforce.headline}
        </p>
        <div className="foot">
          <a href="/#workforce">Open the rota editor</a>
        </div>
      </div>

      {data.benchmark && (
        <div className="card">
          <h2>Where you sit against peers</h2>
          <p className="sub">{data.benchmark.summary}</p>
        </div>
      )}

      <div className="card invest">
        <h2>The investment case</h2>
        <p className="sub">
          {data.invest ? (
            <>
              Biggest opportunity: <b>{data.invest.label}</b> - {data.invest.benefit}{' '}
              {data.invest.finance && data.invest.finance.annual_benefit > 0 && <b>{data.invest.finance.summary}</b>}
            </>
          ) : data.gap_computed ? (
            'You have every Model ED element in place.'
          ) : (
            <>
              Open <a href="/#gaps">Model ED gaps</a> once to compute the investment case - it will then appear here and in the PDF.
            </>
          )}
        </p>
        <button onClick={onReport} disabled={building}>
          Download board report (PDF)
        </button>
        <span className="foot" style={{ marginLeft: 10 }}>
          {reportNote}
        </span>
      </div>
    </>
  )
}
