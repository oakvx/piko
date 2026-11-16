import { useCallback, useEffect, useMemo, useState } from 'react';
import { invoke as tauriInvoke, isTauri } from '@tauri-apps/api/core';
import type { FormEvent, ReactNode } from 'react';
import { PikoClient } from './client';
import PikoGlyph from './PikoGlyph';
import type { AgentEvent, AgentState, Demonstration, Health, Lens, ModelInfo, Observation, Session, Skill } from './types';

const stateText: Record<AgentState, string> = {
  idle: 'Ready to observe', observing: 'Reading the desktop', analyzing: 'Interpreting',
  planning: 'Composing a route', waiting_for_user: 'Waiting for your review',
  executing: 'Acting on your desktop', verifying: 'Checking the outcome',
  paused: 'Paused', completed: 'Verified route finished', failed: 'Stopped with an error',
  cancelled: 'Cancelled',
};

const LENSES: { id: Lens; number: string; title: string; detail: string }[] = [
  { id: 'work', number: '01', title: 'Workfield', detail: 'Direct' },
  { id: 'teach', number: '02', title: 'Demonstrate', detail: 'Observe' },
  { id: 'skills', number: '03', title: 'Library', detail: 'Recall' },
  { id: 'system', number: '04', title: 'System', detail: 'Inspect' },
];

function Mark({ name, size = 18 }: { name: 'arrow' | 'stop' | 'pause' | 'play' | 'eye' | 'refresh' | 'plus' | 'check' | 'close' | 'signal' | 'shield' | 'camera' | 'trash'; size?: number }) {
  const parts: Record<typeof name, ReactNode> = {
    arrow: <><path d="M4 10h12M11 5l5 5-5 5" /></>,
    stop: <rect x="5" y="5" width="10" height="10" rx="2" />,
    pause: <><path d="M7 4v12M13 4v12" /></>,
    play: <path d="m7 4 10 6-10 6z" />,
    eye: <><path d="M2 10s3-6 8-6 8 6 8 6-3 6-8 6-8-6-8-6Z" /><circle cx="10" cy="10" r="2.5" /></>,
    refresh: <><path d="M17 6V2l-3 3a7 7 0 1 0 2.3 8" /><path d="M17 6h-5" /></>,
    plus: <><path d="M10 3v14M3 10h14" /></>,
    check: <path d="m3 10 5 5 9-10" />,
    close: <><path d="M4 4l12 12M16 4 4 16" /></>,
    signal: <><circle cx="10" cy="10" r="3" /><path d="M4 4c-4 4-4 8 0 12M16 4c4 4 4 8 0 12" /></>,
    shield: <><path d="M10 2 17 5v5c0 5-4 7-7 8-3-1-7-3-7-8V5l7-3Z" /><path d="m7 10 2 2 4-4" /></>,
    camera: <><path d="M2 6h3l2-2h6l2 2h3v10H2z" /><circle cx="10" cy="11" r="3" /></>,
    trash: <><path d="M3 5h14M7 5V3h6v2M5 5l1 12h8l1-12" /><path d="M8 8v6M12 8v6" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{parts[name]}</svg>;
}

function Kicker({ children, index }: { children: ReactNode; index?: string }) {
  return <span className="kicker">{index && <span className="kicker-index">{index}</span>}{children}</span>;
}

function timeString(iso: string) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(date);
}

function StatusChip({ state }: { state: AgentState | 'offline' }) {
  return <span className={`state-chip state-chip--${state}`}><span className="state-dot" />{state === 'offline' ? 'Disconnected' : stateText[state]}</span>;
}

function actionLabel(kind: string) {
  return ({ 'ui.click': 'Select element', 'ui.set_text': 'Enter text', 'keyboard.hotkey': 'Keyboard shortcut', 'wait.condition': 'Wait for change' } as Record<string, string>)[kind] ?? kind;
}

function TraceCard({ item, index, session, events, focused, onFocus, frameAvailable }: { item: NonNullable<Session['plan']>['actions'][number]; index: number; session: Session; events: AgentEvent[]; focused: boolean; onFocus: (id: string) => void; frameAvailable: boolean }) {
  const verified = index < session.next_action;
  const attempt = events.some((event) => event.type === 'action.requested' && event.payload.index === index);
  const verifiedEvent = [...events].reverse().find((event) => event.type === 'verification.completed' && event.payload.index === index);
  const failed = verifiedEvent?.payload.verified === false;
  const active = !verified && !failed && attempt && ['executing', 'verifying'].includes(session.state);
  return (
    <article className={`trace-card${verified ? ' trace-card--verified' : ''}${active ? ' trace-card--active' : ''}${failed ? ' trace-card--failed' : ''}${focused ? ' trace-card--focused' : ''}`}>
      <div className="trace-order"><span>{String(index + 1).padStart(2, '0')}</span><span className="trace-order-line" /></div>
      <div className="trace-card-body">
        <div className="trace-card-top"><span className="trace-kind">{item.kind}</span><span className={`trace-flag ${verified ? 'trace-flag--true' : ''}`}>{verified ? 'VERIFIED' : failed ? 'NOT VERIFIED' : active ? 'IN PROGRESS' : 'PENDING'}</span></div>
        <h3>{actionLabel(item.kind)}</h3>
        <p className="trace-target">{item.automation_id || (item.keys.length ? item.keys.join(' + ') : 'Application')}</p>
        <div className="trace-expected"><span className="proof-symbol">◇</span><span>Check <strong>{item.expected.automation_id}</strong> · {item.expected.property.replaceAll('_', ' ')}{item.expected.value === null ? '' : ` · ${String(item.expected.value)}`}</span></div>
        {frameAvailable && item.automation_id && <button type="button" className="trace-focus-button" aria-pressed={focused} onClick={() => onFocus(item.automation_id!)}><Mark name="eye" size={13}/>{focused ? 'Highlighted on snapshot' : 'Locate on snapshot'}</button>}
      </div>
    </article>
  );
}

function RouteView({ session, events, focusedTarget, onFocus, frameAvailable }: { session: Session | null; events: AgentEvent[]; focusedTarget: string | null; onFocus: (id: string) => void; frameAvailable: boolean }) {
  if (!session?.plan) {
    return <div className="empty-route">
      <div className="empty-route-graphic" aria-hidden="true">
        <div className="orbit orbit-a" /><div className="orbit orbit-b" />
        <span className="orbit-label orbit-label-a">observe</span>
        <span className="orbit-label orbit-label-b">reason</span>
        <span className="orbit-label orbit-label-c">verify</span>
        <span className="orbit-center"><PikoGlyph state={session?.state ?? 'idle'} /></span>
      </div>
      <h2>{session?.state === 'failed' ? 'This route could not be composed.' : 'A route begins with an intention.'}</h2>
      <p>{session?.error || 'Describe a task and choose an approved Windows application. Piko will inspect its UI and propose steps for your review.'}</p>
    </div>;
  }
  return <div className="route-content">
    <div className="route-intro"><Kicker index="ROUTE">Proposed procedure</Kicker><h2>{session.plan.objective}</h2><p>{session.plan.explanation}</p></div>
    <div className="route-path" aria-label="Planned actions and verification outcomes">
      {session.plan.actions.map((action, index) => <TraceCard key={`${index}-${action.kind}`} item={action} index={index} session={session} events={events} focused={focusedTarget === action.automation_id} onFocus={onFocus} frameAvailable={frameAvailable} />)}
    </div>
    <div className="route-end"><div className={`end-node${session.state === 'completed' ? ' end-node--confirmed' : ''}`}><Mark name="check" size={16} /></div><div><strong>Completion gate</strong><p>{session.state === 'completed' ? 'Every planned verification completed.' : 'Complete only after all expected outcomes are observed.'}</p></div></div>
  </div>;
}

function EventRail({ events, session, frame, busy, capture, focusedTarget }: { events: AgentEvent[]; session: Session | null; frame: Observation | null; busy: boolean; capture: () => void; focusedTarget: string | null }) {
  const candidate = frame?.elements.find(element => element.automation_id === focusedTarget);
  const rect = candidate?.bounds;
  const area = frame?.capture_bounds;
  const overlay = rect && area && area[2] > 0 && area[3] > 0 ? {
    left: `${Math.max(0, Math.min(100, (rect[0] - area[0]) / area[2] * 100))}%`,
    top: `${Math.max(0, Math.min(100, (rect[1] - area[1]) / area[3] * 100))}%`,
    width: `${Math.max(0, Math.min(100, (rect[2] - area[0]) / area[2] * 100) - Math.max(0, Math.min(100, (rect[0] - area[0]) / area[2] * 100)))}%`,
    height: `${Math.max(0, Math.min(100, (rect[3] - area[1]) / area[3] * 100) - Math.max(0, Math.min(100, (rect[1] - area[1]) / area[3] * 100)))}%`,
  } : null;
  const rows = [...events].reverse().slice(0, 9);
  return <aside className="evidence-rail">
    <div className="rail-heading"><Kicker>Perception</Kicker><span className="rail-live">ON REQUEST</span></div>
    <div className="capture-box">
      {frame ? <><div className="capture-stage"><img className="capture-image" src={`data:image/png;base64,${frame.image_base64}`} alt={`Authorized capture of ${frame.window_title}`} />{focusedTarget && overlay && <div className="capture-focus" style={overlay} title={`UIA element: ${focusedTarget}`}><span>{focusedTarget}</span></div>}</div>{focusedTarget && !overlay && <p className="focus-unavailable">This UI element has no reliable bounds in this observation.</p>}<div className="capture-caption"><span>{frame.window_title || frame.executable}</span><time>{timeString(frame.timestamp)}</time></div></> : <div className="capture-empty"><Mark name="eye" size={27} /><strong>No screen data retained here</strong><span>A single authorized capture appears here when requested.</span></div>}
      <button className="capture-button" type="button" onClick={capture} disabled={!session || busy}><Mark name="camera" size={16} />{frame ? 'Capture again' : 'Capture once'}</button>
    </div>
    <div className="ledger-head"><Kicker>Evidence ledger</Kicker><span>{rows.length} recent</span></div>
    <div className="ledger" aria-live="polite">
      {rows.length ? rows.map((event, index) => <div className="ledger-entry" key={`${event.timestamp}-${event.type}-${index}`}>
        <span className={`ledger-mark${event.payload.verified === false || event.type === 'agent.error' ? ' ledger-mark--error' : ''}`} />
        <div><strong>{event.type.replaceAll('.', ' / ').replaceAll('_', ' ')}</strong><span>{event.payload.action ? String(event.payload.action) : event.payload.verified === true ? 'Observable outcome confirmed' : event.payload.verified === false ? 'Expected change not observed' : event.payload.state ? String(event.payload.state).replaceAll('_', ' ') : 'Recorded by local backend'}</span></div>
        <time>{timeString(event.timestamp)}</time>
      </div>) : <p className="ledger-empty">No events yet. Real session transitions and verifications will appear here.</p>}
    </div>
  </aside>;
}

export default function App() {
  const [draftToken, setDraftToken] = useState('');
  const [token, setToken] = useState('');
  const [backendPort, setBackendPort] = useState(8765);
  const client = useMemo(() => token ? new PikoClient(token, `http://127.0.0.1:${backendPort}`) : null, [token, backendPort]);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [lens, setLens] = useState<Lens>('work');
  const [objective, setObjective] = useState('');
  const [executable, setExecutable] = useState('');
  const [consent, setConsent] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [session, setSession] = useState<Session | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [frame, setFrame] = useState<Observation | null>(null);
  const [focusedTarget, setFocusedTarget] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [modelSelection, setModelSelection] = useState<{ reasoning: string | null; vision: string | null }>({ reasoning: null, vision: null });
  const [modelError, setModelError] = useState('');
  const [chosenReasoning, setChosenReasoning] = useState('');
  const [chosenVision, setChosenVision] = useState('');
  const [skills, setSkills] = useState<Skill[]>([]);
  const [skillConsent, setSkillConsent] = useState(false);
  const [teachExecutable, setTeachExecutable] = useState('');
  const [teachConsent, setTeachConsent] = useState(false);
  const [teachSeconds, setTeachSeconds] = useState(30);
  const [recording, setRecording] = useState(false);
  const [demonstration, setDemonstration] = useState<Demonstration | null>(null);
  const [slug, setSlug] = useState('');
  const [skillDescription, setSkillDescription] = useState('');

  const attempt = useCallback(async (label: string, fn: () => Promise<void>) => {
    setBusy(label); setError(''); setNotice('');
    try { await fn(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  }, []);

  // Installed Windows builds get an ephemeral token directly from the Rust host.
  // No environment variable or control token is persisted in the frontend.
  useEffect(() => {
    if (!isTauri()) return;
    let cancelled = false;
    void (async () => {
      try {
        const config = await tauriInvoke<{ token: string; port: number } | null>('backend_config');
        if (!config) return; // development mode: continue supporting manual local startup
        const next = new PikoClient(config.token, `http://127.0.0.1:${config.port}`);
        for (let attemptNo = 0; attemptNo < 35 && !cancelled; attemptNo++) {
          try {
            const status = await next.health();
            if (cancelled) return;
            setHealth(status); setBackendPort(config.port); setToken(config.token); setConnected(true);
            return;
          } catch {
            await new Promise<void>(resolve => window.setTimeout(resolve, 450));
          }
        }
        if (!cancelled) setError('Bundled Piko backend did not become available. Check Ollama and local diagnostics.');
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const connect = (event: FormEvent) => {
    event.preventDefault();
    const candidate = draftToken.trim();
    if (candidate.length < 24) { setError('Paste the one-time token printed by piko serve.'); return; }
    void attempt('connect', async () => {
      const next = new PikoClient(candidate);
      const status = await next.health();
      setHealth(status); setToken(candidate); setDraftToken(''); setConnected(true);
    });
  };

  const refresh = useCallback(async () => {
    if (!client) return;
    try {
      const [status, history, teach] = await Promise.all([client.health(), client.sessions(), client.teachStatus()]);
      setConnected(true); setHealth(status); setSessions(history); setRecording(teach.recording);
      setSession(current => current ? history.find(s => s.id === current.id) ?? current : history[0] ?? null);
    } catch { setConnected(false); }
  }, [client]);

  useEffect(() => {
    if (!client) return;
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 2000);
    return () => window.clearInterval(timer);
  }, [client, refresh]);

  useEffect(() => {
    if (!client || !session?.id || !connected) return;
    setEvents([]);
    let alive = true;
    const load = async () => {
      try { const latest = await client.events(session.id); if (alive) setEvents(latest); }
      catch { if (alive) setEvents([]); }
    };
    void load();
    const timer = window.setInterval(() => { void load(); }, 2200);
    return () => { alive = false; window.clearInterval(timer); };
  }, [client, connected, session?.id]);

  useEffect(() => {
    if (!client || !connected) return;
    let active = true;
    void client.models().then(result => { if (active) { setModels(result.installed); setModelSelection({ reasoning: result.reasoning, vision: result.vision }); setChosenReasoning(result.reasoning ?? ''); setChosenVision(result.vision ?? ''); setModelError(''); } })
      .catch((e: unknown) => { if (active) setModelError(e instanceof Error ? e.message : String(e)); });
    void client.skills().then(result => { if (active) setSkills(result); }).catch(() => {});
    void client.latestTeach().then(result => { if (active) setDemonstration(result); }).catch(() => {});
    return () => { active = false; };
  }, [client, connected]);

  const startRoute = (event: FormEvent) => {
    event.preventDefault();
    if (!client || !consent || !objective.trim() || !executable.trim()) return;
    void attempt('plan', async () => {
      setFrame(null); setFocusedTarget(null); setEvents([]); setReviewed(false);
      const created = await client.createSession(objective.trim(), executable.trim());
      setSession(created);
      await client.grant(created.app_executable, 'limited', created.id);
      const planned = await client.plan(created.id);
      setSession(planned); await refresh();
    });
  };

  const invoke = (label: string, task: () => Promise<unknown>, message?: string) => {
    void attempt(label, async () => {
      await task();
      if (message) setNotice(message);
      await refresh();
      if (session && client) setSession(await client.session(session.id));
    });
  };

  const capture = () => {
    if (!client || !session) return;
    void attempt('capture', async () => { setFrame(await client.observe(session.id)); });
  };

  const createDemo = (event: FormEvent) => {
    event.preventDefault();
    if (!client || !teachConsent) return;
    void attempt('teach-start', async () => {
      await client.grant(teachExecutable.trim(), 'observe', 'teach');
      const result = await client.startTeach(teachExecutable.trim(), teachSeconds);
      setRecording(result.recording); setDemonstration(null);
      setNotice('Recording authorized observations. Raw input events are not supported yet.');
    });
  };

  const stopDemo = () => {
    if (!client) return;
    void attempt('teach-stop', async () => { setDemonstration(await client.stopTeach()); setRecording(false); });
  };

  const storeDraft = (event: FormEvent) => {
    event.preventDefault();
    if (!client || !session?.plan) return;
    void attempt('skill', async () => {
      await client.saveSkill(session.id, slug.trim(), skillDescription.trim());
      setSkills(await client.skills()); setNotice('Draft saved. It has not been generalized or verified as a reusable Skill.');
    });
  };

  const reviewSavedSkill = (name: string) => {
    if (!client || !skillConsent) return;
    void attempt('skill-review', async () => {
      const prepared = await client.reviewSkill(name);
      await refresh();
      setSession(prepared);
      setFrame(null);
      setReviewed(false);
      setSkillConsent(false);
      setLens('work');
      setNotice('Skill loaded for review. Approve the route separately before executing.');
    });
  };

  const active = session && ['executing', 'verifying'].includes(session.state);
  const recentSessions = [...sessions].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 5);
  const isBlockedByWork = !!active || !!busy;

  if (!token) return <main className="welcome-shell">
    <div className="welcome-top"><span className="logo-text">piko<span>.</span></span><span className="top-serial">LOCAL FIRST / 001</span></div>
    <section className="welcome-stage">
      <div className="welcome-character"><span className="welcome-halo" /><PikoGlyph /></div>
      <div className="welcome-copy"><Kicker index="PIKO OS">Meet the Workfield</Kicker><h1>Show me.<br /><em>I’ll do it.</em></h1><p>A quieter way to work with your computer. Teach, direct, and inspect a local agent — where every action has a reason, and every outcome needs evidence.</p>
        <form className="token-form" onSubmit={connect}>
          <label htmlFor="control-token">Connect to your local Piko runtime</label>
          <div className="token-row"><input id="control-token" autoComplete="off" type="password" value={draftToken} onChange={e => setDraftToken(e.target.value)} placeholder="Paste the token from piko serve" required /><button type="submit" disabled={busy !== null}>Connect <Mark name="arrow" /></button></div>
          <span className="form-hint"><Mark name="shield" size={14} /> Token stays in memory. Nothing is sent to a cloud service.</span>
          {error && <p className="inline-error" role="alert">{error}</p>}
        </form>
      </div>
    </section>
    <div className="welcome-bottom"><span>DESIGNED FOR REAL DESKTOP WORK</span><span>WINDOWS 10 / 11 · ALPHA</span></div>
  </main>;

  return <div className="app-shell">
    <header className="masthead">
      <div className="brand"><span className="brand-icon"><PikoGlyph state={session?.state ?? 'idle'} compact /></span><span className="logo-text">piko<span>.</span></span><span className="brand-divider" /><span className="brand-subtitle">WORKFIELD / ALPHA</span></div>
      <nav className="lens-dial" aria-label="Work modes">{LENSES.map(item => <button type="button" key={item.id} aria-current={lens === item.id ? 'page' : undefined} className={`lens-tab${lens === item.id ? ' lens-tab--active' : ''}`} onClick={() => setLens(item.id)}><small>{item.number}</small>{item.title}</button>)}</nav>
      <div className="head-actions"><span className={`connection-indicator${connected ? '' : ' connection-indicator--off'}`}><span />{connected ? 'LOCAL CONNECTED' : 'OFFLINE'}</span><button type="button" className="kill-switch" onClick={() => client && invoke('emergency', () => client.emergencyStop(), 'Emergency stop requested for all agent sessions.')} disabled={!client || !connected} title="Release inputs and stop every session"><Mark name="stop" size={15} />EMERGENCY STOP</button></div>
    </header>

    <div className="workfield-body">
      <section className="page-heading">
        <div><Kicker index="P / 001">{LENSES.find(item => item.id === lens)?.detail} / Local system</Kicker>
          <h1>{lens === 'work' ? <>Give it a goal.<br /><em>See the whole route.</em></> : lens === 'teach' ? <>Show the process.<br /><em>Keep the knowledge.</em></> : lens === 'skills' ? <>Small lessons.<br /><em>Ready to grow.</em></> : <>Everything local.<br /><em>Nothing hidden.</em></>}</h1>
        </div>
        <div className="heading-right"><span className="heading-cross" aria-hidden="true">✳</span><StatusChip state={connected ? session?.state ?? 'idle' : 'offline'} /><p>Only authorized actions.<br />All outcomes independently verified.</p></div>
      </section>

      {error && <div className="message-banner message-banner--error" role="alert"><span>{error}</span><button type="button" aria-label="Dismiss error" onClick={() => setError('')}><Mark name="close" size={15} /></button></div>}
      {notice && <div className="message-banner" role="status"><span>{notice}</span><button type="button" aria-label="Dismiss notice" onClick={() => setNotice('')}><Mark name="close" size={15} /></button></div>}
      {!connected && <div className="message-banner message-banner--error" role="alert">Runtime unavailable. No new operations can be sent. <button type="button" onClick={() => void refresh()}>Retry connection</button></div>}

      {lens === 'work' && <>
        <div className="workspace-grid">
          <section className="instruction-panel">
            <div className="panel-top"><Kicker index="A">Intent</Kicker><span className="panel-annotation">YOUR INSTRUCTION</span></div>
            <form onSubmit={startRoute} className="intent-form">
              <label htmlFor="objective">What should Piko accomplish?</label>
              <textarea id="objective" rows={4} maxLength={500} value={objective} onChange={e => setObjective(e.target.value)} placeholder="For example: enter a name in the demo app, save it and confirm the result." disabled={isBlockedByWork} required />
              <div className="intent-target"><label htmlFor="executable">Inside this application</label><div className="target-field"><span className="target-bullet" /><input id="executable" placeholder="application.exe" value={executable} onChange={e => { setExecutable(e.target.value); setConsent(false); }} disabled={isBlockedByWork} required /></div><small>Foreground app · exact executable name</small></div>
              <label className="consent-line"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} disabled={isBlockedByWork} /><span>I authorize Piko to inspect and perform ordinary actions inside this application for this session.</span></label>
              <button className="primary-button" type="submit" disabled={!consent || !objective.trim() || !executable.trim() || isBlockedByWork || !connected}><span>{busy === 'plan' ? 'Composing route…' : 'Compose a route'}</span><Mark name="arrow" /></button>
            </form>
            <div className="intent-divider" />
            <div className="session-selector"><div className="mini-heading"><Kicker>Recent work</Kicker><span>{recentSessions.length} sessions</span></div>{recentSessions.length ? recentSessions.map(item => <button className={`session-option${session?.id === item.id ? ' session-option--selected' : ''}`} type="button" key={item.id} onClick={() => { setSession(item); setFrame(null); setFocusedTarget(null); setEvents([]); setReviewed(false); }}><span className="session-option-name">{item.objective}</span><span className="session-option-detail">{item.app_executable}<span>·</span>{item.state.replaceAll('_', ' ')}</span></button>) : <p className="muted-empty">No local sessions yet.</p>}</div>
          </section>

          <section className="route-panel"><div className="panel-top"><Kicker index="B">The route</Kicker><span className="route-count">{session?.plan ? `${session.next_action} / ${session.plan.actions.length} CONFIRMED` : 'NO ROUTE YET'}</span></div><RouteView session={session} events={events} focusedTarget={focusedTarget} onFocus={setFocusedTarget} frameAvailable={frame !== null} />
            <div className="route-actions">
              {session?.state === 'waiting_for_user' && <div className="approval-area"><label className="consent-line"><input type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)} /><span>I've reviewed the route and authorize these actions.</span></label><button className="action-confirm" type="button" disabled={!reviewed || !!busy || !connected} onClick={() => client && invoke('execute', () => client.execute(session.id))}>Execute reviewed route <Mark name="arrow" /></button></div>}
              {active && <div className="execution-controls"><button type="button" disabled={!!busy} onClick={() => client && invoke('pause', () => client.pause(session.id), 'Pause requested at the next safe action boundary.')}><Mark name="pause" size={16} /> Pause after step</button><button type="button" disabled={!!busy} onClick={() => client && invoke('stop', () => client.stop(session.id))}><Mark name="stop" size={16} /> Stop</button></div>}
              {session?.state === 'paused' && <div className="execution-controls"><button type="button" disabled={!!busy} onClick={() => client && invoke('resume', () => client.resume(session.id))}><Mark name="play" size={16} /> Resume with fresh checks</button><button type="button" disabled={!!busy} onClick={() => client && invoke('stop', () => client.stop(session.id))}><Mark name="stop" size={16} /> Cancel</button></div>}
              {session?.state === 'failed' && <p className="operation-note operation-note--error"><Mark name="stop" size={15} />{session.error || 'A required condition failed. No further steps were dispatched.'}</p>}
              {session && !active && <span className="operation-note"><Mark name="shield" size={15} />No unreviewed actions are executed automatically.</span>}
            </div>
          </section>
          <EventRail events={events} session={session} frame={frame} busy={!!busy || !connected} capture={capture} focusedTarget={focusedTarget} />
        </div>
        {session?.plan && <section className="skill-seed"><div><Kicker>Make it reusable</Kicker><h3>Turn this route into a draft.</h3><p>A draft is not a verified general-purpose Skill. It must be reviewed and tested independently.</p></div><form onSubmit={storeDraft} className="skill-form"><input aria-label="Skill name" placeholder="skill-name" pattern="[a-z0-9][a-z0-9-]{0,63}" value={slug} onChange={e => setSlug(e.target.value)} required /><input aria-label="Skill description" placeholder="What does this route do?" value={skillDescription} onChange={e => setSkillDescription(e.target.value)} required /><button type="submit" disabled={!!busy || !connected}>Save draft <Mark name="plus" size={15} /></button></form></section>}
      </>}

      {lens === 'teach' && <div className="mode-layout teach-layout">
        <div className="teach-stage"><div className="panel-top"><Kicker index="A">Demonstration studio</Kicker><span className={`record-indicator${recording ? ' record-indicator--active' : ''}`}><span />{recording ? 'CAPTURING' : 'NOT RECORDING'}</span></div><div className="teach-visual"><span className="teach-visual-grid" /><div className="teach-persona"><PikoGlyph state={recording ? 'observing' : 'idle'} /></div><div className="teach-wave teach-wave-a" /><div className="teach-wave teach-wave-b" /><span className="teach-mode-caption">{recording ? 'AUTHORIZED WINDOW OBSERVATION' : 'WAITING FOR YOUR DEMONSTRATION'}</span></div>
          <div className="teach-limits"><Kicker>What this version records</Kicker><p>Opt-in foreground screenshots and UI Automation observations. It does <strong>not</strong> capture keyboard or mouse events, infer a procedure, or generate a learned Skill yet. Sensitive windows are excluded.</p></div>
          {demonstration && <div className="demo-result"><div><Kicker>Last recording</Kicker><h3>{demonstration.frames} captured observations</h3><p>{demonstration.limitations.join('. ')}</p></div><button type="button" disabled={!!busy} onClick={() => client && invoke('delete-demo', async () => { await client.deleteTeach(demonstration.id); setDemonstration(null); }, 'Local demonstration deleted.')}><Mark name="trash" size={16} /> Delete</button></div>}
        </div>
        <section className="teach-controls"><div className="panel-top"><Kicker index="B">Your recording boundary</Kicker></div><h2>You show.<br /><em>Piko observes.</em></h2><form onSubmit={createDemo}><label htmlFor="teach-app">Approved foreground application</label><input id="teach-app" placeholder="application.exe" value={teachExecutable} onChange={e => { setTeachExecutable(e.target.value); setTeachConsent(false); }} disabled={recording || !!busy} required /><label htmlFor="teach-duration">Maximum duration</label><div className="duration-choices" id="teach-duration">{[15, 30, 60, 120].map(seconds => <button key={seconds} type="button" aria-pressed={teachSeconds === seconds} className={teachSeconds === seconds ? 'duration--chosen' : ''} onClick={() => setTeachSeconds(seconds)} disabled={recording || !!busy}>{seconds}s</button>)}</div><label className="consent-line"><input type="checkbox" checked={teachConsent} onChange={e => setTeachConsent(e.target.checked)} disabled={recording || !!busy} /><span>I authorize time-limited recording of this foreground application.</span></label>{recording ? <button className="primary-button primary-button--stop" type="button" disabled={!!busy} onClick={stopDemo}><Mark name="stop" /> Stop watching</button> : <button className="primary-button" type="submit" disabled={!teachConsent || !teachExecutable.trim() || isBlockedByWork || !connected}><Mark name="eye" /> Watch me</button>}</form></section>
      </div>}

      {lens === 'skills' && <section className="library-board"><div className="panel-top"><Kicker index="A">Procedural library</Kicker><span className="panel-annotation">LOCAL FILES ONLY</span></div><div className="library-summary"><div><h2>{skills.length.toString().padStart(2, '0')}<span> / saved drafts and skills</span></h2><p>Every item keeps its verification status. Drafts have not been proven to generalize.</p></div><button type="button" onClick={() => client && invoke('skills', async () => { setSkills(await client.skills()); })} disabled={!!busy || !connected}><Mark name="refresh" size={16} /> Reload library</button></div><label className="consent-line"><input type="checkbox" checked={skillConsent} disabled={!!busy || !connected} onChange={e => setSkillConsent(e.target.checked)} /><span>I authorize Piko to inspect the foreground application before reviewing a saved Skill. Execution requires a second approval.</span></label>{skills.length ? <div className="library-list">{skills.map(item => <article key={item.name} className="library-card"><div className="library-glyph">✳</div><div><span className="library-state">{item.status.toUpperCase()} / {item.version}</span><h3>{item.name}</h3><p>{item.description}</p><span className="library-info">{item.executable} · {item.actions} actions</span><button type="button" className="system-secondary" disabled={!skillConsent || !!busy || !connected} onClick={() => reviewSavedSkill(item.name)}>Review procedure <Mark name="arrow" size={15} /></button></div></article>)}</div> : <div className="library-empty"><span className="library-star">✳</span><h3>Nothing here. Yet.</h3><p>Once you save a reviewed route, its Markdown Skill draft will appear here.</p><button type="button" onClick={() => setLens('work')}>Compose a route <Mark name="arrow" size={17} /></button></div>}</section>}

      {lens === 'system' && <div className="system-board"><section className="system-card"><Kicker index="01">Runtime</Kicker><h2>Local by design.</h2><div className="system-property"><span>Connection</span><strong>{connected ? 'Loopback / active' : 'Disconnected'}</strong></div><div className="system-property"><span>Transport</span><strong>127.0.0.1:{backendPort}</strong></div><div className="system-property"><span>Host platform</span><strong>{health?.platform || 'Unavailable'}</strong></div><div className="system-property"><span>Active input sessions</span><strong>{health ? health.active_session_count : 'Unknown'}</strong></div><button type="button" className="system-secondary" onClick={() => { setToken(''); setHealth(null); setFrame(null); setSession(null); setConnected(false); }}><Mark name="close" size={16} /> Disconnect this window</button></section>
        <section className="system-card"><Kicker index="02">Inference</Kicker><h2>On-device intelligence.</h2><div className="system-property"><span>Reasoning model</span><strong>{modelSelection.reasoning || 'Not reported'}</strong></div><div className="system-property"><span>Vision model</span><strong>{modelSelection.vision || 'Not configured'}</strong></div><div className="system-property"><span>Ollama discovery</span><strong>{modelError ? 'Unavailable' : models === null ? 'Checking…' : `${models.length} installed`}</strong></div>{modelError && <p className="inline-error">{modelError}</p>}<div className="model-list">{models?.map(model => <div key={model.name}><strong>{model.name}</strong><small>{model.details?.parameter_size || 'Parameter size not reported'}</small></div>)}</div>
          {models && models.length > 0 && <div className="model-choice">
            <label htmlFor="reasoning-model">Reasoning model</label>
            <select id="reasoning-model" value={chosenReasoning} onChange={e => setChosenReasoning(e.target.value)}>
              <option value="">Select installed model</option>
              {models.map(model => <option key={model.name} value={model.name}>{model.name}</option>)}
            </select>
            <label htmlFor="vision-model">Vision model (optional)</label>
            <select id="vision-model" value={chosenVision} onChange={e => setChosenVision(e.target.value)}>
              <option value="">None</option>
              {models.map(model => <option key={model.name} value={model.name}>{model.name}</option>)}
            </select>
            <button type="button" className="system-secondary" disabled={!chosenReasoning || !!busy} onClick={() => client && invoke('select-models', async () => {
              const selected = await client.selectModels(chosenReasoning, chosenVision || null);
              setModelSelection({ reasoning: selected.reasoning, vision: selected.vision });
            }, 'Local model settings updated for this session.')}>Use these models</button>
          </div>}<button type="button" className="system-secondary" onClick={() => client && invoke('models', async () => { const result = await client.models(); setModels(result.installed); setModelSelection({ reasoning: result.reasoning, vision: result.vision }); setChosenReasoning(result.reasoning ?? ''); setChosenVision(result.vision ?? ''); setModelError(''); })} disabled={!!busy}><Mark name="refresh" size={16} /> Refresh Ollama</button></section>
        <section className="system-card system-card--privacy"><Kicker index="03">Safety boundary</Kicker><h2>Never an invisible operator.</h2><p>Capture is opt-in. No background screenshots are streamed by this interface. A plan must be reviewed before desktop actions. No external AI endpoint is configured.</p><div className="privacy-emblem"><Mark name="shield" size={36} /></div>{session && <button type="button" className="system-secondary" disabled={!!busy} onClick={() => client && invoke('revoke', () => client.revoke(session.app_executable), `Permission for ${session.app_executable} revoked.`)}><Mark name="close" size={16} /> Revoke permission: {session.app_executable}</button>}</section>
      </div>}
    </div>
    <footer className="status-footer"><div><span className="footer-symbol">✳</span><span>PIKO / SHOW ME. I’LL DO IT.</span></div><span className="footer-center">OBSERVE <span>→</span> PLAN <span>→</span> EXECUTE <span>→</span> VERIFY</span><div><span>NO HIDDEN TELEMETRY</span><span className="footer-mark">ALPHA 01</span></div></footer>
  </div>;
}
