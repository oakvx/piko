//! Tauri shell for the original Workfield UI.
//! The Windows installer ships a Python sidecar, not a cloud backend.
use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::{process::CommandChild, ShellExt};

#[derive(Clone, serde::Serialize)]
struct BackendConfig {
    token: String,
    port: u16,
}

#[derive(Default)]
struct BackendState {
    config: Option<BackendConfig>,
    child: Mutex<Option<CommandChild>>,
}

#[tauri::command]
fn backend_config(state: tauri::State<'_, BackendState>) -> Option<BackendConfig> {
    state.config.clone()
}

/// Called ONLY after the user clicked a reviewed route's Execute control.
/// The backend independently verifies exact HWND, PID and process creation time
/// before *any* native input. Never accepts window titles or executable paths.
#[cfg(target_os = "windows")]
#[tauri::command]
fn focus_selected_window(window_handle: isize, process_id: u32) -> Result<(), String> {
    #[link(name = "user32")]
    extern "system" {
        fn IsWindow(hwnd: isize) -> i32;
        fn GetWindowThreadProcessId(hwnd: isize, pid: *mut u32) -> u32;
        fn SetForegroundWindow(hwnd: isize) -> i32;
    }
    if window_handle <= 0 || process_id == 0 {
        return Err("No reviewed native window to focus".into());
    }
    let mut actual = 0u32;
    let valid = unsafe {
        IsWindow(window_handle) != 0 &&
        GetWindowThreadProcessId(window_handle, &mut actual) != 0 &&
        actual == process_id
    };
    if !valid {
        return Err("Reviewed window is no longer owned by its original process".into());
    }
    if unsafe { SetForegroundWindow(window_handle) } == 0 {
        return Err("Windows refused foreground activation; no input was sent".into());
    }
    Ok(())
}

#[cfg(not(target_os = "windows"))]
#[tauri::command]
fn focus_selected_window(_window_handle: isize, _process_id: u32) -> Result<(), String> {
    Err("Native window activation requires Windows".into())
}

/// Explicit, user-invoked compact always-on-top view for local game advice.
/// Never captures the desktop or injects input; those remain in the backend.
#[tauri::command]
fn set_coach_overlay(window: tauri::Window, enabled: bool) -> Result<(), String> {
    if enabled {
        window.set_size(tauri::LogicalSize::new(420.0, 340.0))
            .map_err(|e| e.to_string())?;
        window.set_always_on_top(true).map_err(|e| e.to_string())?;
    } else {
        window.set_always_on_top(false).map_err(|e| e.to_string())?;
        window.set_size(tauri::LogicalSize::new(1380.0, 850.0))
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let mut backend = BackendState::default();
            // During development, `piko serve` may be launched independently.
            // Release builds launch the packaged sidecar automatically.
            #[cfg(not(debug_assertions))]
            {
                let listener = std::net::TcpListener::bind("127.0.0.1:0")?;
                let port = listener.local_addr()?.port();
                drop(listener);
                let token = format!("{}{}", uuid::Uuid::new_v4().simple(), uuid::Uuid::new_v4().simple());
                let (mut events, child) = app
                    .shell()
                    .sidecar("piko-agent")?
                    .args(["serve", "--port", &port.to_string()])
                    .env("PIKO_CONTROL_TOKEN", &token)
                    .spawn()?;
                // Drain stderr/stdout without forwarding sensitive output to the UI.
                tauri::async_runtime::spawn(async move {
                    while events.recv().await.is_some() {}
                });
                backend.config = Some(BackendConfig { token, port });
                *backend.child.lock().expect("backend process lock poisoned") = Some(child);
            }
            app.manage(backend);
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::Destroyed) {
                let state = window.state::<BackendState>();
                if let Ok(mut child) = state.child.lock() {
                    if let Some(process) = child.take() {
                        let _ = process.kill();
                    }
                };
            }
        })
        .invoke_handler(tauri::generate_handler![backend_config, set_coach_overlay, focus_selected_window])
        .run(tauri::generate_context!())
        .expect("Piko desktop runtime failed");
}
