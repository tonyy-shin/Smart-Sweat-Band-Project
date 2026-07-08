import { T, scoreColor } from '../theme';
import { Panel, StatTile } from './shared';
import { useSamples } from '../hooks/useSamples';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';

// Mirrors SRI_FULL_STRESS in scoring.py: the mean SRI that maps to a
// zero readiness sub-score. Lets us show what the number MEANS instead
// of a bare %RH/s figure.
const SRI_FULL_STRESS = 0.1;

const fmt = (v) => (v == null ? '—' : v.toFixed(2));

// Real chamber-humidity-over-time curve, sourced from GET /results/samples.
// Shows the source signal SRI is derived from (numpy.gradient of this
// exact curve), rather than re-deriving the gradient client-side.
function HumidityTrend({ samples }) {
  if (samples.length < 2) return null;
  const t0 = samples[0].timestamp_ms;
  const chartData = samples.map((s) => ({
    t: ((s.timestamp_ms - t0) / 1000).toFixed(0),
    humidity_pct: s.humidity_pct,
  }));

  return (
    <div>
      <ResponsiveContainer width="100%" height={90}>
        <LineChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke={T.hairline} strokeDasharray="3 3" />
          <XAxis dataKey="t" stroke={T.inkMuted} tick={{ fontFamily: T.fonts.mono, fontSize: 10 }}
                 label={{ value: 's', position: 'insideBottomRight', fontSize: 10, fill: T.inkMuted }} />
          <YAxis stroke={T.inkMuted} tick={{ fontFamily: T.fonts.mono, fontSize: 10 }}
                 width={36} domain={['auto', 'auto']} />
          <Tooltip contentStyle={{ fontFamily: T.fonts.body, fontSize: 12 }} />
          <Line type="monotone" dataKey="humidity_pct" name="Chamber Humidity %"
                stroke={T.hydration} dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// Sweat-stress meter: how far the session's mean SRI ran toward the
// backend's full-stress threshold. Same color mapping as the readiness
// gauge (via scoreColor), so "orange here" and "orange there" agree.
function StressMeter({ mean }) {
  const frac = Math.max(0, Math.min(mean / SRI_FULL_STRESS, 1));
  const color = scoreColor(100 * (1 - frac));

  return (
    <div style={{ maxWidth: 320 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between',
                    fontSize: 12, marginBottom: 4 }}>
        <span style={{ color: T.inkMuted }}>sweat stress</span>
        <span style={{ fontFamily: T.fonts.mono, fontWeight: 600, color: T.ink }}>
          {Math.round(frac * 100)}%
        </span>
      </div>
      <div style={{ height: 10, borderRadius: 5, background: T.hairline }}>
        <div style={{ width: `${frac * 100}%`, height: '100%',
                      borderRadius: 5, background: color }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4,
                    fontFamily: T.fonts.mono, fontSize: 10, color: T.inkMuted }}>
        <span>0</span>
        <span>full stress ({SRI_FULL_STRESS})</span>
      </div>
      <p style={{ margin: '8px 0 0', fontSize: 12, color: T.inkMuted, lineHeight: 1.5 }}>
        how hard the sweat response ran this session, on the same scale the
        readiness score uses — 100% zeroes the sweat-rate sub-score
      </p>
    </div>
  );
}

export default function SweatRatePanel({ data }) {
  const { mean_sri, peak_sri, sample_count } = data;
  const { status: samplesStatus, samples } = useSamples();

  return (
    <Panel title="Sweat rate index" accent={T.hydration}>
      {/* space-between across full height, matching RehydrationPanel */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column',
                    justifyContent: 'space-between', gap: 12 }}>
        <div style={{ display: 'flex', gap: 32 }}>
          <StatTile label="Mean SRI" value={fmt(mean_sri)} unit="%RH/s" />
          <StatTile label="Peak SRI" value={fmt(peak_sri)} unit="%RH/s" />
        </div>

        {samplesStatus === 'ready' && <HumidityTrend samples={samples} />}

        {mean_sri != null ? (
          <StressMeter mean={mean_sri} />
        ) : (
          <p style={{ margin: 0, fontSize: 13, color: T.inkMuted }}>
            Not enough samples this session for a rate.
          </p>
        )}

        <div style={{ fontSize: 12, color: T.inkMuted }}>{sample_count} samples</div>
      </div>
    </Panel>
  );
}