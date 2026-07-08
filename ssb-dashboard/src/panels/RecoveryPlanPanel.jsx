import { useState } from 'react';
import { T } from '../theme';
import { Panel } from './shared';

// recovery_plan is one "·"-delimited string built by build_recovery_plan()
// in api.py. Rendered as a tappable checklist: purely local UI state
// (resets on refresh) — the tired-athlete equivalent of a sticky note.
export default function RecoveryPlanPanel({ data }) {
  const clauses = data.split('·').map((c) => c.trim()).filter(Boolean);
  const [done, setDone] = useState(() => new Set());

  const toggle = (i) =>
    setDone((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });

  return (
    <Panel title="Recovery plan" accent={T.kelp}>
      <ul style={{ margin: 0, padding: 0, listStyle: 'none',
                   display: 'flex', flexDirection: 'column', gap: 8 }}>
        {clauses.map((clause, i) => {
          const checked = done.has(i);
          return (
            <li key={i}>
              <button
                onClick={() => toggle(i)}
                aria-pressed={checked}
                style={{
                  display: 'flex', alignItems: 'flex-start', gap: 10, width: '100%',
                  background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                  textAlign: 'left', font: 'inherit',
                }}
              >
                <span style={{
                  width: 16, height: 16, borderRadius: 4, flexShrink: 0, marginTop: 1,
                  border: `1.5px solid ${checked ? T.kelp : T.inkMuted}`,
                  background: checked ? T.kelp : 'transparent',
                  color: T.surface, fontSize: 12, lineHeight: '14px', textAlign: 'center',
                }}>
                  {checked ? '✓' : ''}
                </span>
                <span style={{
                  fontSize: 14, lineHeight: 1.5,
                  color: checked ? T.inkMuted : T.ink,
                  textDecoration: checked ? 'line-through' : 'none',
                }}>
                  {clause}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
