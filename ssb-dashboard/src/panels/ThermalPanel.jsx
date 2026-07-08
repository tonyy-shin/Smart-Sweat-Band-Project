import { T } from '../theme';
import { Panel, StatTile, Badge, Stabilizing } from './shared';
import { useSamples } from '../hooks/useSamples';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';

const BASELINE_SESSIONS = 3; // mirrors MIN_BASELINE_SESSIONS in thermal.py

const RECOMMENDATION = {
  active_cooling: { text: 'apply active cooling (ice / shade)', dot: T.heat },
  passive_rest: { text: 'passive rest is sufficient', dot: T.kelp },
  insufficient_data: { text: 'insufficient data', dot: T.inkMuted },
};

// Real skin-temp-over-time curve, sourced from GET /results/samples.
function SkinTempTrend({ samples }) {
  if (samples.length < 2) return null;
  const t0 = samples[0].timestamp_ms;
  const chartData = samples.map((s) => ({
    t: ((s.timestamp_ms - t0) / 1000).toFixed(0),
    skin_temp_c: s.skin_temp_c,
  }));

  return (
    <div style={{ marginBottom: 8 }}>
      <ResponsiveContainer width="100%" height={90}>
        <LineChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke={T.hairline} strokeDasharray="3 3" />
          <XAxis dataKey="t" stroke={T.inkMuted} tick={{ fontFamily: T.fonts.mono, fontSize: 10 }}
                 label={{ value: 's', position: 'insideBottomRight', fontSize: 10, fill: T.inkMuted }} />
          <YAxis stroke={T.inkMuted} tick={{ fontFamily: T.fonts.mono, fontSize: 10 }}
                 width={36} domain={['auto', 'auto']} />
          <Tooltip contentStyle={{ fontFamily: T.fonts.body, fontSize: 12 }} />
          <Line type="monotone" dataKey="skin_temp_c" name="Skin Temp °C"
                stroke={T.heat} dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

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
  const { status: samplesStatus, samples } = useSamples();

  return (
    <Panel title="Thermal recovery" accent={T.heat}>
      <div style={{ marginBottom: 8 }}>
        <StatTile
          label="Skin temp slope"
          value={current_slope == null ? '—' : (current_slope * 60).toFixed(2)}
          unit={current_slope == null ? '' : '°C/min'}
        />
      </div>

      {samplesStatus === 'ready' && <SkinTempTrend samples={samples} />}

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