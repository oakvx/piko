"""Human-facing Windows application catalog, with safe Start Menu launching.

The catalog contains no screenshot pixels and never exposes filesystem paths.
An app ID resolves ONLY to an existing Start Menu shortcut on the local PC;
an executable/path supplied by the frontend is never used to launch anything.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import sys


FRIENDLY_NAMES = {
    "firefox.exe": "Firefox",
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "notepad.exe": "Blocco note",
    "notepad++.exe": "Notepad++",
    "code.exe": "Visual Studio Code",
    "winword.exe": "Microsoft Word",
    "excel.exe": "Microsoft Excel",
    "powerpnt.exe": "Microsoft PowerPoint",
    "explorer.exe": "Esplora file",
    "discord.exe": "Discord",
    "spotify.exe": "Spotify",
    "steam.exe": "Steam",
    "vlc.exe": "VLC",
    "mspaint.exe": "Paint",
    "calc.exe": "Calcolatrice",
    "ms-teams.exe": "Microsoft Teams",
    "teams.exe": "Microsoft Teams",
    "obs64.exe": "OBS Studio",
    "blender.exe": "Blender",
    "photoshop.exe": "Adobe Photoshop",
    "illustrator.exe": "Adobe Illustrator",
    "devenv.exe": "Visual Studio",
    "windowsterminal.exe": "Terminale Windows",
}


def display_name(executable: str) -> str:
    """Presentation hint only. Authorization *always* uses exact exe/HWND/PID."""
    key = Path(executable).name.casefold()
    if key in FRIENDLY_NAMES:
        return FRIENDLY_NAMES[key]
    label = re.sub(r"(?i)\.exe$", "", key).replace("_", " ").replace("-", " ")
    return label.strip().title()[:70] or "Applicazione"


def _start_menu_roots() -> tuple[Path, ...]:
    if sys.platform != "win32":
        return ()
    home = Path.home()
    appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    common = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    return (
        appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        common / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    )


def _shortcuts() -> dict[str, tuple[Path, str]]:
    """Bounded, shallow scan: an app launcher is explicitly user-selected."""
    choices: dict[str, tuple[Path, str]] = {}
    for root in _start_menu_roots():
        if not root.is_dir():
            continue
        count = 0
        # Skip symlinked directories and shortcut links outside the Start Menu.
        for base, folders, files in os.walk(root, followlinks=False):
            folders[:] = [f for f in folders if not (Path(base) / f).is_symlink()]
            if len(Path(base).relative_to(root).parts) > 5:
                folders.clear()
                continue
            for filename in files:
                count += 1
                if count > 2500:
                    break
                path = Path(base) / filename
                if path.suffix.casefold() != ".lnk" or path.is_symlink():
                    continue
                title = path.stem.strip()
                if not title or len(title) > 100 or re.search(
                    r"(?i)\b(uninstall|uninstaller|remove|disinstalla|disinstallazione)\b",
                    title,
                ):
                    continue
                # Hash, not raw paths, cross the loopback API boundary.
                app_id = hashlib.sha256(str(path.absolute()).casefold().encode(
                    "utf-8")).hexdigest()[:24]
                choices[app_id] = (path, title)
            if count > 2500:
                break
    return choices


def list_installed_apps() -> list[dict]:
    result = [
        {"id": app_id, "name": name}
        for app_id, (_, name) in _shortcuts().items()
    ]
    return sorted(result, key=lambda item: item["name"].casefold())[:350]


def launch_installed_app(app_id: str) -> dict:
    """Launch only the exact shortcut offered by this catalog, on user click."""
    if sys.platform != "win32":
        raise RuntimeError("Installed application launching requires Windows")
    choices = _shortcuts()
    if app_id not in choices:
        raise ValueError("Selected installed application is no longer available")
    path, name = choices[app_id]
    if not path.is_file() or path.is_symlink() or path.suffix.casefold() != ".lnk":
        raise ValueError("Selected application shortcut is no longer trusted")
    # Launching a Windows Start Menu link is equivalent to opening it manually.
    # Windows UAC, if required, remains an explicit OS-controlled prompt.
    os.startfile(str(path), "open")
    return {"launched": True, "name": name}
