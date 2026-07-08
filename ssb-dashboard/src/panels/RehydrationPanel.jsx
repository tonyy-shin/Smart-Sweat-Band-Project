import { T, pretty } from '../theme';
import { Panel, StatTile, Badge, Stabilizing } from './shared';

function fmtStart(startS) {
  const m = Math.floor(startS / 60);
  const s = String(Math.round(startS % 60)).padStart(2, '0');
  return `${m}:${s}`;
}

// Intake schedule as a labeled bar list — one row per window, bar width
// proportional to that window's volume. Scales from a single window (one
// wide bar) to many without changing shape. 15-min windows per api.py.
function IntakeWindows({ schedule }) {
  const maxVol = Math.max(...schedule.map((w) => w.volume_ml), 1);

  return (
    <div style={{ maxWidth: 340 }}>
      <div style={{ fontSize: 12, color: T.inkMuted, marginBottom: 8 }}>
        intake windows · 15 min each
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {schedule.map((w) => (
          <div key={w.window_index}
               style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontFamily: T.fonts.mono, fontSize: 11,
                           color: T.inkSecondary, width: 36, flexShrink: 0 }}>
              {fmtStart(w.start_s)}
            </span>
            <div style={{ flex: 1, height: 14 }}>
              <div style={{
                width: `${(w.volume_ml / maxVol) * 100}%`, height: '100%',
                background: T.hydration, borderRadius: '0 4px 4px 0',
              }} />
            </div>
            <span style={{ fontFamily: T.fonts.mono, fontSize: 11,
                           color: T.ink, whiteSpace: 'nowrap' }}>
              {Math.round(w.volume_ml)} ml · {Math.round(w.sodium_mg)} mg
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function RehydrationPanel({ data }) {
  const { total_fluid_ml, total_sodium_mg, schedule, sample_count, status,
          electrolyte_tier, calibration_state } = data;

  if (status !== 'ok') {
    return (
      <Panel title="Rehydration" accent={T.hydration}>
        <p style={{ margin: 0, color: T.inkSecondary }}>
          Not enough samples this session for a fluid prescription.
        </p>
      </Panel>
    );
  }

  return (
    <Panel title="Rehydration" accent={T.hydration}>
      {/* space-between across full height: top/middle/bottom blocks with
          equal gaps, so leftover height reads as rhythm, not dead space */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column',
                    justifyContent: 'space-between', gap: 12 }}>
      <div style={{ display: 'flex', gap: 32 }}>
        <StatTile label="Fluid to drink" value={Math.round(total_fluid_ml)} unit="ml" />
        <StatTile label="Sodium" value={Math.round(total_sodium_mg)} unit="mg" />
      </div>

      {schedule.length > 0 && <IntakeWindows schedule={schedule} />}

      {/* Calibration transparency: these read as visible metadata, never hidden. */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        {electrolyte_tier === 'insufficient_data' ? (
          <Stabilizing>electrolyte tier: stabilizing</Stabilizing>
        ) : (
          <Badge label="electrolyte tier" value={pretty(electrolyte_tier)}
                 dot={electrolyte_tier === 'high' ? T.sodium : T.inkMuted} />
        )}
        <Badge label="volume" value={pretty(calibration_state.volume)} />
        <Badge label="sodium" value={pretty(calibration_state.sodium)} />
        <span style={{ marginLeft: 'auto', fontSize: 12, color: T.inkMuted }}>
          {sample_count} samples
        </span>
      </div>
      </div>
    </Panel>
  );
}
