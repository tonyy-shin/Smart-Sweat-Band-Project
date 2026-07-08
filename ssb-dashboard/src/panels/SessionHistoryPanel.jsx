import { T } from '../theme';
import { Panel, Ticks } from './shared';

// STUB — the backend only exposes the latest session (GET /results).
// Needs something like GET /history returning e.g.:
//   [{ timestamp: "2026-07-08T13:39:09", score: 63.0, stabilizing: true }, ...]
// history.py already stores per-session records in SQLite, so this is an
// endpoint away. Once it exists this becomes a readiness-over-time line.
// Deliberately no fake sparkline — an empty instrument stays honest.
export default function SessionHistoryPanel() {
  return (
    <Panel title="Session history" accent={T.inkMuted}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Ticks filled={0} total={5} color={T.inkMuted} />
        <span style={{ fontSize: 12, color: T.inkMuted }}>no endpoint yet</span>
      </div>
      <p style={{ margin: 0, color: T.inkMuted, fontSize: 13, lineHeight: 1.5 }}>
        Readiness over time will plot here once the backend exposes past
        sessions (they're already stored in SQLite).
      </p>
    </Panel>
  );
}
