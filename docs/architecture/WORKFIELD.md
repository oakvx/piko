# Piko Workfield · original interface contract

The interface is not a chatbot wrapper. Piko is an operator whose actions need
human-legible boundaries. The Workfield organizes the application around a
**spatial trace** of intent, action and evidence rather than chatbot messages,
KPI widgets, or decorative agent chatter.

## The four lenses

1. **Workfield / direct** — a written intent is bound to exactly one approved
   foreground executable; Piko generates a route and waits for explicit review.
   Each action is paired with an expected observable outcome. The verification
   ledger records backend events, not model-generated progress claims. The user
   can request a single authorized screen capture, pause, stop or use the
   persistent emergency stop at the top edge.
2. **Demonstrate / observe** — a separate studio whose visible recording boundary
   is always clear. This alpha records screenshots and UIA snapshots, not input
   events or learned generalized procedures. No simulated learning progress.
3. **Library / recall** — displays real local Skill metadata. Unverified drafts
   are labeled as drafts; they do not become “learned” merely by being saved.
4. **System / inspect** — local runtime status, installed Ollama models and
   security controls are reported only when the backend returns data.

## Interaction and visual language

- Spacious paper-colored environment, dark ink, restrained lavender and mint.
- Custom Piko vector companion: a faceplate embedded in a lavender creature,
  with state-dependent restrained animations. Its state comes from sessions.
- Numbered trace nodes show the specific action kind, target selector and
  verification predicate. Mint is reserved for *actually verified* outcomes.
- No pre-filled tasks, simulated screenshots, invented performance metrics,
  fake model lists, unimplemented chat send controls or arbitrary success banners.
- All primary controls call documented loopback API operations. Each can
  report a real error. Capture is *on demand*; it does not poll or persist frames.
- Token is entered by the user from `piko serve`, kept in React memory only,
  and cleared on disconnection. The frontend does not persist it to disk.
- Responsive down to approximately 930px (Tauri minimum desktop width), with
  a condensed arrangement for smaller browser previews. Reduced-motion support.

## Architecture of UI code

- `src/types.ts`: typed structures mirroring Pydantic responses.
- `src/client.ts`: authenticated same-device client, structured HTTP errors.
- `src/App.tsx`: control logic and original spatial presentation.
- `src/PikoGlyph.tsx`: original SVG companion, no external asset dependencies.
- `src/styles.css`: custom visual system, not a premade AI dashboard kit.
- `src-tauri`: minimal Windows wrapper with window-only capabilities.

The backend is a separately started process in this milestone. The Tauri app
**does not** silently launch, install or download Python, Ollama or any model.

## Verification boundary

Python API tests cover token authorization and an opt-in screenshot request.
The React UI and installer have not yet been built on Windows. No screenshot
streaming, production chat, procedural induction, game mode, or always-on-top
companion window are claimed. These are distinct follow-on milestones.

### Evidence lens

Select **Locate on snapshot** on any planned action after taking an authorized
capture. If Windows UI Automation reported a bounding rectangle for that action's
selector, Piko projects it onto the captured screenshot. The projection is
read-only: it never invents action coordinates, dispatches input or authorizes
an action. Missing/ambiguous coordinates produce a visible diagnostic. This
projection is an aid to review, not proof of current target location; a fresh
UIA observation still gates actual execution. DPI and mixed-monitor alignment
must be tested on Windows hardware before relying on precise outlines.
