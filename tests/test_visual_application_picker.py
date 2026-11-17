"""The application switcher is read-only until the user chooses a target."""
from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from piko import app_catalog
from piko.window_picker import WindowClickPicker


class FakeWindows:
    def __init__(self):
        self.target = {
            "window_handle": 1234, "process_id": 66,
            "process_started_at": 123456.5, "executable": "firefox.exe",
            "display_name": "Firefox", "title": "A tab - Firefox",
            "is_foreground": False,
        }
        self.calls = []

    def list_windows(self, executable=None):
        self.calls.append(executable)
        if executable is not None and executable != "firefox.exe":
            return []
        return [self.target]

    def window_at(self, x, y):
        self.calls.append((x, y))
        return self.target if x == 71 else None

    def emergency_release(self):
        pass


class Listener:
    instances = []

    def __init__(self, on_click):
        self.callback = on_click
        self.started = False
        self.stopped = False
        self.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


def test_click_picker_ignores_other_buttons_requires_real_new_left_click(monkeypatch):
    from piko import window_picker
    clock = [100.0]
    monkeypatch.setattr(window_picker.time, "monotonic", lambda: clock[0])
    Listener.instances.clear()
    windows = FakeWindows()
    picker = WindowClickPicker(windows, listener_factory=Listener)
    assert picker.start()["status"] == "listening"
    hook = Listener.instances[-1]
    assert hook.started
    hook.callback(71, 88, "left", True)  # opening click is ignored
    assert picker.status()["window"] is None
    clock[0] += 1
    hook.callback(71, 88, "right", True)
    hook.callback(71, 88, "left", False)
    assert picker.status()["status"] == "listening"
    hook.callback(71, 88, "left", True)
    assert picker.status()["status"] == "selected"
    assert picker.status()["window"]["process_started_at"] == 123456.5
    assert hook.stopped
    assert windows.calls == [(71, 88)]
    hook.callback(71, 88, "left", True)  # no repeated selection
    assert picker.status()["status"] == "selected"


def test_picker_cancel_and_expiry_stop_hook(monkeypatch):
    from piko import window_picker
    monkeypatch.setattr(window_picker.time, "monotonic", lambda: 20.0)
    Listener.instances.clear()
    picker = WindowClickPicker(FakeWindows(), listener_factory=Listener)
    picker.start(duration=6)
    with pytest.raises(ValueError, match="already running"):
        picker.start()
    hook = Listener.instances[-1]
    assert picker.cancel()["status"] == "cancelled"
    assert hook.stopped
    picker.start(duration=6)
    second = Listener.instances[-1]
    picker._expire(picker._generation)
    assert picker.status()["status"] == "expired"
    assert second.stopped


def test_catalog_friendly_names_do_not_replace_executable_identity():
    assert app_catalog.display_name("FIREFOX.EXE") == "Firefox"
    assert app_catalog.display_name("notepad.exe") == "Blocco note"
    assert app_catalog.display_name("unique_helper.exe") == "Unique Helper"


def test_start_menu_app_ids_are_opaque_and_launch_requires_known_id(monkeypatch, tmp_path):
    root = tmp_path / "Programs"
    root.mkdir()
    good = root / "Notepad++.lnk"
    good.write_bytes(b"fake shortcut; never executed here")
    (root / "Uninstall Something.lnk").write_bytes(b"blocked")
    monkeypatch.setattr(app_catalog, "_start_menu_roots", lambda: (root,))
    launched = []
    monkeypatch.setattr(app_catalog, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(app_catalog.os, "startfile", lambda path, verb: launched.append((path, verb)), raising=False)
    apps = app_catalog.list_installed_apps()
    assert len(apps) == 1
    assert apps[0]["name"] == "Notepad++"
    assert apps[0]["id"] == hashlib.sha256(str(good.absolute()).casefold().encode()).hexdigest()[:24]
    assert "/" not in apps[0]["id"] and "\\" not in apps[0]["id"]
    with pytest.raises(ValueError):
        app_catalog.launch_installed_app("C:/Windows/System32/cmd.exe")
    assert launched == []
    result = app_catalog.launch_installed_app(apps[0]["id"])
    assert result == {"launched": True, "name": "Notepad++"}
    assert launched == [(str(good), "open")]


class FixtureInference:
    async def close(self):
        pass
    async def models(self):
        return []


@pytest.mark.asyncio
async def test_catalog_endpoint_is_token_gated_and_keeps_window_process_binding(tmp_path, monkeypatch):
    from piko.api import create_app
    from piko import api
    fake = FakeWindows()
    monkeypatch.setattr(api, "list_installed_apps", lambda: [{"id": "a" * 24, "name": "Firefox"}])
    app = create_app(token="k" * 36, reasoning_model="fixture",
                     desktop=fake, inference=FixtureInference(), root=tmp_path)
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/windows/catalog")).status_code == 401
            assert (await client.get("/apps/installed")).status_code == 401
            auth = {"Authorization": "Bearer " + "k" * 36}
            result = await client.get("/windows/catalog", headers=auth)
            assert result.status_code == 200
            assert result.json() == [fake.target]
            assert fake.calls == [None]
            installed = await client.get("/apps/installed", headers=auth)
            assert installed.json()[0]["name"] == "Firefox"
            denied = await client.post("/apps/launch", headers=auth,
                json={"app_id": "a" * 24, "confirmed": False})
            assert denied.status_code == 403
            # An enumerated window is not yet an input grant.
            created = await client.post("/sessions", headers=auth, json={
                "objective": "Close the tab", "executable": "firefox.exe",
                "target_window_handle": fake.target["window_handle"],
                "target_process_id": fake.target["process_id"],
                "target_process_started_at": fake.target["process_started_at"],
                "allow_activate": True,
            })
            assert created.status_code == 200
            sid = created.json()["id"]
            planning = await client.post(f"/sessions/{sid}/plan", headers=auth)
            assert planning.status_code == 409
    finally:
        app.state.agent.memory.close()
