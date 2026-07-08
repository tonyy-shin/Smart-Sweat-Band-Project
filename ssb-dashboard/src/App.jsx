import { useResults } from './hooks/useResults'
import { T } from './theme'
import ScorePanel from './panels/ScorePanel'
import RehydrationPanel from './panels/RehydrationPanel'
import ThermalPanel from './panels/ThermalPanel'
import SweatRatePanel from './panels/SweatRatePanel'
import RecoveryPlanPanel from './panels/RecoveryPlanPanel'
import SessionHistoryPanel from './panels/SessionHistoryPanel'

export default function App() {
  const { status, data, reload } = useResults()

  if (status === 'loading') return <p>Loading results…</p>
  if (status === 'no-session') return <p>No session yet — process a workout session and refresh.</p>
  if (status === 'error') {
    return (
      <p>
        Could not reach the backend. Is it running on localhost:8000?{' '}
        <button onClick={reload}>Retry</button>
      </p>
    )
  }

  return (
    <main style={{ background: T.page, minHeight: '100vh', padding: 24,
                   display: 'flex', flexDirection: 'column',
                   fontFamily: T.fonts.body, color: T.ink }}>
      <header style={{ marginBottom: 16, display: 'flex', alignItems: 'baseline',
                       justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <h1 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 10,
                     fontFamily: T.fonts.display, fontSize: 26, fontWeight: 700,
                     textTransform: 'uppercase', letterSpacing: '0.04em',
                     color: T.brand.brown }}>
          {/* paired brand ticks — two colors together = brand, never a data signal */}
          <span style={{ display: 'inline-flex', gap: 3 }}>
            <span style={{ width: 5, height: 18, borderRadius: 2, background: T.brand.orange }} />
            <span style={{ width: 5, height: 18, borderRadius: 2, background: T.brand.brown }} />
          </span>
          Smart Sweat-Band
        </h1>
        <span style={{ fontFamily: T.fonts.mono, fontSize: 12, color: T.inkMuted }}>
          session {new Date(data.timestamp).toLocaleString()}
        </span>
      </header>

      <div className="dashboard">
        <div style={{ gridArea: 'score' }}><ScorePanel data={data.readiness} /></div>
        <div style={{ gridArea: 'rehydration' }}><RehydrationPanel data={data.rehydration} /></div>
        <div style={{ gridArea: 'thermal' }}><ThermalPanel data={data.thermal} /></div>
        <div style={{ gridArea: 'sweat' }}><SweatRatePanel data={data.sweat_rate} /></div>
        <div style={{ gridArea: 'plan' }}><RecoveryPlanPanel data={data.recovery_plan} /></div>
        <div style={{ gridArea: 'history' }}><SessionHistoryPanel /></div>
      </div>

      <footer style={{ marginTop: 14, display: 'flex', alignItems: 'center', gap: 8,
                       fontSize: 12, color: T.inkMuted }}>
        <span style={{ display: 'inline-flex', gap: 3 }}>
          <span style={{ width: 13, height: 6, borderRadius: 2, background: T.brand.orange }} />
          <span style={{ width: 13, height: 6, borderRadius: 2, background: T.brand.brown }} />
        </span>
        Built at RIT
      </footer>
    </main>
  )
}
