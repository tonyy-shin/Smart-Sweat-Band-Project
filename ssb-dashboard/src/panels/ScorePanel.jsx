import { T, scoreColor } from '../theme';
import { Panel, Stabilizing } from './shared';

const CALIBRATED_SESSIONS = 5; // mirrors SCORE_CALIBRATED_SESSIONS in scoring.py

const R = 62;
const CIRC = 2 * Math.PI * R;

function SubScore({ label, value }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 2 }}>
        <span style={{ color: T.inkMuted }}>{label}</span>
        <span style={{ color: T.ink, fontWeight: 600 }}>{Math.round(value)}</span>
      </div>
      <div style={{ height: 6, borderRadius: 3, background: T.hairline }}>
        <div style={{
          width: `${Math.max(0, Math.min(100, value))}%`,
          height: '100%', borderRadius: 3, background: scoreColor(value),
        }} />
      </div>
    </div>
  );
}

export default function ScorePanel({ data }) {
  const { score, rehydration_score, thermal_score, sri_score,
          prior_session_count, stabilizing } = data;
  const color = scoreColor(score);

  return (
    <Panel title="Recovery readiness" accent={color}>
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        justifyContent: 'center', gap: 16,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 28, flexWrap: 'wrap' }}>
          <svg width="170" height="170" viewBox="0 0 170 170" role="img"
               aria-label={`Readiness score ${Math.round(score)} out of 100`}>
            <circle cx="85" cy="85" r={R} fill="none" stroke={T.hairline} strokeWidth="12" />
            <circle
              cx="85" cy="85" r={R} fill="none"
              stroke={color} strokeWidth="12" strokeLinecap="round"
              strokeDasharray={CIRC}
              strokeDashoffset={CIRC * (1 - Math.max(0, Math.min(100, score)) / 100)}
              transform="rotate(-90 85 85)"
            />
            <text x="85" y="94" textAnchor="middle"
                  style={{ fontFamily: T.fonts.mono, fontSize: 44, fontWeight: 600, fill: T.ink }}>
              {Math.round(score)}
            </text>
            <text x="85" y="114" textAnchor="middle"
                  style={{ fontFamily: T.fonts.mono, fontSize: 12, fill: T.inkMuted }}>
              / 100
            </text>
          </svg>

          <div style={{ flex: 1, minWidth: 180 }}>
            <SubScore label="rehydration" value={rehydration_score} />
            <SubScore label="thermal" value={thermal_score} />
            <SubScore label="sweat rate" value={sri_score} />
          </div>
        </div>

        {stabilizing && (
          <div>
            <Stabilizing filled={prior_session_count + 1} total={CALIBRATED_SESSIONS}>
              session {prior_session_count + 1} of {CALIBRATED_SESSIONS} — stabilizing
            </Stabilizing>
          </div>
        )}
      </div>
    </Panel>
  );
}
