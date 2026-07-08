// Shared visual tokens — every panel imports from here, so colors are decided
// in exactly one place. Concept: "bench instrument console" — saline-tinted
// page, chalk readout cards, lab-mono numerals, calibration made visible.
export const T = {
  // Neutrals — cool mineral/saline tint, not generic gray
  page: '#eef3f1',
  surface: '#fcfcfd',
  ink: '#0f2421',          // deep water — near-black with a teal cast
  inkSecondary: '#3f524d',
  inkMuted: '#667872',
  hairline: '#dbe4e1',
  border: 'rgba(15, 36, 33, 0.12)',

  // Domain accents — validated with the dataviz palette checker on the chalk
  // surface: worst adjacent CVD ΔE 20.3, all >= 3:1 contrast, chroma floor ok.
  hydration: '#0d7f9e', // water / fluid marks
  heat: '#c9491d',      // thermal load marks
  kelp: '#0c8050',      // recovered / ready
  sodium: '#a87b23',    // electrolytes / calibration-in-progress

  // Status aliases: state semantics reuse the domain hues on purpose —
  // in this domain "critical" literally means heat. Always paired with text.
  good: '#0c8050',
  warning: '#a87b23',
  critical: '#c9491d',

  // RIT brand nod — CHROME ONLY (masthead, footer credit). Never on a data
  // mark or inside a panel: heat #c9491d must stay the only orange that can
  // mean "thermal". Brand orange always appears paired with brand brown.
  brand: {
    orange: '#f76902',
    brown: '#513127',
  },

  fonts: {
    display: "'Barlow Condensed', 'Arial Narrow', system-ui, sans-serif",
    body: "'Barlow', system-ui, -apple-system, 'Segoe UI', sans-serif",
    mono: "'IBM Plex Mono', ui-monospace, 'Cascadia Mono', monospace",
  },
};

// One shared score→color mapping so the gauge and the sub-score bars
// can never disagree about what "62" means.
export function scoreColor(score) {
  if (score >= 70) return T.good;
  if (score >= 40) return T.warning;
  return T.critical;
}

// Backend enums are snake_case ("insufficient_data") — show them as words.
export function pretty(value) {
  return String(value).replaceAll('_', ' ');
}
