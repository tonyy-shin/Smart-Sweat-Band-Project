import { T } from '../theme';
import { Panel, StatTile, Badge, Stabilizing } from './shared';

// NOTE: a full skin-temp time-series chart still needs a raw-samples endpoint
// (GET /results has no per-sample data). The slope vector below only uses
// current_slope / baseline_slope, which ARE in the response.

const BASELINE_SESSIONS = 3; // mirrors MIN_BASELINE_SESSIONS in thermal.py

const RECOMMENDATION = {
  active_cooling: { text: 'apply active cooling (ice / shade)', dot: T.heat },
  passive_rest: { text: 'passive rest is sufficient', dot: T.kelp },
  insufficient_data: { text: 'insufficient data', dot: T.inkMuted },
};

// Slope vector: projects skin-temp change over the next 5 min at each slope.
// Down = cooling (good, hydration teal), up = warming (heat orange).
// The drawn angle is clamped to ±2.5 °C so extreme slopes can't leave the
// box; the mono label always shows the real (unclamped) projection.
function SlopeViz({ currentSlope, baselineSlope }) {
  const W = 240, H = 96, x0 = 12, x1 = W - 64, yMid = H / 2;
  const PROJECT_S = 300; // 5 minutes
  const PX_PER_C = 14;
  const yEnd = (slope) =>
    yMid - Math.max(-2.5, Math.min(2.5, slope * PROJECT_S)) * PX_PER_C;
  const cur = yEnd(currentSlope);
  const color = currentSlope > 0 ? T.heat : T.hydration;
  const deltaC = (currentSlope * PROJECT_S).toFixed(1);

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} role="img"
         aria-label={`Projected skin temperature change ${deltaC} degrees over 5 minutes`}
         style={{ maxWidth: 320, display: 'block' }}>
      {/* no-change reference */}
      <line x1={x0} y1={yMid} x2={x1} y2={yMid} stroke={T.hairline} strokeWidth="1" />
      {baselineSlope != null && (
        <line x1={x0} y1={yMid} x2={x1} y2={yEnd(baselineSlope)}
              stroke={T.inkMuted} strokeWidth="2" strokeDasharray="4 4" opacity="0.7" />
      )}
      <line x1={x0} y1={yMid} x2={x1} y2={cur}
            stroke={color} strokeWidth="2.5" strokeLinecap="round" />
      <circle cx={x1} cy={cur} r="4" fill={color} stroke={T.surface} strokeWidth="2" />
      <text x={x1 + 8} y={cur + 4} fontSize="11" fontFamily={T.fonts.mono} fill={T.ink}>
        {deltaC}°C
      </text>
      <text x={x0} y={H - 4} fontSize="9" fill={T.inkMuted}>now</text>
      <text x={x1} y={H - 4} fontSize="9" fill={T.inkMuted} textAnchor="end">+5 min</text>
    </svg>
  );
}

export default function ThermalPanel({ data }) {
  const { current_slope, baseline_slope, sessions_used,
          recommendation, insufficient_baseline } = data;
  const rec = RECOMMENDATION[recommendation] ?? RECOMMENDATION.insufficient_data;

  return (
    <Panel title="Thermal recovery" accent={T.heat}>
      <div style={{ marginBottom: 8 }}>
        <StatTile
          label="Skin temp slope"
          value={current_slope == null ? '—' : (current_slope * 60).toFixed(2)}
          unit={current_slope == null ? '' : '°C/min'}
        />
      </div>

      {current_slope != null && (
        <SlopeViz currentSlope={current_slope} baselineSlope={baseline_slope} />
      )}

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 'auto', paddingTop: 8 }}>
        <Badge label="recommendation" value={rec.text} dot={rec.dot} />
        {insufficient_baseline && (
          <Stabilizing filled={sessions_used} total={BASELINE_SESSIONS}>
            baseline {sessions_used} of {BASELINE_SESSIONS}
          </Stabilizing>
        )}
      </div>
    </Panel>
  );
}
