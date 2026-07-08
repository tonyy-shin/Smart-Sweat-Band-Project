import { T } from '../theme';

// Card wrapper every panel sits in. `accent` is the panel's domain color
// (hydration/heat/etc.) shown as a small tick beside the title — identity,
// not decoration.
export function Panel({ title, accent, children }) {
  return (
    <section style={{
      background: T.surface,
      border: `1px solid ${T.border}`,
      borderRadius: 10,
      padding: 16,
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      boxShadow: '0 1px 2px rgba(15, 36, 33, 0.05)',
    }}>
      <h2 style={{
        margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 8,
        fontFamily: T.fonts.display, fontSize: 15, fontWeight: 600,
        color: T.inkSecondary, textTransform: 'uppercase', letterSpacing: '0.07em',
      }}>
        <span style={{
          width: 4, height: 14, borderRadius: 2, flexShrink: 0,
          background: accent ?? T.inkMuted,
        }} />
        {title}
      </h2>
      {children}
    </section>
  );
}

// Label-over-value stat display. Values wear the lab mono — they're sensor
// readouts, not prose.
export function StatTile({ label, value, unit, hint }) {
  return (
    <div>
      <div style={{ fontSize: 12, color: T.inkMuted }}>{label}</div>
      <div style={{ fontFamily: T.fonts.mono, fontSize: 24, fontWeight: 600, color: T.ink }}>
        {value}
        {unit && (
          <span style={{ fontSize: 12, fontWeight: 400, color: T.inkMuted, marginLeft: 4 }}>
            {unit}
          </span>
        )}
      </div>
      {hint && <div style={{ fontSize: 12, color: T.inkMuted }}>{hint}</div>}
    </div>
  );
}

// Small pill: colored dot + label + value. The dot hints state; the text
// carries the actual meaning, so nothing depends on color perception.
export function Badge({ label, value, dot = T.inkMuted }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      border: `1px solid ${T.border}`, borderRadius: 999,
      padding: '2px 10px', fontSize: 12, color: T.inkSecondary,
    }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: dot, flexShrink: 0 }} />
      {label}:&nbsp;<b style={{ color: T.ink, fontWeight: 600 }}>{value}</b>
    </span>
  );
}

// Signature element: the calibration tick-strip. One segment per session
// the baseline needs; filled segments are sessions already banked.
// Encodes prior_session_count / sessions_used — real state, not decoration.
export function Ticks({ filled, total, color = T.sodium }) {
  return (
    <span style={{ display: 'inline-flex', gap: 3 }}
          role="img" aria-label={`${filled} of ${total} sessions`}>
      {Array.from({ length: total }, (_, i) => (
        <span key={i} style={{
          width: 13, height: 6, borderRadius: 2,
          background: i < filled ? color : 'transparent',
          border: `1px solid ${i < filled ? color : T.border}`,
        }} />
      ))}
    </span>
  );
}

// The one shared "still calibrating" pattern. Pass filled/total to show the
// tick-strip; omit them where the panel doesn't know its counts.
export function Stabilizing({ filled, total, children }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 8,
      border: `1px solid ${T.border}`, borderRadius: 999,
      padding: '3px 10px', fontSize: 12, color: T.inkSecondary,
    }}>
      {total != null
        ? <Ticks filled={filled} total={total} />
        : <span style={{ width: 8, height: 8, borderRadius: '50%', background: T.sodium }} />}
      <span>{children}</span>
    </span>
  );
}
