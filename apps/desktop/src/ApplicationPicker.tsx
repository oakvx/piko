import { useEffect, useMemo, useRef, useState } from 'react';
import type { ApplicationWindow, InstalledApplication } from './types';

function clean(value: string): string {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
}

/** Conservative keyword recognition: suggestions never grant access or execute. */
export function suggestedApps(goal: string, windows: ApplicationWindow[]): string[] {
  const text = ` ${clean(goal)} `;
  const aliases: Record<string, string[]> = {
    'firefox.exe': ['firefox', 'mozilla'],
    'chrome.exe': ['chrome', 'google chrome'],
    'msedge.exe': ['microsoft edge', 'edge browser', 'edge'],
    'notepad.exe': ['blocco note', 'blocco notes', 'notepad'],
    'notepad++.exe': ['notepad++'],
    'code.exe': ['visual studio code', 'vs code', 'vscode'],
    'winword.exe': ['microsoft word', 'word'],
    'excel.exe': ['excel'],
    'powerpnt.exe': ['powerpoint'],
    'discord.exe': ['discord'],
    'spotify.exe': ['spotify'],
    'steam.exe': ['steam'],
    'mspaint.exe': ['paint'],
    'obs64.exe': ['obs studio'],
  };
  const matching = new Set<string>();
  for (const window of windows) {
    const tokens = aliases[window.executable] ?? [clean(window.display_name)];
    if (tokens.some(token => token.length > 2 && new RegExp(
      `(^|[^a-z0-9])${token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^a-z0-9]|$)`, 'i',
    ).test(text))) matching.add(window.executable);
  }
  // Never suggest one application as definitive if the goal mentions two.
  return matching.size === 1 ? [...matching] : [];
}

type Props = {
  windows: ApplicationWindow[];
  installed: InstalledApplication[];
  chosen: ApplicationWindow | null;
  goal: string;
  fetching: boolean;
  busy: boolean;
  onSelect: (window: ApplicationWindow) => void;
  onRefresh: () => void;
  onPick: () => void;
  onLaunch: (id: string) => void;
  onClose: () => void;
};

export default function ApplicationPicker({
  windows, installed, chosen, goal, fetching, busy,
  onSelect, onRefresh, onPick, onLaunch, onClose,
}: Props) {
  const [query, setQuery] = useState('');
  const [tab, setTab] = useState<'open' | 'installed'>('open');
  const [expanded, setExpanded] = useState<string | null>(null);
  const [confirmLaunch, setConfirmLaunch] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    inputRef.current?.focus();
    const onEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onEscape);
    return () => window.removeEventListener('keydown', onEscape);
  }, [onClose]);

  const suggested = useMemo(() => suggestedApps(goal, windows), [goal, windows]);
  const groups = useMemo(() => {
    const result = new Map<string, { name: string; exe: string; windows: ApplicationWindow[] }>();
    for (const win of windows) {
      if (!result.has(win.executable)) result.set(win.executable, {
        name: win.display_name, exe: win.executable, windows: [],
      });
      result.get(win.executable)?.windows.push(win);
    }
    return [...result.values()].filter(group => !query || clean(
      `${group.name} ${group.exe} ${group.windows.map(w => w.title).join(' ')}`,
    ).includes(clean(query))).sort((a, b) => {
      const recommended = Number(suggested.includes(b.exe)) - Number(suggested.includes(a.exe));
      if (recommended) return recommended;
      const focused = Number(b.windows.some(w => w.is_foreground)) -
        Number(a.windows.some(w => w.is_foreground));
      return focused || a.name.localeCompare(b.name);
    });
  }, [query, windows, suggested]);
  const installedFiltered = useMemo(() => installed.filter(app =>
    !query || clean(app.name).includes(clean(query))
  ).slice(0, 90), [query, installed]);

  return <div className="app-picker-backdrop" role="presentation" onMouseDown={event => {
    if (event.target === event.currentTarget) onClose();
  }}>
    <section className="app-picker" role="dialog" aria-modal="true" aria-labelledby="app-picker-title">
      <header className="app-picker-head">
        <div><span className="picker-kicker">PIKO / WINDOW SWITCHER</span>
          <h2 id="app-picker-title">Dove vuoi lavorare?</h2>
          <p>Seleziona un'applicazione, non un processo. Piko riconoscerà la finestra autorizzata.</p>
        </div>
        <button className="picker-close" type="button" onClick={onClose} aria-label="Chiudi selezione">×</button>
      </header>
      <div className="picker-search-row">
        <label className="picker-search">
          <span aria-hidden="true">⌕</span>
          <input ref={inputRef} type="search" aria-label="Cerca applicazioni e finestre"
            value={query} onChange={e => { setQuery(e.target.value); setExpanded(null); }}
            placeholder="Cerca Firefox, Blocco note, Discord…" />
        </label>
        <button className="picker-refresh" onClick={onRefresh} type="button"
          disabled={fetching || busy} aria-label="Aggiorna elenco">↻</button>
      </div>
      <nav className="picker-tabs" aria-label="Tipo applicazione">
        <button type="button" className={tab === 'open' ? 'is-active' : ''}
          onClick={() => { setTab('open'); setQuery(''); }}>Finestre aperte <span>{windows.length}</span></button>
        <button type="button" className={tab === 'installed' ? 'is-active' : ''}
          onClick={() => { setTab('installed'); setQuery(''); }}>Applicazioni installate <span>{installed.length}</span></button>
      </nav>
      <div className="picker-scroll">
        {tab === 'open' && (groups.length ? <div className="picker-groups">
          {groups.map(group => {
            const open = expanded === group.exe || (query.length > 0 && groups.length === 1);
            const selected = chosen?.executable === group.exe;
            return <article className={`picker-group${selected ? ' picker-group--chosen' : ''}`} key={group.exe}>
              <button className="picker-group-toggle" type="button"
                onClick={() => setExpanded(open ? null : group.exe)}
                aria-expanded={open} disabled={busy}>
                <span className="picker-app-icon" aria-hidden="true">{group.name.charAt(0).toUpperCase()}</span>
                <span className="picker-app-summary"><strong>{group.name}</strong>
                  <small>{group.windows.length} {group.windows.length === 1 ? 'finestra aperta' : 'finestre aperte'}</small>
                </span>
                {suggested.includes(group.exe) && <span className="picker-hint">Suggerita</span>}
                <span className="picker-chevron" aria-hidden="true">{open ? '⌃' : '⌄'}</span>
              </button>
              {open && <div className="picker-window-list">
                {group.windows.map(item => <button type="button"
                  className={`picker-window${chosen?.window_handle === item.window_handle ? ' picker-window--selected' : ''}`}
                  key={item.window_handle} disabled={busy} onClick={() => onSelect(item)}>
                  <span className="picker-window-symbol" aria-hidden="true">▣</span>
                  <span><strong>{item.title}</strong><small>{item.is_foreground ? 'In primo piano' : 'Pronta in background'}</small></span>
                  <span className="picker-select-mark" aria-hidden="true">{chosen?.window_handle === item.window_handle ? '✓' : '→'}</span>
                </button>)}
              </div>}
            </article>;
          })}
        </div> : <div className="picker-empty"><strong>Nessuna finestra corrispondente.</strong>
          <p>Avvia un'applicazione oppure scegli tra quelle installate.</p>
          <button type="button" onClick={() => { setTab('installed'); setQuery(''); }}>Cerca tra le installate</button>
        </div>)}
        {tab === 'installed' && (installedFiltered.length ? <div className="picker-installed">
          {installedFiltered.map(app => <div className="picker-install-row" key={app.id}>
            <span className="picker-app-icon" aria-hidden="true">{app.name.charAt(0).toUpperCase()}</span>
            <span className="picker-app-summary"><strong>{app.name}</strong><small>Menu Start di Windows</small></span>
            {confirmLaunch === app.id ? <div className="picker-launch-confirm">
              <span>Aprire {app.name}?</span>
              <button type="button" disabled={busy} onClick={() => { setConfirmLaunch(null); onLaunch(app.id); }}>Conferma</button>
              <button type="button" disabled={busy} onClick={() => setConfirmLaunch(null)}>Annulla</button>
            </div> : <button type="button" className="picker-launch" disabled={busy}
              onClick={() => setConfirmLaunch(app.id)}>Apri</button>}
          </div>)}
        </div> : <div className="picker-empty"><strong>Nessuna app trovata.</strong>
          <p>L'elenco include i collegamenti del menu Start. Alcune app portatili potrebbero non comparire.</p>
        </div>)}
      </div>
      <footer className="picker-footer">
        <div className="picker-privacy">Solo nomi e titoli delle finestre locali. Nessuno screenshot viene acquisito.</div>
        <button type="button" className="picker-aim" onClick={onPick} disabled={busy}>
          <span aria-hidden="true">⊕</span> Seleziona cliccando una finestra
        </button>
      </footer>
    </section>
  </div>;
}
