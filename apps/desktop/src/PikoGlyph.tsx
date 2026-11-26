import type { AgentState } from './types';

/** Original vector companion. Visual state mirrors the actual session state. */
export default function PikoGlyph({ state = 'idle', compact = false }: { state?: AgentState; compact?: boolean }) {
  return (
    <svg className={`piko-glyph piko-glyph--${state}${compact ? ' piko-glyph--compact' : ''}`}
      viewBox="0 0 150 156" fill="none" role="img" aria-label={`Piko, ${state.replaceAll('_', ' ')}`}>
      <ellipse cx="75" cy="142" rx="44" ry="8" fill="#050402" opacity=".22" />
      <g className="glyph-body">
        <path d="M40 43C41 19 59 14 75 14c18 0 36 11 37 29 13 7 21 25 19 48-2 32-24 50-56 50-34 0-55-18-57-50-1-21 7-40 22-48Z" fill="#d7a84c" stroke="#4a3a1f" strokeWidth="2.8" />
        <path d="M44 42c7-16 17-20 32-20 16 0 29 9 33 19" stroke="#f1dcac" strokeWidth="5" strokeLinecap="round" />
        <path d="M20 82c-10 0-14 12-10 21 3 6 10 8 17 5" fill="#c6933c" stroke="#4a3a1f" strokeWidth="2.5" />
        <path d="M130 82c10 0 14 12 10 21-3 6-10 8-17 5" fill="#c6933c" stroke="#4a3a1f" strokeWidth="2.5" />
        <path d="M34 67c0-17 14-29 41-29 29 0 43 13 43 29v21c0 18-15 32-43 32-28 0-41-14-41-32V67Z" fill="#17140d" stroke="#5a4a2c" strokeWidth="2.4" />
        <path d="M40 69c4-14 15-24 35-24" stroke="#f1dcac" opacity=".2" strokeWidth="3" strokeLinecap="round" />
        <g className="glyph-eyes">
          <rect className="glyph-eye" x="49" y="73" rx="8" width="16" height="21" fill="#f3ead3" />
          <rect className="glyph-eye" x="85" y="73" rx="8" width="16" height="21" fill="#f3ead3" />
          <path className="glyph-mouth" d="M70 101c3 3 8 3 11 0" stroke="#8a5a34" strokeWidth="2.8" strokeLinecap="round" />
        </g>
        <path d="M51 134c-1 8-3 11-11 11M99 134c1 8 3 11 11 11" stroke="#4a3a1f" strokeWidth="6" strokeLinecap="round" />
        <circle cx="116" cy="53" r="5" fill="#8a5a34" stroke="#4a3a1f" strokeWidth="2" />
      </g>
      <g className="glyph-sparks">
        <path d="M15 41v12M9 47h12" stroke="#e8c272" strokeWidth="2" strokeLinecap="round" />
        <path d="M134 32v9M129.5 36.5h9" stroke="#e8c272" strokeWidth="2" strokeLinecap="round" />
      </g>
    </svg>
  );
}
