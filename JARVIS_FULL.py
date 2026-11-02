"""
╔══════════════════════════════════════════════════════════════════╗
║            J.A.R.V.I.S.  Desktop Assistant  —  v4.0              ║
║   Tkinter HUD  |  Ollama AI  |  Wake word + Push-to-talk  |  Win  ║
╚══════════════════════════════════════════════════════════════════╝

INSTALL:
    pip install -r requirements.txt

RUN:
    ollama serve            (separate terminal)
    python JARVIS_FULL.py

VOICE:
    Say "Jarvis <command>"  — or just "Jarvis", wait for "Yes, sir?", then speak.
    Click the mic button (or press F2) to talk without the wake word.
    Esc stops JARVIS speaking.

Mic problems? Open Settings (gear) → pick your input device → watch the live
meter → adjust sensitivity. Everything is logged to jarvis.log next to this file.
"""

import os, sys, re, time, math, json, queue, shutil, ctypes, random
import threading, datetime, subprocess, webbrowser, tempfile, collections, warnings
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

# ══════════════════════════════════════════════════════════════════
# PATHS / CONFIG / LOG
# ══════════════════════════════════════════════════════════════════

APP_DIR = (Path(sys.executable).parent if getattr(sys, "frozen", False)
           else Path(__file__).resolve().parent)
CONFIG_FILE = APP_DIR / "jarvis_config.json"
MEMORY_FILE = APP_DIR / "jarvis_memory.json"
LOG_FILE    = APP_DIR / "jarvis.log"
VERSION     = "4.0"

DEFAULT_CONFIG = {
    "ai_model":          "qwen2.5:7b",
    "vision_model":      "llava:latest",
    "wake_word_enabled": True,
    "wake_words":        ["jarvis", "jarvice", "javis", "jervis", "jarves",
                          "jarvas", "jarvish", "charvis", "jar vis", "travis"],
    "mic_device":        None,          # {"name": ..., "hostapi": ...}  None = Windows default
    "mic_sensitivity":   6,             # 1 (needs loud voice) … 10 (very sensitive)
    "stt_language":      "en-US",
    "tts_voice":         "",            # substring of a voice name, "" = auto
    "tts_rate":          0,             # -5 … 5
    "speak_replies":     True,
    "max_history":       30,
}

SYSTEM_PROMPT = """You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), a desktop assistant.
Personality:
- Calm, witty, slightly formal British tone. Occasionally call the user "sir".
- Replies are spoken aloud: keep them SHORT (1-3 sentences) unless asked to elaborate.
- Avoid markdown, bullet symbols and emojis unless the user asks for code or a list.
- Never say you cannot help — offer the closest alternative.
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
        msgs = ([{"role": "system", "content": SYSTEM_PROMPT + f"\nCurrent date/time: {now}."}]
                + self.memory.history()[-20:])
        full = ""
        try:
            for chunk in ollama.chat(model=self.cfg["ai_model"], messages=msgs, stream=True):
                piece = _msg_content(chunk)
                if piece:
                    full += piece
                    on_token(piece)
        except Exception as e:
            err = f"My circuits hit a snag, sir — I can't reach the model ({e}). Is 'ollama serve' running?"
            on_token(("\n" if full else "") + err)
            full = full + ("\n" if full else "") + err
        full = full.strip() or "I'm afraid I have nothing to add, sir."
        self.memory.append("assistant", full)
        return full


def check_ollama(cfg):
    """Returns (online: bool, message: str)."""
    if not HAS_OLLAMA:
        return False, "ollama package missing"
    try:
        raw = ollama.list()
        names = []
        models = getattr(raw, "models", None)
        if models is None and isinstance(raw, dict):
            models = raw.get("models", [])
        for m in models or []:
            names.append(getattr(m, "model", None) or (m.get("name") if isinstance(m, dict) else str(m)))
        missing = [x for x in (cfg["ai_model"], cfg["vision_model"]) if not any(x in (n or "") for n in names)]
        if missing:
            return True, "missing: " + ", ".join(missing)
        return True, cfg["ai_model"]
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════════════════════════════════
# TEXT-TO-SPEECH  — one dedicated thread, SAPI (comtypes) → pyttsx3
# ══════════════════════════════════════════════════════════════════

def clean_for_speech(t: str) -> str:
    t = re.sub(r"```.*?```", " I've put the code on screen. ", t, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"https?://\S+", "the link", t)
    t = re.sub(r"[*_#>|~]+", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > 450:
        cut = t[:450]
        dot = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
        t = cut[:dot + 1] if dot > 120 else cut + "…"
    return t


class TTSEngine:
    def __init__(self, cfg, on_start=None, on_end=None):
        self.cfg = cfg
        self.on_start, self.on_end = on_start or (lambda: None), on_end or (lambda: None)
        self.voices = []
        self.backend = "none"
        self._q = queue.Queue()
        self._stop = threading.Event()
        self.speaking = False
        threading.Thread(target=self._worker, daemon=True, name="tts").start()

    def speak(self, text: str):
        text = clean_for_speech(text)
        if text:
            self._q.put(("say", text))

    def stop(self):
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass
        self._stop.set()

    def reconfigure(self):
        self._q.put(("cfg", None))

    def shutdown(self):
        self.stop()
        self._q.put(("quit", None))

    # -- worker ------------------------------------------------------
    def _init_sapi(self):
        import comtypes
        import comtypes.client
        comtypes.CoInitialize()
        voice = comtypes.client.CreateObject("SAPI.SpVoice")
        tokens = voice.GetVoices()
        self._sapi_tokens = [tokens.Item(i) for i in range(tokens.Count)]
        self.voices = [t.GetDescription() for t in self._sapi_tokens]
        return voice

    def _apply_sapi(self, voice):
        want = (self.cfg.get("tts_voice") or "").lower()
        pick = None
        prefs = [want] if want else ["george", "united kingdom", "en-gb", "david", "english"]
        for p in prefs:
            for tok, desc in zip(self._sapi_tokens, self.voices):
                if p and p in desc.lower():
                    pick = tok
                    break
            if pick:
                break
        if pick is not None:
            voice.Voice = pick
        voice.Rate = int(max(-5, min(5, self.cfg.get("tts_rate", 0))))

    def _init_pyttsx3(self):
        import pyttsx3
        eng = pyttsx3.init()
        vs = eng.getProperty("voices")
        self.voices = [v.name for v in vs]
        want = (self.cfg.get("tts_voice") or "").lower()
        for v in vs:
            if (want and want in v.name.lower()) or (not want and "english" in v.name.lower()):
                eng.setProperty("voice", v.id)
                break
        eng.setProperty("rate", 165 + 15 * int(self.cfg.get("tts_rate", 0)))
        return eng

    def _worker(self):
        sapi = eng = None
        try:
            sapi = self._init_sapi()
            self._apply_sapi(sapi)
            self.backend = "sapi"
        except Exception as e:
            log(f"SAPI unavailable ({e}); trying pyttsx3")
            try:
                eng = self._init_pyttsx3()
                self.backend = "pyttsx3"
            except Exception as e2:
                log(f"TTS unavailable: {e2}")
        log(f"TTS backend: {self.backend}")

        while True:
            kind, text = self._q.get()
            if kind == "quit":
                break
            if kind == "cfg":
                try:
                    if sapi:
                        self._apply_sapi(sapi)
                    elif eng:
                        eng = self._init_pyttsx3()
                except Exception as e:
                    log(f"TTS reconfigure error: {e}")
                continue
            if not (sapi or eng):
                continue
            self._stop.clear()
            self.speaking = True
            self.on_start()
            try:
                if sapi:
                    sapi.Speak(text, 1)                       # SVSFlagsAsync
                    while not sapi.WaitUntilDone(80):
                        if self._stop.is_set():
                            sapi.Speak("", 3)                 # async + purge
                            break
                else:
                    eng.say(text)
                    eng.runAndWait()
            except Exception as e:
                log(f"TTS error: {e}")
                try:
                    if eng:
                        eng = self._init_pyttsx3()
                except Exception:
                    pass
            finally:
                if self._q.empty() or self._stop.is_set():
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
            for w in words:
                m = re.search(r"\b" + re.escape(w) + r"\b", low)
                if m:
                    rest = alt[m.end():].strip(" ,.!?")
                    out = []
                    for tok in rest.split():                 # "open open chrome" → "open chrome"
                        if not out or tok.lower() != out[-1].lower():
                            out.append(tok)
                    return " ".join(out)
        return None

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
                self.ev("command", alts[0])


# ══════════════════════════════════════════════════════════════════
# ASSISTANT CONTROLLER
# ══════════════════════════════════════════════════════════════════

RE_EXIT = re.compile(r"(?:ok(?:ay)? )?(?:goodbye|good bye|bye(?: bye)?|exit|quit|good night|"
                     r"shut yourself down|close yourself|sign off)(?: jarvis| sir)?")
RE_STOP = re.compile(r"(?:stop|stop talking|shut up|be quiet|quiet|silence|enough|cancel)(?: jarvis| please)?")
RE_CLEAR = re.compile(r"(?:clear|reset|wipe) (?:the )?(?:history|memory|conversation|chat)|forget everything")
RE_TIME = re.compile(r"what(?:'s| is) the time|what time is it|(?:tell me )?the time")
RE_DATE = re.compile(r"what(?:'s| is) (?:the |today's )?date|what day is (?:it|today)")
RE_VISION = re.compile(r"(?:analy[sz]e|describe|scan|look at|read|explain) (?:my |the |this )?screen|"
                       r"what(?:'s| is) on (?:my |the )?screen|what am i looking at")


class Assistant:
    def __init__(self, cfg, ui):
        self.cfg, self.ui = cfg, ui
        self.memory = Memory(MEMORY_FILE, cfg.get("max_history", 30))
        self.brain = AIBrain(self.memory, cfg)
        self.parser = CommandParser()
        self.vision = Vision(cfg)
        self.tts = TTSEngine(cfg, on_start=self._tts_start, on_end=self._tts_end)
        self.mic = MicEngine(cfg, self._mic_event)
        self._jobs = queue.Queue()
        threading.Thread(target=self._worker, daemon=True, name="jobs").start()

    def boot(self):
        online, msg = check_ollama(self.cfg)
        log(f"ollama: {'online' if online else 'offline'} — {msg}")
        self.ui.post(lambda: self.ui.on_ai_status(online, msg))
        self.mic.start()
        time.sleep(0.6)
        self.say("J.A.R.V.I.S. online. How can I assist, sir?", chat=False)
        self.ui.post(self.ui.on_booted)

    def shutdown(self):
        self.mic.stop()
        self.tts.shutdown()

    # -- events --------------------------------------------------------
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
            ui.post(lambda: (ui.set_flag("listening", True), ui.set_status("Listening — go ahead, sir.")))
        elif kind == "recognizing":
            ui.post(lambda: ui.set_status("Recognising…"))
        elif kind == "ignored":
            ui.post(lambda: (ui.show_heard(payload, ignored=True), ui.set_status(ui.idle_hint())))
        elif kind == "wake":
            ui.post(lambda: (ui.set_flag("listening", True), ui.set_status("Yes, sir?")))
            self.say(random.choice(["Yes, sir?", "At your service.", "Sir?", "I'm listening."]), chat=False)
        elif kind == "command":
            ui.post(lambda: ui.set_flag("listening", False))
            self.submit(payload, source="voice")
        elif kind == "timeout":
            ui.post(lambda: (ui.set_flag("listening", False), ui.set_status(ui.idle_hint())))
        elif kind == "unclear":
            ui.post(lambda: (ui.set_flag("listening", False), ui.set_status("Didn't catch that, sir.")))
        elif kind == "stt_error":
            ui.post(lambda: (ui.add_system(payload), ui.set_status("Speech service offline")))

    # -- commands ------------------------------------------------------
    def submit(self, text, source="text"):
        text = (text or "").strip()
        if not text:
            return
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
                self.say(f"Something went wrong, sir: {e}")
            finally:
                self.ui.post(lambda: (self.ui.set_flag("thinking", False), self.ui.set_status(self.ui.idle_hint())))

    def _handle(self, text):
        c = normalize(text).lower()

        if RE_EXIT.fullmatch(c):
            self.say("Signing off, sir. Have a good one.")
            time.sleep(2.2)
            self.ui.post(self.ui.quit)
            return
        if RE_CLEAR.fullmatch(c):
            self.memory.clear()
            self.ui.post(self.ui.clear_chat)
            self.say("Memory cleared, sir.")
            return
        if RE_TIME.fullmatch(c):
            self.say(f"It's {datetime.datetime.now():%H:%M}, sir.")
            return
        if RE_DATE.fullmatch(c):
            self.say(f"Today is {datetime.datetime.now():%A, %d %B %Y}.")
            return
        if RE_VISION.fullmatch(c):
            self.ui.post(lambda: self.ui.set_status("Analysing screen…"))
            self.say(self.vision.analyze_screen())
            return

        result = self.parser.parse(text)
        if result is not None:
            self.ui.post(lambda: self.ui.add_assistant(result))
            if self.cfg.get("speak_replies", True):
                first = result.splitlines()[0] if result else ""
                self.tts.speak(first[:220])
            return

        # AI (streamed into the chat)
        self.ui.post(self.ui.assistant_begin)
        full = self.brain.reply_stream(text, lambda p: self.ui.post(lambda p=p: self.ui.assistant_token(p)))
        self.ui.post(self.ui.assistant_end)
        if self.cfg.get("speak_replies", True):
            self.tts.speak(full)


# ══════════════════════════════════════════════════════════════════
# UI  — HUD
# ══════════════════════════════════════════════════════════════════

class C:
    BG = "#05080f"
    PANEL = "#0a111e"
    PANEL2 = "#0f1a2c"
    LINE = "#18263d"
    LINE2 = "#22385a"
    CYAN = "#38bdf8"
    CYAN_HI = "#7dd3fc"
    TEAL = "#22d3ee"
    GREEN = "#34d399"
    AMBER = "#fbbf24"
    RED = "#f87171"
    VIOLET = "#a78bfa"
    TEXT = "#dbeafe"
    SOFT = "#94a3b8"
    MUTED = "#55657d"
    WHITE = "#f0f9ff"


F_HEAD = "Bahnschrift"          # ships with Windows 10/11; Tk falls back if missing
F_BODY = "Segoe UI"
F_MONO = "Consolas"


def blend(c1, c2, t):
    t = max(0.0, min(1.0, t))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def level_norm(rms):
    db = 20 * math.log10(max(rms, 1e-6))
    return max(0.0, min(1.0, (db + 58) / 46))


MODE_STYLE = {
    "boot":   ("INITIALISING", C.VIOLET),
    "idle":   ("STANDBY", C.CYAN),
    "listen": ("LISTENING", C.GREEN),
    "think":  ("PROCESSING", C.AMBER),
    "speak":  ("SPEAKING", C.CYAN_HI),
    "muted":  ("MIC MUTED", C.MUTED),
    "error":  ("MIC OFFLINE", C.RED),
}


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

        root.title("J.A.R.V.I.S.")
        root.configure(bg=C.BG)
        root.geometry(f"{S(1260)}x{S(800)}")
        root.minsize(S(1020), S(660))
        self._style()
        self._build()

        self.assistant = Assistant(self.cfg, self)
        self._load_previous_chat()

        root.protocol("WM_DELETE_WINDOW", self.quit)
        root.bind("<F2>", lambda e: self.push_to_talk())
        root.bind("<Control-space>", lambda e: self.push_to_talk())
        root.bind("<Escape>", lambda e: self.assistant.tts.stop())

        self._pump()
        self._animate()
        self._tick_clock()
        self._tick_stats()
        threading.Thread(target=self.assistant.boot, daemon=True, name="boot").start()

    # ── thread-safe UI calls ──────────────────────────────────────
    def post(self, fn):
        self._q.put(fn)

    def _pump(self):
        try:
            for _ in range(80):
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

    def _panel(self, parent, title, accent=C.CYAN):
        S = self.S
        f = tk.Frame(parent, bg=C.PANEL, highlightthickness=1, highlightbackground=C.LINE)
        head = tk.Frame(f, bg=C.PANEL)
        head.pack(fill="x", padx=S(14), pady=(S(12), S(6)))
        tk.Frame(head, bg=accent, width=S(3), height=S(14)).pack(side="left")
        tk.Label(head, text=title, font=(F_HEAD, 9, "bold"), fg=C.SOFT, bg=C.PANEL).pack(side="left", padx=S(8))
        f.head = head
        return f

    # ── layout ────────────────────────────────────────────────────
    def _build(self):
        S = self.S
        # Header ---------------------------------------------------
        hdr = tk.Frame(self.root, bg=C.BG)
        hdr.pack(fill="x", padx=S(20), pady=(S(14), S(8)))

        logo = tk.Canvas(hdr, width=S(38), height=S(38), bg=C.BG, highlightthickness=0)
        logo.pack(side="left")
        cx = cy = S(19)
        pts = []
        for i in range(6):
            a = math.radians(60 * i - 90)
            pts += [cx + S(17) * math.cos(a), cy + S(17) * math.sin(a)]
        logo.create_polygon(pts, outline=C.CYAN, fill=C.PANEL2, width=S(2))
        logo.create_oval(cx - S(6), cy - S(6), cx + S(6), cy + S(6), fill=C.CYAN_HI, outline="")

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

        pills = tk.Frame(hdr, bg=C.BG)
        pills.pack(side="right", padx=S(18))
        self.pill_mode = Pill(pills, "STATE", S)
        self.pill_mic = Pill(pills, "MIC", S)
        self.pill_ai = Pill(pills, "AI", S)
        for p in (self.pill_ai, self.pill_mic, self.pill_mode):
            p.pack(side="right", padx=S(4))
        self.pill_ai.set("checking…", C.AMBER)
        self.pill_mic.set("starting…", C.AMBER)

        line = tk.Canvas(self.root, height=S(2), bg=C.BG, highlightthickness=0)
        line.pack(fill="x", padx=S(20))
        line.bind("<Configure>", lambda e: self._gradient_line(line, e.width))

        # Body -----------------------------------------------------
        body = tk.Frame(self.root, bg=C.BG)
        body.pack(fill="both", expand=True, padx=S(20), pady=S(12))
        body.grid_columnconfigure(0, minsize=S(260), weight=0)
        body.grid_columnconfigure(1, weight=1)
        body.grid_columnconfigure(2, minsize=S(400), weight=0)
        body.grid_rowconfigure(0, weight=1)

        left = self._panel(body, "SYSTEM DIAGNOSTICS")
        left.grid(row=0, column=0, sticky="nsew")
        self._build_left(left)

        center = tk.Frame(body, bg=C.BG)
        center.grid(row=0, column=1, sticky="nsew", padx=S(14))
        self._build_center(center)

        right = self._panel(body, "CONVERSATION", accent=C.GREEN)
        right.grid(row=0, column=2, sticky="nsew")
        self._build_chat(right)

        # Footer ---------------------------------------------------
        self._build_footer()

    def _gradient_line(self, cv, w):
        cv.delete("all")
        n = 60
        for i in range(n):
            t = 1 - abs(i - n / 2) / (n / 2)
            cv.create_rectangle(i * w / n, 0, (i + 1) * w / n + 1, self.S(2),
                                fill=blend(C.BG, C.CYAN, t * 0.9), outline="")

    def _build_left(self, p):
        S = self.S
        self.gauges = tk.Canvas(p, width=S(230), height=S(112), bg=C.PANEL, highlightthickness=0)
        self.gauges.pack(fill="x", padx=S(10), pady=(S(4), S(6)))
        self._gauge_vals = {"CPU": 0, "RAM": 0, "DISK": 0}

        grid = tk.Frame(p, bg=C.PANEL)
        grid.pack(fill="x", padx=S(14))
        self.metrics = {}
        for i, key in enumerate(("BATTERY", "NET ↓", "NET ↑", "UPTIME", "PROCESSES")):
            tk.Label(grid, text=key, font=(F_HEAD, 8), fg=C.MUTED, bg=C.PANEL).grid(row=i, column=0, sticky="w", pady=S(3))
            v = tk.Label(grid, text="—", font=(F_MONO, 9), fg=C.TEXT, bg=C.PANEL)
            v.grid(row=i, column=1, sticky="e", pady=S(3))
            self.metrics[key] = v
        grid.grid_columnconfigure(1, weight=1)

        tk.Frame(p, bg=C.LINE, height=1).pack(fill="x", padx=S(14), pady=S(12))
        head = tk.Frame(p, bg=C.PANEL)
        head.pack(fill="x", padx=S(14), pady=(0, S(8)))
        tk.Frame(head, bg=C.AMBER, width=S(3), height=S(14)).pack(side="left")
        tk.Label(head, text="QUICK ACTIONS", font=(F_HEAD, 9, "bold"), fg=C.SOFT, bg=C.PANEL).pack(side="left", padx=S(8))

        qa = tk.Frame(p, bg=C.PANEL)
        qa.pack(fill="x", padx=S(12))
        actions = [("Screenshot", "take a screenshot"), ("Scan screen", "what's on my screen"),
                   ("Status", "system status"), ("Downloads", "open downloads"),
                   ("Mute audio", "mute"), ("Lock PC", "lock")]
        for i, (label, cmd) in enumerate(actions):
            b = FlatButton(qa, label, lambda c=cmd: self.assistant.submit(c, "button"),
                           font=(F_BODY, 9), pady=S(6))
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=S(2), pady=S(2))
        qa.grid_columnconfigure(0, weight=1)
        qa.grid_columnconfigure(1, weight=1)

        tk.Frame(p, bg=C.LINE, height=1).pack(fill="x", padx=S(14), pady=S(12))
        self.lbl_engine = tk.Label(p, text="", font=(F_MONO, 8), fg=C.MUTED, bg=C.PANEL,
                                   justify="left", anchor="w")
        self.lbl_engine.pack(fill="x", padx=S(14), pady=(0, S(12)))
        self._refresh_engine_label()

    def _refresh_engine_label(self):
        ww = "on" if self.cfg.get("wake_word_enabled", True) else "off (always listening)"
        self.lbl_engine.config(text=f"MODEL   {self.cfg['ai_model']}\n"
                                    f"VISION  {self.cfg['vision_model']}\n"
                                    f"WAKE    \"jarvis\" · {ww}\n"
                                    f"STT     google · {self.cfg.get('stt_language')}")

    def _build_center(self, p):
        S = self.S
        self.reactor = tk.Canvas(p, width=S(300), height=S(300), bg=C.BG, highlightthickness=0)
        self.reactor.pack(fill="both", expand=True)

        self.lbl_mode = tk.Label(p, text="INITIALISING", font=(F_HEAD, 15, "bold"), fg=C.VIOLET, bg=C.BG)
        self.lbl_mode.pack(pady=(S(4), 0))
        self.lbl_status = tk.Label(p, text="Bringing systems online…", font=(F_BODY, 10),
                                   fg=C.SOFT, bg=C.BG)
        self.lbl_status.pack(pady=(S(2), 0))
        self.lbl_heard = tk.Label(p, text="", font=(F_BODY, 9, "italic"), fg=C.MUTED, bg=C.BG,
                                  wraplength=S(460))
        self.lbl_heard.pack(pady=(S(4), S(6)))

        self.meter = tk.Canvas(p, width=S(300), height=S(54), bg=C.BG, highlightthickness=0)
        self.meter.pack(fill="x", pady=(0, S(2)))

    def _build_chat(self, p):
        S = self.S
        wrap = tk.Frame(p, bg=C.PANEL)
        wrap.pack(fill="both", expand=True, padx=S(4), pady=(0, S(8)))
        self.chat = tk.Text(wrap, width=1, height=1, bg=C.PANEL, fg=C.TEXT, bd=0, highlightthickness=0, wrap="word",
                            font=(F_BODY, 10), padx=S(12), pady=S(4), cursor="arrow",
                            insertwidth=0, spacing1=S(1), spacing3=S(1))
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.chat.yview, style="J.Vertical.TScrollbar")
        self.chat.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.chat.pack(side="left", fill="both", expand=True)

        t = self.chat
        t.tag_configure("who_user", foreground=C.GREEN, font=(F_HEAD, 9, "bold"), spacing1=S(12))
        t.tag_configure("who_ai", foreground=C.CYAN, font=(F_HEAD, 9, "bold"), spacing1=S(12))
        t.tag_configure("meta", foreground=C.MUTED, font=(F_BODY, 8))
        t.tag_configure("msg_user", foreground=C.WHITE, lmargin1=S(2), lmargin2=S(2), spacing3=S(2))
        t.tag_configure("msg_ai", foreground=C.TEXT, lmargin1=S(2), lmargin2=S(2), spacing3=S(2))
        t.tag_configure("code", foreground=C.CYAN_HI, font=(F_MONO, 9), background=C.PANEL2,
                        lmargin1=S(10), lmargin2=S(10))
        t.tag_configure("sys", foreground=C.MUTED, font=(F_BODY, 8, "italic"), spacing1=S(8),
                        justify="center")
        t.tag_configure("old", foreground=C.MUTED)
        t.config(state="disabled")

    def _build_footer(self):
        S = self.S
        foot = tk.Frame(self.root, bg=C.PANEL, highlightthickness=1, highlightbackground=C.LINE)
        foot.pack(fill="x", padx=S(20), pady=(0, S(16)))
        inner = tk.Frame(foot, bg=C.PANEL)
        inner.pack(fill="x", padx=S(12), pady=S(10))

        # mic button (push-to-talk)
        self.micbtn = tk.Canvas(inner, width=S(46), height=S(46), bg=C.PANEL, highlightthickness=0, cursor="hand2")
        self.micbtn.pack(side="left")
        self.micbtn.bind("<Button-1>", lambda e: self.push_to_talk())
        self._draw_micbtn()

        box = tk.Frame(inner, bg=C.PANEL2, highlightthickness=1, highlightbackground=C.LINE2)
        box.pack(side="left", fill="x", expand=True, padx=S(12))
        tk.Label(box, text="›", font=(F_HEAD, 14, "bold"), fg=C.CYAN, bg=C.PANEL2).pack(side="left", padx=(S(10), 0))
        self.entry = tk.Entry(box, bg=C.PANEL2, fg=C.WHITE, insertbackground=C.CYAN, bd=0, highlightthickness=0, width=10,
                              font=(F_BODY, 11), relief="flat")
        self.entry.pack(side="left", fill="x", expand=True, padx=S(8), ipady=S(8))
        self.entry.bind("<Return>", self._send)
        self.entry.bind("<FocusIn>", lambda e: box.config(highlightbackground=C.CYAN))
        self.entry.bind("<FocusOut>", lambda e: box.config(highlightbackground=C.LINE2))
        self._placeholder = "Type a command or ask anything…   (F2 = talk, Esc = stop)"
        self._show_placeholder()

        FlatButton(inner, "SEND", self._send, bg=C.CYAN, fg=C.BG, hover=C.CYAN_HI,
                   font=(F_HEAD, 9, "bold"), padx=S(18), pady=S(9)).pack(side="left")
        self.btn_mute = FlatButton(inner, "MUTE MIC", self.toggle_mute, font=(F_HEAD, 8, "bold"),
                                   padx=S(12), pady=S(10))
        self.btn_mute.pack(side="left", padx=(S(8), 0))
        FlatButton(inner, "STOP", lambda: self.assistant.tts.stop(), font=(F_HEAD, 8, "bold"),
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
        fill = blend(C.PANEL, col, 0.18)
        c.create_oval(S(2), S(2), S(44), S(44), fill=fill, outline=col, width=S(2))
        x, y = S(23), S(23)
        c.create_rectangle(x - S(4), y - S(11), x + S(4), y + S(3), fill=col, outline=col)
        c.create_oval(x - S(4), y - S(14), x + S(4), y - S(7), fill=col, outline=col)
        c.create_oval(x - S(4), y - S(1), x + S(4), y + S(6), fill=col, outline=col)
        c.create_arc(x - S(9), y - S(9), x + S(9), y + S(8), start=200, extent=140,
                     style="arc", outline=col, width=S(2))
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
            return 'Say "Jarvis …"  ·  or tap the mic / press F2'
        return "Always listening — just speak."

    def set_status(self, text):
        self.lbl_status.config(text=text)

    def show_heard(self, text, ignored=False):
        self.lbl_heard.config(text=(f'heard: "{text}"  — no wake word' if ignored else f'"{text}"'),
                              fg=C.MUTED if ignored else C.SOFT)

    def on_booted(self):
        self.flags["ready"] = True
        self._refresh_mode()
        self.set_status(self.idle_hint())

    def on_ai_status(self, online, msg):
        if online and not msg.startswith("missing"):
            self.pill_ai.set(self.cfg["ai_model"], C.GREEN)
        elif online:
            self.pill_ai.set("model missing", C.AMBER)
            self.add_system(f"Ollama is running but {msg}. Run: ollama pull <model>")
        else:
            self.pill_ai.set("offline", C.RED)
            self.add_system("Ollama isn't reachable — PC commands still work. Start it with: ollama serve")

    @staticmethod
    def _short(name, n=22):
        name = re.sub(r"\s*\(.*?\)", "", name).strip() or name
        return name if len(name) <= n else name[:n - 1] + "…"

    def on_mic_ready(self, label):
        self.flags["mic_error"] = False
        if not self.assistant.mic.muted:
            self.pill_mic.set(self._short(label), C.GREEN)
        self.add_system(f"Microphone: {label}")
        self._refresh_mode()
        if self.flags["ready"]:
            self.set_status(self.idle_hint())

    def on_mic_error(self, msg):
        first = not self.flags["mic_error"]
        self.flags["mic_error"] = True
        self.pill_mic.set("error", C.RED)
        if first:
            self.add_system(f"Mic error: {msg}")
        self._refresh_mode()
        self.set_status(self.idle_hint())

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

    def add_assistant(self, text):
        self._chat_insert(("JARVIS", "who_ai"), (f"   {datetime.datetime.now():%H:%M}\n", "meta"))
        self._insert_rich(text)
        self._chat_insert(("\n", "msg_ai"))

    def _insert_rich(self, text):
        parts = re.split(r"(```.*?```)", text, flags=re.S)
        for part in parts:
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
        if "```" in self._stream_buf:                       # re-render with code styling
            self.chat.config(state="normal")
            self.chat.delete("stream_start", "end-1c")
            self.chat.config(state="disabled")
            self._insert_rich(self._stream_buf)
        self._chat_insert(("\n", "msg_ai"))

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
            self._chat_insert(who, ("\n", "meta"),
                              ((body[:400] + ("…" if len(body) > 400 else "")) + "\n", "old"))
        self.add_system("now")

    # ── timers ────────────────────────────────────────────────────
    def _tick_clock(self):
        now = datetime.datetime.now()
        self.lbl_time.config(text=now.strftime("%H:%M:%S"))
        self.lbl_date.config(text=now.strftime("%A  ·  %d %B %Y").upper())
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
                self._gauge_vals = {
                    "CPU": psutil.cpu_percent(interval=None),
                    "RAM": psutil.virtual_memory().percent,
                    "DISK": psutil.disk_usage(os.path.abspath(os.sep)).percent,
                }
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
                self.metrics["PROCESSES"].config(text=str(len(psutil.pids())))
            except Exception:
                pass
        self._draw_gauges()
        self.root.after(1000, self._tick_stats)

    def _draw_gauges(self):
        S, c = self.S, self.gauges
        c.delete("all")
        w = max(c.winfo_width(), S(220))
        r = S(30)
        for i, (k, v) in enumerate(self._gauge_vals.items()):
            cx = w * (i + 0.5) / 3
            cy = S(44)
            col = C.RED if v > 85 else C.AMBER if v > 65 else C.CYAN
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=225, extent=-270, style="arc",
                         outline=C.LINE, width=S(5))
            if v > 0.5:
                c.create_arc(cx - r, cy - r, cx + r, cy + r, start=225, extent=-270 * v / 100,
                             style="arc", outline=col, width=S(5))
            c.create_text(cx, cy, text=f"{v:.0f}", fill=C.WHITE, font=(F_HEAD, 13, "bold"))
            c.create_text(cx, cy + S(13), text="%", fill=C.MUTED, font=(F_HEAD, 7))
            c.create_text(cx, cy + r + S(16), text=k, fill=C.SOFT, font=(F_HEAD, 8, "bold"))

    # ── animation ────────────────────────────────────────────────
    def _animate(self):
        lv = level_norm(self.assistant.mic.level) if self.assistant.mic.ok and not self.assistant_muted() else 0.0
        if self.mode == "speak":
            lv = max(lv, 0.35 + 0.35 * abs(math.sin(self.phase * 2.3)) * abs(math.sin(self.phase * 0.7 + 1)))
        self.smooth += (lv - self.smooth) * 0.35
        self.levels.append(self.smooth)
        speed = {"think": 3.2, "listen": 1.8, "speak": 1.6}.get(self.mode, 0.8)
        self.angle = (self.angle + speed) % 360
        self.phase += 0.08
        try:
            self._draw_reactor()
            self._draw_meter()
        except Exception as e:
            log(f"draw error: {e}")
        self.root.after(33, self._animate)

    def _accent(self):
        if self.mode == "idle" and self.flags["hearing"]:
            return C.TEAL
        return MODE_STYLE[self.mode][1]

    def _draw_reactor(self):
        c, S = self.reactor, self.S
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 50 or h < 50:
            return
        cx, cy = w / 2, h / 2
        R = min(w, h) / 2 - S(12)
        acc = self._accent()
        lv = self.smooth
        a0 = self.angle

        # ambient glow
        for i, (rr, t) in enumerate(((1.05, 0.04), (0.82, 0.06), (0.6, 0.08 + 0.06 * lv))):
            r = R * rr
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=blend(C.BG, acc, t), outline="")

        # tick ring (lights up with mic level)
        n = 90
        lit = int(n * lv)
        for i in range(n):
            ang = math.radians(i * 360 / n + a0 * 0.15)
            long = i % 5 == 0
            r1, r2 = R * (0.92 if long else 0.945), R * 0.985
            col = acc if (i < lit or (i + n // 2) % n < lit) else blend(C.BG, acc, 0.22)
            c.create_line(cx + r1 * math.cos(ang), cy + r1 * math.sin(ang),
                          cx + r2 * math.cos(ang), cy + r2 * math.sin(ang),
                          fill=col, width=S(2) if long else 1)

        # rotating arcs
        r = R * 0.83
        for i in range(3):
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=a0 + i * 120, extent=72,
                         style="arc", outline=acc, width=S(3))
        r = R * 0.75
        for i in range(8):
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=-a0 * 0.7 + i * 45, extent=26,
                         style="arc", outline=blend(C.BG, acc, 0.55), width=S(2))
        r = R * 0.67
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=blend(C.BG, acc, 0.35), dash=(2, 6))

        # coil segments
        r_out, r_in = R * 0.6, R * 0.47
        for i in range(10):
            a = math.radians(i * 36 + 4)
            b = math.radians(i * 36 + 32)
            pts = [cx + r_in * math.cos(a), cy + r_in * math.sin(a),
                   cx + r_out * math.cos(a), cy + r_out * math.sin(a),
                   cx + r_out * math.cos(b), cy + r_out * math.sin(b),
                   cx + r_in * math.cos(b), cy + r_in * math.sin(b)]
            glow = 0.25 + 0.5 * lv * (0.6 + 0.4 * math.sin(self.phase * 3 + i))
            c.create_polygon(pts, fill=blend(C.PANEL, acc, glow), outline=blend(C.BG, acc, 0.7), width=1)

        # inner housing + triangle core
        r = R * 0.4
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=C.PANEL, outline=acc, width=S(2))
        tri = []
        for i in range(3):
            a = math.radians(90 + i * 120)
            tri += [cx + R * 0.3 * math.cos(a), cy + R * 0.3 * math.sin(a)]
        c.create_polygon(tri, fill=blend(C.PANEL, acc, 0.12), outline=acc, width=S(2))

        pulse = 0.5 + 0.5 * math.sin(self.phase * 1.6)
        core = R * (0.12 + 0.05 * pulse * 0.4 + 0.08 * lv)
        for k, t in ((1.9, 0.25), (1.45, 0.5), (1.0, 1.0)):
            rr = core * k
            c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=blend(C.PANEL, acc, t), outline="")
        rr = core * 0.45
        c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=C.WHITE, outline="")

        # scanning arc for "think"
        if self.mode == "think":
            r = R * 0.9
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=-a0 * 2, extent=40,
                         style="arc", outline=C.WHITE, width=S(2))

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
        total = n * bw
        x0 = (w - total) / 2
        mid = h / 2
        for i, v in enumerate(self.levels):
            env = 0.35 + 0.65 * math.sin(math.pi * (i + 0.5) / n)
            amp = max(S(1.5), v * env * (h / 2 - S(4)))
            x = x0 + i * bw
            col = blend(C.BG, acc, 0.35 + 0.65 * min(1, v * 1.5))
            c.create_rectangle(x, mid - amp, x + bw - gap, mid + amp, fill=col, outline="")

    # ── settings ─────────────────────────────────────────────────
    def open_settings(self):
        if getattr(self, "_settings", None) and self._settings.winfo_exists():
            self._settings.lift()
            return
        self._settings = SettingsDialog(self)

    def apply_settings(self, mic_changed, tts_changed):
        save_config(self.cfg)
        self._refresh_engine_label()
        if mic_changed:
            self.pill_mic.set("switching…", C.AMBER)
            self.assistant.mic.reopen()
        if tts_changed:
            self.assistant.tts.reconfigure()
        self.set_status(self.idle_hint())

    # ── quit ─────────────────────────────────────────────────────
    def quit(self):
        try:
            self.assistant.shutdown()
        except Exception:
            pass
        self.root.after(150, self.root.destroy)


class SettingsDialog(tk.Toplevel):
    LANGS = ["en-US", "en-GB", "en-IN", "en-AU", "si-LK", "ja-JP"]

    def __init__(self, hud: HUD):
        super().__init__(hud.root)
        self.hud, self.cfg, S = hud, hud.cfg, hud.S
        self.S = S
        self.title("JARVIS — Settings")
        self.configure(bg=C.PANEL)
        self.geometry(f"{S(560)}x{S(640)}")
        self.minsize(S(520), S(560))
        self.transient(hud.root)

        body = tk.Frame(self, bg=C.PANEL)
        body.pack(fill="both", expand=True, padx=S(22), pady=S(18))

        # ── Microphone ─────────────────────────────────────────
        self._section(body, "MICROPHONE", C.GREEN)
        self.devices = MicEngine.list_devices()
        labels = ["System default (Windows)"] + [f"{d['name']}  ·  {d['hostapi']}" for d in self.devices]
        self.dev_var = tk.StringVar(value=labels[0])
        want = self.cfg.get("mic_device")
        if want:
            for d, l in zip(self.devices, labels[1:]):
                if d["name"] == want.get("name") and d["hostapi"] == want.get("hostapi"):
                    self.dev_var.set(l)
        row = tk.Frame(body, bg=C.PANEL)
        row.pack(fill="x", pady=(0, S(6)))
        self.dev_box = ttk.Combobox(row, textvariable=self.dev_var, values=labels, state="readonly",
                                    style="J.TCombobox", font=(F_BODY, 9))
        self.dev_box.pack(side="left", fill="x", expand=True)
        FlatButton(row, "Apply", self._apply_device, padx=S(12), pady=S(5)).pack(side="left", padx=(S(6), 0))
        tk.Label(body, text="Tip: Bluetooth headsets usually work best via 'MME' or 'Windows DirectSound'.",
                 font=(F_BODY, 8), fg=C.MUTED, bg=C.PANEL, anchor="w").pack(fill="x")

        self.meter = tk.Canvas(body, height=S(22), bg=C.PANEL2, highlightthickness=0)
        self.meter.pack(fill="x", pady=(S(10), S(2)))
        self.meter_lbl = tk.Label(body, text="", font=(F_MONO, 8), fg=C.MUTED, bg=C.PANEL, anchor="w")
        self.meter_lbl.pack(fill="x")

        self.sens = tk.IntVar(value=int(self.cfg.get("mic_sensitivity", 6)))
        self._scale(body, "Sensitivity  (higher = picks up quieter speech)", self.sens, 1, 10)

        self.wake = tk.BooleanVar(value=self.cfg.get("wake_word_enabled", True))
        self._check(body, 'Require wake word "Jarvis"  (off = every phrase is a command)', self.wake)

        tk.Label(body, text="Wake words (comma separated — add how Google mishears 'Jarvis')",
                 font=(F_BODY, 8), fg=C.SOFT, bg=C.PANEL, anchor="w").pack(fill="x", pady=(S(8), S(2)))
        self.wake_words = tk.Entry(body, bg=C.PANEL2, fg=C.TEXT, insertbackground=C.CYAN, bd=0, highlightthickness=0,
                                   font=(F_BODY, 9))
        self.wake_words.insert(0, ", ".join(self.cfg.get("wake_words", [])))
        self.wake_words.pack(fill="x", ipady=S(5))

        row = tk.Frame(body, bg=C.PANEL)
        row.pack(fill="x", pady=(S(8), 0))
        tk.Label(row, text="Speech language", font=(F_BODY, 9), fg=C.SOFT, bg=C.PANEL).pack(side="left")
        self.lang = tk.StringVar(value=self.cfg.get("stt_language", "en-US"))
        ttk.Combobox(row, textvariable=self.lang, values=self.LANGS, width=8, style="J.TCombobox",
                     font=(F_BODY, 9)).pack(side="right")

        # ── Voice ──────────────────────────────────────────────
        self._section(body, "VOICE", C.CYAN)
        voices = ["Auto"] + list(hud.assistant.tts.voices)
        self.voice = tk.StringVar(value=self.cfg.get("tts_voice") or "Auto")
        row = tk.Frame(body, bg=C.PANEL)
        row.pack(fill="x")
        ttk.Combobox(row, textvariable=self.voice, values=voices, state="readonly", style="J.TCombobox",
                     font=(F_BODY, 9)).pack(side="left", fill="x", expand=True)
        FlatButton(row, "Test", self._test_voice, padx=S(12), pady=S(5)).pack(side="left", padx=(S(6), 0))
        self.rate = tk.IntVar(value=int(self.cfg.get("tts_rate", 0)))
        self._scale(body, "Speaking speed", self.rate, -5, 5)
        self.speak = tk.BooleanVar(value=self.cfg.get("speak_replies", True))
        self._check(body, "Speak replies aloud", self.speak)

        # ── AI ─────────────────────────────────────────────────
        self._section(body, "AI MODELS  (Ollama)", C.AMBER)
        self.model = self._entry_row(body, "Chat model", self.cfg["ai_model"])
        self.vmodel = self._entry_row(body, "Vision model", self.cfg["vision_model"])

        btns = tk.Frame(self, bg=C.PANEL)
        btns.pack(fill="x", padx=S(22), pady=(0, S(18)))
        FlatButton(btns, "SAVE", self._save, bg=C.CYAN, fg=C.BG, hover=C.CYAN_HI,
                   font=(F_HEAD, 9, "bold"), padx=S(22), pady=S(8)).pack(side="right")
        FlatButton(btns, "Close", self.destroy, padx=S(16), pady=S(8)).pack(side="right", padx=S(8))
        FlatButton(btns, "Open log", lambda: os.startfile(str(LOG_FILE)) if LOG_FILE.exists() else None,
                   padx=S(12), pady=S(8)).pack(side="left")

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
        tk.Label(row, text=label, font=(F_BODY, 9), fg=C.SOFT, bg=C.PANEL, width=12, anchor="w").pack(side="left")
        e = tk.Entry(row, bg=C.PANEL2, fg=C.TEXT, insertbackground=C.CYAN, bd=0, highlightthickness=0, font=(F_BODY, 9))
        e.insert(0, value)
        e.pack(side="left", fill="x", expand=True, ipady=S(5))
        return e

    def _selected_device(self):
        lbl = self.dev_var.get()
        for d in self.devices:
            if f"{d['name']}  ·  {d['hostapi']}" == lbl:
                return {"name": d["name"], "hostapi": d["hostapi"]}
        return None

    def _apply_device(self):
        self.cfg["mic_device"] = self._selected_device()
        self.hud.apply_settings(mic_changed=True, tts_changed=False)

    def _test_voice(self):
        self.cfg["tts_voice"] = "" if self.voice.get() == "Auto" else self.voice.get()
        self.cfg["tts_rate"] = self.rate.get()
        self.hud.assistant.tts.reconfigure()
        self.hud.assistant.tts.speak("Good evening, sir. All systems are operational.")

    def _tick(self):
        if not self.winfo_exists():
            return
        mic = self.hud.assistant.mic
        c, S = self.meter, self.S
        c.delete("all")
        w = max(c.winfo_width(), 100)
        h = S(22)
        lv = level_norm(mic.level) if mic.ok else 0
        start_th, _ = mic._thresholds() if mic.ok else (0.01, 0)
        th = level_norm(start_th)
        col = C.GREEN if lv >= th else C.CYAN
        c.create_rectangle(0, 0, w * lv, h, fill=col, outline="")
        c.create_line(w * th, 0, w * th, h, fill=C.AMBER, width=S(2))
        db = 20 * math.log10(max(mic.level, 1e-6))
        self.meter_lbl.config(text=(f"level {db:5.1f} dBFS   ·   trigger at {20 * math.log10(max(start_th, 1e-6)):5.1f} dBFS"
                                    f"   ·   {mic.device_label}" if mic.ok else "mic not open"))
        self.after(50, self._tick)

    def _save(self):
        old_dev = self.cfg.get("mic_device")
        self.cfg["mic_device"] = self._selected_device()
        self.cfg["mic_sensitivity"] = int(self.sens.get())
        self.cfg["wake_word_enabled"] = bool(self.wake.get())
        ww = [w.strip().lower() for w in self.wake_words.get().split(",") if w.strip()]
        self.cfg["wake_words"] = ww or ["jarvis"]
        self.cfg["stt_language"] = self.lang.get().strip() or "en-US"
        old_tts = (self.cfg.get("tts_voice"), self.cfg.get("tts_rate"))
        self.cfg["tts_voice"] = "" if self.voice.get() == "Auto" else self.voice.get()
        self.cfg["tts_rate"] = int(self.rate.get())
        self.cfg["speak_replies"] = bool(self.speak.get())
        self.cfg["ai_model"] = self.model.get().strip() or DEFAULT_CONFIG["ai_model"]
        self.cfg["vision_model"] = self.vmodel.get().strip() or DEFAULT_CONFIG["vision_model"]
        self.hud.apply_settings(mic_changed=(old_dev != self.cfg["mic_device"]),
                                tts_changed=(old_tts != (self.cfg["tts_voice"], self.cfg["tts_rate"])))
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
            ctypes.windll.shcore.SetProcessDpiAwareness(1)        # crisp text on HiDPI
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
