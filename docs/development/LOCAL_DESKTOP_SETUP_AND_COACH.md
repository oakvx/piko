# Background applications, local Ollama setup and Live Coach

Piko remains local-first. **The frontend does not send prompts, screenshots,
model outputs or desktop events to a cloud service.** Model downloads do
contact the official Ollama registry, and first-run runtime installation
downloads the official signed Ollama Windows installer. Internet access is
needed to obtain packages; inference after installation uses
`http://127.0.0.1:11434`.

## Windows application selection

1. In Workfield, enter the goal and the exact executable basename (e.g.
   `firefox.exe` or `notepad.exe`) and tick the authorization box.
2. Piko enumerates top-level windows of **that executable only**. For multiple
   browser or document windows select the correct window by title/PID.
   A browser with 30+ subprocesses normally has far fewer top-level windows.
3. UI Automation reads the selected window without requiring it to be in the
   foreground. Piko pins the HWND, PID and process-creation time.
4. The route appears for a **separate execution review**. Only when the user
   explicitly clicks Execute does the Tauri host request foreground focus
   for the exact window. The Python input layer independently rechecks its
   identity, checks user grants, and rejects any unexpected foreground switch.
5. Native Windows may refuse activation of a protected or elevated window;
   Piko fails closed and asks the user to focus it manually. Elevated/admin
   windows and restricted game processes may be inaccessible.

**Background UIA is always available when Windows permits it.** On supported
Windows/Pillow versions Piko additionally attempts HWND-specific background
pixel capture via Pillow ImageGrab, with process-lifetime verification both
before and after capture. Some GPU-accelerated, protected, minimized or
exclusive-fullscreen windows provide blank pixels: in this case Piko safely
falls back to its semantic UIA tree without capturing the unrelated
foreground application. No background screenshots are fabricated.

For browser tab closure, the limited keyboard allowlist now permits reviewed
`Ctrl+W`, but the agent must observe a meaningful window-title change before
claiming success. A last-tab closure or unchanged tab title may be reported as
unverified rather than falsely confirmed.

## First-run local AI installation

First run directs unconfigured Windows installations to System → First-run setup.

- Piko reads coarse local RAM, CPU cores, free disk and NVIDIA VRAM (when
  `nvidia-smi` is available). This is a conservative recommendation, not a
  benchmark or a guarantee of speed.
- It proposes Qwen 2.5 1.5B for constrained hardware, Qwen 3 4B for general
  desktops, Qwen 3 8B for more capable NVIDIA GPUs, and optionally Qwen 3 VL
  2B for image analysis.
- The user reviews model choices and explicitly authorizes the external
  downloads. Missing Ollama is downloaded from its official Windows address,
  its **Authenticode signature must validate as Ollama**, and the official
  installer is executed silently. Missing models are pulled through the
  locally running Ollama service. Failed checks stop installation; unsigned
  fallbacks are never executed.
- The status UI reports download/install stages and errors. No inference
  account or API key is required. Cloud model tags are not accepted by the
  installer-model allowlist.
- Ollama is a **separately installed dependency** with its own updater and
  Windows uninstaller. Piko must not silently uninstall or destroy an existing
  Ollama installation or shared models. The Piko NSIS installer does not bundle
  the multi-gigabyte Ollama runtime; first-run setup is a single consented
  installation flow, subject to internet availability and free disk space.

The current setup model sizes are approximate. Some systems will have less
usable RAM/VRAM than reported; a user can choose a smaller model manually.

## Coach: local game observations

The Coach lens is **advice-only**:

1. Install/select a vision-capable local Ollama model in System.
2. Enter the game executable, consent to a maximum 30-minute read-only
   session, select its precise window, and start.
3. Return focus to the game. Piko samples **only when that exact HWND/PID is
   foreground**, never a foreign application. Each frame is acquired through HWND-specific capture (not an unrestricted
   desktop crop), supplied directly to the loopback Ollama vision model and
   discarded after analysis; no local screenshot history or upload is created.
4. Optionally enable the compact, always-on-top Tauri advice window and
   return focus to the game. A small latency is expected: minimum sample
   interval is four seconds, plus actual local inference time.
5. Stop from the overlay or Coach lens. Expiration, lost/replaced target
   identity and password controls revoke capture. No mouse/keyboard actions
   are ever issued by Coach.

This is **not** low-latency video streaming or a game-internal overlay.
Borderless/windowed display is more reliable; exclusive fullscreen, protected
game rendering and anti-cheat may block screenshots or overlays. Piko does
not bypass anti-cheat, OS security boundaries or GPU protection.

## Validation before stable release

Run the Windows GUI suite and local Ollama smoke separately on Windows 10
22H2 and Windows 11 x64. Test Firefox multiple-window selection, Notepad in
background, user-refused foreground activation, process reuse, permissions
and emergency stop. Test Ollama signed installer integrity and failure
recovery on a clean VM and adequate/low-disk machines. Test Coach foreground
changes, window close, model timeout and stop. Hosted Windows CI is not
equivalent to this physical/VM acceptance.
