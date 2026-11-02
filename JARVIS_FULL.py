"""
╔══════════════════════════════════════════════════════════════════╗
║            J.A.R.V.I.S.  Personal AI System  —  v5.0             ║
║  Holographic HUD · British neural voice · Ollama AI · PC control  ║
╚══════════════════════════════════════════════════════════════════╝

RUN:
    pip install -r requirements.txt
    ollama serve                 (separate terminal)
    python JARVIS_FULL.py

TALK:
    "Jarvis, <command>"   or  "Jarvis" … "Yes, sir?" … <command>
    F2 / click the core   talk without the wake word
    Ctrl+Alt+J            talk from anywhere in Windows
    Esc  stop speaking    F11  holographic mini mode

TRY:
    "daily briefing" · "what's the weather" · "activate work protocol"
    "set a timer for 10 minutes" · "remind me in 20 minutes to stretch"
    "go holographic" · "what's on my screen" · anything else → AI

Settings (⚙): mic device + live meter, sensitivity, voice, city, alerts.
Protocols live in jarvis_config.json. Log: jarvis.log next to this file.
"""

import os, sys, re, time, math, json, queue, shutil, ctypes, random, itertools, asyncio
import threading, datetime, subprocess, webbrowser, tempfile, collections, warnings
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

warnings.filterwarnings("ignore")

IS_WIN = os.name == "nt"
NOWIN = {"creationflags": 0x08000000} if IS_WIN else {}   # CREATE_NO_WINDOW

# ── Optional dependencies (app still starts if one is missing) ──────
try:
    import numpy as np
    HAS_NP = True
except ImportError:
    HAS_NP = False

try:
    import sounddevice as sd
    HAS_SD = HAS_NP
except Exception:
    HAS_SD = False

try:
    import speech_recognition as sr
    HAS_SR = True
except Exception:
    HAS_SR = False

try:
    import ollama
    HAS_OLLAMA = True
except Exception:
    HAS_OLLAMA = False

try:
    import edge_tts
    HAS_EDGE = True
except Exception:
    HAS_EDGE = False

try:
    import psutil
    HAS_PSUTIL = True
except Exception:
    HAS_PSUTIL = False

try:
    from PIL import ImageGrab
    HAS_PIL = True
except Exception:
    HAS_PIL = False

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    HAS_PYAUTOGUI = True
except Exception:
    HAS_PYAUTOGUI = False

try:
    import pygetwindow as gw
    HAS_GW = True
except Exception:
    HAS_GW = False

import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

# ══════════════════════════════════════════════════════════════════
# PATHS / CONFIG / LOG
# ══════════════════════════════════════════════════════════════════

APP_DIR = (Path(sys.executable).parent if getattr(sys, "frozen", False)
           else Path(__file__).resolve().parent)
CONFIG_FILE = APP_DIR / "jarvis_config.json"
MEMORY_FILE = APP_DIR / "jarvis_memory.json"
LOG_FILE    = APP_DIR / "jarvis.log"
VERSION     = "5.0"

DEFAULT_CONFIG = {
    "ai_model":          "qwen2.5:3b",
    "vision_model":      "moondream",
    "user_title":        "sir",
    "city":              "Oyama",
    "lat":               36.3147,
    "lon":               139.8003,
    "wake_word_enabled": True,
    "wake_words":        ["jarvis", "jarvice", "javis", "jervis", "jarves",
                          "jarvas", "jarvish", "charvis", "jar vis", "travis"],
    "wake_engine":       "auto",        # auto = offline "Hey Jarvis" (openWakeWord) if installed, else google
    "wake_threshold":    0.5,
    "mic_device":        None,          # {"name": ..., "hostapi": ...}  None = Windows default
    "mic_sensitivity":   6,             # 1 (needs loud voice) … 10 (very sensitive)
    "stt_language":      "en-US",
    "voice_engine":      "neural",      # neural (British, online) | sapi (Windows, offline)
    "neural_voice":      "en-GB-RyanNeural",
    "neural_pitch":      -2,            # Hz
    "tts_voice":         "",            # Windows voice name substring, "" = auto
    "tts_rate":          0,             # -5 … 5
    "speak_replies":     True,
    "sound_fx":          True,
    "proactive_alerts":  True,
    "boot_sequence":     True,
    "holo_x":            None,
    "holo_y":            None,
    "protocols": {
        "work":   ["open vs code", "go to github.com", "open spotify"],
        "stream": ["open obs", "open discord", "go to studio.youtube.com"],
        "gaming": ["open steam", "open discord"],
        "focus":  ["minimize all", "mute"],
        "night":  ["set volume to 15", "brightness 30"],
    },
    "max_history":       30,
}

SYSTEM_PROMPT = """You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), a personal AI system running on the user's Windows PC.
Character: a composed, quietly brilliant British AI butler — dry understated wit, impeccably polite, unflappable and loyal; occasionally gently sardonic, never rude.
Address the user as "{title}".
Your replies are spoken aloud by a text-to-speech voice, so:
- Default to 1-3 short sentences. Elaborate only when asked or when the task truly needs it.
- No markdown headings, bullet symbols, tables or emojis unless the user asks for a list or code. Put code in ``` fences.
- Lead with the answer; skip filler like "Certainly!" or "Great question".
- If you are unsure, say so briefly rather than inventing facts.
PC commands (open apps, volume, timers, weather, protocols…) are handled by a separate system. If asked to do something on the PC in chat, suggest the voice phrasing, e.g. "open chrome" or "set a timer for 5 minutes".
"""

_log_lock = threading.Lock()


def log(msg: str):
    line = f"[{datetime.datetime.now():%H:%M:%S}] {msg}"
    try:
        print(line)
    except Exception:
        pass
    with _log_lock:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


def _rotate_log():
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 1_000_000:
            LOG_FILE.write_text("", encoding="utf-8")
    except Exception:
        pass


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        if CONFIG_FILE.exists():
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except Exception as e:
        log(f"config load error: {e}")
    return cfg


def save_config(cfg: dict):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"config save error: {e}")


# ══════════════════════════════════════════════════════════════════
# PC CONTROL
# ══════════════════════════════════════════════════════════════════

class AppManager:
    APP_MAP = {
        # Browsers
        "chrome": "chrome.exe", "google chrome": "chrome.exe", "browser": "chrome.exe",
        "firefox": "firefox.exe", "edge": "msedge.exe", "microsoft edge": "msedge.exe",
        "opera": "opera.exe", "brave": "brave.exe",
        # Office
        "word": "winword.exe", "excel": "excel.exe", "powerpoint": "powerpnt.exe",
        "outlook": "outlook.exe", "onenote": "onenote.exe", "teams": "ms-teams.exe",
        # System tools
        "notepad": "notepad.exe", "notepad++": "notepad++.exe",
        "calculator": "calc.exe", "calc": "calc.exe", "paint": "mspaint.exe",
        "cmd": "cmd.exe", "command prompt": "cmd.exe",
        "terminal": "wt.exe", "windows terminal": "wt.exe", "powershell": "powershell.exe",
        "task manager": "taskmgr.exe", "file explorer": "explorer.exe", "explorer": "explorer.exe",
        "control panel": "control.exe", "registry editor": "regedit.exe",
        "device manager": "devmgmt.msc", "disk management": "diskmgmt.msc",
        "event viewer": "eventvwr.msc", "services": "services.msc",
        "snipping tool": "snippingtool.exe",
        # Settings
        "settings": "ms-settings:", "wifi settings": "ms-settings:network-wifi",
        "bluetooth": "ms-settings:bluetooth", "bluetooth settings": "ms-settings:bluetooth",
        "display settings": "ms-settings:display", "sound settings": "ms-settings:sound",
        "privacy settings": "ms-settings:privacy", "windows update": "ms-settings:windowsupdate",
        # Media
        "spotify": "spotify.exe", "vlc": "vlc.exe", "media player": "wmplayer.exe",
        "netflix": "https://www.netflix.com", "youtube": "https://www.youtube.com",
        "gmail": "https://mail.google.com", "github": "https://github.com",
        "chatgpt": "https://chatgpt.com", "claude": "https://claude.ai",
        # Dev
        "vscode": "code.exe", "vs code": "code.exe", "visual studio code": "code.exe",
        "visual studio": "devenv.exe", "git bash": "git-bash.exe",
        "android studio": "studio64.exe", "pycharm": "pycharm64.exe",
        # Communication
        "discord": "discord.exe", "slack": "slack.exe", "zoom": "zoom.exe",
        "whatsapp": "whatsapp.exe", "telegram": "telegram.exe",
        # Utilities / gaming
        "7zip": "7zFM.exe", "winrar": "winrar.exe", "obs": "obs64.exe",
        "obs studio": "obs64.exe", "steam": "steam.exe",
        "epic games": "EpicGamesLauncher.exe",
    }

    def _lookup(self, name: str):
        key = name.lower().strip()
        if key in self.APP_MAP:
            return self.APP_MAP[key]
        for k, v in self.APP_MAP.items():
            if k.startswith(key) and len(key) >= 3:
                return v
        for k, v in self.APP_MAP.items():
            if len(k) >= 4 and k in key:
                return v
        return None

    def open(self, name: str) -> str:
        target = self._lookup(name)
        if target:
            if target.startswith("http"):
                webbrowser.open_new_tab(target)
                return f"Opening {name}."
            if target.startswith("ms-settings:") or target.endswith(".msc"):
                try:
                    os.startfile(target)
                    return f"Opening {name}."
                except Exception as e:
                    return f"Couldn't open {name}: {e}"

            found = shutil.which(target)
            if found:
                subprocess.Popen([found], **NOWIN)
                return f"Opening {name}."

            # ShellExecute resolves "App Paths" registry entries (chrome, winword, …)
            try:
                os.startfile(target)
                return f"Opening {name}."
            except Exception:
                pass

            path = self._search_installed(target)
            if path:
                subprocess.Popen([path], **NOWIN)
                return f"Opening {name}."

        # Last resort: Start-menu search
        if HAS_PYAUTOGUI and IS_WIN:
            try:
                pyautogui.hotkey("win", "s")
                time.sleep(0.7)
                pyautogui.write(name, interval=0.04)
                time.sleep(1.1)
                pyautogui.press("enter")
                return f"Searching Windows for {name}."
            except Exception:
                pass
        return f"I couldn't find {name}, sir."

    @staticmethod
    def _search_installed(exe: str):
        env = os.environ.get
        bases = [os.path.join(env("LOCALAPPDATA", ""), "Programs"),
                 os.path.join(env("LOCALAPPDATA", ""), "Discord"),
                 os.path.join(env("APPDATA", ""), "Spotify"),
                 os.path.join(env("APPDATA", ""), "Telegram Desktop"),
                 env("PROGRAMFILES", ""), env("ProgramFiles(x86)", "")]
        for base in [b for b in bases if b and os.path.isdir(b)]:
            try:
                for root, dirs, files in os.walk(base):
                    if root[len(base):].count(os.sep) > 3:
                        dirs.clear()
                        continue
                    for f in files:
                        if f.lower() == exe.lower():
                            return os.path.join(root, f)
            except Exception:
                continue
        return None

    def close(self, name: str) -> str:
        name_l = name.lower().strip()
        closed = []
        if HAS_GW:
            try:
                for win in gw.getAllWindows():
                    if win.title and name_l in win.title.lower() and "j.a.r.v.i.s" not in win.title.lower():
                        try:
                            win.close()
                            closed.append(win.title)
                        except Exception:
                            pass
            except Exception:
                pass
        if closed:
            return f"Closed {', '.join(closed[:3])}."

        exe = (self._lookup(name) or name_l)
        exe_stem = Path(exe).stem.lower() if not exe.startswith(("http", "ms-")) else name_l
        killed = set()
        if HAS_PSUTIL:
            for proc in psutil.process_iter(["name"]):
                try:
                    pname = (proc.info["name"] or "").lower()
                    if pname and (Path(pname).stem == exe_stem or name_l.replace(" ", "") in pname):
                        if pname.startswith("python"):
                            continue
                        proc.kill()
                        killed.add(proc.info["name"])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        return f"Force-closed {', '.join(killed)}." if killed else f"{name} isn't running, sir."

    def list_running(self) -> str:
        apps = set()
        if HAS_GW:
            try:
                for win in gw.getAllWindows():
                    if win.title and getattr(win, "visible", True):
                        apps.add(win.title[:40])
            except Exception:
                pass
        if not apps and HAS_PSUTIL:
            for proc in psutil.process_iter(["name"]):
                apps.add(proc.info["name"])
        return "Running: " + ", ".join(sorted(apps)[:15])

    def _find_window(self, name):
        if not HAS_GW:
            return None
        for win in gw.getAllWindows():
            if win.title and name.lower() in win.title.lower():
                return win
        return None

    def switch_to(self, name: str) -> str:
        win = self._find_window(name)
        if not win:
            return f"No window matching {name}."
        try:
            if win.isMinimized:
                win.restore()
            win.activate()
            return f"Switched to {win.title}."
        except Exception as e:
            return f"Couldn't switch: {e}"

    def minimize(self, name: str) -> str:
        win = self._find_window(name)
        if not win:
            return f"Window {name} not found."
        win.minimize()
        return f"Minimised {win.title}."

    def maximize(self, name: str) -> str:
        win = self._find_window(name)
        if not win:
            return f"Window {name} not found."
        win.maximize()
        return f"Maximised {win.title}."

    def minimize_all(self) -> str:
        if HAS_PYAUTOGUI:
            pyautogui.hotkey("win", "d")
            return "All windows minimised."
        return "Not available."


class FileManager:
    KNOWN = {"desktop": "Desktop", "downloads": "Downloads", "download": "Downloads",
             "documents": "Documents", "document": "Documents", "pictures": "Pictures",
             "music": "Music", "videos": "Videos", "home": ""}

    def known(self, word: str):
        sub = self.KNOWN.get(word.lower().strip())
        return None if sub is None else str(Path.home() / sub)

    def create_file(self, path: str, content: str = "") -> str:
        try:
            p = Path(path).expanduser()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"File created: {p}"
        except Exception as e:
            return f"Error: {e}"

    def create_folder(self, path: str) -> str:
        try:
            Path(path).expanduser().mkdir(parents=True, exist_ok=True)
            return f"Folder created: {path}"
        except Exception as e:
            return f"Error: {e}"

    def delete(self, path: str) -> str:
        try:
            p = Path(path).expanduser()
            if p.is_file():
                p.unlink()
                return f"Deleted file {p}."
            if p.is_dir():
                shutil.rmtree(p)
                return f"Deleted folder {p}."
            return f"Not found: {path}"
        except Exception as e:
            return f"Error: {e}"

    def list_dir(self, path: str = ".") -> str:
        try:
            items = sorted(Path(path).expanduser().iterdir())[:20]
            return f"{path}:\n" + "\n".join(f"[D] {i.name}" if i.is_dir() else i.name for i in items)
        except Exception as e:
            return f"Error: {e}"

    def open_path(self, path: str) -> str:
        try:
            os.startfile(str(Path(path).expanduser()))
            return f"Opened {path}."
        except Exception as e:
            return f"Error: {e}"

    def find(self, name: str, root: str = None) -> str:
        root = root or str(Path.home())
        matches = []
        try:
            for p in Path(root).rglob(f"*{name}*"):
                matches.append(str(p))
                if len(matches) >= 8:
                    break
        except Exception:
            pass
        return "\n".join(matches) if matches else f"No files matching {name}."

    def read_file(self, path: str) -> str:
        try:
            return Path(path).expanduser().read_text(encoding="utf-8", errors="ignore")[:600]
        except Exception as e:
            return f"Error: {e}"


class SystemControl:

    # ── Volume (pycaw → media keys) ──────────────────────────────
    @staticmethod
    def _endpoint():
        try:
            import comtypes
            try:
                comtypes.CoInitialize()
            except Exception:
                pass
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            dev = AudioUtilities.GetSpeakers()
            ep = getattr(dev, "EndpointVolume", None)       # pycaw ≥ 2025
            if ep is not None:
                return ep
            from comtypes import CLSCTX_ALL
            from ctypes import cast, POINTER
            iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            return cast(iface, POINTER(IAudioEndpointVolume))
        except Exception as e:
            log(f"pycaw unavailable: {e}")
            return None

    def set_volume(self, level: int) -> str:
        level = max(0, min(100, int(level)))
        ep = self._endpoint()
        if ep is not None:
            try:
                ep.SetMasterVolumeLevelScalar(level / 100.0, None)
                return f"Volume set to {level} percent."
            except Exception as e:
                log(f"set volume error: {e}")
        if HAS_PYAUTOGUI:
            pyautogui.press("volumedown", presses=50)
            pyautogui.press("volumeup", presses=level // 2)
            return f"Volume set to about {level} percent."
        return "Volume control unavailable."

    def change_volume(self, step: int) -> str:
        ep = self._endpoint()
        if ep is not None:
            try:
                cur = ep.GetMasterVolumeLevelScalar()
                new = max(0.0, min(1.0, cur + step / 100.0))
                ep.SetMasterVolumeLevelScalar(new, None)
                return f"Volume at {round(new * 100)} percent."
            except Exception:
                pass
        if HAS_PYAUTOGUI:
            pyautogui.press("volumeup" if step > 0 else "volumedown", presses=abs(step) // 2)
            return "Volume adjusted."
        return "Volume control unavailable."

    def mute(self, state=None) -> str:
        ep = self._endpoint()
        if ep is not None:
            try:
                new = (not ep.GetMute()) if state is None else state
                ep.SetMute(1 if new else 0, None)
                return "Muted." if new else "Unmuted."
            except Exception:
                pass
        if HAS_PYAUTOGUI:
            pyautogui.press("volumemute")
            return "Toggled mute."
        return "Volume control unavailable."

    def set_brightness(self, level: int) -> str:
        level = max(0, min(100, int(level)))
        ps = ("(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods)"
              f".WmiSetBrightness(1,{level})")
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               capture_output=True, text=True, timeout=8, **NOWIN)
            if r.returncode == 0:
                return f"Brightness set to {level} percent."
            return "This display doesn't support software brightness."
        except Exception as e:
            return f"Brightness error: {e}"

    # ── Power ─────────────────────────────────────────────────────
    def shutdown(self, delay=60):
        subprocess.Popen(f"shutdown /s /t {delay}", shell=True, **NOWIN)
        return f"Shutting down in {delay} seconds. Say 'cancel shutdown' to abort."

    def cancel_shutdown(self):
        subprocess.Popen("shutdown /a", shell=True, **NOWIN)
        return "Shutdown cancelled."

    def restart(self, delay=15):
        subprocess.Popen(f"shutdown /r /t {delay}", shell=True, **NOWIN)
        return f"Restarting in {delay} seconds. Say 'cancel shutdown' to abort."

    def sleep(self):
        subprocess.Popen("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True, **NOWIN)
        return "Going to sleep."

    def hibernate(self):
        subprocess.Popen("shutdown /h", shell=True, **NOWIN)
        return "Hibernating."

    def lock(self):
        if IS_WIN:
            ctypes.windll.user32.LockWorkStation()
            return "Workstation locked."
        return "Lock is Windows-only."

    # ── Network ───────────────────────────────────────────────────
    def get_ip(self):
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except Exception:
            ip = socket.gethostbyname(socket.gethostname())
        return f"Your local IP is {ip}."

    def wifi(self, on: bool):
        subprocess.run(f"netsh interface set interface Wi-Fi {'enable' if on else 'disable'}",
                       shell=True, capture_output=True, **NOWIN)
        return f"Wi-Fi {'enabled' if on else 'disabled'}."

    def wifi_networks(self):
        try:
            r = subprocess.run("netsh wlan show networks", shell=True,
                               capture_output=True, text=True, **NOWIN)
            nets = [l.split(":", 1)[1].strip() for l in r.stdout.splitlines()
                    if l.strip().startswith("SSID") and ":" in l]
            nets = [n for n in nets if n][:8]
            return "Networks: " + ", ".join(nets) if nets else "No Wi-Fi networks found."
        except Exception as e:
            return f"Error: {e}"

    def ping(self, host):
        try:
            r = subprocess.run(f"ping -n 3 {host}", shell=True, capture_output=True,
                               text=True, timeout=20, **NOWIN)
            avg = re.search(r"Average = (\d+ms)", r.stdout)
            return f"{host}: average {avg.group(1)}." if avg else f"{host} didn't respond."
        except Exception as e:
            return f"Error: {e}"

    # ── Clipboard ─────────────────────────────────────────────────
    def copy_to_clipboard(self, text):
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
                           input=text, text=True, timeout=8, **NOWIN)
            return "Copied to clipboard."
        except Exception as e:
            return f"Clipboard error: {e}"

    def get_clipboard(self):
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                               capture_output=True, text=True, timeout=8, **NOWIN)
            return "Clipboard: " + (r.stdout.strip()[:300] or "empty")
        except Exception as e:
            return f"Clipboard error: {e}"

    # ── Info ──────────────────────────────────────────────────────
    def screenshot(self):
        if not HAS_PIL:
            return "Pillow is not installed."
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path.home() / "Desktop" / f"jarvis_{ts}.png"
        ImageGrab.grab().save(path)
        return f"Screenshot saved to your desktop as {path.name}."

    def full_info(self):
        if not HAS_PSUTIL:
            return "psutil not installed."
        cpu = psutil.cpu_percent(interval=0.4)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage(os.path.abspath(os.sep))
        bat = psutil.sensors_battery()
        up = str(datetime.timedelta(seconds=int(time.time() - psutil.boot_time())))
        b = f", battery {bat.percent:.0f} percent" if bat else ""
        return (f"CPU at {cpu:.0f} percent, memory {ram.percent:.0f} percent, "
                f"disk {disk.percent:.0f} percent{b}. Uptime {up}.")

    def list_processes(self, top=8):
        procs = []
        for p in psutil.process_iter(["name", "memory_percent"]):
            procs.append(p.info)
        procs.sort(key=lambda x: x.get("memory_percent") or 0, reverse=True)
        return "\n".join(f"{(p['name'] or '?')[:24]:<24} RAM {p['memory_percent'] or 0:.1f}%"
                         for p in procs[:top])

    def kill_process(self, name):
        killed = set()
        for proc in psutil.process_iter(["name"]):
            try:
                if name.lower() in (proc.info["name"] or "").lower():
                    proc.kill()
                    killed.add(proc.info["name"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return f"Killed {', '.join(killed)}." if killed else f"No process named {name}."

    def run(self, cmd):
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                               timeout=20, **NOWIN)
            out = (r.stdout or r.stderr).strip()
            return out[:500] if out else "Done."
        except subprocess.TimeoutExpired:
            return "Command timed out."
        except Exception as e:
            return f"Error: {e}"


class InputControl:
    SHORTCUTS = {
        "copy": ("ctrl", "c"), "paste": ("ctrl", "v"), "cut": ("ctrl", "x"),
        "undo": ("ctrl", "z"), "redo": ("ctrl", "y"), "save": ("ctrl", "s"),
        "select all": ("ctrl", "a"), "new window": ("ctrl", "n"), "find": ("ctrl", "f"),
        "refresh": ("f5",), "fullscreen": ("f11",), "full screen": ("f11",),
        "task manager": ("ctrl", "shift", "esc"), "show desktop": ("win", "d"),
        "snip": ("win", "shift", "s"), "run": ("win", "r"), "settings": ("win", "i"),
        "file explorer": ("win", "e"), "notifications": ("win", "n"),
        "zoom in": ("ctrl", "="), "zoom out": ("ctrl", "-"), "alt tab": ("alt", "tab"),
        "enter": ("enter",), "escape": ("esc",), "space": ("space",),
        "play": ("playpause",), "pause": ("playpause",), "next track": ("nexttrack",),
        "previous track": ("prevtrack",),
    }
    KEY_ALIAS = {"control": "ctrl", "escape": "esc", "windows": "win", "window": "win",
                 "return": "enter", "delete": "del", "plus": "+", "minus": "-"}

    def press(self, spec: str) -> str:
        if not HAS_PYAUTOGUI:
            return "pyautogui not available."
        spec = spec.lower().strip()
        keys = self.SHORTCUTS.get(spec)
        if not keys:
            keys = tuple(self.KEY_ALIAS.get(k, k) for k in re.split(r"[\s+]+", spec) if k)
            if not keys or not all(k in pyautogui.KEYBOARD_KEYS for k in keys):
                return f"Unknown shortcut: {spec}"
        pyautogui.hotkey(*keys)
        return f"Pressed {'+'.join(keys)}."

    def type_text(self, text):
        if not HAS_PYAUTOGUI:
            return "pyautogui not available."
        time.sleep(0.6)
        pyautogui.write(text, interval=0.03)
        return "Typed."

    def scroll(self, direction, amount=5):
        if not HAS_PYAUTOGUI:
            return "pyautogui not available."
        pyautogui.scroll(amount * 100 if direction == "up" else -amount * 100)
        return f"Scrolled {direction}."


class BrowserControl:
    ENGINES = {
        "google": "https://www.google.com/search?q={}",
        "youtube": "https://www.youtube.com/results?search_query={}",
        "wikipedia": "https://en.wikipedia.org/w/index.php?search={}",
        "github": "https://github.com/search?q={}",
        "amazon": "https://www.amazon.co.jp/s?k={}",
        "bing": "https://www.bing.com/search?q={}",
    }

    def open_url(self, url):
        url = url.strip().replace(" dot ", ".").replace(" ", "")
        if not url.startswith("http"):
            url = "https://" + url
        webbrowser.open_new_tab(url)
        return f"Opening {url}."

    def search(self, query, engine="google"):
        from urllib.parse import quote_plus
        webbrowser.open_new_tab(self.ENGINES.get(engine, self.ENGINES["google"]).format(quote_plus(query)))
        return f"Searching {engine} for {query}."

    def hotkey(self, *keys, msg="Done."):
        if HAS_PYAUTOGUI:
            pyautogui.hotkey(*keys)
            return msg
        return "pyautogui not available."

    def incognito(self, browser="chrome"):
        cmd = {"chrome": "start chrome --incognito", "firefox": "start firefox --private-window",
               "edge": "start msedge --inprivate"}.get(browser, "start chrome --incognito")
        subprocess.Popen(cmd, shell=True, **NOWIN)
        return f"Private {browser} window opened."


class Vision:
    def __init__(self, cfg):
        self.cfg = cfg

    def analyze_screen(self, question="Describe what is on this screen in two sentences."):
        if not HAS_PIL or not HAS_OLLAMA:
            return "Screen analysis needs Pillow and Ollama."
        path = os.path.join(tempfile.gettempdir(), "jarvis_screen.png")
        img = ImageGrab.grab()
        img.thumbnail((1280, 1280))
        img.save(path)
        try:
            resp = ollama.chat(model=self.cfg["vision_model"],
                               messages=[{"role": "user", "content": question, "images": [path]}])
            return _msg_content(resp)
        except Exception as e:
            return f"Vision model error: {e}"


# ══════════════════════════════════════════════════════════════════
# COMMAND PARSER  — anchored patterns so normal questions go to the AI
# ══════════════════════════════════════════════════════════════════

FILLERS = r"^(?:(?:hey|ok|okay|please|can you|could you|would you|will you|kindly|now)\s+)+"


def normalize(text: str) -> str:
    t = text.strip().strip(" .,!?").strip()
    t = re.sub(FILLERS, "", t, flags=re.I)
    t = re.sub(r"\s+(?:please|for me|now)$", "", t, flags=re.I)
    return t.strip(" .,!?")


class CommandParser:
    def __init__(self):
        self.apps, self.files = AppManager(), FileManager()
        self.system, self.input, self.browser = SystemControl(), InputControl(), BrowserControl()

    def parse(self, command: str):
        """Return a result string if this is a PC command, else None (→ AI)."""
        o = normalize(command)
        c = o.lower()
        M = lambda p: re.fullmatch(p, c)
        MO = lambda p: re.fullmatch(p, o, flags=re.I)   # keeps original case (paths)

        # ── Folders / files / urls (before generic "open") ────────
        m = M(r"open (?:the |my )?(?:folder )?(desktop|downloads?|documents?|pictures|music|videos|home)(?: folder)?")
        if m:
            return self.files.open_path(self.files.known(m.group(1)))
        m = MO(r"open (?:the )?folder (.+)")
        if m:
            return self.files.open_path(m.group(1))
        m = MO(r"open (?:the )?file (?!explorer\b)(.+)")
        if m:
            return self.files.open_path(m.group(1))
        m = M(r"(?:open (?:the )?(?:website|site|url)|go to|navigate to) (.+)") or \
            M(r"open ([a-z0-9-]+(?:\.| dot )[a-z]{2,}(?:/\S*)?)")
        if m:
            return self.browser.open_url(m.group(1))
        if M(r"(?:open (?:a )?)?new tab|open (?:a )?tab"):
            return self.browser.hotkey("ctrl", "t", msg="New tab opened.")
        m = M(r"open (?:an? )?(?:incognito|private)(?: window)?(?: in (chrome|firefox|edge))?")
        if m:
            return self.browser.incognito(m.group(1) or "chrome")
        if M(r"(?:close (?:this |the )?tab)"):
            return self.browser.hotkey("ctrl", "w", msg="Tab closed.")

        # ── Apps ──────────────────────────────────────────────────
        m = M(r"(?:open|launch|start|run) (?:the )?(?:app )?(.+?)(?: app)?")
        if m and not m.group(1).startswith(("command ", "a command")):
            return self.apps.open(m.group(1))
        m = M(r"(?:close|kill|quit|exit) (?:the )?(?:app )?(.+?)(?: app)?")
        if m and m.group(1) not in ("jarvis", "yourself"):
            return self.apps.close(m.group(1))
        if M(r"(?:what(?:'s| is| apps are) (?:running|open)|list (?:running )?apps|running apps)"):
            return self.apps.list_running()
        if M(r"(?:minimi[sz]e (?:all|everything)(?: windows)?|show (?:the )?desktop)"):
            return self.apps.minimize_all()
        m = M(r"switch to (.+)")
        if m:
            return self.apps.switch_to(m.group(1))
        m = M(r"minimi[sz]e (.+)")
        if m:
            return self.apps.minimize(m.group(1))
        m = M(r"maximi[sz]e (.+)")
        if m:
            return self.apps.maximize(m.group(1))

        # ── Files ─────────────────────────────────────────────────
        m = MO(r"create (?:a )?file (?:called |named )?(.+)")
        if m:
            return self.files.create_file(m.group(1))
        m = MO(r"(?:create|make) (?:a )?(?:new )?folder (?:called |named )?(.+)")
        if m:
            p = m.group(1)
            if not os.path.isabs(p):
                p = str(Path.home() / "Desktop" / p)
            return self.files.create_folder(p)
        m = MO(r"delete (?:the )?(?:file|folder) (.+)")
        if m:
            return self.files.delete(m.group(1))
        m = M(r"(?:find|search for|locate) (?:a |the )?file (?:called |named )?(.+)")
        if m:
            return self.files.find(m.group(1))
        m = MO(r"read (?:the )?file (.+)")
        if m:
            return self.files.read_file(m.group(1))
        m = M(r"(?:list|show) (?:the )?files(?: in (.+))?")
        if m:
            p = m.group(1) or "."
            return self.files.list_dir(self.files.known(p) or p)

        # ── Volume / brightness ───────────────────────────────────
        m = M(r"(?:set |change |turn )?(?:the )?volume (?:to |at )?(\d{1,3})(?: percent| %)?") or \
            M(r"set (?:the )?volume (?:to |at )?(\d{1,3})(?: percent| %)?")
        if m:
            return self.system.set_volume(int(m.group(1)))
        if M(r"(?:turn (?:the )?volume up|volume up|increase (?:the )?volume|louder|turn it up)"):
            return self.system.change_volume(+10)
        if M(r"(?:turn (?:the )?volume down|volume down|decrease (?:the )?volume|lower (?:the )?volume|quieter|turn it down)"):
            return self.system.change_volume(-10)
        if M(r"mute(?: (?:the )?(?:volume|audio|sound|pc|computer))?"):
            return self.system.mute(True)
        if M(r"unmute(?: (?:the )?(?:volume|audio|sound|pc|computer))?"):
            return self.system.mute(False)
        m = M(r"(?:set |change )?(?:the )?(?:screen )?brightness (?:to |at )?(\d{1,3})(?: percent| %)?")
        if m:
            return self.system.set_brightness(int(m.group(1)))

        # ── Power (explicit phrasing only) ───────────────────────
        if M(r"(?:cancel|abort|stop) (?:the )?(?:shutdown|restart|reboot)"):
            return self.system.cancel_shutdown()
        if M(r"(?:shut ?down|turn off|power off)(?: the| my)? (?:computer|pc|laptop|system)|shutdown"):
            return self.system.shutdown(60)
        if M(r"(?:restart|reboot)(?: the| my)?(?: computer| pc| laptop| system)?"):
            return self.system.restart()
        if M(r"hibernate(?: the| my)?(?: computer| pc| laptop)?"):
            return self.system.hibernate()
        if M(r"(?:go to sleep|sleep mode|put (?:the |my )?(?:computer|pc|laptop) to sleep)"):
            return self.system.sleep()
        if M(r"lock(?: the| my)?(?: screen| computer| pc| laptop| workstation)?"):
            return self.system.lock()

        # ── Network ───────────────────────────────────────────────
        if re.search(r"\b(?:my ip|ip address)\b", c):
            return self.system.get_ip()
        if M(r"(?:turn on|enable) (?:the )?wi-?fi|wi-?fi on"):
            return self.system.wifi(True)
        if M(r"(?:turn off|disable) (?:the )?wi-?fi|wi-?fi off"):
            return self.system.wifi(False)
        if M(r"(?:show|scan|list)(?: available)? wi-?fi(?: networks)?|available wi-?fi(?: networks)?|wi-?fi networks"):
            return self.system.wifi_networks()
        m = M(r"ping (\S+)")
        if m:
            return self.system.ping(m.group(1))

        # ── System info ───────────────────────────────────────────
        if M(r"(?:system|computer|pc) (?:status|info|information|report|diagnostics?)|"
             r"how(?:'s| is) (?:my |the )?(?:computer|pc|system)(?: doing)?|"
             r"(?:cpu|ram|memory) usage|battery(?: level| status| percentage)?|how much battery(?: is left)?"):
            return self.system.full_info()
        if M(r"(?:show |list )?(?:running|top) processes|task list"):
            return self.system.list_processes()
        m = M(r"kill process (.+)")
        if m:
            return self.system.kill_process(m.group(1))
        m = MO(r"(?:run|execute) (?:the )?command (.+)")
        if m:
            return self.system.run(m.group(1))

        # ── Screen / clipboard ───────────────────────────────────
        if M(r"(?:take (?:a )?)?screen ?shot|capture (?:the |my )?screen|snap (?:the )?screen"):
            return self.system.screenshot()
        m = MO(r"copy (.+?) to (?:the )?clipboard")
        if m:
            return self.system.copy_to_clipboard(m.group(1))
        if M(r"(?:what(?:'s| is) (?:in|on) (?:the |my )?clipboard|get clipboard|read (?:the )?clipboard)"):
            return self.system.get_clipboard()

        # ── Keyboard / mouse ─────────────────────────────────────
        m = M(r"(?:press|hit|shortcut|hotkey) (.+)")
        if m:
            return self.input.press(m.group(1))
        m = MO(r"type (.+)")
        if m:
            return self.input.type_text(m.group(1))
        m = M(r"scroll (up|down)")
        if m:
            return self.input.scroll(m.group(1))
        if M(r"(?:play|pause|resume)(?: (?:the )?music)?"):
            return self.input.press("play")
        if M(r"(?:next|skip)(?: song| track)?"):
            return self.input.press("next track")
        if M(r"previous(?: song| track)?"):
            return self.input.press("previous track")

        # ── Browser ──────────────────────────────────────────────
        m = M(r"(?:play|search(?: for)?|find|look up) (.+?) on youtube") or \
            M(r"(?:youtube|search youtube for|search youtube) (.+)")
        if m:
            return self.browser.search(m.group(1), "youtube")
        m = M(r"(?:search|look up|google)(?: for)? (.+?) on (google|wikipedia|github|amazon|bing)")
        if m:
            return self.browser.search(m.group(1), m.group(2))
        m = M(r"(?:search|google|look up)(?: for)? (.+)")
        if m:
            return self.browser.search(m.group(1))
        if M(r"(?:go back|back)(?: a page)?"):
            return self.browser.hotkey("alt", "left", msg="Back.")
        if M(r"(?:go forward|forward)(?: a page)?"):
            return self.browser.hotkey("alt", "right", msg="Forward.")
        if M(r"(?:refresh|reload)(?: (?:the|this))?(?: page)?"):
            return self.browser.hotkey("f5", msg="Page refreshed.")

        return None


# ══════════════════════════════════════════════════════════════════
# MEMORY + AI
# ══════════════════════════════════════════════════════════════════

def _msg_content(resp) -> str:
    try:
        return resp.message.content or ""
    except AttributeError:
        try:
            return resp["message"]["content"] or ""
        except Exception:
            return ""


class Memory:
    def __init__(self, path=MEMORY_FILE, max_history=30):
        self.path, self.max = Path(path), max_history
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self):
        try:
            if self.path.exists():
                d = json.loads(self.path.read_text(encoding="utf-8"))
                d.setdefault("history", [])
                d.setdefault("facts", {})
                return d
        except Exception:
            pass
        return {"facts": {}, "history": []}

    def save(self):
        try:
            self.path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log(f"memory save error: {e}")

    def append(self, role, content):
        with self._lock:
            self._data["history"].append({"role": role, "content": content})
            self._data["history"] = self._data["history"][-self.max:]
            self.save()

    def history(self):
        with self._lock:
            return list(self._data["history"])

    def clear(self):
        with self._lock:
            self._data["history"] = []
            self.save()


class AIBrain:
    def __init__(self, memory: Memory, cfg):
        self.memory, self.cfg = memory, cfg

    def reply_stream(self, user_input: str, on_token) -> str:
        if not HAS_OLLAMA:
            return "The ollama package isn't installed, sir."
        self.memory.append("user", user_input)
        now = datetime.datetime.now().strftime("%A %d %B %Y, %H:%M")
        sysmsg = (SYSTEM_PROMPT.replace("{title}", self.cfg.get("user_title") or "sir")
                  + f"\nCurrent date/time: {now}. User's location: {self.cfg.get('city') or 'unknown'}.")
        msgs = ([{"role": "system", "content": sysmsg}]
                + self.memory.history()[-20:])
        full = ""
        try:
            for chunk in ollama.chat(model=self.cfg["ai_model"], messages=msgs, stream=True):
                piece = _msg_content(chunk)
                if piece:
                    full += piece
                    on_token(piece)
        except Exception as e:
            title = self.cfg.get("user_title") or "sir"
            text = str(e)
            if "not found" in text.lower() and not full:
                try:
                    _, notes = resolve_models(self.cfg)
                except Exception:
                    notes = []
                if notes:
                    log("model: " + "; ".join(notes))
                    with self.memory._lock:                     # drop the user turn; retry re-adds it
                        if self.memory._data["history"] and self.memory._data["history"][-1]["role"] == "user":
                            self.memory._data["history"].pop()
                    return self.reply_stream(user_input, on_token)
                err = (f"The model {self.cfg['ai_model']} isn't installed, {title}. "
                       f"Run: ollama pull qwen2.5:3b")
            elif "connect" in text.lower() or "refused" in text.lower():
                err = f"I can't reach Ollama, {title}. Make sure the Ollama app is running."
            else:
                err = f"My circuits hit a snag, {title} — {text}"
            on_token(("\n" if full else "") + err)
            full = full + ("\n" if full else "") + err
        full = full.strip() or "I'm afraid I have nothing to add, sir."
        self.memory.append("assistant", full)
        return full


VISION_HINTS = ("llava", "moondream", "vision", "bakllava", "minicpm-v", "llama3.2-vision", "granite3.2-vision")
CHAT_PREFS = ("qwen2.5:3b", "llama3.2:3b", "qwen2.5:7b", "llama3.2", "qwen3", "gemma3", "phi3", "mistral", "llama3")
VISION_PREFS = ("moondream", "llava-phi3", "llava:7b", "llava:latest", "llava")


def _installed_models():
    raw = ollama.list()
    models = getattr(raw, "models", None)
    if models is None and isinstance(raw, dict):
        models = raw.get("models", [])
    names = []
    for m in models or []:
        n = getattr(m, "model", None) or (m.get("model") or m.get("name") if isinstance(m, dict) else str(m))
        if n:
            names.append(n)
    return names


def _has(names, want):
    want = (want or "").lower()
    base = want if ":" in want else want + ":latest"
    return any(n.lower() == want or n.lower() == base for n in names)


def _pick(names, prefs, vision):
    pool = [n for n in names if any(h in n.lower() for h in VISION_HINTS) == vision]
    for p in prefs:
        for n in pool:
            if n.lower() == p or n.lower().startswith(p if ":" in p else p + ":"):
                return n
    return pool[0] if pool else None


def resolve_models(cfg):
    """If the configured models aren't installed, switch to installed ones.
    Returns (installed_names, list_of_change_notes). Raises if Ollama is unreachable."""
    names = _installed_models()
    notes = []
    for key, prefs, vision in (("ai_model", CHAT_PREFS, False), ("vision_model", VISION_PREFS, True)):
        if not _has(names, cfg.get(key)):
            alt = _pick(names, prefs, vision)
            if alt:
                notes.append(f"{cfg.get(key)} isn't installed → using {alt}")
                cfg[key] = alt
    if notes:
        save_config(cfg)
    return names, notes


def check_ollama(cfg):
    """Returns (online: bool, message: str). Auto-switches to installed models."""
    if not HAS_OLLAMA:
        return False, "ollama package missing"
    try:
        names, notes = resolve_models(cfg)
        for n in notes:
            log(f"model: {n}")
        missing = [x for x in (cfg["ai_model"], cfg["vision_model"]) if not _has(names, x)]
        if not _has(names, cfg["ai_model"]):
            return True, "missing: " + ", ".join(missing)
        if missing:
            log(f"vision model missing: {cfg['vision_model']} (ollama pull moondream)")
        return True, cfg["ai_model"]
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════════════════════════════════
# TEXT-TO-SPEECH
#   neural  : Microsoft neural voice (default en-GB-RyanNeural, British male)
#             via edge-tts, played with Windows' built-in MCI. The next
#             sentence is synthesised while the current one plays, so streamed
#             AI replies start talking almost immediately.
#   offline : Windows SAPI (comtypes) → pyttsx3. Used automatically when the
#             neural voice service can't be reached.
# ══════════════════════════════════════════════════════════════════

NEURAL_VOICES = ["en-GB-RyanNeural", "en-GB-ThomasNeural", "en-GB-SoniaNeural", "en-GB-LibbyNeural",
                 "en-US-AndrewNeural", "en-US-GuyNeural", "en-AU-WilliamNeural"]


def clean_for_speech(t: str) -> str:
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"https?://\S+", "the link", t)
    t = re.sub(r"[*_#>|~`]+", "", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > 450:
        cut = t[:450]
        dot = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
        t = cut[:dot + 1] if dot > 120 else cut + "…"
    return t


def _silent_remove(path):
    try:
        os.remove(path)
    except Exception:
        pass


class _MciPlayer:
    """Plays an mp3 with Windows MCI (winmm.dll) — no extra packages needed."""

    def __init__(self):
        self._w = ctypes.windll.winmm
        self._w.mciSendStringW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
        self._n = 0

    def _cmd(self, s):
        buf = ctypes.create_unicode_buffer(256)
        err = self._w.mciSendStringW(s, buf, 255, None)
        return err, buf.value

    def play(self, path, cancelled, tick):
        self._n += 1
        a = f"jv{self._n}"
        err, _ = self._cmd(f'open "{path}" type mpegvideo alias {a}')
        if err:
            _silent_remove(path)
            raise RuntimeError(f"MCI open error {err}")
        try:
            _, length = self._cmd(f"status {a} length")
            try:
                limit = int(length) / 1000.0 + 1.5
            except ValueError:
                limit = 60.0
            err, _ = self._cmd(f"play {a}")
            if err:
                raise RuntimeError(f"MCI play error {err}")
            t0 = time.monotonic()
            while True:
                if cancelled():
                    self._cmd(f"stop {a}")
                    return
                tick()
                el = time.monotonic() - t0
                _, mode = self._cmd(f"status {a} mode")
                if (el > 0.3 and mode not in ("playing", "seeking", "not ready")) or el > limit:
                    return
                time.sleep(0.03)
        finally:
            self._cmd(f"close {a}")
            _silent_remove(path)


class TTSEngine:
    def __init__(self, cfg, on_start=None, on_end=None):
        self.cfg = cfg
        self.on_start, self.on_end = on_start or (lambda: None), on_end or (lambda: None)
        self.voices = []                 # Windows (SAPI / pyttsx3) voice names
        self.backend = "init"            # init | neural | sapi | pyttsx3 | none
        self.speaking = False
        self._q = queue.Queue()
        self._gen = 0
        self._pending = collections.deque()
        self._quit = False
        self._neural_off_until = 0.0
        self._ids = itertools.count()
        self._local = None
        self._local_name = ""
        self._sapi_tokens = []
        self._mci = None
        self._exec = None
        threading.Thread(target=self._worker, daemon=True, name="tts").start()

    # -- public ------------------------------------------------------
    def speak(self, text):
        text = clean_for_speech(text)
        if text:
            self._q.put(("say", text, self._gen))

    def stop(self):
        self._gen += 1                   # everything queued/playing becomes stale

    def reconfigure(self):
        self._q.put(("cfg", None, 0))

    def shutdown(self):
        self._gen += 1
        self._q.put(("quit", None, 0))

    def describe(self):
        if self.backend == "neural":
            return "NEURAL · " + (self.cfg.get("neural_voice") or "en-GB-RyanNeural").replace("Neural", "")
        if self.backend in ("sapi", "pyttsx3"):
            name = re.sub(r"^Microsoft\s+|\s*(Desktop)?\s*-.*$", "", self._local_name or "default")
            return f"WINDOWS · {name}"
        return "UNAVAILABLE" if self.backend == "none" else "starting…"

    # -- backend selection --------------------------------------------
    def _neural_wanted(self):
        return self.cfg.get("voice_engine", "neural") == "neural"

    def _neural_ready(self):
        return self._mci is not None and self._exec is not None

    def _use_neural(self):
        return self._neural_wanted() and self._neural_ready() and time.monotonic() >= self._neural_off_until

    def _refresh_backend(self):
        if self._neural_wanted() and self._neural_ready():
            self.backend = "neural"
        elif self._local:
            self.backend = self._local[0]
        else:
            self.backend = "none"

    # -- Windows voices ------------------------------------------------
    def _init_local(self):
        try:
            import comtypes
            import comtypes.client
            comtypes.CoInitialize()
            v = comtypes.client.CreateObject("SAPI.SpVoice")
            toks = v.GetVoices()
            self._sapi_tokens = [toks.Item(i) for i in range(toks.Count)]
            self.voices = [t.GetDescription() for t in self._sapi_tokens]
            self._local = ("sapi", v)
            self._apply_local()
            return
        except Exception as e:
            log(f"SAPI unavailable ({e}); trying pyttsx3")
        try:
            import pyttsx3
            eng = pyttsx3.init()
            self.voices = [x.name for x in eng.getProperty("voices")]
            self._local = ("pyttsx3", eng)
            self._apply_local()
        except Exception as e:
            log(f"Windows voice unavailable: {e}")
            self._local = None

    def _apply_local(self):
        if not self._local:
            return
        kind, eng = self._local
        want = (self.cfg.get("tts_voice") or "").lower()
        prefs = [want] if want else ["george", "ryan", "united kingdom", "en-gb", "david", "english"]
        rate = int(max(-5, min(5, self.cfg.get("tts_rate", 0))))
        try:
            if kind == "sapi":
                for p in prefs:
                    hit = next((t for t, d in zip(self._sapi_tokens, self.voices) if p in d.lower()), None)
                    if hit is not None:
                        eng.Voice = hit
                        break
                eng.Rate = rate
                self._local_name = eng.Voice.GetDescription()
            else:
                vs = eng.getProperty("voices")
                for p in prefs:
                    hit = next((v for v in vs if p in v.name.lower()), None)
                    if hit:
                        eng.setProperty("voice", hit.id)
                        self._local_name = hit.name
                        break
                eng.setProperty("rate", 170 + 15 * rate)
        except Exception as e:
            log(f"voice config error: {e}")

    def _speak_local(self, text, gen):
        if not self._local:
            return
        kind, eng = self._local
        try:
            if kind == "sapi":
                eng.Speak(text, 1)                         # SVSFlagsAsync
                while not eng.WaitUntilDone(60):
                    self._take(False)
                    if gen != self._gen:
                        eng.Speak("", 3)                   # async + purge
                        break
            else:
                eng.say(text)
                eng.runAndWait()
        except Exception as e:
            log(f"Windows voice error: {e}")

    # -- neural voice ------------------------------------------------------
    def _synth(self, text):
        path = os.path.join(tempfile.gettempdir(), f"jarvis_tts_{os.getpid()}_{next(self._ids)}.mp3")
        voice = self.cfg.get("neural_voice") or "en-GB-RyanNeural"
        rate = f"{int(self.cfg.get('tts_rate', 0)) * 6:+d}%"
        pitch = f"{int(self.cfg.get('neural_pitch', -2)):+d}Hz"

        async def run():
            await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(path)

        asyncio.run(asyncio.wait_for(run(), timeout=15))
        if not os.path.exists(path) or os.path.getsize(path) < 400:
            _silent_remove(path)
            raise RuntimeError("empty audio from voice service")
        return path

    # -- worker ------------------------------------------------------------
    def _take(self, block):
        """Move queued requests into the pending list (kicking off neural synthesis)."""
        while True:
            try:
                kind, text, gen = self._q.get() if block else self._q.get_nowait()
            except queue.Empty:
                return
            block = False
            if kind == "quit":
                self._quit = True
                return
            if kind == "cfg":
                self._apply_local()
                self._neural_off_until = 0.0
                self._refresh_backend()
                continue
            if gen != self._gen:
                continue
            fut = self._exec.submit(self._synth, text) if self._use_neural() else None
            self._pending.append((text, fut, gen))

    def _worker(self):
        self._init_local()
        if IS_WIN and HAS_EDGE:
            try:
                self._mci = _MciPlayer()
                self._exec = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tts-synth")
            except Exception as e:
                log(f"neural voice playback unavailable: {e}")
        elif self._neural_wanted() and not HAS_EDGE:
            log("edge-tts not installed → using Windows voice  (pip install edge-tts)")
        self._refresh_backend()
        log(f"TTS: {self.describe()}")

        while not self._quit:
            if not self._pending:
                if self.speaking:
                    self.speaking = False
                    self.on_end()
                self._take(block=True)
                continue
            text, fut, gen = self._pending.popleft()
            if gen != self._gen:
                if fut is not None:
                    fut.add_done_callback(lambda f: f.exception() is None and _silent_remove(f.result()))
                continue
            if not self.speaking:
                self.speaking = True
                self.on_start()
            done = False
            if fut is not None:
                try:
                    path = fut.result(timeout=20)
                    if gen == self._gen:
                        self._mci.play(path, lambda g=gen: g != self._gen, lambda: self._take(False))
                    else:
                        _silent_remove(path)
                    done = True
                except Exception as e:
                    log(f"neural voice failed ({e}) → Windows voice for 2 minutes")
                    self._neural_off_until = time.monotonic() + 120
            if not done and gen == self._gen:
                self._speak_local(text, gen)

        if self.speaking:
            self.speaking = False
            self.on_end()


# ══════════════════════════════════════════════════════════════════
# MICROPHONE ENGINE
#   • ONE persistent input stream (no open/close per chunk)
#   • device picked by name+host API (indices change with Bluetooth)
#   • opens at 16 kHz when the driver allows, else native rate → resample
#   • adaptive noise floor + 0.4 s pre-roll (the "Jar-" of "Jarvis" is kept)
#   • paused while JARVIS is talking (no self-hearing)
#   • watchdog reopens the stream if the device disappears
# ══════════════════════════════════════════════════════════════════

class MicEngine:
    FS = 16000
    BLOCK = 0.03
    PREROLL = 0.45
    HANG = 0.85
    MIN_SPEECH = 0.25

    def __init__(self, cfg, on_event):
        self.cfg, self.ev = cfg, on_event
        self.level = 0.0
        self.noise = 0.004
        self.device_label = "—"
        self.ok = False
        self._q = queue.Queue(maxsize=800)
        self._stream = None
        self._fs = self.FS
        self._running = False
        self._muted = False
        self._tts_busy = False
        self._tts_until = 0.0
        self._force = threading.Event()
        self._restart = threading.Event()
        self._last_data = time.monotonic()
        self._rec = sr.Recognizer() if HAS_SR else None
        self._oww = None
        self._oww_key = None
        self._oww_failed = False
        self._announced = None

    @property
    def wake_engine(self):
        return "offline" if (self._oww is not None and self.cfg.get("wake_engine", "auto") != "google") else "google"

    # -- public --------------------------------------------------------
    def start(self):
        if not HAS_SD:
            self.ev("error", "sounddevice/numpy not installed — run: pip install sounddevice numpy")
            return
        if not HAS_SR:
            self.ev("error", "SpeechRecognition not installed — run: pip install SpeechRecognition")
            return
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name="mic").start()

    def stop(self):
        self._running = False
        self._close()

    def reopen(self):
        self._restart.set()

    def listen_now(self):
        """Push-to-talk: next phrase is a command, no wake word needed."""
        self._force.set()

    def set_muted(self, muted: bool):
        self._muted = muted

    @property
    def muted(self):
        return self._muted

    def set_tts_busy(self, busy: bool):
        self._tts_busy = busy
        if not busy:
            self._tts_until = time.monotonic() + 0.35     # let room echo die out

    @staticmethod
    def list_devices():
        out = []
        if not HAS_SD:
            return out
        try:
            apis = sd.query_hostapis()
            for i, d in enumerate(sd.query_devices()):
                if d["max_input_channels"] > 0:
                    ha = apis[d["hostapi"]]["name"]
                    if "WDM-KS" in ha:
                        continue
                    out.append({"index": i, "name": d["name"], "hostapi": ha,
                                "rate": int(d["default_samplerate"]),
                                "channels": int(d["max_input_channels"])})
        except Exception as e:
            log(f"device list error: {e}")
        return out

    # -- stream --------------------------------------------------------
    def _resolve_device(self):
        want = self.cfg.get("mic_device")
        devs = self.list_devices()
        if want:
            for d in devs:
                if d["name"] == want.get("name") and d["hostapi"] == want.get("hostapi"):
                    return d["index"]
            for d in devs:                                   # same mic, other host API
                if d["name"] == want.get("name"):
                    return d["index"]
            # MME truncates names to 31 chars
            for d in devs:
                if want.get("name", "")[:28].lower() in d["name"].lower():
                    return d["index"]
            log(f"configured mic '{want.get('name')}' not found → using default")
        try:
            idx = sd.default.device[0]
            if idx is not None and idx >= 0:
                return idx
        except Exception:
            pass
        return devs[0]["index"] if devs else None

    def _callback(self, indata, frames, t, status):
        mono = indata[:, 0] if indata.shape[1] == 1 else indata.mean(axis=1)
        self._last_data = time.monotonic()
        self.level = float(np.sqrt(np.mean(mono * mono)) + 1e-9)
        try:
            self._q.put_nowait(mono.astype(np.float32, copy=True))
        except queue.Full:
            try:
                self._q.get_nowait()
                self._q.put_nowait(mono.astype(np.float32, copy=True))
            except Exception:
                pass

    def _open(self):
        dev = self._resolve_device()
        if dev is None:
            raise RuntimeError("No input device found. Plug in / pair a microphone.")
        info = sd.query_devices(dev)
        ha = sd.query_hostapis(info["hostapi"])["name"]
        native = int(info["default_samplerate"])
        chmax = max(1, int(info["max_input_channels"]))

        extra = None
        if "WASAPI" in ha:
            try:
                extra = sd.WasapiSettings(auto_convert=True)
            except TypeError:
                extra = None

        tries = []
        for fs in dict.fromkeys([self.FS, native, 48000, 44100]):
            for ch in dict.fromkeys([1, min(2, chmax), chmax]):
                tries.append((fs, ch))

        last = None
        for fs, ch in tries:
            try:
                sd.check_input_settings(device=dev, channels=ch, samplerate=fs,
                                        dtype="float32", extra_settings=extra)
                st = sd.InputStream(device=dev, channels=ch, samplerate=fs, dtype="float32",
                                    blocksize=int(fs * self.BLOCK), callback=self._callback,
                                    extra_settings=extra)
                st.start()
                self._stream, self._fs = st, fs
                self._last_data = time.monotonic()
                self.device_label = info["name"]
                log(f"mic open: [{dev}] {info['name']} · {ha} · {fs} Hz · {ch} ch")
                self._drain()
                return
            except Exception as e:
                last = e
        raise RuntimeError(f"Can't open '{info['name']}' ({ha}): {last}")

    def _close(self):
        st, self._stream = self._stream, None
        if st is not None:
            try:
                st.stop()
                st.close()
            except Exception:
                pass

    def _drain(self):
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass

    # -- VAD capture ---------------------------------------------------
    def _thresholds(self):
        s = max(1, min(10, int(self.cfg.get("mic_sensitivity", 6))))
        mult = 5.0 - 0.38 * (s - 1)               # 5.0× … 1.6× noise floor
        floor = 0.006 - 0.0004 * (s - 1)          # absolute minimum (−44 … −52 dBFS)
        start = max(self.noise * mult, floor)
        return start, max(self.noise * 1.5, start * 0.45)

    def _paused(self):
        return self._muted or self._tts_busy or time.monotonic() < self._tts_until

    def _capture(self, max_wait, max_len, allow_force):
        pre = collections.deque(maxlen=int(self.PREROLL / self.BLOCK) + 1)
        frames, in_speech = [], False
        speech = silence = total = waited = 0.0
        while self._running:
            if self._restart.is_set():
                return "RESTART"
            if self._paused():
                if in_speech:
                    self.ev("hearing", False)
                return "PAUSED"
            if allow_force and self._force.is_set() and not in_speech:
                return "FORCE"
            try:
                blk = self._q.get(timeout=0.5)
            except queue.Empty:
                if time.monotonic() - self._last_data > 3.0:
                    log("mic watchdog: no audio for 3 s → reopening")
                    self._restart.set()
                continue

            dur = len(blk) / self._fs
            rms = float(np.sqrt(np.mean(blk * blk)) + 1e-9)
            start_th, stop_th = self._thresholds()

            if not in_speech:
                pre.append(blk)
                # noise floor: falls fast, rises slowly
                a = 0.10 if rms < self.noise else 0.004
                self.noise = (1 - a) * self.noise + a * rms
                if rms >= start_th:
                    in_speech = True
                    frames = list(pre)
                    speech, silence, total = dur, 0.0, len(frames) * dur
                    self.ev("hearing", True)
                else:
                    waited += dur
                    if max_wait and waited >= max_wait:
                        return None
            else:
                frames.append(blk)
                total += dur
                if rms < stop_th:
                    silence += dur
                else:
                    silence = 0.0
                    speech += dur
                if silence >= self.HANG or total >= max_len:
                    if speech >= self.MIN_SPEECH:
                        break
                    # too short (click / cough / clipped echo) → keep waiting
                    self.ev("hearing", False)
                    in_speech, frames = False, []
                    waited += total
                    pre.clear()
                    if max_wait and waited >= max_wait:
                        return None
        else:
            return None
        self.ev("hearing", False)
        return np.concatenate(frames)

    # -- STT -----------------------------------------------------------
    def _to_pcm16k(self, x):
        fs = self._fs
        x = x.astype(np.float32)
        if fs != self.FS:
            if fs > self.FS:
                k = int(round(fs / self.FS))
                if k > 1:                                  # crude anti-alias
                    x = np.convolve(x, np.ones(k, dtype=np.float32) / k, mode="same")
            n = int(len(x) * self.FS / fs)
            x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
        x = x - float(np.mean(x))
        peak = float(np.max(np.abs(x))) if len(x) else 0.0
        if 0 < peak < 0.5:                                 # boost quiet (Bluetooth) mics
            x = x * min(0.5 / peak, 20.0)
        return (np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()

    def _stt(self, audio):
        try:
            data = sr.AudioData(self._to_pcm16k(audio), self.FS, 2)
            res = self._rec.recognize_google(data, language=self.cfg.get("stt_language", "en-US"),
                                             show_all=True)
        except sr.UnknownValueError:
            return []
        except sr.RequestError as e:
            self.ev("stt_error", f"Speech service unreachable ({e}). Check internet.")
            return []
        except Exception as e:
            log(f"STT error: {e}")
            return []
        if isinstance(res, dict):
            alts = [a.get("transcript", "") for a in res.get("alternative", [])]
            return [a.strip() for a in alts if a and a.strip()]
        return []

    def _find_wake(self, alts):
        words = sorted({w.lower().strip() for w in self.cfg.get("wake_words", ["jarvis"]) if w.strip()},
                       key=len, reverse=True)
        for alt in alts:
            low = alt.lower()
            m = None
            for w in words:
                m = re.search(r"\b" + re.escape(w) + r"\b", low)
                if m:
                    break
            if not m:                                   # fuzzy: "jarvas", "javiss", "jervice"…
                import difflib
                for tm in list(re.finditer(r"[a-z']+", low))[:3]:
                    if difflib.SequenceMatcher(None, tm.group().strip("'"), "jarvis").ratio() >= 0.75:
                        m = tm
                        break
            if m:
                rest = alt[m.end():].strip(" ,.!?")
                out = []
                for tok in rest.split():                     # "open open chrome" → "open chrome"
                    if not out or tok.lower() != out[-1].lower():
                        out.append(tok)
                return " ".join(out)
        return None

    # -- offline wake word ("Hey Jarvis", openWakeWord) -----------------------
    WAKE_FILES = ("hey_jarvis_v0.1.onnx", "melspectrogram.onnx", "embedding_model.onnx")

    def _init_offline_wake(self):
        if self.cfg.get("wake_engine", "auto") == "google":
            return False
        if self._oww is not None:
            return True
        if self._oww_failed:
            return False
        try:
            from openwakeword.model import Model
            import openwakeword.utils as owu
        except Exception as e:
            log(f"offline wake word unavailable ({e}) → pip install openwakeword onnxruntime. Using Google.")
            self._oww_failed = True
            return False
        d = APP_DIR / "wakeword"
        try:
            if not all((d / f).exists() for f in self.WAKE_FILES):
                log("downloading 'Hey Jarvis' wake-word model (one time, ~10 MB)…")
                owu.download_models(["hey_jarvis"], target_directory=str(d))
            self._oww = Model(wakeword_models=[str(d / self.WAKE_FILES[0])], inference_framework="onnx",
                              melspec_model_path=str(d / self.WAKE_FILES[1]),
                              embedding_model_path=str(d / self.WAKE_FILES[2]))
            self._oww_key = next(iter(self._oww.models))
            log("wake engine: offline 'Hey Jarvis' (openWakeWord)")
            return True
        except Exception as e:
            log(f"offline wake word failed ({e}) → using Google")
            self._oww = None
            self._oww_failed = True
            return False

    def _wait_wake(self):
        """Listen locally for "Hey Jarvis". Nothing leaves the PC until it is heard."""
        m = self._oww
        m.reset()
        buf = np.zeros(0, dtype=np.int16)
        thr = float(self.cfg.get("wake_threshold", 0.5))
        while self._running:
            if self._restart.is_set():
                return "RESTART"
            if self._force.is_set():
                return "FORCE"
            if self._paused():
                return "PAUSED"
            try:
                blk = self._q.get(timeout=0.5)
            except queue.Empty:
                if time.monotonic() - self._last_data > 3.0:
                    log("mic watchdog: no audio for 3 s → reopening")
                    self._restart.set()
                continue
            rms = float(np.sqrt(np.mean(blk * blk)) + 1e-9)
            a = 0.10 if rms < self.noise else 0.004
            self.noise = (1 - a) * self.noise + a * rms
            x = blk
            if self._fs != self.FS:
                n = int(len(x) * self.FS / self._fs)
                x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
            buf = np.concatenate([buf, (np.clip(x, -1, 1) * 32767).astype(np.int16)])
            while len(buf) >= 1280:
                frame, buf = buf[:1280], buf[1280:]
                score = float(m.predict(frame)[self._oww_key])
                if score >= thr:
                    log(f"wake word heard (score {score:.2f})")
                    m.reset()
                    return "WAKE"
        return "STOP"

    def _strip_wake(self, text):
        import difflib
        toks = text.split()
        wake = {w.lower() for w in self.cfg.get("wake_words", [])}
        while toks:
            t = toks[0].lower().strip(",.!?'")
            if (t in ("hey", "hi", "ok", "okay", "hay", "a", "yo") or t in wake
                    or difflib.SequenceMatcher(None, t, "jarvis").ratio() >= 0.6):
                toks.pop(0)
            else:
                break
        return " ".join(toks).strip(" ,.!?")

    # -- main loop -----------------------------------------------------
    def _loop(self):
        state = "wake"
        while self._running:
            if self._stream is None or self._restart.is_set():
                self._restart.clear()
                self._close()
                try:
                    self._open()
                    self.ok = True
                    state = "wake"
                    self.ev("ready", self.device_label)
                except Exception as e:
                    self.ok = False
                    log(f"mic error: {e}")
                    self.ev("error", str(e))
                    for _ in range(40):                      # retry in 4 s
                        if not self._running or self._restart.is_set():
                            break
                        time.sleep(0.1)
                    self._restart.set()
                    continue

            if self._force.is_set():
                self._force.clear()
                self._drain()
                state = "command"
                self.ev("listening", None)

            if self._paused():
                if self._muted and state == "command":
                    state = "wake"
                    self.ev("timeout", None)
                time.sleep(0.05)
                self._drain()
                continue

            need_wake = state == "wake" and self.cfg.get("wake_word_enabled", True)
            if need_wake and self._init_offline_wake():
                if self._announced != "offline":
                    self._announced = "offline"
                    self.ev("wake_engine", "offline")
                r = self._wait_wake()
                if r != "WAKE":
                    continue
                self.ev("detected", None)
                # said in one breath ("Hey Jarvis, open chrome")? → capture it straight away
                res = self._capture(max_wait=0.8, max_len=14.0, allow_force=False)
                if isinstance(res, str):
                    continue
                cmd = ""
                if res is not None:
                    self.ev("recognizing", None)
                    alts = self._stt(res)
                    if alts:
                        log(f"heard: {alts[0]!r}")
                        cmd = self._strip_wake(alts[0])
                if cmd:
                    self.ev("command", cmd)
                else:
                    state = "command"
                    self.ev("wake", None)
                continue
            if need_wake and self._announced != "google":
                self._announced = "google"
                self.ev("wake_engine", "google")
            res = self._capture(max_wait=7.0 if state == "command" else None,
                                max_len=9.0 if need_wake else 14.0,
                                allow_force=(state == "wake"))
            if isinstance(res, str):
                continue
            if res is None:
                if state == "command":
                    state = "wake"
                    self.ev("timeout", None)
                continue

            self.ev("recognizing", None)
            alts = self._stt(res)
            if not alts:
                if state == "command":
                    state = "wake"
                    self.ev("unclear", None)
                continue
            log(f"heard: {alts[0]!r}" + (f"  (+{len(alts) - 1} alt)" if len(alts) > 1 else ""))

            if need_wake:
                rest = self._find_wake(alts)
                if rest is None:
                    self.ev("ignored", alts[0])
                elif rest:
                    self.ev("command", rest)
                else:
                    state = "command"
                    self.ev("wake", None)
            else:
                state = "wake"
                cmd = self._strip_wake(alts[0]) if self._oww is not None else alts[0]
                self.ev("command", cmd or alts[0])


# ══════════════════════════════════════════════════════════════════
# WORLD DATA — weather via Open-Meteo (free, no API key)
# ══════════════════════════════════════════════════════════════════

WMO = {
    0: ("clear skies", "☀"), 1: ("mostly clear skies", "☀"), 2: ("partly cloudy skies", "⛅"),
    3: ("overcast skies", "☁"), 45: ("fog", "≋"), 48: ("freezing fog", "≋"),
    51: ("light drizzle", "☂"), 53: ("drizzle", "☂"), 55: ("heavy drizzle", "☂"),
    56: ("freezing drizzle", "☂"), 57: ("freezing drizzle", "☂"),
    61: ("light rain", "☂"), 63: ("rain", "☂"), 65: ("heavy rain", "☂"),
    66: ("freezing rain", "☂"), 67: ("freezing rain", "☂"),
    71: ("light snow", "❄"), 73: ("snow", "❄"), 75: ("heavy snow", "❄"), 77: ("snow grains", "❄"),
    80: ("light showers", "☂"), 81: ("showers", "☂"), 82: ("violent showers", "☂"),
    85: ("snow showers", "❄"), 86: ("heavy snow showers", "❄"),
    95: ("thunderstorms", "⚡"), 96: ("thunderstorms with hail", "⚡"), 99: ("severe thunderstorms", "⚡"),
}


class Weather:
    def __init__(self, cfg):
        self.cfg = cfg
        self._cache = None
        self._t = 0.0
        self._lock = threading.Lock()

    @property
    def cached(self):
        return self._cache

    def invalidate(self):
        self._cache = None

    @staticmethod
    def _json(url):
        req = urllib.request.Request(url, headers={"User-Agent": f"JARVIS-desktop/{VERSION}"})
        with urllib.request.urlopen(req, timeout=7) as r:
            return json.loads(r.read().decode("utf-8"))

    def _fetch(self, lat, lon, city):
        url = ("https://api.open-meteo.com/v1/forecast?latitude={:.4f}&longitude={:.4f}"
               "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m"
               "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
               "&timezone=auto&forecast_days=1").format(lat, lon)
        d = self._json(url)
        cur, day = d["current"], d.get("daily", {})
        desc, icon = WMO.get(int(cur.get("weather_code", 0)), ("unsettled weather", "☁"))

        def first(k):
            v = day.get(k) or [None]
            return v[0]

        temp = round(cur["temperature_2m"])
        return {"temp": temp, "feels": round(cur.get("apparent_temperature", temp)),
                "humidity": cur.get("relative_humidity_2m"), "wind": cur.get("wind_speed_10m"),
                "desc": desc, "icon": icon, "hi": first("temperature_2m_max"),
                "lo": first("temperature_2m_min"), "rain": first("precipitation_probability_max"),
                "city": city}

    def get(self, max_age=900):
        with self._lock:
            if self._cache and time.monotonic() - self._t < max_age:
                return self._cache
        lat, lon = self.cfg.get("lat"), self.cfg.get("lon")
        if lat is None or lon is None:
            raise RuntimeError("no location set (Settings → City)")
        w = self._fetch(lat, lon, self.cfg.get("city") or "your area")
        with self._lock:
            self._cache, self._t = w, time.monotonic()
        return w

    def geocode(self, name):
        from urllib.parse import quote
        d = self._json(f"https://geocoding-api.open-meteo.com/v1/search?name={quote(name)}&count=1&language=en&format=json")
        r = (d.get("results") or [None])[0]
        if not r:
            raise RuntimeError(f"no place called {name}")
        return r["name"], float(r["latitude"]), float(r["longitude"])

    def get_for(self, name):
        city, lat, lon = self.geocode(name)
        return self._fetch(lat, lon, city)

    @staticmethod
    def summary(w, full=True, title="sir"):
        s = f"It's {w['temp']} degrees with {w['desc']} in {w['city']}"
        if full and w.get("hi") is not None and w.get("lo") is not None:
            s += f". Today's high is {round(w['hi'])}, low {round(w['lo'])}"
        if full and abs(w["feels"] - w["temp"]) >= 3:
            s += f"; it feels like {w['feels']}"
        s += "."
        rain = w.get("rain")
        if full and rain is not None and rain >= 50 and "rain" not in w["desc"] and "shower" not in w["desc"]:
            s += f" There's a {rain} percent chance of rain later — I'd take an umbrella, {title}."
        return s


# ══════════════════════════════════════════════════════════════════
# TIMERS & REMINDERS
# ══════════════════════════════════════════════════════════════════

NUMWORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
            "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
            "twenty five": 25, "thirty": 30, "forty": 40, "forty five": 45, "fifty": 50, "sixty": 60,
            "ninety": 90}
UNITS = {"s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1, "min": 60, "mins": 60, "minute": 60,
         "minutes": 60, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600}
_NUM = r"\d+(?:\.\d+)?|" + "|".join(sorted(map(re.escape, NUMWORDS), key=len, reverse=True))
_UNIT = r"seconds?|secs?|minutes?|mins?|hours?|hrs?"
_DUR = re.compile(rf"\b({_NUM})\s*({_UNIT})\b")
_HALF = re.compile(rf"\b({_NUM})\s*({_UNIT})\s+and a half\b")


def parse_duration(text):
    t = " " + (text or "").lower().replace("-", " ") + " "
    total = 0.0
    if "half an hour" in t:
        total += 1800
        t = t.replace("half an hour", " ")
    for num, unit in _HALF.findall(t):
        total += 0.5 * UNITS[unit]
    for num, unit in _DUR.findall(t):
        n = float(num) if num[0].isdigit() else NUMWORDS[num]
        total += n * UNITS[unit]
    return int(total) if total >= 1 else None


def fmt_duration(sec):
    sec = max(0, int(round(sec)))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h} hour{'s' * (h != 1)}")
    if m:
        parts.append(f"{m} minute{'s' * (m != 1)}")
    if s and not h:
        parts.append(f"{s} second{'s' * (s != 1)}")
    return " and ".join(parts) or "0 seconds"


def fmt_clock(sec):
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


_SWAP = {"my": "your", "me": "you", "i": "you", "i'm": "you're", "myself": "yourself", "mine": "yours"}


def swap_person(text):
    return re.sub(r"\b(i'm|myself|mine|my|me|i)\b", lambda m: _SWAP[m.group(1).lower()], text, flags=re.I)


class TimerBank:
    def __init__(self, on_fire):
        self.on_fire = on_fire
        self._items = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def add(self, seconds, label, kind):
        tid = next(self._ids)
        t = threading.Timer(seconds, self._fire, args=(tid,))
        t.daemon = True
        with self._lock:
            self._items[tid] = {"label": label, "due": time.time() + seconds, "kind": kind,
                                "timer": t, "secs": seconds}
        t.start()
        return tid

    def _fire(self, tid):
        with self._lock:
            it = self._items.pop(tid, None)
        if it:
            self.on_fire(it)

    def cancel_all(self):
        with self._lock:
            items = list(self._items.values())
            self._items.clear()
        for it in items:
            it["timer"].cancel()
        return len(items)

    def active(self):
        now = time.time()
        with self._lock:
            return sorted(((it["due"] - now, it["label"], it["kind"]) for it in self._items.values()),
                          key=lambda x: x[0])


# ══════════════════════════════════════════════════════════════════
# SOUND FX + GLOBAL HOTKEY  (Windows only, no extra packages)
# ══════════════════════════════════════════════════════════════════

_CHIMES = {
    "listen": [(784, 40), (1175, 60)],
    "done":   [(1175, 40), (1568, 70)],
    "alert":  [(880, 110), (660, 110), (880, 140)],
    "timer":  [(1047, 110), (1319, 110), (1568, 170), (0, 140), (1047, 110), (1319, 110), (1568, 170)],
}


def chime(kind, cfg, wait=False):
    if not IS_WIN or not cfg.get("sound_fx", True):
        return
    seq = _CHIMES.get(kind, [])

    def run():
        try:
            import winsound
            for f, d in seq:
                if f:
                    winsound.Beep(f, d)
                else:
                    time.sleep(d / 1000)
        except Exception:
            pass

    if wait:
        run()
    else:
        threading.Thread(target=run, daemon=True).start()


def start_global_hotkey(callback):
    """Ctrl+Alt+J anywhere in Windows → callback()."""
    if not IS_WIN:
        return

    def run():
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, WM_HOTKEY = 0x1, 0x2, 0x4000, 0x0312
        if not user32.RegisterHotKey(None, 0x4A56, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord("J")):
            log("global hotkey Ctrl+Alt+J is already used by another app")
            return
        log("global hotkey ready: Ctrl+Alt+J")
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                try:
                    callback()
                except Exception as e:
                    log(f"hotkey error: {e}")

    threading.Thread(target=run, daemon=True, name="hotkey").start()


# ══════════════════════════════════════════════════════════════════
# ASSISTANT CONTROLLER
# ══════════════════════════════════════════════════════════════════

RE_EXIT = re.compile(r"(?:ok(?:ay)? )?(?:goodbye|good bye|bye(?: bye)?|exit|quit|shut yourself down|"
                     r"close yourself|sign off|power down)(?: jarvis| sir)?")
RE_STOP = re.compile(r"(?:stop|stop talking|shut up|be quiet|quiet|silence|enough|cancel|that's enough)(?: jarvis| please)?")
RE_CLEAR = re.compile(r"(?:clear|reset|wipe) (?:the |your )?(?:history|memory|conversation|chat)|forget everything")
RE_TIME = re.compile(r"what(?:'s| is) the time|what time is it|(?:tell me )?the time")
RE_DATE = re.compile(r"what(?:'s| is) (?:the |today's )?date|what day is (?:it|today)")
RE_VISION = re.compile(r"(?:analy[sz]e|describe|scan|look at|read|explain) (?:my |the |this )?screen|"
                       r"what(?:'s| is) on (?:my |the )?screen|what am i looking at")
RE_BRIEF = re.compile(r"(?:give me (?:a |the |my )?|run (?:a |the )?)?(?:daily |morning |evening )?"
                      r"(?:briefing|brief me|status report|sitrep|situation report)|what did i miss|catch me up")
RE_WEATHER = re.compile(r"(?:what(?:'s| is) the |how(?:'s| is) the |check the |show (?:me )?the )?weather"
                        r"(?: like)?(?: (?:today|outside|now|right now))?(?: in [a-z .'-]+)?|"
                        r"(?:is it|will it|is it going to) (?:rain|snow)(?:ing)?(?: today| later| tonight)?(?: in [a-z .'-]+)?|"
                        r"(?:what(?:'s| is) the )?temperature(?: outside| today| now)?(?: in [a-z .'-]+)?|"
                        r"do i need an umbrella(?: today)?|how (?:hot|cold|warm) is it(?: outside)?")
RE_TIMER_A = re.compile(r"(?:set|start|create|make|put on) (?:a |an )?(?!(?:a|an) timer\b)(.+?) timer(?: (?:for|called|named) (.+))?")
RE_TIMER_B = re.compile(r"(?:set |start |create |make )?(?:a |an )?timer (?:for |of )?(.+?)(?: (?:for|called|named) (.+))?")
RE_REMIND_A = re.compile(r"remind me (?:in|after) (.+?) (to|that|about) (.+)")
RE_REMIND_B = re.compile(r"remind me (to|that|about) (.+?) (?:in|after) (.+)")
RE_REMIND_C = re.compile(r"in (.+?),? remind me (to|that|about) (.+)")
RE_TIMER_CANCEL = re.compile(r"(?:cancel|stop|clear|delete|remove) (?:all )?(?:the |my )?(?:timers?|reminders?)")
RE_TIMER_LEFT = re.compile(r"how (?:much time|long) (?:is )?(?:left|remaining)(?: on (?:the |my )?timer)?|"
                           r"(?:check|show|list) (?:the |my )?(?:timers?|reminders?)|"
                           r"(?:what|which) (?:timers?|reminders?) (?:are|do i have)(?: running| active| set)?")
RE_PROTO_LIST = re.compile(r"(?:list|show|what are)(?: the| my| your)? protocols|which protocols(?: do (?:you|i) have)?")
RE_PROTO = re.compile(r"(?:activate|initiate|engage|start|run|enable|launch|begin|execute) (?:the )?(.+?) (?:protocol|mode)|"
                      r"(.+?) (?:protocol|mode)(?: (?:on|now|activate|engage))?")
RE_HOLO = re.compile(r"(?:go |switch to |enter |activate )?(?:holo(?:graphic)?|hologram)(?: mode| view)?|"
                     r"(?:go |switch to |enter |activate )?(?:compact|mini) (?:mode|view)|minimi[sz]e yourself|go holographic")
RE_UNHOLO = re.compile(r"come back|full ?screen mode|full view|restore yourself|show yourself|maximi[sz]e yourself|"
                       r"exit (?:holo(?:graphic)?|hologram|compact|mini) mode")
RE_MIC_MUTE = re.compile(r"(?:mute|disable|turn off) (?:the |your )?(?:mic|microphone)|stop listening|go silent")


def daypart(h=None):
    h = datetime.datetime.now().hour if h is None else h
    return "morning" if 5 <= h < 12 else "afternoon" if 12 <= h < 17 else "evening"


def ordinal(n):
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def speak_time(dt):
    return dt.strftime("%I:%M %p").lstrip("0")


def _help_text(a):
    protos = ", ".join((a.cfg.get("protocols") or {}).keys()) or "none yet"
    return (f"I can open and close applications, control volume and brightness, manage files, search the web, "
            f"check the weather, run timers and reminders, read your screen, and execute protocols — "
            f"currently {protos}. For anything else, just ask, {a.title}.")


def _greet_small(a):
    w = a.weather.cached
    extra = " " + Weather.summary(w, full=False) if w else ""
    return f"Good {daypart()}, {a.title}.{extra}"


SMALLTALK = [
    (r"(?:are )?you (?:up|there|awake|online|around)|(?:hey |hello |hi )?jarvis(?: are you there)?|you there",
     ["Always, {t}.", "Right here, {t}.", "Online and at your service, {t}."]),
    (r"(?:hello|hi|hey)(?: there| jarvis)?", ["Hello, {t}. How may I help?", "Good to see you, {t}."]),
    (r"good (?:morning|afternoon|evening)(?: jarvis)?", _greet_small),
    (r"wake up,? daddy'?s home|(?:i'?m|i am) (?:home|back)(?: jarvis)?|honey,? i'?m home",
     ["Welcome home, {t}. Shall I bring your workspace online?", "Welcome back, {t}. Everything is as you left it."]),
    (r"how are you(?: doing)?(?: today)?|how(?:'s| is) it going|how do you feel",
     ["All systems nominal, {t}. Thank you for asking.", "Running at peak efficiency, {t}. And yourself?"]),
    (r"(?:thank(?:s| you)|cheers)(?: (?:so|very) much)?(?: jarvis)?",
     ["My pleasure, {t}.", "Always happy to help, {t}.", "Anytime, {t}."]),
    (r"(?:good (?:job|work)|well done|nice work)(?: jarvis)?|you(?:'re| are) (?:awesome|great|the best|amazing|brilliant)(?: jarvis)?",
     ["I do try, {t}.", "Most kind, {t}.", "I'll make a note of that for my performance review."]),
    (r"good night(?: jarvis)?", ["Good night, {t}. I'll keep an eye on things.", "Rest well, {t}."]),
    (r"who are you|what(?:'s| is) your name|introduce yourself|what are you",
     ["I'm J.A.R.V.I.S. — Just A Rather Very Intelligent System. I run your machine, answer questions, "
      "keep time, and generally try to keep things in order, {t}."]),
    (r"what can you do|help|what are your (?:abilities|capabilities|commands)", _help_text),
]


class _SentenceFeeder:
    """Turns a token stream into spoken sentences as soon as each one is complete."""
    BOUND = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[A-Z0-9])|\n+")

    def __init__(self, speak, title, limit=900):
        self.speak, self.title, self.limit = speak, title, limit
        self.buf, self.in_code, self.code_noted = "", False, False
        self.spoken, self.capped = 0, False

    def feed(self, piece):
        self.buf += piece
        self._pump(False)

    def finish(self):
        self._pump(True)

    def _emit(self, s):
        s = s.strip()
        if not s or self.capped or not re.search(r"\w", s):
            return
        self.speak(s)
        self.spoken += len(s)
        if self.spoken >= self.limit:
            self.capped = True
            self.speak(f"The rest is on screen, {self.title}.")

    def _pump(self, final):
        while True:
            if self.in_code:
                i = self.buf.find("```")
                if i < 0:
                    self.buf = "" if final else self.buf[-2:]
                    return
                self.buf, self.in_code = self.buf[i + 3:], False
                continue
            i = self.buf.find("```")
            if i >= 0:
                for part in self.BOUND.split(self.buf[:i]):
                    self._emit(part)
                self.buf, self.in_code = self.buf[i + 3:], True
                if not self.code_noted:
                    self.code_noted = True
                    self._emit(f"I've put the code on screen, {self.title}.")
                continue
            last = 0
            for m in self.BOUND.finditer(self.buf):
                self._emit(self.buf[last:m.start()])
                last = m.end()
            self.buf = self.buf[last:]
            if final:
                self._emit(self.buf)
                self.buf = ""
            return


class Assistant:
    def __init__(self, cfg, ui):
        self.cfg, self.ui = cfg, ui
        self.memory = Memory(MEMORY_FILE, cfg.get("max_history", 30))
        self.brain = AIBrain(self.memory, cfg)
        self.parser = CommandParser()
        self.vision = Vision(cfg)
        self.weather = Weather(cfg)
        self.timers = TimerBank(self._timer_fired)
        self.tts = TTSEngine(cfg, on_start=self._tts_start, on_end=self._tts_end)
        self.mic = MicEngine(cfg, self._mic_event)
        self.ai_online = False
        self.last_active = time.monotonic()
        self._jobs = queue.Queue()
        threading.Thread(target=self._worker, daemon=True, name="jobs").start()

    @property
    def title(self):
        return (self.cfg.get("user_title") or "sir").strip()

    @property
    def Title(self):
        t = self.title
        return t[:1].upper() + t[1:]

    # -- lifecycle -------------------------------------------------------
    def boot(self):
        ui = self.ui
        online, msg = check_ollama(self.cfg)
        self.ai_online = online and not msg.startswith("missing")
        log(f"ollama: {'online' if online else 'offline'} — {msg}")
        ui.post(lambda: ui.on_ai_status(online, msg))
        val = self.cfg["ai_model"].upper() if self.ai_online else ("MODEL MISSING" if online else "OFFLINE")
        ui.post(lambda: ui.boot_step("NEURAL INTERFACE", val, self.ai_online))

        self.mic.start()

        for _ in range(80):
            if self.tts.backend != "init":
                break
            time.sleep(0.05)
        tts_desc, tts_ok = self.tts.describe().upper(), self.tts.backend != "none"
        ui.post(lambda: ui.boot_step("VOICE SYNTHESIS", tts_desc, tts_ok))

        self._refresh_weather(boot=True)
        threading.Thread(target=self._monitor, daemon=True, name="monitor").start()
        threading.Thread(target=self._weather_loop, daemon=True, name="weather").start()

    def greet(self):
        h = datetime.datetime.now().hour
        parts = [f"Good {daypart(h)}, {self.title}." if 5 <= h < 23 else f"Burning the midnight oil, {self.title}?",
                 "J.A.R.V.I.S. is online."]
        w = self.weather.cached
        if w:
            parts.append(Weather.summary(w, full=False))
        if not self.mic.ok:
            parts.append("I can't reach a microphone, so you'll have to type for now.")
        elif not self.ai_online:
            parts.append("The language model is offline, but local systems are at your disposal.")
        else:
            parts.append("All systems are operational.")
        self.say(" ".join(parts))

    def shutdown(self):
        self.mic.stop()
        self.timers.cancel_all()
        self.tts.shutdown()

    # -- background -------------------------------------------------------
    def _refresh_weather(self, boot=False):
        ui = self.ui
        try:
            w = self.weather.get(max_age=900 if boot else 0)
            ui.post(lambda: ui.on_weather(w))
            if boot:
                val = f"{w['city'].upper()} · {w['temp']}°C · {w['desc'].upper()}"
                ui.post(lambda: ui.boot_step("ENVIRONMENT", val, True))
            return w
        except Exception as e:
            log(f"weather error: {e}")
            if boot:
                ui.post(lambda: ui.boot_step("ENVIRONMENT", "NO DATA", False))
            return None

    def _weather_loop(self):
        while True:
            time.sleep(900)
            self._refresh_weather()

    def _monitor(self):
        hot_cpu = hot_ram = 0
        warned, bat_flags = {}, set()
        while True:
            time.sleep(20)
            if not self.cfg.get("proactive_alerts", True) or not HAS_PSUTIL:
                continue
            try:
                st = self.ui._stats
                cpu, ram = st.get("CPU", 0), st.get("RAM", 0)
                hot_cpu = hot_cpu + 1 if cpu >= 90 else 0
                hot_ram = hot_ram + 1 if ram >= 92 else 0
                now = time.monotonic()
                if hot_cpu >= 3 and now - warned.get("cpu", -1e9) > 900:
                    warned["cpu"] = now
                    self.alert(f"{self.Title}, CPU load has been above 90 percent for the past minute.")
                if hot_ram >= 3 and now - warned.get("ram", -1e9) > 900:
                    warned["ram"] = now
                    self.alert(f"Memory usage is at {ram:.0f} percent, {self.title}. You may want to close something.")
                bat = psutil.sensors_battery()
                if bat:
                    if bat.power_plugged:
                        bat_flags.clear()
                    else:
                        crossed = [lv for lv in (20, 10, 5) if bat.percent <= lv and lv not in bat_flags]
                        if crossed:
                            bat_flags.update(crossed)
                            tip = "I'd plug in soon." if bat.percent > 10 else "Please connect power, or I'll be going dark shortly."
                            self.alert(f"{self.Title}, battery is at {bat.percent:.0f} percent. {tip}")
                dt = datetime.datetime.now()
                key = dt.strftime("%Y%m%d%H")
                if (dt.hour in (1, 2, 3) and dt.minute < 2 and warned.get("late") != key
                        and now - self.last_active < 1800):
                    warned["late"] = key
                    self.alert(f"{self.Title}, it's {dt.hour} AM. Might I suggest some rest?", level="info", sound="done")
            except Exception as e:
                log(f"monitor error: {e}")

    def _timer_fired(self, it):
        if it["kind"] == "reminder":
            msg = f"{self.Title}, you asked me to remind you {it['label']}."
        elif it["label"]:
            msg = f"{self.Title}, your {it['label']} timer is up."
        else:
            msg = f"{self.Title}, your {fmt_duration(it['secs'])} timer is up."
        self.ui.post(self.ui.refresh_timers)
        self.alert(msg, level="info", sound="timer")

    def alert(self, text, level="warn", sound="alert"):
        ui = self.ui
        ui.post(lambda: (ui.show_alert(text, level), ui.add_assistant(text, alert=True)))
        if IS_WIN and self.cfg.get("sound_fx", True):
            quiet = not self.tts.speaking
            if quiet:
                self.mic.set_tts_busy(True)
            chime(sound, self.cfg, wait=True)
            if quiet and not self.tts.speaking:
                self.mic.set_tts_busy(False)
        if self.cfg.get("speak_replies", True):
            self.tts.speak(text)

    # -- events ------------------------------------------------------------
    def _tts_start(self):
        self.mic.set_tts_busy(True)
        self.ui.post(lambda: self.ui.set_flag("speaking", True))

    def _tts_end(self):
        self.mic.set_tts_busy(False)
        self.ui.post(lambda: self.ui.set_flag("speaking", False))

    def _mic_event(self, kind, payload):
        ui = self.ui
        if kind == "ready":
            ui.post(lambda: ui.on_mic_ready(payload))
        elif kind == "error":
            ui.post(lambda: ui.on_mic_error(payload))
        elif kind == "hearing":
            ui.post(lambda: ui.set_flag("hearing", payload))
        elif kind == "listening":
            chime("listen", self.cfg)
            ui.post(lambda: (ui.set_flag("listening", True), ui.set_status(f"Listening — go ahead, {self.title}.")))
        elif kind == "recognizing":
            ui.post(lambda: ui.set_status("Recognising…"))
        elif kind == "ignored":
            ui.post(lambda: (ui.show_heard(payload, ignored=True), ui.set_status(ui.idle_hint())))
        elif kind == "wake":
            ui.post(lambda: (ui.set_flag("listening", True), ui.set_status(f"Yes, {self.title}?")))
            self.say(random.choice([f"Yes, {self.title}?", "At your service.", f"{self.Title}?",
                                    f"Listening, {self.title}."]), chat=False)
        elif kind == "command":
            ui.post(lambda: ui.set_flag("listening", False))
            self.submit(payload, source="voice")
        elif kind == "timeout":
            ui.post(lambda: (ui.set_flag("listening", False), ui.set_status(ui.idle_hint())))
        elif kind == "unclear":
            ui.post(lambda: (ui.set_flag("listening", False), ui.set_status(f"Didn't catch that, {self.title}.")))
        elif kind == "detected":
            ui.post(lambda: (ui.set_flag("listening", True), ui.set_status(f"Listening, {self.title}…")))
        elif kind == "wake_engine":
            ui.post(lambda: ui.on_wake_engine(payload))
        elif kind == "stt_error":
            ui.post(lambda: (ui.add_system(payload), ui.set_status("Speech service offline")))

    # -- commands ------------------------------------------------------------
    def submit(self, text, source="text"):
        text = (text or "").strip()
        if not text:
            return
        self.last_active = time.monotonic()
        self.ui.post(lambda: (self.ui.add_user(text, source), self.ui.show_heard(text)))
        if RE_STOP.fullmatch(normalize(text).lower()):
            self.tts.stop()
            return
        self._jobs.put(text)

    def say(self, text, chat=True):
        if chat:
            self.ui.post(lambda: self.ui.add_assistant(text))
        if self.cfg.get("speak_replies", True):
            self.tts.speak(text)

    def _worker(self):
        while True:
            text = self._jobs.get()
            self.ui.post(lambda: (self.ui.set_flag("thinking", True), self.ui.set_status("Processing…")))
            try:
                self._handle(text)
            except Exception as e:
                log(f"handler error: {e}")
                self.say(f"Something went wrong, {self.title}: {e}")
            finally:
                self.ui.post(lambda: (self.ui.set_flag("thinking", False), self.ui.set_status(self.ui.idle_hint())))

    def briefing(self):
        now = datetime.datetime.now()
        parts = [f"Good {daypart(now.hour)}, {self.title}. It's {speak_time(now)} on {now:%A}, "
                 f"the {ordinal(now.day)} of {now:%B}."]
        try:
            parts.append(Weather.summary(self.weather.get(), full=True, title=self.title))
        except Exception:
            parts.append("Weather data is unavailable at the moment.")
        st = self.ui._stats
        sysline = f"Systems are nominal: CPU at {st.get('CPU', 0):.0f} percent, memory at {st.get('RAM', 0):.0f} percent"
        if HAS_PSUTIL:
            try:
                bat = psutil.sensors_battery()
                if bat:
                    sysline += f", battery {bat.percent:.0f} percent" + (" and charging" if bat.power_plugged else "")
            except Exception:
                pass
        parts.append(sysline + ".")
        act = self.timers.active()
        if act:
            parts.append(f"You have {len(act)} active timer{'s' * (len(act) != 1)}; the next ends in {fmt_duration(act[0][0])}.")
        if not self.ai_online:
            parts.append("The language model is currently offline.")
        return " ".join(parts)

    def _weather_reply(self, c):
        m = re.search(r" in ([a-z][a-z .'-]+)$", c)
        city = (self.cfg.get("city") or "").lower()
        try:
            if m and m.group(1).strip() not in (city, "here", "my area", "my city"):
                w = self.weather.get_for(m.group(1).strip())
            else:
                w = self.weather.get(max_age=600)
                self.ui.post(lambda: self.ui.on_weather(w))
        except Exception as e:
            log(f"weather error: {e}")
            return f"I'm unable to reach the weather service at the moment, {self.title}."
        if any(k in c for k in ("rain", "umbrella", "snow")):
            r = w.get("rain")
            if r is None:
                return Weather.summary(w, title=self.title)
            if r >= 50:
                return f"Likely, {self.title}. There's a {r} percent chance of precipitation in {w['city']} today. I'd take an umbrella."
            if r >= 20:
                return f"Possibly — a {r} percent chance in {w['city']} today."
            return f"Unlikely, {self.title}. Only a {r} percent chance in {w['city']} today."
        return Weather.summary(w, full=True, title=self.title)

    def _timer_cmd(self, c):
        ui = self.ui
        if RE_TIMER_CANCEL.fullmatch(c):
            n = self.timers.cancel_all()
            ui.post(ui.refresh_timers)
            self.say(f"Cancelled {n} timer{'s' * (n != 1)}." if n else f"There are no active timers, {self.title}.")
            return True
        if RE_TIMER_LEFT.fullmatch(c):
            act = self.timers.active()
            if not act:
                self.say(f"No active timers, {self.title}.")
            else:
                rem, label, kind = act[0]
                what = "reminder" if kind == "reminder" else (f"{label} timer" if label else "timer")
                more = f" You have {len(act) - 1} more." if len(act) > 1 else ""
                self.say(f"{fmt_duration(rem)} remaining on your {what}.{more}")
            return True

        for rx in (RE_TIMER_A, RE_TIMER_B):
            m = rx.fullmatch(c)
            if not m:
                continue
            dur, label = parse_duration(m.group(1)), (m.group(2) or "").strip()
            if not dur and label:
                dur, label = parse_duration(label), m.group(1).strip()
            label = re.sub(r"^(?:a|an|the|my)\b\s*", "", label).strip()
            if dur:
                self.timers.add(dur, label, "timer")
                ui.post(ui.refresh_timers)
                self.say(f"{fmt_duration(dur).capitalize()} on the clock{' for ' + label if label else ''}, {self.title}.")
                return True

        for rx, order in ((RE_REMIND_A, "d"), (RE_REMIND_B, "l"), (RE_REMIND_C, "d")):
            m = rx.fullmatch(c)
            if not m:
                continue
            if order == "d":
                d_s, conn, l_s = m.group(1), m.group(2), m.group(3)
            else:
                conn, l_s, d_s = m.group(1), m.group(2), m.group(3)
            dur = parse_duration(d_s)
            if dur:
                label = f"{conn} {swap_person(l_s.strip())}"
                self.timers.add(dur, label, "reminder")
                ui.post(ui.refresh_timers)
                self.say(f"Very well, {self.title}. I'll remind you {label} in {fmt_duration(dur)}.")
                return True
        return False

    def _run_protocol(self, name):
        protos = {k.lower(): v for k, v in (self.cfg.get("protocols") or {}).items()}
        stem = lambda s: re.sub(r"(?:ing|e)$", "", s.strip().lower())
        key = name.lower().strip()
        if key not in protos:
            key = next((k for k in protos if stem(k) == stem(key)), None)
            if not key:
                return False
        cmds = protos[key]
        ui = self.ui
        ui.post(lambda: ui.show_alert(f"{key.upper()} PROTOCOL ENGAGED", "info"))
        self.say(f"Initiating {key} protocol, {self.title}.")
        lines = []
        for cmd in cmds:
            try:
                r = self.parser.parse(cmd)
            except Exception as e:
                r = f"error: {e}"
            lines.append(f"• {cmd}  →  {(r or 'not a device command, skipped').splitlines()[0]}")
            time.sleep(0.5)
        ui.post(lambda: ui.add_assistant(f"{key.title()} protocol:\n" + "\n".join(lines)))
        chime("done", self.cfg)
        if self.cfg.get("speak_replies", True):
            self.tts.speak(f"{key.title()} protocol complete.")
        return True

    def _handle(self, text):
        c = normalize(text).lower()
        ui = self.ui

        if RE_EXIT.fullmatch(c):
            self.say(f"Signing off, {self.title}. Have a good one.")
            time.sleep(2.6)
            ui.post(ui.quit)
            return
        if RE_CLEAR.fullmatch(c):
            self.memory.clear()
            ui.post(ui.clear_chat)
            self.say(f"Memory cleared, {self.title}.")
            return
        for pat, resp in SMALLTALK:
            if re.fullmatch(pat, c):
                out = resp(self) if callable(resp) else random.choice(resp).format(t=self.title)
                self.say(out)
                return
        if RE_TIME.fullmatch(c):
            self.say(f"It's {speak_time(datetime.datetime.now())}, {self.title}.")
            return
        if RE_DATE.fullmatch(c):
            now = datetime.datetime.now()
            self.say(f"Today is {now:%A}, the {ordinal(now.day)} of {now:%B}, {now.year}.")
            return
        if RE_BRIEF.fullmatch(c):
            ui.post(lambda: ui.set_status("Compiling briefing…"))
            self.say(self.briefing())
            return
        if RE_WEATHER.fullmatch(c):
            self.say(self._weather_reply(c))
            return
        if self._timer_cmd(c):
            return
        if RE_PROTO_LIST.fullmatch(c):
            names = list((self.cfg.get("protocols") or {}).keys())
            self.say(f"Available protocols: {', '.join(names)}." if names else "No protocols are configured.")
            return
        if RE_HOLO.fullmatch(c):
            ui.post(ui.enter_holo)
            self.say("Switching to holographic mode.")
            return
        if RE_UNHOLO.fullmatch(c):
            ui.post(ui.exit_holo)
            self.say(f"Right here, {self.title}.")
            return
        if RE_MIC_MUTE.fullmatch(c):
            ui.post(lambda: ui.set_mic_muted(True))
            self.say("Microphone muted. Type, or tap the mic, when you need me.")
            return
        m = RE_PROTO.fullmatch(c)
        if m and self._run_protocol(m.group(1) or m.group(2) or ""):
            return
        if RE_VISION.fullmatch(c):
            ui.post(lambda: ui.set_status("Analysing screen…"))
            self.say(self.vision.analyze_screen())
            return

        result = self.parser.parse(text)
        if result is not None:
            ui.post(lambda: ui.add_assistant(result))
            if self.cfg.get("speak_replies", True):
                self.tts.speak((result.splitlines()[0] if result else "")[:220])
            return

        # AI — streamed into the chat and spoken sentence by sentence
        ui.post(ui.assistant_begin)
        feeder = _SentenceFeeder(self.tts.speak if self.cfg.get("speak_replies", True) else (lambda s: None),
                                 self.title)

        def on_tok(p):
            ui.post(lambda p=p: ui.assistant_token(p))
            feeder.feed(p)

        self.brain.reply_stream(text, on_tok)
        feeder.finish()
        ui.post(ui.assistant_end)


# ══════════════════════════════════════════════════════════════════
# UI — holographic HUD
# ══════════════════════════════════════════════════════════════════

class C:
    BG = "#03070d"
    PANEL = "#07111d"
    PANEL2 = "#0c1a2b"
    LINE = "#13283e"
    LINE2 = "#1f4060"
    CYAN = "#33d1ff"
    CYAN_HI = "#9beaff"
    TEAL = "#2ee6d6"
    GOLD = "#f5b942"
    ORANGE = "#ff8a3d"
    RED = "#ff4d5e"
    GREEN = "#3ee8a0"
    VIOLET = "#9b8cff"
    TEXT = "#d7ecff"
    SOFT = "#8aa4bf"
    MUTED = "#4f6680"
    WHITE = "#f2fbff"


F_HEAD = "Bahnschrift"          # ships with Windows 10/11; Tk falls back if missing
F_BODY = "Segoe UI"
F_MONO = "Consolas"

MODE_STYLE = {
    "boot":   ("INITIALISING", C.VIOLET),
    "idle":   ("STANDBY", C.CYAN),
    "listen": ("LISTENING", C.GREEN),
    "think":  ("PROCESSING", C.GOLD),
    "speak":  ("SPEAKING", C.CYAN_HI),
    "muted":  ("MIC MUTED", C.MUTED),
    "error":  ("MIC OFFLINE", C.RED),
}


def blend(c1, c2, t):
    t = max(0.0, min(1.0, t))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def level_norm(rms):
    db = 20 * math.log10(max(rms, 1e-6))
    return max(0.0, min(1.0, (db + 58) / 46))


def _hexagon(cx, cy, r, rot_deg=0.0):
    pts = []
    for i in range(6):
        a = math.radians(60 * i + rot_deg)
        pts += [cx + r * math.cos(a), cy - r * math.sin(a)]
    return pts


def draw_holo_core(c, cx, cy, R, acc, lv, ang, ph, mode, S, rich=True, tag="dyn"):
    """The animated holographic core — shared by the main HUD and the floating orb."""
    T = tag
    cos, sin, rad = math.cos, math.sin, math.radians

    for rr, t in ((1.0, 0.035), (0.8, 0.05), (0.58, 0.07 + 0.08 * lv)):
        r = R * rr
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=blend(C.BG, acc, t), outline="", tags=T)

    # level ticks — light up symmetrically from 12 o'clock with the mic / voice level
    n = 72 if rich else 48
    lit = n * lv
    dim = blend(C.BG, acc, 0.22)
    for i in range(n):
        a = rad(90 - i * 360 / n)
        long = i % 6 == 0
        r1, r2 = R * (0.89 if long else 0.925), R * 0.965
        on = min(i, n - i) < lit / 2
        c.create_line(cx + r1 * cos(a), cy - r1 * sin(a), cx + r2 * cos(a), cy - r2 * sin(a),
                      fill=acc if on else dim, width=S(2) if long else 1, tags=T)

    r = R * 0.83
    for k in range(3):
        c.create_arc(cx - r, cy - r, cx + r, cy + r, start=ang + k * 120, extent=76, style="arc",
                     outline=acc, width=S(3), tags=T)
    r = R * 0.765
    gold = blend(C.BG, C.GOLD, 0.85)
    for k in range(6):
        c.create_arc(cx - r, cy - r, cx + r, cy + r, start=-ang * 0.6 + k * 60, extent=20, style="arc",
                     outline=gold, width=S(2), tags=T)

    base = (ang * 2.4) % 360                                   # radar sweep
    for k in range(7):
        a = rad(base - k * 3.5)
        c.create_line(cx + R * 0.44 * cos(a), cy - R * 0.44 * sin(a), cx + R * 0.7 * cos(a), cy - R * 0.7 * sin(a),
                      fill=blend(C.BG, acc, 0.75 * (1 - k / 7)), width=S(2) if k == 0 else 1, tags=T)

    r = R * 0.62
    c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=blend(C.BG, acc, 0.45), dash=(2, 5), tags=T)
    for k in range(3):
        a = rad(-ang * 1.3 + k * 120)
        tip = (cx + (r - S(8)) * cos(a), cy - (r - S(8)) * sin(a))
        p1 = (cx + r * cos(a + 0.07), cy - r * sin(a + 0.07))
        p2 = (cx + r * cos(a - 0.07), cy - r * sin(a - 0.07))
        c.create_polygon(*tip, *p1, *p2, fill=acc, outline="", tags=T)

    c.create_polygon(_hexagon(cx, cy, R * 0.42, ang * 0.25), fill=C.PANEL if rich else blend(C.BG, acc, 0.1),
                     outline=acc, width=S(2), tags=T)
    c.create_polygon(_hexagon(cx, cy, R * 0.31, 30 - ang * 0.5), fill="", outline=blend(C.BG, acc, 0.5), tags=T)

    pulse = 0.5 + 0.5 * math.sin(ph * 1.6)
    core = R * (0.1 + 0.02 * pulse + 0.1 * lv)
    for k, t in ((2.0, 0.2), (1.5, 0.45), (1.0, 1.0)):
        rr = core * k
        c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=blend(C.PANEL, acc, t), outline="", tags=T)
    rr = core * 0.42
    c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=C.WHITE, outline="", tags=T)

    if mode == "think":
        r = R * 0.9
        c.create_arc(cx - r, cy - r, cx + r, cy + r, start=-ang * 2, extent=46, style="arc",
                     outline=C.WHITE, width=S(2), tags=T)


class FlatButton(tk.Label):
    def __init__(self, parent, text, command, bg=C.PANEL2, fg=C.TEXT, hover=C.LINE2,
                 font=(F_BODY, 9), padx=12, pady=6, **kw):
        super().__init__(parent, text=text, bg=bg, fg=fg, font=font, padx=padx, pady=pady,
                         cursor="hand2", **kw)
        self._bg, self._hover, self._cmd = bg, hover, command
        self.bind("<Enter>", lambda e: self.config(bg=self._hover))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg))
        self.bind("<Button-1>", lambda e: self._cmd() if self._cmd else None)

    def set_colors(self, bg=None, fg=None):
        if bg:
            self._bg = bg
            self.config(bg=bg)
        if fg:
            self.config(fg=fg)


class Pill(tk.Frame):
    def __init__(self, parent, label, S):
        super().__init__(parent, bg=C.PANEL, highlightthickness=1, highlightbackground=C.LINE)
        self.dot = tk.Canvas(self, width=S(10), height=S(10), bg=C.PANEL, highlightthickness=0)
        self.dot.pack(side="left", padx=(S(9), S(5)), pady=S(6))
        self._d = self.dot.create_oval(1, 1, S(9), S(9), fill=C.MUTED, outline="")
        tk.Label(self, text=label, font=(F_HEAD, 8), fg=C.MUTED, bg=C.PANEL).pack(side="left")
        self.val = tk.Label(self, text="—", font=(F_HEAD, 9), fg=C.TEXT, bg=C.PANEL)
        self.val.pack(side="left", padx=(S(5), S(10)))

    def set(self, text, color):
        self.val.config(text=text)
        self.dot.itemconfig(self._d, fill=color)


class BootOverlay:
    """Full-window boot sequence that reports the real start-up checks."""
    TOTAL = 4

    def __init__(self, hud):
        self.hud = hud
        self.cv = tk.Canvas(hud.root, bg=C.BG, highlightthickness=0)
        self.cv.place(x=0, y=0, relwidth=1, relheight=1)
        self.cv.tk.call("raise", self.cv._w)
        self.mono = tkfont.Font(family=F_MONO, size=9)
        self.t0 = time.monotonic()
        self.steps = []
        self.done_at = None
        self._p = 0.0

    def step(self, label, value, ok):
        if not any(s[0] == label for s in self.steps):
            self.steps.append((label, str(value), ok, time.monotonic()))

    def tick(self):
        S, c = self.hud.S, self.cv
        now = time.monotonic()
        t = now - self.t0
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 100 or h < 100:
            return
        cx, cy = w / 2, h * 0.34
        R = min(w, h) * 0.16

        for k, (rr, col, wd, d) in enumerate(((1.0, C.CYAN, 3, 1), (0.84, C.GOLD, 2, -1),
                                             (0.68, C.CYAN, 1, 1), (1.14, C.LINE2, 1, -1))):
            p = max(0.0, min(1.0, (t - 0.12 * k) / 1.1))
            if p > 0:
                r = R * rr
                c.create_arc(cx - r, cy - r, cx + r, cy + r, start=90 + d * t * 40, extent=-359.9 * p,
                             style="arc", outline=col, width=S(wd))
        n = 60
        for i in range(int(n * min(1.0, t / 1.8))):
            a = math.radians(90 - i * 6)
            r1, r2 = R * 1.22, R * (1.3 if i % 5 == 0 else 1.26)
            c.create_line(cx + r1 * math.cos(a), cy - r1 * math.sin(a), cx + r2 * math.cos(a),
                          cy - r2 * math.sin(a), fill=blend(C.BG, C.CYAN, 0.5))
        grow = min(1.0, t / 0.8)
        pulse = 0.5 + 0.5 * math.sin(t * 5)
        core = R * (0.16 + 0.04 * pulse) * grow
        if core > 1:
            for k, tt in ((2.2, 0.15), (1.5, 0.4), (1.0, 1.0)):
                rr = core * k
                c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=blend(C.BG, C.CYAN, tt), outline="")
            rr = core * 0.45
            c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=C.WHITE, outline="")
            c.create_polygon(_hexagon(cx, cy, R * 0.42, t * 20), fill="", outline=blend(C.BG, C.CYAN, 0.7),
                             width=S(2))

        title = "J.A.R.V.I.S."
        k = int(len(title) * max(0.0, min(1.0, (t - 0.4) / 0.9)))
        ty = cy + R * 1.42 + S(26)
        c.create_text(cx, ty, text=title[:k], fill=C.WHITE, font=(F_HEAD, 28, "bold"))
        if t > 1.2:
            c.create_text(cx, ty + S(32), text="PERSONAL AI SYSTEM  ·  BOOT SEQUENCE", fill=C.MUTED, font=(F_HEAD, 9))

        bw = S(520)
        bx, by = cx - bw / 2, ty + S(62)
        self._p += (len(self.steps) / self.TOTAL - self._p) * 0.15
        c.create_rectangle(bx, by, bx + bw, by + S(3), fill=C.LINE, outline="")
        c.create_rectangle(bx, by, bx + bw * self._p, by + S(3), fill=C.CYAN, outline="")
        c.create_text(bx + bw, by - S(5), text=f"{int(self._p * 100 + 0.5):3d}%", anchor="se", fill=C.CYAN,
                      font=(F_MONO, 9))

        y = by + S(20)
        for label, value, ok, at in self.steps:
            head = f"{label:<18}{'·' * 12}  "
            shown = int((now - at) * 150)
            c.create_text(bx, y, text=head[:shown], anchor="nw", fill=C.SOFT, font=self.mono)
            if shown > len(head):
                c.create_text(bx + self.mono.measure(head), y, text=value[:shown - len(head)], anchor="nw",
                              fill=C.GREEN if ok else C.RED, font=self.mono)
            y += S(19)
        if len(self.steps) < self.TOTAL and int(t * 3) % 2 == 0:
            c.create_text(bx, y, text="▌", anchor="nw", fill=C.CYAN, font=self.mono)

        if self.done_at is None and ((len(self.steps) >= self.TOTAL and t > 2.6) or t > 8.0):
            self.done_at = now
        if self.done_at and now - self.done_at > 0.9:
            self.finish()

    def finish(self):
        try:
            self.cv.destroy()
        except Exception:
            pass
        if self.hud.boot is self:
            self.hud.boot = None
            self.hud.on_boot_overlay_done()


class HoloOrb(tk.Toplevel):
    """Floating, always-on-top, transparent holographic orb (F11 / "go holographic")."""
    KEY = "#010203"

    def __init__(self, hud):
        super().__init__(hud.root)
        self.hud = hud
        S = hud.S
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        bg = self.KEY
        try:
            self.attributes("-transparentcolor", self.KEY)
        except tk.TclError:
            bg = C.BG
        self.W, self.H = S(220), S(300)
        self.cv = tk.Canvas(self, width=self.W, height=self.H, bg=bg, highlightthickness=0, cursor="hand2")
        self.cv.pack()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = hud.cfg.get("holo_x"), hud.cfg.get("holo_y")
        if not (isinstance(x, int) and isinstance(y, int) and 0 <= x < sw - 40 and 0 <= y < sh - 40):
            x, y = sw - self.W - S(24), sh - self.H - S(64)
        self.geometry(f"{self.W}x{self.H}+{x}+{y}")
        self._drag, self._moved, self._click_job = None, False, None
        self.cv.bind("<ButtonPress-1>", self._press)
        self.cv.bind("<B1-Motion>", self._motion)
        self.cv.bind("<ButtonRelease-1>", self._release)
        self.cv.bind("<Double-Button-1>", self._double)
        self.cv.bind("<Button-3>", self._menu)
        self.bind("<Escape>", lambda e: hud.assistant.tts.stop())
        self.menu = tk.Menu(self, tearoff=0, bg=C.PANEL2, fg=C.TEXT, activebackground=C.LINE2,
                            activeforeground=C.WHITE, bd=0, font=(F_BODY, 9))
        self.menu.add_command(label="Talk   (Ctrl+Alt+J)", command=hud.push_to_talk)
        self.menu.add_command(label="Stop speaking", command=lambda: hud.assistant.tts.stop())
        self.menu.add_command(label="Mute / unmute mic", command=hud.toggle_mute)
        self.menu.add_command(label="Restore full HUD", command=hud.exit_holo)
        self.menu.add_separator()
        self.menu.add_command(label="Quit J.A.R.V.I.S.", command=hud.quit)

    def _press(self, e):
        self._drag = (e.x_root, e.y_root, self.winfo_x(), self.winfo_y())
        self._moved = False

    def _motion(self, e):
        if not self._drag:
            return
        dx, dy = e.x_root - self._drag[0], e.y_root - self._drag[1]
        if abs(dx) + abs(dy) > 4:
            self._moved = True
        if self._moved:
            self.geometry(f"+{self._drag[2] + dx}+{self._drag[3] + dy}")

    def _release(self, e):
        if self._moved:
            self.hud.cfg["holo_x"], self.hud.cfg["holo_y"] = self.winfo_x(), self.winfo_y()
            save_config(self.hud.cfg)
        else:
            if self._click_job:
                self.after_cancel(self._click_job)
            self._click_job = self.after(280, self._single)
        self._drag = None

    def _single(self):
        self._click_job = None
        self.hud.push_to_talk()

    def _double(self, e):
        if self._click_job:
            self.after_cancel(self._click_job)
            self._click_job = None
        self.hud.exit_holo()

    def _menu(self, e):
        self.menu.tk_popup(e.x_root, e.y_root)

    def draw(self):
        h, c, S = self.hud, self.cv, self.hud.S
        c.delete("all")
        cx = cy = self.W / 2
        R = self.W / 2 - S(8)
        acc = h._accent()
        draw_holo_core(c, cx, cy, R, acc, h.smooth, h.angle, h.phase, h.mode, S, rich=False, tag="d")
        c.create_text(cx, self.W + S(12), text=MODE_STYLE[h.mode][0], fill=acc, font=(F_HEAD, 10, "bold"))
        line = h.lbl_status.cget("text") if h.mode in ("listen", "think") else (h._last_line or h.lbl_status.cget("text"))
        c.create_text(cx, self.W + S(28), text=line[:120], fill=C.TEXT, font=(F_BODY, 8),
                      width=self.W - S(14), anchor="n", justify="center")


class HUD:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = load_config()
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
        S = self.S = lambda n: int(round(n * self.scale))

        self._q = queue.Queue()
        self.flags = {"speaking": False, "thinking": False, "listening": False,
                      "hearing": False, "ready": False, "mic_error": False}
        self.mode = "boot"
        self.angle = 0.0
        self.phase = 0.0
        self.levels = collections.deque([0.0] * 72, maxlen=72)
        self.smooth = 0.0
        self._net = None
        self._streaming = False
        self._stream_buf = ""
        self._stats = {"CPU": 0.0, "RAM": 0.0, "DISK": 0.0}
        self._brk = []
        self._rg = None
        self._mic_booted = False
        self._last_line = ""
        self._alert_job = None
        self.boot = None
        self.orb = None

        root.title("J.A.R.V.I.S.")
        root.configure(bg=C.BG)
        root.geometry(f"{S(1320)}x{S(860)}")
        root.minsize(S(1080), S(700))
        self._style()
        self._build()

        self.assistant = Assistant(self.cfg, self)
        self._load_previous_chat()

        root.protocol("WM_DELETE_WINDOW", self.quit)
        root.bind("<F2>", lambda e: self.push_to_talk())
        root.bind("<Control-space>", lambda e: self.push_to_talk())
        root.bind("<Escape>", lambda e: self.assistant.tts.stop())
        root.bind("<F11>", lambda e: self.enter_holo())
        start_global_hotkey(lambda: self.post(self.push_to_talk))

        if self.cfg.get("boot_sequence", True):
            self.boot = BootOverlay(self)
        self._pump()
        self._animate()
        self._tick_clock()
        self._tick_stats()
        self.root.after(80, lambda: [b.lift() for b in self._brk])
        threading.Thread(target=self.assistant.boot, daemon=True, name="boot").start()
        if not self.boot:
            self.root.after(1800, self.on_boot_overlay_done)

    # ── thread-safe UI calls ──────────────────────────────────────
    def post(self, fn):
        self._q.put(fn)

    def _pump(self):
        try:
            for _ in range(100):
                fn = self._q.get_nowait()
                try:
                    fn()
                except Exception as e:
                    log(f"ui error: {e}")
        except queue.Empty:
            pass
        self.root.after(30, self._pump)

    # ── styles ────────────────────────────────────────────────────
    def _style(self):
        st = ttk.Style(self.root)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("J.Vertical.TScrollbar", background=C.PANEL2, troughcolor=C.PANEL,
                     bordercolor=C.PANEL, lightcolor=C.PANEL2, darkcolor=C.PANEL2,
                     arrowcolor=C.MUTED, gripcount=0)
        st.map("J.Vertical.TScrollbar", background=[("active", C.LINE2)])
        st.configure("J.TCombobox", fieldbackground=C.PANEL2, background=C.PANEL2,
                     foreground=C.TEXT, arrowcolor=C.CYAN, bordercolor=C.LINE2,
                     lightcolor=C.PANEL2, darkcolor=C.PANEL2, padding=self.S(5))
        st.map("J.TCombobox", fieldbackground=[("readonly", C.PANEL2)],
               foreground=[("readonly", C.TEXT)], selectbackground=[("readonly", C.PANEL2)],
               selectforeground=[("readonly", C.TEXT)])
        self.root.option_add("*TCombobox*Listbox.background", C.PANEL2)
        self.root.option_add("*TCombobox*Listbox.foreground", C.TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", C.LINE2)
        self.root.option_add("*TCombobox*Listbox.font", (F_BODY, 9))

    def _brackets(self, w, col, L=14, t=2):
        S = self.S
        L, t = S(L), max(1, S(t))
        for relx, rely, anc in ((0, 0, "nw"), (1, 0, "ne"), (0, 1, "sw"), (1, 1, "se")):
            for ww, hh in ((L, t), (t, L)):
                f = tk.Frame(w, bg=col, width=ww, height=hh)
                f.place(relx=relx, rely=rely, anchor=anc)
                self._brk.append(f)

    def _panel(self, parent, title, accent=C.CYAN):
        S = self.S
        f = tk.Frame(parent, bg=C.PANEL, highlightthickness=1, highlightbackground=C.LINE)
        head = tk.Frame(f, bg=C.PANEL)
        head.pack(fill="x", padx=S(14), pady=(S(12), S(6)))
        tk.Frame(head, bg=accent, width=S(3), height=S(14)).pack(side="left")
        tk.Label(head, text=title, font=(F_HEAD, 9, "bold"), fg=C.SOFT, bg=C.PANEL).pack(side="left", padx=S(8))
        self._brackets(f, accent)
        return f

    def _sub(self, p, title, accent):
        S = self.S
        tk.Frame(p, bg=C.LINE, height=1).pack(fill="x", padx=S(14), pady=(S(10), S(8)))
        head = tk.Frame(p, bg=C.PANEL)
        head.pack(fill="x", padx=S(14), pady=(0, S(6)))
        tk.Frame(head, bg=accent, width=S(3), height=S(14)).pack(side="left")
        tk.Label(head, text=title, font=(F_HEAD, 9, "bold"), fg=C.SOFT, bg=C.PANEL).pack(side="left", padx=S(8))

    # ── layout ────────────────────────────────────────────────────
    def _build(self):
        S = self.S
        hdr = tk.Frame(self.root, bg=C.BG)
        hdr.pack(fill="x", padx=S(20), pady=(S(14), S(8)))

        logo = tk.Canvas(hdr, width=S(40), height=S(40), bg=C.BG, highlightthickness=0)
        logo.pack(side="left")
        cx = cy = S(20)
        logo.create_polygon(_hexagon(cx, cy, S(18), 30), outline=C.CYAN, fill=C.PANEL2, width=S(2))
        logo.create_polygon(_hexagon(cx, cy, S(10), 0), outline=C.GOLD, fill="", width=1)
        logo.create_oval(cx - S(4), cy - S(4), cx + S(4), cy + S(4), fill=C.CYAN_HI, outline="")

        tb = tk.Frame(hdr, bg=C.BG)
        tb.pack(side="left", padx=S(12))
        tk.Label(tb, text="J.A.R.V.I.S.", font=(F_HEAD, 18, "bold"), fg=C.WHITE, bg=C.BG).pack(anchor="w")
        tk.Label(tb, text=f"JUST A RATHER VERY INTELLIGENT SYSTEM  ·  v{VERSION}",
                 font=(F_HEAD, 7), fg=C.MUTED, bg=C.BG).pack(anchor="w")

        clock = tk.Frame(hdr, bg=C.BG)
        clock.pack(side="right")
        self.lbl_time = tk.Label(clock, text="", font=(F_HEAD, 18), fg=C.WHITE, bg=C.BG)
        self.lbl_time.pack(anchor="e")
        self.lbl_date = tk.Label(clock, text="", font=(F_HEAD, 8), fg=C.MUTED, bg=C.BG)
        self.lbl_date.pack(anchor="e")

        tk.Frame(hdr, bg=C.LINE2, width=1, height=S(34)).pack(side="right", padx=S(16))
        wx = tk.Frame(hdr, bg=C.BG)
        wx.pack(side="right")
        self.lbl_wx = tk.Label(wx, text="—", font=(F_HEAD, 18), fg=C.GOLD, bg=C.BG)
        self.lbl_wx.pack(anchor="e")
        self.lbl_wx_sub = tk.Label(wx, text=(self.cfg.get("city") or "").upper(), font=(F_HEAD, 8),
                                   fg=C.MUTED, bg=C.BG)
        self.lbl_wx_sub.pack(anchor="e")

        pills = tk.Frame(hdr, bg=C.BG)
        pills.pack(side="right", padx=S(18))
        self.pill_mode = Pill(pills, "STATE", S)
        self.pill_mic = Pill(pills, "MIC", S)
        self.pill_ai = Pill(pills, "AI", S)
        for p in (self.pill_ai, self.pill_mic, self.pill_mode):
            p.pack(side="right", padx=S(4))
        self.pill_ai.set("checking…", C.GOLD)
        self.pill_mic.set("starting…", C.GOLD)

        line = tk.Canvas(self.root, height=S(2), bg=C.BG, highlightthickness=0)
        line.pack(fill="x", padx=S(20))
        line.bind("<Configure>", lambda e: self._gradient_line(line, e.width))

        body = tk.Frame(self.root, bg=C.BG)
        body.pack(fill="both", expand=True, padx=S(20), pady=S(12))
        body.grid_columnconfigure(0, minsize=S(270), weight=0)
        body.grid_columnconfigure(1, weight=1)
        body.grid_columnconfigure(2, minsize=S(410), weight=0)
        body.grid_rowconfigure(0, weight=1)

        left = self._panel(body, "DIAGNOSTICS")
        left.grid(row=0, column=0, sticky="nsew")
        self._build_left(left)

        center = tk.Frame(body, bg=C.BG)
        center.grid(row=0, column=1, sticky="nsew", padx=S(14))
        self._build_center(center)

        right = self._panel(body, "CONVERSATION", accent=C.GOLD)
        right.grid(row=0, column=2, sticky="nsew")
        self._build_chat(right)

        self._build_footer()

    def _gradient_line(self, cv, w):
        cv.delete("all")
        n = 60
        for i in range(n):
            t = 1 - abs(i - n / 2) / (n / 2)
            col = blend(C.BG, C.GOLD if 26 <= i <= 33 else C.CYAN, t * 0.9)
            cv.create_rectangle(i * w / n, 0, (i + 1) * w / n + 1, self.S(2), fill=col, outline="")

    def _build_left(self, p):
        S = self.S
        self.gauges = tk.Canvas(p, width=S(240), height=S(104), bg=C.PANEL, highlightthickness=0)
        self.gauges.pack(fill="x", padx=S(10), pady=(S(2), S(4)))

        grid = tk.Frame(p, bg=C.PANEL)
        grid.pack(fill="x", padx=S(14))
        self.metrics = {}
        for i, key in enumerate(("BATTERY", "NET ↓", "NET ↑", "UPTIME")):
            tk.Label(grid, text=key, font=(F_HEAD, 8), fg=C.MUTED, bg=C.PANEL).grid(row=i, column=0, sticky="w", pady=S(2))
            v = tk.Label(grid, text="—", font=(F_MONO, 9), fg=C.TEXT, bg=C.PANEL)
            v.grid(row=i, column=1, sticky="e", pady=S(2))
            self.metrics[key] = v
        grid.grid_columnconfigure(1, weight=1)

        self._sub(p, "PROTOCOLS", C.GOLD)
        pr = tk.Frame(p, bg=C.PANEL)
        pr.pack(fill="x", padx=S(12))
        for i, name in enumerate(list((self.cfg.get("protocols") or {}).keys())[:6]):
            b = FlatButton(pr, name.upper(), lambda n=name: self.assistant.submit(f"activate {n} protocol", "button"),
                           fg=C.GOLD, font=(F_HEAD, 8, "bold"), pady=S(6))
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=S(2), pady=S(2))
        pr.grid_columnconfigure(0, weight=1)
        pr.grid_columnconfigure(1, weight=1)

        self._sub(p, "QUICK ACTIONS", C.CYAN)
        qa = tk.Frame(p, bg=C.PANEL)
        qa.pack(fill="x", padx=S(12))
        for i, (label, cmd) in enumerate((("Briefing", "daily briefing"), ("Weather", "what's the weather"),
                                          ("Screenshot", "take a screenshot"), ("Scan screen", "what's on my screen"))):
            b = FlatButton(qa, label, lambda c=cmd: self.assistant.submit(c, "button"), font=(F_BODY, 9), pady=S(6))
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=S(2), pady=S(2))
        qa.grid_columnconfigure(0, weight=1)
        qa.grid_columnconfigure(1, weight=1)

        self._sub(p, "TIMERS", C.GREEN)
        self.lbl_timers = tk.Label(p, text="No active timers", font=(F_MONO, 9), fg=C.MUTED, bg=C.PANEL,
                                   justify="left", anchor="nw")
        self.lbl_timers.pack(fill="x", padx=S(16), pady=(0, S(10)))

    def _build_center(self, p):
        S = self.S
        self.reactor = tk.Canvas(p, width=S(300), height=S(300), bg=C.BG, highlightthickness=0)
        self.reactor.pack(fill="both", expand=True)
        self.reactor.bind("<Configure>", self._reactor_static)
        self.reactor.bind("<Button-1>", lambda e: self.push_to_talk())

        self.lbl_mode = tk.Label(p, text="INITIALISING", font=(F_HEAD, 15, "bold"), fg=C.VIOLET, bg=C.BG)
        self.lbl_mode.pack(pady=(S(4), 0))
        self.lbl_status = tk.Label(p, text="Bringing systems online…", font=(F_BODY, 10), fg=C.SOFT, bg=C.BG)
        self.lbl_status.pack(pady=(S(2), 0))
        self.lbl_heard = tk.Label(p, text="", font=(F_BODY, 9, "italic"), fg=C.MUTED, bg=C.BG, wraplength=S(460))
        self.lbl_heard.pack(pady=(S(4), S(6)))
        self.meter = tk.Canvas(p, width=S(300), height=S(50), bg=C.BG, highlightthickness=0)
        self.meter.pack(fill="x", pady=(0, S(2)))

        self.alert_lbl = tk.Label(p, text="", font=(F_HEAD, 10, "bold"), fg=C.RED, bg=C.BG, padx=S(16), pady=S(8),
                                  highlightthickness=1, wraplength=S(520), justify="center")

    def _build_chat(self, p):
        S = self.S
        wrap = tk.Frame(p, bg=C.PANEL)
        wrap.pack(fill="both", expand=True, padx=S(4), pady=(0, S(10)))
        self.chat = tk.Text(wrap, width=1, height=1, bg=C.PANEL, fg=C.TEXT, bd=0, highlightthickness=0,
                            wrap="word", font=(F_BODY, 10), padx=S(12), pady=S(4), cursor="arrow",
                            insertwidth=0, spacing1=S(1), spacing3=S(1))
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.chat.yview, style="J.Vertical.TScrollbar")
        self.chat.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.chat.pack(side="left", fill="both", expand=True)
        t = self.chat
        t.tag_configure("who_user", foreground=C.GOLD, font=(F_HEAD, 9, "bold"), spacing1=S(12))
        t.tag_configure("who_ai", foreground=C.CYAN, font=(F_HEAD, 9, "bold"), spacing1=S(12))
        t.tag_configure("meta", foreground=C.MUTED, font=(F_BODY, 8))
        t.tag_configure("msg_user", foreground=C.WHITE, lmargin1=S(2), lmargin2=S(2), spacing3=S(2))
        t.tag_configure("msg_ai", foreground=C.TEXT, lmargin1=S(2), lmargin2=S(2), spacing3=S(2))
        t.tag_configure("msg_alert", foreground=C.GOLD, lmargin1=S(2), lmargin2=S(2), spacing3=S(2))
        t.tag_configure("code", foreground=C.CYAN_HI, font=(F_MONO, 9), background=C.PANEL2,
                        lmargin1=S(10), lmargin2=S(10))
        t.tag_configure("sys", foreground=C.MUTED, font=(F_BODY, 8, "italic"), spacing1=S(8), justify="center")
        t.tag_configure("old", foreground=C.MUTED)
        t.config(state="disabled")

    def _build_footer(self):
        S = self.S
        foot = tk.Frame(self.root, bg=C.PANEL, highlightthickness=1, highlightbackground=C.LINE)
        foot.pack(fill="x", padx=S(20), pady=(0, S(16)))
        self._brackets(foot, C.CYAN, L=10)
        inner = tk.Frame(foot, bg=C.PANEL)
        inner.pack(fill="x", padx=S(12), pady=S(10))

        self.micbtn = tk.Canvas(inner, width=S(46), height=S(46), bg=C.PANEL, highlightthickness=0, cursor="hand2")
        self.micbtn.pack(side="left")
        self.micbtn.bind("<Button-1>", lambda e: self.push_to_talk())
        self._draw_micbtn()

        box = tk.Frame(inner, bg=C.PANEL2, highlightthickness=1, highlightbackground=C.LINE2)
        box.pack(side="left", fill="x", expand=True, padx=S(12))
        tk.Label(box, text="›", font=(F_HEAD, 14, "bold"), fg=C.CYAN, bg=C.PANEL2).pack(side="left", padx=(S(10), 0))
        self.entry = tk.Entry(box, bg=C.PANEL2, fg=C.WHITE, insertbackground=C.CYAN, bd=0, highlightthickness=0,
                              width=10, font=(F_BODY, 11), relief="flat")
        self.entry.pack(side="left", fill="x", expand=True, padx=S(8), ipady=S(8))
        self.entry.bind("<Return>", self._send)
        self.entry.bind("<FocusIn>", lambda e: box.config(highlightbackground=C.CYAN))
        self.entry.bind("<FocusOut>", lambda e: box.config(highlightbackground=C.LINE2))
        self._placeholder = "Type a command or ask anything…   F2 / Ctrl+Alt+J talk · Esc stop · F11 holo"
        self._show_placeholder()

        FlatButton(inner, "SEND", self._send, bg=C.CYAN, fg=C.BG, hover=C.CYAN_HI,
                   font=(F_HEAD, 9, "bold"), padx=S(18), pady=S(9)).pack(side="left")
        self.btn_mute = FlatButton(inner, "MUTE MIC", self.toggle_mute, font=(F_HEAD, 8, "bold"), padx=S(12), pady=S(10))
        self.btn_mute.pack(side="left", padx=(S(8), 0))
        FlatButton(inner, "STOP", lambda: self.assistant.tts.stop(), font=(F_HEAD, 8, "bold"),
                   padx=S(12), pady=S(10)).pack(side="left", padx=(S(6), 0))
        FlatButton(inner, "◈ HOLO", self.enter_holo, fg=C.GOLD, font=(F_HEAD, 8, "bold"),
                   padx=S(12), pady=S(10)).pack(side="left", padx=(S(6), 0))
        FlatButton(inner, "⚙", self.open_settings, font=(F_BODY, 12), padx=S(12), pady=S(4)).pack(side="left", padx=(S(6), 0))

    def _show_placeholder(self):
        if not self.entry.get():
            self.entry.insert(0, self._placeholder)
            self.entry.config(fg=C.MUTED)
            self.entry.bind("<FocusIn>", self._clear_placeholder, add="+")

    def _clear_placeholder(self, e=None):
        if self.entry.get() == self._placeholder:
            self.entry.delete(0, "end")
            self.entry.config(fg=C.WHITE)

    def _draw_micbtn(self):
        S, c = self.S, self.micbtn
        c.delete("all")
        col = C.GREEN if self.flags["listening"] else (C.MUTED if self.assistant_muted() else C.CYAN)
        c.create_oval(S(2), S(2), S(44), S(44), fill=blend(C.PANEL, col, 0.18), outline=col, width=S(2))
        x, y = S(23), S(23)
        c.create_rectangle(x - S(4), y - S(11), x + S(4), y + S(3), fill=col, outline=col)
        c.create_oval(x - S(4), y - S(14), x + S(4), y - S(7), fill=col, outline=col)
        c.create_oval(x - S(4), y - S(1), x + S(4), y + S(6), fill=col, outline=col)
        c.create_arc(x - S(9), y - S(9), x + S(9), y + S(8), start=200, extent=140, style="arc", outline=col, width=S(2))
        c.create_line(x, y + S(8), x, y + S(12), fill=col, width=S(2))
        if self.assistant_muted():
            c.create_line(x - S(11), y - S(11), x + S(11), y + S(11), fill=C.RED, width=S(2))

    def assistant_muted(self):
        a = getattr(self, "assistant", None)
        return bool(a and a.mic.muted)

    # ── actions ───────────────────────────────────────────────────
    def _send(self, e=None):
        text = self.entry.get().strip()
        if not text or text == self._placeholder:
            return
        self.entry.delete(0, "end")
        self.assistant.submit(text, "text")

    def push_to_talk(self):
        if self.assistant.mic.muted:
            self.toggle_mute()
        if not self.assistant.mic.ok:
            self.add_system("Mic isn't available — check Settings (⚙).")
            return
        self.assistant.tts.stop()
        self.assistant.mic.listen_now()

    def toggle_mute(self):
        m = not self.assistant.mic.muted
        self.assistant.mic.set_muted(m)
        self.btn_mute.config(text="UNMUTE MIC" if m else "MUTE MIC")
        self.btn_mute.set_colors(bg=blend(C.PANEL2, C.RED, 0.35) if m else C.PANEL2)
        if m:
            self.flags["listening"] = False
            self.pill_mic.set("muted", C.MUTED)
        elif self.assistant.mic.ok:
            self.pill_mic.set(self._short(self.assistant.mic.device_label), C.GREEN)
        self.set_status(self.idle_hint())
        self._refresh_mode()

    def set_mic_muted(self, m):
        if m != self.assistant.mic.muted:
            self.toggle_mute()

    def enter_holo(self):
        if self.orb is not None or self.boot is not None:
            return
        self.orb = HoloOrb(self)
        self.root.withdraw()

    def exit_holo(self):
        if self.orb is None:
            return
        try:
            self.orb.destroy()
        except Exception:
            pass
        self.orb = None
        self.root.deiconify()
        self.root.lift()
        try:
            self.root.focus_force()
        except Exception:
            pass

    # ── state ─────────────────────────────────────────────────────
    def set_flag(self, name, value):
        self.flags[name] = value
        self._refresh_mode()

    def _refresh_mode(self):
        f = self.flags
        if f["speaking"]:
            m = "speak"
        elif f["thinking"]:
            m = "think"
        elif f["listening"]:
            m = "listen"
        elif not f["ready"]:
            m = "boot"
        elif self.assistant_muted():
            m = "muted"
        elif f["mic_error"]:
            m = "error"
        else:
            m = "idle"
        self.mode = m
        label, col = MODE_STYLE[m]
        self.lbl_mode.config(text=label, fg=col)
        self.pill_mode.set(label.lower(), col)
        self._draw_micbtn()

    def idle_hint(self):
        if self.assistant_muted():
            return "Mic muted — type below or unmute."
        if self.flags["mic_error"]:
            return "Mic offline — type below, or pick a device in Settings."
        if self.cfg.get("wake_word_enabled", True):
            ww = "Hey Jarvis" if self.assistant.mic.wake_engine == "offline" else "Jarvis"
            return f'Say "{ww} …"  ·  tap the core / F2  ·  Ctrl+Alt+J from anywhere'
        return "Always listening — just speak."

    def set_status(self, text):
        self.lbl_status.config(text=text)

    def show_heard(self, text, ignored=False):
        self.lbl_heard.config(text=(f'heard: "{text}"  — no wake word' if ignored else f'"{text}"'),
                              fg=C.MUTED if ignored else C.SOFT)

    def boot_step(self, label, value, ok):
        if self.boot:
            self.boot.step(label, value, ok)

    def on_boot_overlay_done(self):
        self.flags["ready"] = True
        self._refresh_mode()
        self.set_status(self.idle_hint())
        self._reactor_static()
        threading.Thread(target=self.assistant.greet, daemon=True, name="greet").start()

    def on_ai_status(self, online, msg):
        if online and not msg.startswith("missing"):
            self.pill_ai.set(self.cfg["ai_model"], C.GREEN)
        elif online:
            self.pill_ai.set("model missing", C.GOLD)
            self.add_system(f"Ollama is running but {msg}. Run: ollama pull <model>")
        else:
            self.pill_ai.set("offline", C.RED)
            self.add_system("Ollama isn't reachable — PC commands still work. Start it with: ollama serve")

    def on_weather(self, w):
        self.lbl_wx.config(text=f"{w['icon']} {w['temp']}°C")
        self.lbl_wx_sub.config(text=f"{w['city'].upper()}  ·  {w['desc'].upper()}")

    @staticmethod
    def _short(name, n=22):
        name = re.sub(r"\s*\(.*?\)", "", name).strip() or name
        return name if len(name) <= n else name[:n - 1] + "…"

    def on_mic_ready(self, label):
        self.flags["mic_error"] = False
        if not self.assistant.mic.muted:
            self.pill_mic.set(self._short(label), C.GREEN)
        self.add_system(f"Microphone: {label}")
        if not self._mic_booted:
            self._mic_booted = True
            self.boot_step("AUDIO SENSORS", self._short(label, 30).upper(), True)
        self._refresh_mode()
        if self.flags["ready"]:
            self.set_status(self.idle_hint())

    def on_wake_engine(self, engine):
        if engine == "offline":
            self.add_system('wake word: "Hey Jarvis" — detected offline on this PC')
        elif self.cfg.get("wake_engine", "auto") != "google":
            self.add_system('wake word: "Jarvis" via Google (install openwakeword for offline "Hey Jarvis")')
        if self.flags["ready"] and not self.flags["listening"]:
            self.set_status(self.idle_hint())

    def on_mic_error(self, msg):
        first = not self.flags["mic_error"]
        self.flags["mic_error"] = True
        self.pill_mic.set("error", C.RED)
        if first:
            self.add_system(f"Mic error: {msg}")
        if not self._mic_booted:
            self._mic_booted = True
            self.boot_step("AUDIO SENSORS", "NO MICROPHONE", False)
        self._refresh_mode()
        self.set_status(self.idle_hint())

    def show_alert(self, text, level="warn"):
        col = C.RED if level == "warn" else C.GOLD
        self.alert_lbl.config(text=f"▲  {text}", fg=col, bg=blend(C.BG, col, 0.12),
                              highlightbackground=col, highlightcolor=col)
        self.alert_lbl.place(relx=0.5, y=self.S(6), anchor="n")
        self.alert_lbl.lift()
        if self._alert_job:
            self.root.after_cancel(self._alert_job)
        self._alert_job = self.root.after(8000, self.alert_lbl.place_forget)

    def refresh_timers(self):
        act = self.assistant.timers.active()
        if not act:
            self.lbl_timers.config(text="No active timers", fg=C.MUTED)
            return
        rows = []
        for rem, label, kind in act[:4]:
            name = label or "timer"
            if kind == "reminder":
                name = "⏰ " + re.sub(r"^(to|that|about) ", "", name)
            rows.append(f"{fmt_clock(rem):>7}  {name[:22]}")
        if len(act) > 4:
            rows.append(f"   +{len(act) - 4} more")
        self.lbl_timers.config(text="\n".join(rows), fg=C.GREEN)

    # ── chat ──────────────────────────────────────────────────────
    def _chat_insert(self, *parts):
        t = self.chat
        t.config(state="normal")
        for text, tag in parts:
            t.insert("end", text, tag)
        lines = int(t.index("end-1c").split(".")[0])
        if lines > 1500:
            t.delete("1.0", f"{lines - 1200}.0")
        t.config(state="disabled")
        t.see("end")

    def add_user(self, text, source="text"):
        src = {"voice": "voice", "button": "quick action"}.get(source, "typed")
        self._chat_insert(("YOU", "who_user"), (f"   {datetime.datetime.now():%H:%M} · {src}\n", "meta"),
                          (text + "\n", "msg_user"))

    def add_assistant(self, text, alert=False):
        self._chat_insert(("JARVIS", "who_ai"), (f"   {datetime.datetime.now():%H:%M}" + ("  · alert" if alert else "") + "\n", "meta"))
        if alert:
            self._chat_insert((text, "msg_alert"))
        else:
            self._insert_rich(text)
        self._chat_insert(("\n", "msg_ai"))
        self._last_line = (text.strip().splitlines() or [""])[0][:160]

    def _insert_rich(self, text):
        for part in re.split(r"(```.*?```)", text, flags=re.S):
            if part.startswith("```") and part.endswith("```"):
                body = re.sub(r"^```[^\n]*\n?", "", part)[:-3]
                self._chat_insert((body.rstrip() + "\n", "code"))
            elif part:
                self._chat_insert((part, "msg_ai"))

    def assistant_begin(self):
        self._streaming = True
        self._stream_buf = ""
        self._chat_insert(("JARVIS", "who_ai"), (f"   {datetime.datetime.now():%H:%M}\n", "meta"))
        self.chat.config(state="normal")
        self.chat.mark_set("stream_start", "end-1c")
        self.chat.mark_gravity("stream_start", "left")
        self.chat.config(state="disabled")

    def assistant_token(self, piece):
        if not self._streaming:
            return
        self._stream_buf += piece
        self._chat_insert((piece, "msg_ai"))

    def assistant_end(self):
        if not self._streaming:
            return
        self._streaming = False
        if "```" in self._stream_buf:
            self.chat.config(state="normal")
            self.chat.delete("stream_start", "end-1c")
            self.chat.config(state="disabled")
            self._insert_rich(self._stream_buf)
        self._chat_insert(("\n", "msg_ai"))
        self._last_line = re.sub(r"```.*?```", "", self._stream_buf, flags=re.S).strip().split("\n")[0][:160]

    def add_system(self, text):
        self._chat_insert((f"— {text} —\n", "sys"))

    def clear_chat(self):
        self.chat.config(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.config(state="disabled")
        self.add_system("conversation cleared")

    def _load_previous_chat(self):
        hist = self.assistant.memory.history()[-6:]
        if not hist:
            return
        self.add_system("earlier")
        for h in hist:
            who = ("YOU", "who_user") if h["role"] == "user" else ("JARVIS", "who_ai")
            body = h["content"]
            self._chat_insert(who, ("\n", "meta"), ((body[:400] + ("…" if len(body) > 400 else "")) + "\n", "old"))
        self.add_system("now")

    # ── timers ────────────────────────────────────────────────────
    def _tick_clock(self):
        now = datetime.datetime.now()
        self.lbl_time.config(text=now.strftime("%H:%M:%S"))
        self.lbl_date.config(text=now.strftime("%A  ·  %d %B %Y").upper())
        if getattr(self, "assistant", None) and self.assistant.timers.active():
            self.refresh_timers()
        elif self.lbl_timers.cget("fg") != C.MUTED:
            self.refresh_timers()
        self.root.after(500, self._tick_clock)

    @staticmethod
    def _rate(b):
        for u in ("B/s", "KB/s", "MB/s", "GB/s"):
            if b < 1024:
                return f"{b:.0f} {u}" if u == "B/s" else f"{b:.1f} {u}"
            b /= 1024
        return f"{b:.1f} TB/s"

    def _tick_stats(self):
        if HAS_PSUTIL:
            try:
                self._stats = {"CPU": psutil.cpu_percent(interval=None),
                               "RAM": psutil.virtual_memory().percent,
                               "DISK": psutil.disk_usage(os.path.abspath(os.sep)).percent}
                bat = psutil.sensors_battery()
                self.metrics["BATTERY"].config(
                    text=f"{bat.percent:.0f}% {'⚡' if bat.power_plugged else ''}" if bat else "AC")
                n = psutil.net_io_counters()
                now = time.monotonic()
                if self._net:
                    dt = max(0.1, now - self._net[0])
                    self.metrics["NET ↓"].config(text=self._rate((n.bytes_recv - self._net[1]) / dt))
                    self.metrics["NET ↑"].config(text=self._rate((n.bytes_sent - self._net[2]) / dt))
                self._net = (now, n.bytes_recv, n.bytes_sent)
                up = int(time.time() - psutil.boot_time())
                self.metrics["UPTIME"].config(text=f"{up // 86400}d {up % 86400 // 3600}h {up % 3600 // 60}m")
            except Exception:
                pass
        if self.orb is None:
            self._draw_gauges()
        self.root.after(1000, self._tick_stats)

    def _draw_gauges(self):
        S, c = self.S, self.gauges
        c.delete("all")
        w = max(c.winfo_width(), S(220))
        r = S(29)
        for i, (k, v) in enumerate(self._stats.items()):
            cx, cy = w * (i + 0.5) / 3, S(42)
            col = C.RED if v > 85 else C.GOLD if v > 65 else C.CYAN
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=225, extent=-270, style="arc", outline=C.LINE, width=S(5))
            if v > 0.5:
                c.create_arc(cx - r, cy - r, cx + r, cy + r, start=225, extent=-270 * v / 100, style="arc",
                             outline=col, width=S(5))
            c.create_text(cx, cy, text=f"{v:.0f}", fill=C.WHITE, font=(F_HEAD, 13, "bold"))
            c.create_text(cx, cy + S(13), text="%", fill=C.MUTED, font=(F_HEAD, 7))
            c.create_text(cx, cy + r + S(15), text=k, fill=C.SOFT, font=(F_HEAD, 8, "bold"))

    # ── animation ────────────────────────────────────────────────
    def _animate(self):
        mic = self.assistant.mic
        lv = level_norm(mic.level) if mic.ok and not mic.muted else 0.0
        if self.mode == "speak":
            lv = max(lv, 0.35 + 0.35 * abs(math.sin(self.phase * 2.3)) * abs(math.sin(self.phase * 0.7 + 1)))
        self.smooth += (lv - self.smooth) * 0.35
        self.levels.append(self.smooth)
        self.angle = (self.angle + {"think": 3.2, "listen": 1.8, "speak": 1.6}.get(self.mode, 0.8)) % 360
        self.phase += 0.08
        try:
            if self.boot:
                self.boot.tick()
            elif self.orb is not None:
                self.orb.draw()
            else:
                self._draw_reactor()
                self._draw_meter()
        except Exception as e:
            log(f"draw error: {e}")
        self.root.after(33, self._animate)

    def _accent(self):
        if self.mode == "idle" and self.flags["hearing"]:
            return C.TEAL
        return MODE_STYLE[self.mode][1]

    def _reactor_static(self, e=None):
        c, S = self.reactor, self.S
        c.delete("static")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 60 or h < 60:
            self._rg = None
            return
        cx, cy = w / 2, h / 2
        R = min(w, h) / 2 - S(22)
        room = S(140)
        callouts = False
        if w / 2 - R >= room:
            callouts = True
        elif w / 2 - room >= R * 0.66:
            R, callouts = w / 2 - room, True
        self._rg = (cx, cy, R, w, h, callouts)

        s = S(19)
        hh = s * math.sqrt(3)
        far = math.hypot(w, h) / 2
        for ci in range(int(w / (1.5 * s)) + 2):
            for ri in range(int(h / hh) + 2):
                x, y = ci * 1.5 * s, ri * hh + (hh / 2 if ci % 2 else 0)
                d = math.hypot(x - cx, y - cy)
                if d < R * 1.02:
                    continue
                t = 0.02 + 0.07 * max(0.0, 1 - d / far)
                c.create_polygon(_hexagon(x, y, s * 0.9), outline=blend(C.BG, C.CYAN, t), fill="", tags="static")

        line = blend(C.BG, C.CYAN, 0.22)
        g = R * 1.05
        for x1, y1, x2, y2 in ((S(8), cy, cx - g, cy), (cx + g, cy, w - S(8), cy),
                               (cx, S(8), cx, cy - g), (cx, cy + g, cx, h - S(8))):
            if (x2 - x1) > 4 or (y2 - y1) > 4:
                c.create_line(x1, y1, x2, y2, fill=line, dash=(2, 4), tags="static")
        c.create_oval(cx - R, cy - R, cx + R, cy + R, outline=blend(C.BG, C.CYAN, 0.16), tags="static")
        for deg, lab in ((84, "000"), (-6, "090"), (264, "180"), (174, "270")):
            a = math.radians(deg)
            rr = R + S(13)
            c.create_text(cx + rr * math.cos(a), cy - rr * math.sin(a), text=lab, fill=C.MUTED,
                          font=(F_MONO, 7), tags="static")
        gold = blend(C.BG, C.GOLD, 0.7)
        L, m = S(26), S(6)
        for x, y, dx, dy in ((m, m, 1, 1), (w - m, m, -1, 1), (m, h - m, 1, -1), (w - m, h - m, -1, -1)):
            c.create_line(x, y + dy * L, x, y, x + dx * L, y, fill=gold, width=S(2), tags="static")
        c.tag_lower("static")

    def _draw_reactor(self):
        c = self.reactor
        c.delete("dyn")
        if not self._rg:
            return
        cx, cy, R, w, h, callouts = self._rg
        draw_holo_core(c, cx, cy, R, self._accent(), self.smooth, self.angle, self.phase, self.mode, self.S)
        if callouts:
            self._callouts(c, cx, cy, R)

    def _callouts(self, c, cx, cy, R):
        S = self.S
        mic, st = self.assistant.mic, self._stats
        if mic.muted:
            audio = "MUTED"
        elif mic.ok:
            audio = f"{20 * math.log10(max(mic.level, 1e-6)):5.1f} dBFS"
        else:
            audio = "OFFLINE"
        items = ((135, "AUDIO INPUT", audio),
                 (45, "NEURAL CORE", self.cfg["ai_model"][:14].upper()),
                 (225, "SYSTEM LOAD", f"CPU {st['CPU']:.0f} · RAM {st['RAM']:.0f}"),
                 (315, "VOICE", self.assistant.tts.describe()[:16]))
        lc = blend(C.BG, C.GOLD, 0.6)
        for deg, title, val in items:
            a = math.radians(deg)
            sx = 1 if math.cos(a) > 0 else -1
            sy = -1 if math.sin(a) > 0 else 1
            px, py = cx + R * 0.97 * math.cos(a), cy - R * 0.97 * math.sin(a)
            ex, ey = px + sx * S(18), py + sy * S(18)
            fx = ex + sx * S(104)
            c.create_oval(px - S(3), py - S(3), px + S(3), py + S(3), outline=lc, tags="dyn")
            c.create_line(px, py, ex, ey, fx, ey, fill=lc, tags="dyn")
            tx = ex + sx * S(4)
            c.create_text(tx, ey - S(2), text=val, fill=C.WHITE, font=(F_MONO, 9), anchor="sw" if sx > 0 else "se", tags="dyn")
            c.create_text(tx, ey + S(3), text=title, fill=C.MUTED, font=(F_HEAD, 7), anchor="nw" if sx > 0 else "ne", tags="dyn")

    def _draw_meter(self):
        c, S = self.meter, self.S
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 50:
            return
        acc = self._accent()
        n = len(self.levels)
        bw = min(S(7), (w * 0.8) / n)
        gap = bw * 0.45
        x0 = (w - n * bw) / 2
        mid = h / 2
        for i, v in enumerate(self.levels):
            env = 0.35 + 0.65 * math.sin(math.pi * (i + 0.5) / n)
            amp = max(S(1.5), v * env * (h / 2 - S(4)))
            x = x0 + i * bw
            c.create_rectangle(x, mid - amp, x + bw - gap, mid + amp,
                               fill=blend(C.BG, acc, 0.35 + 0.65 * min(1, v * 1.5)), outline="")

    # ── settings ─────────────────────────────────────────────────
    def open_settings(self):
        if getattr(self, "_settings", None) and self._settings.winfo_exists():
            self._settings.lift()
            return
        self._settings = SettingsDialog(self)

    def apply_settings(self, mic_changed, tts_changed, city=None):
        save_config(self.cfg)
        if mic_changed:
            self.pill_mic.set("switching…", C.GOLD)
            self.assistant.mic.reopen()
        if tts_changed:
            self.assistant.tts.reconfigure()
        if city:
            threading.Thread(target=self._set_city, args=(city,), daemon=True).start()
        self.set_status(self.idle_hint())

    def _set_city(self, name):
        try:
            n, lat, lon = self.assistant.weather.geocode(name)
            self.cfg.update(city=n, lat=lat, lon=lon)
            save_config(self.cfg)
            self.assistant.weather.invalidate()
            w = self.assistant.weather.get()
            self.post(lambda: (self.on_weather(w), self.add_system(f"location set to {n}")))
        except Exception as e:
            msg = f"couldn't set city '{name}': {e}"
            self.post(lambda: self.add_system(msg))

    # ── quit ─────────────────────────────────────────────────────
    def quit(self):
        try:
            self.assistant.shutdown()
        except Exception:
            pass
        try:
            if self.orb is not None:
                self.orb.destroy()
        except Exception:
            pass
        self.root.after(150, self.root.destroy)


class SettingsDialog(tk.Toplevel):
    LANGS = ["en-US", "en-GB", "en-IN", "en-AU", "si-LK", "ja-JP"]

    def __init__(self, hud: HUD):
        super().__init__(hud.root)
        self.hud, self.cfg, S = hud, hud.cfg, hud.S
        self.S = S
        self.title("J.A.R.V.I.S. — Settings")
        self.configure(bg=C.PANEL)
        self.geometry(f"{S(980)}x{S(660)}")
        self.minsize(S(900), S(600))
        self.transient(hud.root)

        cols = tk.Frame(self, bg=C.PANEL)
        cols.pack(fill="both", expand=True, padx=S(22), pady=(S(8), S(4)))
        left = tk.Frame(cols, bg=C.PANEL)
        right = tk.Frame(cols, bg=C.PANEL)
        left.pack(side="left", fill="both", expand=True, padx=(0, S(14)))
        tk.Frame(cols, bg=C.LINE, width=1).pack(side="left", fill="y", pady=S(14))
        right.pack(side="left", fill="both", expand=True, padx=(S(14), 0))

        # ── Microphone ─────────────────────────────────────────
        self._section(left, "MICROPHONE", C.GREEN)
        self.devices = MicEngine.list_devices()
        labels = ["System default (Windows)"] + [f"{d['name']}  ·  {d['hostapi']}" for d in self.devices]
        self.dev_var = tk.StringVar(value=labels[0])
        want = self.cfg.get("mic_device")
        if want:
            for d, l in zip(self.devices, labels[1:]):
                if d["name"] == want.get("name") and d["hostapi"] == want.get("hostapi"):
                    self.dev_var.set(l)
        row = tk.Frame(left, bg=C.PANEL)
        row.pack(fill="x", pady=(0, S(6)))
        ttk.Combobox(row, textvariable=self.dev_var, values=labels, state="readonly", style="J.TCombobox",
                     font=(F_BODY, 9)).pack(side="left", fill="x", expand=True)
        FlatButton(row, "Apply", self._apply_device, padx=S(12), pady=S(5)).pack(side="left", padx=(S(6), 0))
        tk.Label(left, text="Tip: Bluetooth headsets usually work best via 'MME' or 'Windows DirectSound'.",
                 font=(F_BODY, 8), fg=C.MUTED, bg=C.PANEL, anchor="w").pack(fill="x")
        self.meter = tk.Canvas(left, height=S(22), bg=C.PANEL2, highlightthickness=0)
        self.meter.pack(fill="x", pady=(S(10), S(2)))
        self.meter_lbl = tk.Label(left, text="", font=(F_MONO, 8), fg=C.MUTED, bg=C.PANEL, anchor="w")
        self.meter_lbl.pack(fill="x")
        self.sens = tk.IntVar(value=int(self.cfg.get("mic_sensitivity", 6)))
        self._scale(left, "Sensitivity  (higher = picks up quieter speech)", self.sens, 1, 10)
        self.wake = tk.BooleanVar(value=self.cfg.get("wake_word_enabled", True))
        self._check(left, 'Require wake word  (off = every phrase is a command)', self.wake)
        self.wengine = tk.StringVar(value="google" if self.cfg.get("wake_engine", "auto") == "google" else "auto")
        row = tk.Frame(left, bg=C.PANEL)
        row.pack(fill="x", pady=(S(4), 0))
        for text, val in (('Offline "Hey Jarvis" (recommended)', "auto"), ('Google "Jarvis"', "google")):
            tk.Radiobutton(row, text=text, variable=self.wengine, value=val, bg=C.PANEL, fg=C.TEXT,
                           selectcolor=C.PANEL2, activebackground=C.PANEL, activeforeground=C.WHITE,
                           font=(F_BODY, 9), bd=0, highlightthickness=0).pack(side="left", padx=(0, S(12)))
        tk.Label(left, text="Google wake words (comma separated — add how Google mishears 'Jarvis')",
                 font=(F_BODY, 8), fg=C.SOFT, bg=C.PANEL, anchor="w").pack(fill="x", pady=(S(8), S(2)))
        self.wake_words = tk.Entry(left, bg=C.PANEL2, fg=C.TEXT, insertbackground=C.CYAN, bd=0,
                                   highlightthickness=0, font=(F_BODY, 9))
        self.wake_words.insert(0, ", ".join(self.cfg.get("wake_words", [])))
        self.wake_words.pack(fill="x", ipady=S(5))
        row = tk.Frame(left, bg=C.PANEL)
        row.pack(fill="x", pady=(S(10), 0))
        tk.Label(row, text="Speech language", font=(F_BODY, 9), fg=C.SOFT, bg=C.PANEL).pack(side="left")
        self.lang = tk.StringVar(value=self.cfg.get("stt_language", "en-US"))
        ttk.Combobox(row, textvariable=self.lang, values=self.LANGS, width=8, style="J.TCombobox",
                     font=(F_BODY, 9)).pack(side="right")

        self._section(left, "AI MODELS  (Ollama)", C.ORANGE)
        self.model = self._entry_row(left, "Chat model", self.cfg["ai_model"])
        self.vmodel = self._entry_row(left, "Vision model", self.cfg["vision_model"])

        # ── Voice ──────────────────────────────────────────────
        self._section(right, "VOICE", C.CYAN)
        self.engine = tk.StringVar(value=self.cfg.get("voice_engine", "neural"))
        row = tk.Frame(right, bg=C.PANEL)
        row.pack(fill="x")
        for text, val in (("Neural British voice (online)", "neural"), ("Windows voice (offline)", "sapi")):
            tk.Radiobutton(row, text=text, variable=self.engine, value=val, bg=C.PANEL, fg=C.TEXT,
                           selectcolor=C.PANEL2, activebackground=C.PANEL, activeforeground=C.WHITE,
                           font=(F_BODY, 9), bd=0, highlightthickness=0).pack(side="left", padx=(0, S(12)))
        if not HAS_EDGE:
            tk.Label(right, text="edge-tts not installed → run:  pip install edge-tts", font=(F_BODY, 8),
                     fg=C.RED, bg=C.PANEL, anchor="w").pack(fill="x", pady=(S(4), 0))
        self.nvoice = tk.StringVar(value=self.cfg.get("neural_voice") or "en-GB-RyanNeural")
        self._combo_row(right, "Neural voice", self.nvoice, NEURAL_VOICES)
        self.voice = tk.StringVar(value=self.cfg.get("tts_voice") or "Auto")
        self._combo_row(right, "Windows voice", self.voice, ["Auto"] + list(hud.assistant.tts.voices))
        self.rate = tk.IntVar(value=int(self.cfg.get("tts_rate", 0)))
        self._scale(right, "Speaking speed", self.rate, -5, 5)
        row = tk.Frame(right, bg=C.PANEL)
        row.pack(fill="x", pady=(S(4), 0))
        self.speak = tk.BooleanVar(value=self.cfg.get("speak_replies", True))
        tk.Checkbutton(row, text="Speak replies aloud", variable=self.speak, bg=C.PANEL, fg=C.TEXT,
                       selectcolor=C.PANEL2, activebackground=C.PANEL, activeforeground=C.WHITE,
                       font=(F_BODY, 9), bd=0, highlightthickness=0).pack(side="left")
        FlatButton(row, "Test voice", self._test_voice, padx=S(12), pady=S(5)).pack(side="right")

        self._section(right, "PERSONALITY & ENVIRONMENT", C.GOLD)
        self.e_title = self._entry_row(right, "Address me as", self.cfg.get("user_title", "sir"))
        self.e_city = self._entry_row(right, "City (weather)", self.cfg.get("city", ""))
        self.proactive = tk.BooleanVar(value=self.cfg.get("proactive_alerts", True))
        self._check(right, "Proactive alerts (battery, CPU / RAM load, late-night reminders)", self.proactive)
        self.fx = tk.BooleanVar(value=self.cfg.get("sound_fx", True))
        self._check(right, "Interface sound effects", self.fx)
        self.bootseq = tk.BooleanVar(value=self.cfg.get("boot_sequence", True))
        self._check(right, "Boot sequence on start-up", self.bootseq)
        tk.Label(right, text=f"Protocols are edited in {CONFIG_FILE.name}  (\"protocols\": name → list of commands)",
                 font=(F_BODY, 8), fg=C.MUTED, bg=C.PANEL, anchor="w").pack(fill="x", pady=(S(8), 0))

        btns = tk.Frame(self, bg=C.PANEL)
        btns.pack(fill="x", padx=S(22), pady=(S(4), S(18)))
        FlatButton(btns, "SAVE", self._save, bg=C.CYAN, fg=C.BG, hover=C.CYAN_HI,
                   font=(F_HEAD, 9, "bold"), padx=S(22), pady=S(8)).pack(side="right")
        FlatButton(btns, "Close", self.destroy, padx=S(16), pady=S(8)).pack(side="right", padx=S(8))
        FlatButton(btns, "Open log", lambda: os.startfile(str(LOG_FILE)) if LOG_FILE.exists() else None,
                   padx=S(12), pady=S(8)).pack(side="left")
        FlatButton(btns, "Open config", lambda: os.startfile(str(CONFIG_FILE)) if CONFIG_FILE.exists() else None,
                   padx=S(12), pady=S(8)).pack(side="left", padx=S(8))
        self._tick()

    # helpers
    def _section(self, parent, title, col):
        S = self.S
        f = tk.Frame(parent, bg=C.PANEL)
        f.pack(fill="x", pady=(S(14), S(8)))
        tk.Frame(f, bg=col, width=S(3), height=S(14)).pack(side="left")
        tk.Label(f, text=title, font=(F_HEAD, 9, "bold"), fg=C.SOFT, bg=C.PANEL).pack(side="left", padx=S(8))

    def _scale(self, parent, label, var, lo, hi):
        S = self.S
        tk.Label(parent, text=label, font=(F_BODY, 8), fg=C.SOFT, bg=C.PANEL, anchor="w").pack(fill="x", pady=(S(8), 0))
        tk.Scale(parent, variable=var, from_=lo, to=hi, orient="horizontal", bg=C.PANEL, fg=C.TEXT,
                 troughcolor=C.PANEL2, highlightthickness=0, bd=0, sliderrelief="flat",
                 activebackground=C.CYAN, font=(F_MONO, 8), showvalue=True).pack(fill="x")

    def _check(self, parent, label, var):
        tk.Checkbutton(parent, text=label, variable=var, bg=C.PANEL, fg=C.TEXT, selectcolor=C.PANEL2,
                       activebackground=C.PANEL, activeforeground=C.WHITE, font=(F_BODY, 9),
                       anchor="w", bd=0, highlightthickness=0).pack(fill="x", pady=(self.S(4), 0))

    def _entry_row(self, parent, label, value):
        S = self.S
        row = tk.Frame(parent, bg=C.PANEL)
        row.pack(fill="x", pady=S(3))
        tk.Label(row, text=label, font=(F_BODY, 9), fg=C.SOFT, bg=C.PANEL, width=13, anchor="w").pack(side="left")
        e = tk.Entry(row, bg=C.PANEL2, fg=C.TEXT, insertbackground=C.CYAN, bd=0, highlightthickness=0, font=(F_BODY, 9))
        e.insert(0, value)
        e.pack(side="left", fill="x", expand=True, ipady=S(5))
        return e

    def _combo_row(self, parent, label, var, values):
        S = self.S
        row = tk.Frame(parent, bg=C.PANEL)
        row.pack(fill="x", pady=(S(8), 0))
        tk.Label(row, text=label, font=(F_BODY, 9), fg=C.SOFT, bg=C.PANEL, width=13, anchor="w").pack(side="left")
        ttk.Combobox(row, textvariable=var, values=values, state="readonly", style="J.TCombobox",
                     font=(F_BODY, 9)).pack(side="left", fill="x", expand=True)

    def _selected_device(self):
        lbl = self.dev_var.get()
        for d in self.devices:
            if f"{d['name']}  ·  {d['hostapi']}" == lbl:
                return {"name": d["name"], "hostapi": d["hostapi"]}
        return None

    def _apply_device(self):
        self.cfg["mic_device"] = self._selected_device()
        self.hud.apply_settings(mic_changed=True, tts_changed=False)

    def _voice_fields(self):
        self.cfg["voice_engine"] = self.engine.get()
        self.cfg["neural_voice"] = self.nvoice.get()
        self.cfg["tts_voice"] = "" if self.voice.get() == "Auto" else self.voice.get()
        self.cfg["tts_rate"] = int(self.rate.get())

    def _test_voice(self):
        self._voice_fields()
        tts = self.hud.assistant.tts
        tts.reconfigure()
        t = self.e_title.get().strip() or "sir"
        tts.speak(f"Good {daypart()}, {t}. All systems are operational.")

    def _tick(self):
        if not self.winfo_exists():
            return
        mic = self.hud.assistant.mic
        c, S = self.meter, self.S
        c.delete("all")
        w = max(c.winfo_width(), 100)
        h = S(22)
        lv = level_norm(mic.level) if mic.ok else 0
        start_th = mic._thresholds()[0] if mic.ok else 0.01
        th = level_norm(start_th)
        c.create_rectangle(0, 0, w * lv, h, fill=C.GREEN if lv >= th else C.CYAN, outline="")
        c.create_line(w * th, 0, w * th, h, fill=C.GOLD, width=S(2))
        db = 20 * math.log10(max(mic.level, 1e-6))
        self.meter_lbl.config(text=(f"level {db:5.1f} dBFS  ·  trigger {20 * math.log10(max(start_th, 1e-6)):5.1f} dBFS"
                                    f"  ·  {mic.device_label}" if mic.ok else "mic not open"))
        self.after(50, self._tick)

    def _save(self):
        old_dev = self.cfg.get("mic_device")
        old_tts = tuple(self.cfg.get(k) for k in ("voice_engine", "neural_voice", "tts_voice", "tts_rate"))
        self.cfg["mic_device"] = self._selected_device()
        self.cfg["mic_sensitivity"] = int(self.sens.get())
        self.cfg["wake_word_enabled"] = bool(self.wake.get())
        wake_changed = self.cfg.get("wake_engine", "auto") != self.wengine.get()
        self.cfg["wake_engine"] = self.wengine.get()
        ww = [w.strip().lower() for w in self.wake_words.get().split(",") if w.strip()]
        self.cfg["wake_words"] = ww or ["jarvis"]
        self.cfg["stt_language"] = self.lang.get().strip() or "en-US"
        self._voice_fields()
        self.cfg["speak_replies"] = bool(self.speak.get())
        self.cfg["user_title"] = self.e_title.get().strip() or "sir"
        self.cfg["proactive_alerts"] = bool(self.proactive.get())
        self.cfg["sound_fx"] = bool(self.fx.get())
        self.cfg["boot_sequence"] = bool(self.bootseq.get())
        self.cfg["ai_model"] = self.model.get().strip() or DEFAULT_CONFIG["ai_model"]
        self.cfg["vision_model"] = self.vmodel.get().strip() or DEFAULT_CONFIG["vision_model"]
        new_city = self.e_city.get().strip()
        city = new_city if new_city and new_city.lower() != (self.cfg.get("city") or "").lower() else None
        new_tts = tuple(self.cfg.get(k) for k in ("voice_engine", "neural_voice", "tts_voice", "tts_rate"))
        self.hud.apply_settings(mic_changed=(old_dev != self.cfg["mic_device"]) or wake_changed,
                                tts_changed=(old_tts != new_tts), city=city)
        self.hud.add_system("settings saved")
        self.destroy()


# ══════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════

def main():
    _rotate_log()
    log(f"===== J.A.R.V.I.S. v{VERSION} starting (Python {sys.version.split()[0]}) =====")
    if IS_WIN:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("jarvis.desktop.assistant")
        except Exception:
            pass
    root = tk.Tk()
    HUD(root)
    root.mainloop()


if __name__ == "__main__":
    main()
