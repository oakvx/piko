import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { invoke as tauriInvoke, isTauri } from '@tauri-apps/api/core';
import type { ChangeEvent, FormEvent, ReactNode } from 'react';
import { PikoClient } from './client';
import PikoGlyph from './PikoGlyph';
import TeachStepEditor from './TeachStepEditor';
import type { AgentEvent, AgentState, Demonstration, Health, Lens, ModelInfo, Observation, Plan, Session, Skill, TeachAnalysis } from './types';

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
  { id: 'coach', number: '04', title: 'Coach', detail: 'Live vision' },
  { id: 'system', number: '05', title: 'System', detail: 'Inspect' },
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
  const [windowCandidates, setWindowCandidates] = useState<Array<{ window_handle: number; title: string; process_id: number; process_started_at: number }>>([]);
  const [selectedWindow, setSelectedWindow] = useState('');
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
  const [setupState, setSetupState] = useState<Awaited<ReturnType<PikoClient['setup']>> | null>(null);
  const [setupReasoning, setSetupReasoning] = useState('');
  const [setupVision, setSetupVision] = useState('');
  const [setupConsent, setSetupConsent] = useState(false);
  const [chosenReasoning, setChosenReasoning] = useState('');
  const [chosenVision, setChosenVision] = useState('');
  const [skills, setSkills] = useState<Skill[]>([]);
  const [skillConsent, setSkillConsent] = useState(false);
  const [skillParameterValues, setSkillParameterValues] = useState<Record<string, string>>({});
  const [coachExecutable, setCoachExecutable] = useState('');
  const [coachWindows, setCoachWindows] = useState<Array<{ window_handle: number; title: string; process_id: number }>>([]);
  const [coachWindow, setCoachWindow] = useState('');
  const [coachConsent, setCoachConsent] = useState(false);
  const [coachOverlay, setCoachOverlay] = useState(false);
  const [coachState, setCoachState] = useState<Awaited<ReturnType<PikoClient['coachStatus']>> | null>(null);
  const [teachExecutable, setTeachExecutable] = useState('');
  const [teachConsent, setTeachConsent] = useState(false);
  const [teachSeconds, setTeachSeconds] = useState(30);
  const [recording, setRecording] = useState(false);
  const previousTeachRecording = useRef(false);
  const setupPrompted = useRef(false);
  const [demonstration, setDemonstration] = useState<Demonstration | null>(null);
  const [teachAnalysis, setTeachAnalysis] = useState<TeachAnalysis | null>(null);
  const [teachPlanJson, setTeachPlanJson] = useState('');
  const [teachCorrectionConfirmed, setTeachCorrectionConfirmed] = useState(false);
  const [teachSlug, setTeachSlug] = useState('');
  const [teachDescription, setTeachDescription] = useState('');
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
      if (previousTeachRecording.current && !teach.recording) {
        // A permission revoke, a window switch or a duration timeout can
        // stop Teach without the user clicking the Stop button. Recover its
        // completed manifest instead of leaving the review editor empty.
        void client.latestTeach().then(result => {
          setDemonstration(result);
          if (result.stopped_reason) {
            setNotice(`Teach stopped safely: ${result.stopped_reason.replaceAll('_', ' ')}.`);
          }
        }).catch(() => {});
        setTeachConsent(false);
      }
      previousTeachRecording.current = teach.recording;
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

  useEffect(() => {
    if (!client || !connected) return;
    let active = true;
    const check = () => { void client.coachStatus().then(result => { if (active) setCoachState(result); }).catch(() => {}); };
    check();
    const timer = window.setInterval(check, 2500);
    return () => { active = false; window.clearInterval(timer); };
  }, [client, connected]);

  const discoverCoachWindow = () => {
    if (!client || !coachConsent || !coachExecutable.trim()) return;
    void attempt('coach-windows', async () => {
      const found = await client.windows(coachExecutable.trim());
      setCoachWindows(found);
      setCoachWindow(found.length === 1 ? String(found[0].window_handle) : '');
      if (!found.length) throw new Error('No visible window for that game. Start it first.');
      setNotice(found.length === 1 ? 'Game window identified.' : 'Choose the exact game window.');
    });
  };

  const beginCoaching = () => {
    if (!client || !coachConsent || !coachWindow) return;
    void attempt('coach-start', async () => {
      setCoachState(await client.startCoach(coachExecutable.trim(), Number(coachWindow)) as Awaited<ReturnType<PikoClient['coachStatus']>>);
      setNotice('Visual coaching is active. Focus the game; no desktop input is sent.');
    });
  };

  const endCoaching = () => {
    if (!client) return;
    void attempt('coach-stop', async () => {
      setCoachState(await client.stopCoach() as Awaited<ReturnType<PikoClient['coachStatus']>>);
      if (coachOverlay && isTauri()) await tauriInvoke('set_coach_overlay', { enabled: false });
      setCoachOverlay(false);
      setNotice('Local capture and coaching stopped. No frames were saved.');
    });
  };

  const toggleCoachOverlay = () => {
    if (!isTauri()) { setError('Compact always-on-top overlay requires the installed Piko app.'); return; }
    void attempt('coach-overlay', async () => {
      await tauriInvoke('set_coach_overlay', { enabled: !coachOverlay });
      setCoachOverlay(!coachOverlay);
    });
  };

  const findTargetWindows = () => {
    if (!client || !consent || !executable.trim()) return;
    void attempt('find-windows', async () => {
      const found = await client.windows(executable.trim());
      setWindowCandidates(found);
      setSelectedWindow(found.length === 1 ? String(found[0].window_handle) : '');
      if (found.length === 0) throw new Error('No visible window for this executable. Open the app and try again.');
      setNotice(found.length === 1 ? 'Window found. Piko can inspect it without keeping it in front.' : 'Choose the exact authorized window. Multiple windows share this executable.');
    });
  };

  useEffect(() => {
    if (!client || !connected) return;
    let active = true;
    const check = async () => {
      try {
        const state = await client.setup();
        if (!active) return;
        if (!setupPrompted.current && !state.ollama_installed && state.stage === 'idle') {
          setupPrompted.current = true;
          setLens('system');
        }
        setSetupState(previous => {
          if (previous?.stage !== 'ready' && state.stage === 'ready') {
            void client.models().then(result => {
              if (active) {
                setModels(result.installed);
                setModelSelection({ reasoning: result.reasoning, vision: result.vision });
                setModelError('');
              }
            }).catch(() => {});
          }
          return state;
        });
        setSetupReasoning(old => old || state.hardware.reasoning_model);
        setSetupVision(old => old || state.hardware.vision_model || 'none');
      } catch { /* setup status never blocks the main Workfield */ }
    };
    void check();
    const timer = window.setInterval(() => { void check(); }, 2600);
    return () => { active = false; window.clearInterval(timer); };
  }, [client, connected]);

  const installLocalAI = () => {
    if (!client || !setupConsent || !setupReasoning) return;
    void attempt('setup-local-ai', async () => {
      setSetupState(await client.installLocalAI(setupReasoning,
        setupVision === 'none' ? null : setupVision));
      setNotice('Local installation started. Piko checks the official signature and downloads only the models selected.');
      setSetupConsent(false);
    });
  };

  const startRoute = (event: FormEvent) => {
    event.preventDefault();
    if (!client || !consent || !objective.trim() || !executable.trim()) return;
    void attempt('plan', async () => {
      setFrame(null); setFocusedTarget(null); setEvents([]); setReviewed(false);
      // Discover only the executable explicitly named and authorized by the user.
      // Never guess which of several Firefox windows should be controlled.
      const candidates = await client.windows(executable.trim());
      setWindowCandidates(candidates);
      const selected = candidates.find(w => String(w.window_handle) === selectedWindow);
      const target = selected ?? (candidates.length === 1 ? candidates[0] : null);
      if (!target) throw new Error(candidates.length === 0
        ? 'No visible window matches this executable. Open it first.'
        : 'Several windows match. Select one in the target list before composing a route.');
      const created = await client.createSession(objective.trim(), executable.trim(), target);
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
      previousTeachRecording.current = result.recording;
      setRecording(result.recording); setDemonstration(null); setTeachAnalysis(null);
      setNotice('Recording scoped observations and permitted structural input events. Typed characters are excluded.');
    });
  };

  const stopDemo = () => {
    if (!client) return;
    void attempt('teach-stop', async () => {
      setDemonstration(await client.stopTeach());
      previousTeachRecording.current = false;
      setRecording(false);
      setTeachConsent(false);
    });
  };

  const analyzeDemonstration = () => {
    if (!client || !demonstration) return;
    void attempt('teach-analysis', async () => {
      const analysis = await client.analyzeTeach(demonstration.id);
      setTeachAnalysis(analysis);
      setTeachCorrectionConfirmed(false);
      const actions = analysis.steps.filter(step => step.automation_id).map(step => ({
        kind: 'ui.click',
        automation_id: step.automation_id,
        text: null,
        keys: [],
        timeout_seconds: 5,
        expected: {
          automation_id: step.automation_id,
          property: 'text_equals',
          value: 'REPLACE_WITH_OBSERVED_OUTCOME',
        },
      }));
      setTeachPlanJson(JSON.stringify({
        objective: 'Describe the demonstrated outcome',
        explanation: 'User-reviewed and corrected procedure from a Teach recording',
        actions,
      }, null, 2));
    });
  };

  const saveCorrectedDemonstration = (event: FormEvent) => {
    event.preventDefault();
    if (!client || !demonstration || !teachAnalysis || !teachCorrectionConfirmed) return;
    void attempt('teach-correction', async () => {
      const plan = JSON.parse(teachPlanJson) as Plan;
      await client.saveTeachDraft(
        demonstration.id, teachSlug, teachDescription, plan, teachCorrectionConfirmed);
      setSkills(await client.skills());
      setNotice('Corrected procedure saved as a DRAFT. Run it under a separate approval to test.');
    });
  };

  const storeDraft = (event: FormEvent) => {
    event.preventDefault();
    if (!client || !session?.plan) return;
    void attempt('skill', async () => {
      await client.saveSkill(session.id, slug.trim(), skillDescription.trim());
      setSkills(await client.skills()); setNotice('Draft saved. It has not been generalized or verified as a reusable Skill.');
    });
  };

  const importSkillArchive = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!client || !file) return;
    void attempt('skill-import', async () => {
      if (file.size > 1_000_000) throw new Error('Archive exceeds the 1 MB import limit.');
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(new Error('Cannot read Skill archive.'));
        reader.readAsDataURL(file);
      });
      const encoded = dataUrl.split(',', 2)[1];
      if (!encoded) throw new Error('Invalid Skill archive.');
      await client.importSkill(encoded);
      setSkills(await client.skills());
      setNotice('Imported Skill is a draft; external instructions are never executed.');
    });
  };

  const exportSkillArchive = (name: string) => {
    if (!client) return;
    void attempt('skill-export', async () => {
      const blob = await client.exportSkill(name);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${name}.piko-skill.zip`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 2000);
    });
  };

  const rollbackSkillDraft = (name: string) => {
    if (!client) return;
    void attempt('skill-rollback', async () => {
      const available = await client.skillRevisions(name);
      const last = available.revisions.at(-1);
      if (!last) throw new Error('No archived revision is available.');
      if (!window.confirm(`Restore revision ${last} of ${name} as a new draft?`)) return;
      await client.rollbackSkill(name, last);
      setSkills(await client.skills());
      setNotice('Previous draft restored as a new revision. Verification status is unchanged.');
    });
  };

  const reviewSavedSkill = (name: string) => {
    if (!client || !skillConsent) return;
    void attempt('skill-review', async () => {
      const inputs = skills.find(item => item.name === name)?.parameters ?? [];
      const parameters = Object.fromEntries(inputs.map(key =>
        [key, skillParameterValues[`${name}:${key}`] ?? '']));
      if (inputs.some(key => !parameters[key])) {
        throw new Error('Enter every declared Skill parameter before review.');
      }
      const prepared = await client.reviewSkill(name, parameters);
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

  if (coachOverlay) return <div className="coach-float"><div className="coach-float-heading"><span className="logo-text">piko<span>.</span></span><span>LIVE LOCAL COACH</span></div><div className="coach-live-status">{coachState?.stage || 'Connecting'} · {coachState?.frames || 0} analyzed frames</div><p className="coach-float-advice">{coachState?.advice || 'Focus your approved game window to receive a suggestion.'}</p>{coachState?.error && <p className="inline-error">{coachState.error}</p>}<div className="coach-float-buttons"><button type="button" onClick={toggleCoachOverlay}>Expand</button><button type="button" onClick={endCoaching}>Stop coaching</button></div><p className="coach-float-note">Frames stay on your PC. Keep the game in the foreground.</p></div>;

  return <div className="app-shell">
    <header className="masthead">
      <div className="brand"><span className="brand-icon"><PikoGlyph state={session?.state ?? 'idle'} compact /></span><span className="logo-text">piko<span>.</span></span><span className="brand-divider" /><span className="brand-subtitle">WORKFIELD / ALPHA</span></div>
      <nav className="lens-dial" aria-label="Work modes">{LENSES.map(item => <button type="button" key={item.id} aria-current={lens === item.id ? 'page' : undefined} className={`lens-tab${lens === item.id ? ' lens-tab--active' : ''}`} onClick={() => setLens(item.id)}><small>{item.number}</small>{item.title}</button>)}</nav>
      <div className="head-actions"><span className={`connection-indicator${connected ? '' : ' connection-indicator--off'}`}><span />{connected ? 'LOCAL CONNECTED' : 'OFFLINE'}</span><button type="button" className="kill-switch" onClick={() => client && invoke('emergency', () => client.emergencyStop(), 'Emergency stop requested for all agent sessions.')} disabled={!client || !connected} title="Release inputs and stop every session"><Mark name="stop" size={15} />EMERGENCY STOP</button></div>
    </header>

    <div className="workfield-body">
      <section className="page-heading">
        <div><Kicker index="P / 001">{LENSES.find(item => item.id === lens)?.detail} / Local system</Kicker>
          <h1>{lens === 'work' ? <>Give it a goal.<br /><em>See the whole route.</em></> : lens === 'coach' ? <>See the game.<br /><em>Know the next move.</em></> : lens === 'teach' ? <>Show the process.<br /><em>Keep the knowledge.</em></> : lens === 'skills' ? <>Small lessons.<br /><em>Ready to grow.</em></> : <>Everything local.<br /><em>Nothing hidden.</em></>}</h1>
        </div>
        <div className="heading-right"><span className="heading-cross" aria-hidden="true">✳</span><StatusChip state={connected ? session?.state ?? 'idle' : 'offline'} /><p>Only authorized actions.<br />All outcomes independently verified.</p></div>
      </section>

      {error && <div className="message-banner message-banner--error" role="alert"><span>{error}</span><button type="button" aria-label="Dismiss error" onClick={() => setError('')}><Mark name="close" size={15} /></button></div>}
      {notice && <div className="message-banner" role="status"><span>{notice}</span><button type="button" aria-label="Dismiss notice" onClick={() => setNotice('')}><Mark name="close" size={15} /></button></div>}
      {connected && setupState && !setupState.running && setupState.stage !== 'ready' && !modelSelection.reasoning && <div className="message-banner" role="status">Local AI is not configured. Piko can select a model for this computer and install Ollama on first run. <button type="button" onClick={() => setLens('system')}>Set up local AI</button></div>}
      {!connected && <div className="message-banner message-banner--error" role="alert">Runtime unavailable. No new operations can be sent. <button type="button" onClick={() => void refresh()}>Retry connection</button></div>}

      {lens === 'work' && <>
        <div className="workspace-grid">
          <section className="instruction-panel">
            <div className="panel-top"><Kicker index="A">Intent</Kicker><span className="panel-annotation">YOUR INSTRUCTION</span></div>
            <form onSubmit={startRoute} className="intent-form">
              <label htmlFor="objective">What should Piko accomplish?</label>
              <textarea id="objective" rows={4} maxLength={500} value={objective} onChange={e => setObjective(e.target.value)} placeholder="For example: enter a name in the demo app, save it and confirm the result." disabled={isBlockedByWork} required />
              <div className="intent-target"><label htmlFor="executable">Inside this application</label><div className="target-field"><span className="target-bullet" /><input id="executable" placeholder="application.exe" value={executable} onChange={e => { setExecutable(e.target.value); setConsent(false); setWindowCandidates([]); setSelectedWindow(''); }} disabled={isBlockedByWork} required /></div><small>Any open window · exact executable name (e.g. firefox.exe)</small><button type="button" className="target-discover" onClick={findTargetWindows} disabled={!consent || !executable.trim() || isBlockedByWork}>Find application windows</button>{windowCandidates.length > 0 && <select className="target-picker" aria-label="Authorized application window" value={selectedWindow} onChange={e => setSelectedWindow(e.target.value)} disabled={isBlockedByWork}><option value="">{windowCandidates.length > 1 ? 'Select the correct window' : 'Auto-selected window'}</option>{windowCandidates.map(item => <option key={item.window_handle} value={item.window_handle}>{item.title || item.process_id} · PID {item.process_id}</option>)}</select>}</div>
              <label className="consent-line"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} disabled={isBlockedByWork} /><span>I authorize Piko to inspect this selected application in the background and, after I approve the route, activate its exact window to perform actions. Other applications are excluded.</span></label>
              <button className="primary-button" type="submit" disabled={!consent || !objective.trim() || !executable.trim() || isBlockedByWork || !connected}><span>{busy === 'plan' ? 'Composing route…' : 'Compose a route'}</span><Mark name="arrow" /></button>
            </form>
            <div className="intent-divider" />
            <div className="session-selector"><div className="mini-heading"><Kicker>Recent work</Kicker><span>{recentSessions.length} sessions</span></div>{recentSessions.length ? recentSessions.map(item => <button className={`session-option${session?.id === item.id ? ' session-option--selected' : ''}`} type="button" key={item.id} onClick={() => { setSession(item); setFrame(null); setFocusedTarget(null); setEvents([]); setReviewed(false); }}><span className="session-option-name">{item.objective}</span><span className="session-option-detail">{item.app_executable}<span>·</span>{item.state.replaceAll('_', ' ')}</span></button>) : <p className="muted-empty">No local sessions yet.</p>}</div>
          </section>

          <section className="route-panel"><div className="panel-top"><Kicker index="B">The route</Kicker><span className="route-count">{session?.plan ? `${session.next_action} / ${session.plan.actions.length} CONFIRMED` : 'NO ROUTE YET'}</span></div><RouteView session={session} events={events} focusedTarget={focusedTarget} onFocus={setFocusedTarget} frameAvailable={frame !== null} />
            <div className="route-actions">
              {session?.state === 'waiting_for_user' && <div className="approval-area"><label className="consent-line"><input type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)} /><span>I've reviewed the route and authorize these actions.</span></label><button className="action-confirm" type="button" disabled={!reviewed || !!busy || !connected} onClick={() => client && invoke('execute', async () => {
                  if (isTauri() && session.allow_activate && session.target_window_handle && session.target_process_id) {
                    await tauriInvoke('focus_selected_window', {
                      windowHandle: session.target_window_handle, processId: session.target_process_id,
                    });
                  }
                  await client.execute(session.id);
                })}>Execute reviewed route <Mark name="arrow" /></button></div>}
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
          <div className="teach-limits"><Kicker>What this version records</Kicker><p>Opt-in foreground screenshots, UIA observations and permitted click/scroll/special-key events on Windows. Raw typed characters are excluded. Inferred steps are tentative until reviewed and tested.</p></div>
          {demonstration && <div className="demo-result"><div><Kicker>Last recording</Kicker><h3>{demonstration.frames} captured observations</h3><p>{demonstration.limitations.join('. ')}</p>{demonstration.stopped_reason && <p className="operation-note">Recording ended for safety: {demonstration.stopped_reason.replaceAll('_', ' ')}.</p>}<button type="button" className="system-secondary" disabled={!!busy || recording} onClick={analyzeDemonstration}>Analyze evidence <Mark name="arrow" size={15} /></button></div><button type="button" disabled={!!busy || recording} onClick={() => client && invoke('delete-demo', async () => { await client.deleteTeach(demonstration.id); setDemonstration(null); setTeachAnalysis(null); }, 'Local demonstration deleted.')}><Mark name="trash" size={16} /> Delete</button></div>}
          {teachAnalysis && <section className="skill-seed" aria-label="Teach correction editor">
            <div><Kicker>Evidence → correction</Kicker><h3>{teachAnalysis.input_events} permitted events · {teachAnalysis.steps.length} candidate steps</h3><p>{teachAnalysis.uncertainties.join('. ')}. Unresolved steps must be supplied manually; this is not autonomous learning yet.</p></div>
            <form className="skill-form" onSubmit={saveCorrectedDemonstration}>
              <label htmlFor="teach-draft-slug">Draft name</label>
              <input id="teach-draft-slug" pattern="[a-z0-9][a-z0-9-]{0,63}" value={teachSlug} onChange={e => setTeachSlug(e.target.value)} required />
              <label htmlFor="teach-draft-desc">Description</label>
              <input id="teach-draft-desc" value={teachDescription} onChange={e => setTeachDescription(e.target.value)} required />
              <TeachStepEditor value={teachPlanJson}
                targets={teachAnalysis.observed_targets ?? []}
                onChange={value => { setTeachPlanJson(value); setTeachCorrectionConfirmed(false); }} />
              <details className="teach-advanced-editor"><summary>Advanced typed JSON procedure</summary>
                <label htmlFor="teach-corrected-plan">Strict JSON — edited steps still require observable UIA targets</label>
                <textarea id="teach-corrected-plan" rows={10} value={teachPlanJson}
                  onChange={e => { setTeachPlanJson(e.target.value); setTeachCorrectionConfirmed(false); }} />
              </details>
              <label className="consent-line"><input type="checkbox"
                checked={teachCorrectionConfirmed} onChange={e => setTeachCorrectionConfirmed(e.target.checked)} />
                <span>I reviewed and corrected every selector, parameter and expected outcome. This remains an unverified draft.</span>
              </label>
              <button type="submit" disabled={!!busy || !connected || teachAnalysis.input_events < 1 || !teachCorrectionConfirmed}>Save reviewed draft <Mark name="plus" size={15} /></button>
            </form>
          </section>}
        </div>
        <section className="teach-controls"><div className="panel-top"><Kicker index="B">Your recording boundary</Kicker></div><h2>You show.<br /><em>Piko observes.</em></h2><form onSubmit={createDemo}><label htmlFor="teach-app">Approved foreground application</label><input id="teach-app" placeholder="application.exe" value={teachExecutable} onChange={e => { setTeachExecutable(e.target.value); setTeachConsent(false); }} disabled={recording || !!busy} required /><label htmlFor="teach-duration">Maximum duration</label><div className="duration-choices" id="teach-duration">{[15, 30, 60, 120].map(seconds => <button key={seconds} type="button" aria-pressed={teachSeconds === seconds} className={teachSeconds === seconds ? 'duration--chosen' : ''} onClick={() => setTeachSeconds(seconds)} disabled={recording || !!busy}>{seconds}s</button>)}</div><label className="consent-line"><input type="checkbox" checked={teachConsent} onChange={e => setTeachConsent(e.target.checked)} disabled={recording || !!busy} /><span>I authorize time-limited recording of this foreground application.</span></label>{recording ? <button className="primary-button primary-button--stop" type="button" disabled={!!busy} onClick={stopDemo}><Mark name="stop" /> Stop watching</button> : <button className="primary-button" type="submit" disabled={!teachConsent || !teachExecutable.trim() || isBlockedByWork || !connected}><Mark name="eye" /> Watch me</button>}</form></section>
      </div>}

      {lens === 'skills' && <section className="library-board"><div className="panel-top"><Kicker index="A">Procedural library</Kicker><span className="panel-annotation">LOCAL FILES ONLY</span></div><div className="library-summary"><div><h2>{skills.length.toString().padStart(2, '0')}<span> / saved drafts and skills</span></h2><p>Every item keeps its verification status. Drafts have not been proven to generalize.</p></div><button type="button" onClick={() => client && invoke('skills', async () => { setSkills(await client.skills()); })} disabled={!!busy || !connected}><Mark name="refresh" size={16} /> Reload library</button></div><label htmlFor="skill-import-zip">Import locally reviewed Skill archive (.zip)</label><input id="skill-import-zip" type="file" accept=".zip" disabled={!!busy || !connected} onChange={importSkillArchive} />
        <label className="consent-line"><input type="checkbox" checked={skillConsent} disabled={!!busy || !connected} onChange={e => setSkillConsent(e.target.checked)} /><span>I authorize Piko to inspect the foreground application before reviewing a saved Skill. Execution requires a second approval.</span></label>{skills.length ? <div className="library-list">{skills.map(item => <article key={item.name} className="library-card"><div className="library-glyph">✳</div><div><span className="library-state">{item.status.toUpperCase()} / {item.version}</span><h3>{item.name}</h3><p>{item.description}</p><span className="library-info">{item.executable} · {item.actions} actions</span>
            {!!item.parameters?.length && <div className="skill-param-grid" aria-label="Skill input parameters">{item.parameters.map(parameter => <label className="skill-param-control" key={parameter} htmlFor={`skill-param-${item.name}-${parameter}`}><span>{parameter}</span><input id={`skill-param-${item.name}-${parameter}`} type="text" autoComplete="off" maxLength={1000} placeholder={`Value for ${parameter}`} value={skillParameterValues[`${item.name}:${parameter}`] ?? ''} onChange={e => setSkillParameterValues(previous => ({ ...previous, [`${item.name}:${parameter}`]: e.target.value }))} disabled={!!busy || !connected} /></label>)}</div>}
            <div className="execution-controls">
              <button type="button" className="system-secondary" disabled={!skillConsent || !!busy || !connected || (item.parameters ?? []).some(parameter => !(skillParameterValues[`${item.name}:${parameter}`] ?? ''))} onClick={() => reviewSavedSkill(item.name)}>Review procedure <Mark name="arrow" size={15} /></button>
              <button type="button" className="system-secondary" disabled={!!busy || !connected} onClick={() => exportSkillArchive(item.name)}>Export ZIP</button>
              <button type="button" className="system-secondary" disabled={!!busy || !connected || item.status !== 'draft'} onClick={() => rollbackSkillDraft(item.name)}>Rollback draft</button>
              <button type="button" className="system-secondary" disabled={!!busy || !connected} onClick={() => client && invoke('skill-history', async () => {
                const history = await client.skillHistory(item.name);
                setNotice(`${item.name}: ${history.length} executions recorded; ${history.filter(x => x.completed).length} completed. No automatic certification.`);
              })}>History</button>
            </div></div></article>)}</div> : <div className="library-empty"><span className="library-star">✳</span><h3>Nothing here. Yet.</h3><p>Once you save a reviewed route, its Markdown Skill draft will appear here.</p><button type="button" onClick={() => setLens('work')}>Compose a route <Mark name="arrow" size={17} /></button></div>}</section>}

      {lens === 'coach' && <section className="coach-panel"><div className="panel-top"><Kicker index="LIVE">Local vision coaching</Kicker><span className="panel-annotation">NO CLOUD / NO INPUT / NO RECORDINGS</span></div><h2>Your game stays in control.</h2><p>Piko analyzes only the selected game window while it is foreground and offers concise advice. Frames are processed by your local vision model and immediately discarded. Fullscreen-exclusive titles may block capture; borderless/windowed mode is recommended.</p><div className="coach-controls"><label htmlFor="coach-app">Game executable</label><input id="coach-app" placeholder="game.exe" value={coachExecutable} onChange={e => { setCoachExecutable(e.target.value); setCoachWindows([]); setCoachWindow(''); setCoachConsent(false); }} disabled={!!coachState?.active} /><label className="consent-line"><input type="checkbox" checked={coachConsent} onChange={e => setCoachConsent(e.target.checked)} disabled={!!coachState?.active} /><span>I authorize Piko to capture frames of this exact game window for up to 30 minutes, process them exclusively with local Ollama, and stop immediately on request. No clicks or keystrokes will be sent.</span></label><button type="button" className="system-secondary" onClick={discoverCoachWindow} disabled={!coachConsent || !coachExecutable.trim() || !!busy || !!coachState?.active}>Find game windows</button>{coachWindows.length > 0 && <select aria-label="Game window" value={coachWindow} onChange={e => setCoachWindow(e.target.value)} disabled={!!coachState?.active}><option value="">Select a game window</option>{coachWindows.map(w => <option key={w.window_handle} value={w.window_handle}>{w.title || 'Untitled'} · PID {w.process_id}</option>)}</select>}<div className="coach-actions">{coachState?.active ? <><button className="primary-button primary-button--stop" type="button" onClick={endCoaching}>Stop local capture</button><button className="system-secondary" type="button" onClick={toggleCoachOverlay}>Compact always-on-top advice</button></> : <button className="primary-button" type="button" onClick={beginCoaching} disabled={!coachConsent || !coachWindow || !modelSelection.vision || !!busy}>Start visual coaching <Mark name="arrow" /></button>}</div>{!modelSelection.vision && <p className="inline-error">Choose or install a local vision model in System first.</p>}<div className="coach-evidence"><strong>{coachState?.stage || 'Not started'}</strong><span>{coachState?.frames || 0} analyzed frames · Most recent: {coachState?.observed_at ? timeString(coachState.observed_at) : 'None'}</span></div><p className="coach-advice">{coachState?.advice || 'Advice will appear here once the authorized game window is visible in the foreground.'}</p>{coachState?.error && <p className="inline-error">{coachState.error}</p>}</div></section>}

      {lens === 'system' && <div className="system-board"><section className="system-card setup-card"><Kicker index="00">First-run setup</Kicker><h2>Intelligence, installed locally.</h2><p>Piko recommends models using RAM, CPU and detected NVIDIA VRAM. You can change them before downloading. No screenshots or prompts leave your computer.</p>{setupState ? <><div className="system-property"><span>RAM / CPU</span><strong>{setupState.hardware.ram_gb} GB / {setupState.hardware.cpu_cores} cores</strong></div><div className="system-property"><span>GPU VRAM</span><strong>{setupState.hardware.gpu_vram_gb === null ? 'Not detected' : `${setupState.hardware.gpu_vram_gb} GB`}</strong></div><div className="system-property"><span>Free disk</span><strong>{setupState.hardware.free_disk_gb} GB</strong></div><p className="setup-hint">{setupState.hardware.note}</p><label htmlFor="setup-reasoning">Recommended reasoning model</label><select id="setup-reasoning" value={setupReasoning} onChange={e => { setSetupReasoning(e.target.value); setSetupConsent(false); }} disabled={setupState.running}><option value="qwen2.5:1.5b">Qwen 2.5 · 1.5B (light)</option><option value="qwen3:4b">Qwen 3 · 4B (balanced)</option><option value="qwen3:8b">Qwen 3 · 8B (powerful)</option></select><label htmlFor="setup-vision">Local vision model</label><select id="setup-vision" value={setupVision} onChange={e => { setSetupVision(e.target.value); setSetupConsent(false); }} disabled={setupState.running}><option value="none">None (text / UIA only)</option><option value="qwen3-vl:2b-instruct">Qwen 3 VL · 2B (screen analysis)</option></select><label className="consent-line"><input type="checkbox" checked={setupConsent} onChange={e => setSetupConsent(e.target.checked)} disabled={setupState.running} /><span>Install the official signed Ollama runtime if missing, and download the selected models from the Ollama registry. This requires internet access, disk space and may use several GB.</span></label><button type="button" className="primary-button" disabled={!setupConsent || setupState.running || !!busy} onClick={installLocalAI}>{setupState.running ? 'Installing local AI…' : 'Install recommended local AI'} <Mark name="arrow" /></button><p className="setup-hint">Stage: {setupState.stage} {setupState.running ? `· ${setupState.progress}%` : ''} · Estimated model data {setupState.hardware.estimate_download_gb} GB</p>{setupState.error && <p className="inline-error" role="alert">{setupState.error}</p>}{setupState.stage === 'ready' && <p className="setup-ready">Local inference ready: {setupState.reasoning}</p>}</> : <p>Checking local system…</p>}</section><section className="system-card"><Kicker index="01">Runtime</Kicker><h2>Local by design.</h2><div className="system-property"><span>Connection</span><strong>{connected ? 'Loopback / active' : 'Disconnected'}</strong></div><div className="system-property"><span>Transport</span><strong>127.0.0.1:{backendPort}</strong></div><div className="system-property"><span>Host platform</span><strong>{health?.platform || 'Unavailable'}</strong></div><div className="system-property"><span>Active input sessions</span><strong>{health ? health.active_session_count : 'Unknown'}</strong></div><button type="button" className="system-secondary" onClick={() => { setToken(''); setHealth(null); setFrame(null); setSession(null); setConnected(false); }}><Mark name="close" size={16} /> Disconnect this window</button></section>
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
