import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { useHistory } from '../hooks/useHistory';
import { Panel, Stabilizing } from './shared';
import { T } from '../theme';

const SCORE_CALIBRATED_SESSIONS = 5;

function MiniTrend({ data, dataKey, name, color }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 11, color: T.inkMuted, marginBottom: 2 }}>{name}</div>
      <ResponsiveContainer width="100%" height={70}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke={T.hairline} strokeDasharray="3 3" />
          <XAxis dataKey="label" stroke={T.inkMuted} tick={{ fontFamily: T.fonts.mono, fontSize: 10 }} />
          <YAxis stroke={T.inkMuted} tick={{ fontFamily: T.fonts.mono, fontSize: 10 }} width={40} domain={['auto', 'auto']} />
          <Tooltip contentStyle={{ fontFamily: T.fonts.body, fontSize: 12 }} />
          <Line type="monotone" dataKey={dataKey} name={name} stroke={color} connectNulls={false} dot />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function SessionHistoryPanel() {
  const { status, sessions } = useHistory();

  if (status === 'loading') {
    return <Panel title="Session History">Loading…</Panel>;
  }
  if (status === 'error') {
    return <Panel title="Session History">Couldn't load session history.</Panel>;
  }

  if (sessions.length === 0) {
    return (
      <Panel title="Session History">
        <Stabilizing filled={0} total={SCORE_CALIBRATED_SESSIONS}>
          No sessions yet
        </Stabilizing>
      </Panel>
    );
  }

  const chartData = sessions.map((s, i) => ({
    label: `#${i + 1}`,
    score: s.score,
    thermal_slope: s.thermal_slope,
    sri: s.mean_sri,
  }));

  const stabilizing = sessions.length < SCORE_CALIBRATED_SESSIONS;

  return (
    <Panel title="Session History">
      {stabilizing && (
        <Stabilizing filled={sessions.length} total={SCORE_CALIBRATED_SESSIONS}>
          stabilizing
        </Stabilizing>
      )}
      <MiniTrend data={chartData} dataKey="score" name="Readiness Score" color={T.kelp} />
      <MiniTrend data={chartData} dataKey="thermal_slope" name="Thermal Slope (°C/s)" color={T.heat} />
      <MiniTrend data={chartData} dataKey="sri" name="Mean SRI (%RH/s)" color={T.hydration} />
    </Panel>
  );
}