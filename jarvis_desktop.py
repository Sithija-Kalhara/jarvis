"""
╔══════════════════════════════════════════════════════════════╗
║        J.A.R.V.I.S.  Desktop App  —  v3.0                  ║
║   Real Tkinter Window | No Flask | No Browser | No Ports    ║
╚══════════════════════════════════════════════════════════════╝

INSTALL (run once):
    pip install SpeechRecognition pyttsx3 pyautogui Pillow psutil ollama sounddevice

USAGE:
    python jarvis_desktop.py

ACTIVATE:
    Say "Jarvis <command>" — microphone always listening in background
"""

import os, sys, time, threading, json, subprocess, webbrowser
import re, datetime, random, math, warnings
import psutil
from pathlib import Path
from PIL import ImageGrab
import pyttsx3
import ollama
from pc_control import CommandParser

warnings.filterwarnings("ignore")

# ── Try best available mic backend ────────────────────────────
# sounddevice works on Python 3.14; pyaudio is fallback
try:
    import sounddevice as sd
    import numpy as np
    MIC_BACKEND = "sounddevice"
except ImportError:
    MIC_BACKEND = "pyaudio"

import speech_recognition as sr

# ── Tkinter ────────────────────────────────────────────────────
import tkinter as tk
from tkinter import font as tkfont
import tkinter.messagebox as msgbox

# ══════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════

WAKE_WORD     = "jarvis"
AI_MODEL      = "qwen2.5:7b"
VISION_MODEL  = "llava:latest"
MEMORY_FILE   = "jarvis_memory.json"
MAX_HISTORY   = 30
ENERGY_THRESH = 300

SYSTEM_PROMPT = """You are J.A.R.V.I.S. (Just A Rather Very Intelligent System).
Personality:
- Calm, witty, slightly formal British tone.
- Keep replies SHORT — 1 to 3 sentences max unless asked to elaborate.
- Occasionally call the user "sir".
- Never say you cannot help — offer the closest alternative.
- Be crisp on task completion: "Done, sir." or "Opening now."
"""

# ══════════════════════════════════════════════════════════════
# MEMORY
# ══════════════════════════════════════════════════════════════

class Memory:
    def __init__(self, path=MEMORY_FILE):
        self.path = Path(path)
        self._data = self._load()

    def _load(self):
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"facts": {}, "history": []}

    def save(self):
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def append_turn(self, role, content):
        self._data["history"].append({"role": role, "content": content})
        if len(self._data["history"]) > MAX_HISTORY:
            self._data["history"] = self._data["history"][-MAX_HISTORY:]
        self.save()

    def get_history(self):
        return self._data["history"]

    def clear_history(self):
        self._data["history"] = []
        self.save()

# ══════════════════════════════════════════════════════════════
# TTS (runs in its own thread to avoid blocking UI)
# ══════════════════════════════════════════════════════════════

class TTSEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self._engine = None
        self._init_engine()

    def _init_engine(self):
        try:
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", 155)
            self._engine.setProperty("volume", 0.92)
            voices = self._engine.getProperty("voices")
            for v in voices:
                if "english" in v.name.lower():
                    self._engine.setProperty("voice", v.id)
                    break
        except Exception as e:
            print(f"TTS init error: {e}")

    def speak(self, text: str):
        def _run():
            with self._lock:
                try:
                    self._engine.say(text)
                    self._engine.runAndWait()
                except Exception:
                    # Reinit if crashed
                    try:
                        self._init_engine()
                        self._engine.say(text)
                        self._engine.runAndWait()
                    except Exception:
                        pass
        threading.Thread(target=_run, daemon=True).start()

# ══════════════════════════════════════════════════════════════
# MICROPHONE — works with sounddevice OR pyaudio
# ══════════════════════════════════════════════════════════════

class MicManager:
    """
    Uses sounddevice if available (Python 3.14 safe).
    Falls back to pyaudio via speech_recognition.
    """

    def __init__(self, on_audio_level=None):
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = ENERGY_THRESH
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.6
        self.recognizer.phrase_threshold = 0.3
        self.recognizer.non_speaking_duration = 0.5
        self.on_audio_level = on_audio_level  # callback(float 0-1)
        self._backend = MIC_BACKEND
        print(f"🎤 Mic backend: {self._backend}")

        if self._backend == "sounddevice":
            self._calibrate_sd()
        else:
            self._calibrate_pyaudio()

    def _calibrate_sd(self):
        print("🔧 Calibrating mic (sounddevice)...")
        try:
            mic = sr.Microphone()
            with mic as src:
                self.recognizer.adjust_for_ambient_noise(src, duration=2)
            print(f"✅ Threshold: {self.recognizer.energy_threshold:.0f}")
        except Exception as e:
            print(f"⚠️ Calibration warning: {e}")

    def _calibrate_pyaudio(self):
        print("🔧 Calibrating mic (pyaudio)...")
        try:
            mic = sr.Microphone()
            with mic as src:
                self.recognizer.adjust_for_ambient_noise(src, duration=2)
            print(f"✅ Threshold: {self.recognizer.energy_threshold:.0f}")
        except Exception as e:
            print(f"⚠️ Calibration warning: {e}")

    def listen_once(self, timeout=3, phrase_limit=10):
        """Blocking listen, returns text or None."""
        try:
            mic = sr.Microphone()
            with mic as src:
                self.recognizer.adjust_for_ambient_noise(src, duration=0.3)
                audio = self.recognizer.listen(src, timeout=timeout,
                                               phrase_time_limit=phrase_limit)
            text = self.recognizer.recognize_google(audio, language="en-US")
            return text
        except (sr.WaitTimeoutError, sr.UnknownValueError):
            return None
        except sr.RequestError as e:
            print(f"   Speech API error: {e}")
            return None
        except Exception as e:
            print(f"   Mic error: {e}")
            return None

    def start_wake_loop(self, on_wake):
        """Background thread that fires on_wake(command) when wake word heard."""
        def _loop():
            rec = sr.Recognizer()
            rec.energy_threshold = ENERGY_THRESH
            rec.dynamic_energy_threshold = True
            rec.pause_threshold = 0.5
            rec.phrase_threshold = 0.3
            rec.non_speaking_duration = 0.4

            try:
                mic = sr.Microphone()
            except Exception as e:
                print(f"❌ Cannot open microphone: {e}")
                print("   Make sure a microphone is connected.")
                return

            try:
                with mic as src:
                    rec.adjust_for_ambient_noise(src, duration=1)
                print(f"🎙️ Wake-word listener active. Say '{WAKE_WORD.upper()}'")
            except Exception as e:
                print(f"⚠️ Mic calibration issue: {e}")

            while True:
                try:
                    with mic as src:
                        audio = rec.listen(src, timeout=2, phrase_time_limit=8)
                    try:
                        text = rec.recognize_google(audio, language="en-US")
                        lower = text.lower()
                        if WAKE_WORD in lower:
                            idx = lower.find(WAKE_WORD)
                            cmd = text[idx + len(WAKE_WORD):].strip(" ,.")
                            on_wake(cmd)
                    except (sr.UnknownValueError, sr.RequestError):
                        pass
                except sr.WaitTimeoutError:
                    pass
                except Exception as e:
                    time.sleep(0.5)

        threading.Thread(target=_loop, daemon=True).start()

# ══════════════════════════════════════════════════════════════
# PC CONTROL
# ══════════════════════════════════════════════════════════════

class PCManager:
    APP_MAP = {
        "notepad":        "notepad.exe",
        "calculator":     "calc.exe",
        "calc":           "calc.exe",
        "chrome":         "chrome.exe",
        "google chrome":  "chrome.exe",
        "browser":        "chrome.exe",
        "firefox":        "firefox.exe",
        "word":           "winword.exe",
        "excel":          "excel.exe",
        "powerpoint":     "powerpnt.exe",
        "cmd":            "cmd.exe",
        "terminal":       "cmd.exe",
        "powershell":     "powershell.exe",
        "paint":          "mspaint.exe",
        "spotify":        "spotify.exe",
        "settings":       "ms-settings:",
        "task manager":   "taskmgr.exe",
        "file explorer":  "explorer.exe",
        "explorer":       "explorer.exe",
        "edge":           "msedge.exe",
        "vscode":         "code.exe",
        "vs code":        "code.exe",
        "discord":        "discord.exe",
        "zoom":           "zoom.exe",
        "vlc":            "vlc.exe",
    }

    def open_app(self, name):
        key = name.lower().strip()
        exe = self.APP_MAP.get(key)
        if exe:
            try:
                subprocess.Popen(exe, shell=True)
                return f"Opened {name}."
            except Exception as e:
                return f"Failed to open {name}: {e}"
        try:
            import pyautogui
            pyautogui.hotkey("win", "s")
            time.sleep(0.6)
            pyautogui.write(name, interval=0.05)
            time.sleep(1)
            pyautogui.press("enter")
            return f"Searching Windows for {name}."
        except Exception:
            return f"Cannot open '{name}'."


    def get_system_info(self):
        cpu  = psutil.cpu_percent(interval=0.5)
        ram  = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        now  = datetime.datetime.now().strftime("%H:%M")
        return (f"{now} | CPU {cpu}% | "
                f"RAM {ram.percent}% ({ram.available // 1024**2} MB free) | "
                f"Disk {disk.percent}%")

    def type_text(self, text):
        try:
            import pyautogui
            time.sleep(0.5)
            pyautogui.write(text, interval=0.04)
            return f"Typed: {text}"
        except Exception as e:
            return f"Cannot type: {e}"

    def run_command(self, cmd):
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            out = (r.stdout or r.stderr).strip()
            return out[:300] if out else "Done."
        except Exception as e:
            return f"Error: {e}"

    def analyze_screen(self):
        path = "jarvis_screen.png"
        ImageGrab.grab().save(path)
        try:
            resp = ollama.chat(model=VISION_MODEL, messages=[{
                "role": "user",
                "content": "Describe what's on this screen in 2 sentences.",
                "images": [path]
            }])
            try:
                return resp.message.content
            except AttributeError:
                return resp["message"]["content"]
        except Exception as e:
            return f"Screen analysis error: {e}"

# ══════════════════════════════════════════════════════════════
# AI BRAIN
# ══════════════════════════════════════════════════════════════

class AIBrain:
    def __init__(self, memory: Memory):
        self.memory = memory

    def reply(self, user_input: str) -> str:
        self.memory.append_turn("user", user_input)
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + self.memory.get_history()
        try:
            resp = ollama.chat(model=AI_MODEL, messages=msgs)
            try:
                answer = resp.message.content
            except AttributeError:
                answer = resp["message"]["content"]
        except Exception as e:
            answer = f"My circuits hit a snag, sir. ({e})"
        self.memory.append_turn("assistant", answer)
        return answer

# ══════════════════════════════════════════════════════════════
# COMMAND HANDLER
# ══════════════════════════════════════════════════════════════

def handle_command(command: str, pc: PCManager, brain: AIBrain,
                   tts: TTSEngine, mic: MicManager, ui) -> str:
    """Process a command. Returns response text."""
    command = command.strip()
    if not command:
        tts.speak("Yes, sir?")
        follow = mic.listen_once(timeout=6)
        if follow:
            return handle_command(follow, pc, brain, tts, mic, ui)
        return "Waiting..."

    c = command.lower()

    # ── Quick time/date ──────────────────────────────────────
    if any(x in c for x in ("what time", "current time", "time is it")):
        r = datetime.datetime.now().strftime("It is %H:%M, sir.")
        tts.speak(r); return r

    if any(x in c for x in ("what day", "today's date", "what date")):
        r = datetime.datetime.now().strftime("Today is %A, %d %B %Y.")
        tts.speak(r); return r

    # ── Open app ─────────────────────────────────────────────
    if c.startswith("open "):
        app = command[5:].strip()
        r = pc.open_app(app)
        tts.speak(r); return r

    # ── Search ───────────────────────────────────────────────
    if any(x in c for x in ("search for", "google", "look up")):
        q = re.sub(r"(search for|search|google|look up)", "", c).strip()
        r = pc.search_web(q)
        tts.speak(f"Searching for {q}, sir.")
        return r

    # ── Screenshot ───────────────────────────────────────────
    if any(x in c for x in ("screenshot", "capture screen", "take a screenshot")):
        r = pc.take_screenshot()
        tts.speak(r); return r

    # ── Type ─────────────────────────────────────────────────
    if c.startswith("type "):
        text = command[5:].strip()
        r = pc.type_text(text)
        tts.speak(r); return r

    # ── System info ──────────────────────────────────────────
    if any(x in c for x in ("system status", "system info", "cpu", "ram usage")):
        r = pc.get_system_info()
        tts.speak(r); return r

    # ── Screen analysis ──────────────────────────────────────
    if any(x in c for x in ("analyze screen", "what's on screen", "what is on my screen")):
        tts.speak("Analyzing your screen, sir.")
        r = pc.analyze_screen()
        tts.speak(r[:250])
        return r

    # ── Run command ──────────────────────────────────────────
    if c.startswith("run "):
        cmd = command[4:].strip()
        r = pc.run_command(cmd)
        tts.speak("Done, sir." if len(r) < 20 else r[:150])
        return r

    # ── Memory ───────────────────────────────────────────────
    if any(x in c for x in ("clear history", "forget everything", "reset memory")):
        brain.memory.clear_history()
        r = "Memory cleared, sir."
        tts.speak(r); return r

    # ── Exit ─────────────────────────────────────────────────
    if any(x in c for x in ("goodbye", "exit", "quit", "shutdown", "bye")):
        tts.speak("Signing off, sir. Have a good one.")
        time.sleep(1.5)
        ui.quit_app()
        return "Goodbye."

    # ── AI fallback ──────────────────────────────────────────
    response = brain.reply(command)
    tts.speak(response[:300])
    return response

# ══════════════════════════════════════════════════════════════
# DESKTOP UI  (Tkinter — pure desktop, no browser)
# ══════════════════════════════════════════════════════════════

DARK       = "#050d1a"
DARK2      = "#0a1628"
DARK3      = "#0f1f38"
BLUE       = "#4fc3f7"
BLUE2      = "#0288d1"
BLUE3      = "#01579b"
BLUE_DIM   = "#1a3a5c"
GREEN      = "#00e676"
AMBER      = "#ffab40"
WHITE      = "#e1f5fe"
FONT_MONO  = ("Consolas", 10)
FONT_TITLE = ("Consolas", 13, "bold")
FONT_BIG   = ("Consolas", 22, "bold")
FONT_SMALL = ("Consolas", 8)

class JARVISApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("J.A.R.V.I.S.  v3.0")
        self.root.configure(bg=DARK)
        self.root.geometry("900x620")
        self.root.minsize(750, 500)
        self.root.resizable(True, True)

        # Remove default title bar decorations on Windows for cleaner look
        # self.root.overrideredirect(True)  # uncomment if you want borderless

        self._mode = "idle"
        self._angle = 0          # reactor ring rotation
        self._wave_phase = 0     # waveform animation phase
        self._log_lines = []
        self._busy = False

        self._build_ui()
        self._start_animation()

        # Core systems
        self.memory = Memory()
        self.tts    = TTSEngine()
        self.pc     = PCManager()
        self.brain  = AIBrain(self.memory)
        self.mic    = MicManager()

        self._log("[ sys ] JARVIS v3.0 initialising...")
        self.set_mode("idle", "Starting up…")

        # Start mic in background after UI is ready
        self.root.after(200, self._start_mic)

    # ── BUILD UI ────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar ───────────────────────────────────────────
        top = tk.Frame(self.root, bg=DARK, height=44)
        top.pack(fill="x", padx=12, pady=(10, 0))

        tk.Label(top, text="JARVIS", font=("Consolas", 15, "bold"),
                 fg=BLUE, bg=DARK).pack(side="left")
        tk.Label(top, text="  /  v3.0  /  LOCAL AI SYSTEM",
                 font=("Consolas", 9), fg=BLUE2, bg=DARK).pack(side="left")

        self.lbl_time = tk.Label(top, text="", font=FONT_MONO, fg=BLUE2, bg=DARK)
        self.lbl_time.pack(side="right", padx=10)

        self.lbl_badge = tk.Label(top, text="● STANDBY",
                                   font=("Consolas", 9, "bold"), fg=GREEN, bg=DARK)
        self.lbl_badge.pack(side="right", padx=16)

        tk.Frame(self.root, bg=BLUE3, height=1).pack(fill="x", padx=12)

        # ── Main content ──────────────────────────────────────
        content = tk.Frame(self.root, bg=DARK)
        content.pack(fill="both", expand=True, padx=12, pady=8)
        content.columnconfigure(0, weight=0)
        content.columnconfigure(1, weight=1)
        content.columnconfigure(2, weight=0)
        content.rowconfigure(0, weight=1)

        # LEFT: system stats
        left = tk.Frame(content, bg=DARK2, width=190)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.pack_propagate(False)
        self._build_left(left)

        # CENTER: reactor + status
        center = tk.Frame(content, bg=DARK)
        center.grid(row=0, column=1, sticky="nsew")
        self._build_center(center)

        # RIGHT: log
        right = tk.Frame(content, bg=DARK2, width=220)
        right.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        right.pack_propagate(False)
        self._build_right(right)

        # ── Bottom: waveform + input ──────────────────────────
        tk.Frame(self.root, bg=BLUE3, height=1).pack(fill="x", padx=12)
        bottom = tk.Frame(self.root, bg=DARK, height=110)
        bottom.pack(fill="x", padx=12, pady=6)
        bottom.pack_propagate(False)
        self._build_bottom(bottom)

    def _card(self, parent, title):
        f = tk.Frame(parent, bg=DARK3, bd=0, highlightthickness=1,
                     highlightbackground=BLUE3)
        f.pack(fill="x", padx=8, pady=4)
        tk.Label(f, text=title, font=FONT_SMALL, fg=BLUE2, bg=DARK3,
                 anchor="w").pack(fill="x", padx=8, pady=(5, 2))
        tk.Frame(f, bg=BLUE3, height=1).pack(fill="x", padx=8)
        return f

    def _build_left(self, parent):
        tk.Label(parent, text="SYSTEM", font=("Consolas", 9, "bold"),
                 fg=BLUE2, bg=DARK2).pack(pady=(10, 4))

        # CPU
        cf = self._card(parent, "CPU USAGE")
        self.lbl_cpu = tk.Label(cf, text="—", font=FONT_MONO, fg=BLUE, bg=DARK3)
        self.lbl_cpu.pack(padx=8, pady=2, anchor="w")
        self.bar_cpu = self._bar(cf)

        # RAM
        rf = self._card(parent, "MEMORY")
        self.lbl_ram = tk.Label(rf, text="—", font=FONT_MONO, fg=BLUE, bg=DARK3)
        self.lbl_ram.pack(padx=8, pady=2, anchor="w")
        self.bar_ram = self._bar(rf)

        # Disk
        df = self._card(parent, "DISK")
        self.lbl_disk = tk.Label(df, text="—", font=FONT_MONO, fg=BLUE, bg=DARK3)
        self.lbl_disk.pack(padx=8, pady=2, anchor="w")
        self.bar_disk = self._bar(df)

        # Model info
        mf = self._card(parent, "AI ENGINE")
        for txt in (f"Model: {AI_MODEL}", f"Vision: {VISION_MODEL}", f'Wake: "{WAKE_WORD}"'):
            tk.Label(mf, text=txt, font=FONT_SMALL, fg=BLUE2, bg=DARK3,
                     anchor="w").pack(fill="x", padx=8, pady=1)
        tk.Label(mf, text="", bg=DARK3).pack(pady=2)

    def _bar(self, parent):
        canvas = tk.Canvas(parent, height=5, bg=DARK3, highlightthickness=0)
        canvas.pack(fill="x", padx=8, pady=(0, 6))
        return canvas

    def _update_bar(self, canvas, pct, color=BLUE2):
        canvas.update_idletasks()
        w = canvas.winfo_width()
        canvas.delete("all")
        canvas.create_rectangle(0, 0, w, 5, fill=BLUE_DIM, outline="")
        fill_w = int(w * pct / 100)
        c = "#ef5350" if pct > 85 else AMBER if pct > 65 else color
        canvas.create_rectangle(0, 0, fill_w, 5, fill=c, outline="")

    def _build_center(self, parent):
        # Reactor canvas
        self.reactor_canvas = tk.Canvas(parent, width=240, height=240,
                                         bg=DARK, highlightthickness=0)
        self.reactor_canvas.pack(pady=(10, 6))

        self.lbl_mode = tk.Label(parent, text="STANDBY",
                                  font=("Consolas", 11, "bold"), fg=BLUE2, bg=DARK)
        self.lbl_mode.pack()

        self.lbl_status = tk.Label(parent, text='Say  "Jarvis"  to activate',
                                    font=FONT_MONO, fg=BLUE, bg=DARK,
                                    wraplength=340, justify="center")
        self.lbl_status.pack(pady=4)

    def _build_right(self, parent):
        tk.Label(parent, text="LOG", font=("Consolas", 9, "bold"),
                 fg=BLUE2, bg=DARK2).pack(pady=(10, 4))

        self.log_text = tk.Text(parent, bg=DARK3, fg=BLUE2,
                                 font=("Consolas", 8), bd=0,
                                 highlightthickness=1, highlightbackground=BLUE3,
                                 state="disabled", wrap="word",
                                 insertbackground=BLUE)
        self.log_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Cmd history
        cf = self._card(parent, "COMMAND HISTORY")
        self.cmd_text = tk.Text(cf, bg=DARK3, fg=BLUE, font=("Consolas", 8),
                                 bd=0, highlightthickness=0,
                                 state="disabled", wrap="word", height=5)
        self.cmd_text.pack(fill="x", padx=8, pady=(4, 6))

    def _build_bottom(self, parent):
        # Waveform canvas
        self.wave_canvas = tk.Canvas(parent, height=48, bg=DARK,
                                      highlightthickness=0)
        self.wave_canvas.pack(fill="x", padx=8, pady=(4, 0))

        # Text input row
        row = tk.Frame(parent, bg=DARK)
        row.pack(fill="x", padx=8, pady=(4, 4))

        tk.Label(row, text="⌨", font=("Consolas", 11), fg=BLUE2, bg=DARK).pack(side="left")

        self.entry = tk.Entry(row, bg=DARK3, fg=BLUE, font=FONT_MONO,
                               insertbackground=BLUE, bd=0,
                               highlightthickness=1, highlightbackground=BLUE2,
                               relief="flat")
        self.entry.pack(side="left", fill="x", expand=True, padx=(6, 6), ipady=5)
        self.entry.bind("<Return>", self._on_type_command)

        self.btn_send = tk.Button(row, text="SEND", font=("Consolas", 9, "bold"),
                                   fg=DARK, bg=BLUE2, activebackground=BLUE,
                                   activeforeground=DARK, bd=0, padx=14, pady=4,
                                   cursor="hand2",
                                   command=self._on_type_command)
        self.btn_send.pack(side="left")

        tk.Label(row, text="  MIC:", font=FONT_SMALL, fg=BLUE3, bg=DARK).pack(side="left")
        self.lbl_mic = tk.Label(row, text="●", font=("Consolas", 12),
                                  fg=BLUE_DIM, bg=DARK)
        self.lbl_mic.pack(side="left")

    # ── ANIMATION ───────────────────────────────────────────────

    def _start_animation(self):
        self._animate()
        self._update_clock()
        self._update_stats()

    def _animate(self):
        self._draw_reactor()
        self._draw_waveform()
        self._angle = (self._angle + 1.2) % 360
        self._wave_phase += 0.12
        self.root.after(30, self._animate)

    def _draw_reactor(self):
        c = self.reactor_canvas
        c.delete("all")
        cx, cy, R = 120, 120, 108

        # Mode colours
        colors = {
            "idle":   (BLUE3,  BLUE2, BLUE,  "#7dd3fc"),
            "listen": (BLUE3,  GREEN, GREEN, "#a7f3d0"),
            "think":  (BLUE3,  AMBER, AMBER, "#fde68a"),
            "speak":  (BLUE2,  BLUE,  WHITE, WHITE),
        }
        c1, c2, c3, core_col = colors.get(self._mode, colors["idle"])

        # Static outer ring
        c.create_oval(cx-R, cy-R, cx+R, cy+R, outline=BLUE3,
                      width=1, dash=(3, 7))

        # Rotating ring A
        a = math.radians(self._angle)
        for i in range(4):
            aa = a + i * math.pi / 2
            x = cx + (R - 12) * math.cos(aa)
            y = cy + (R - 12) * math.sin(aa)
            c.create_oval(x-5, y-5, x+5, y+5, fill=c2, outline="")
        c.create_oval(cx-(R-12), cy-(R-12), cx+(R-12), cy+(R-12),
                      outline=c2, width=1, dash=(10, 8))

        # Rotating ring B (reverse)
        b = math.radians(-self._angle * 0.6)
        c.create_oval(cx-74, cy-74, cx+74, cy+74,
                      outline=c3, width=1, dash=(5, 9))
        for i in range(4):
            bb = b + i * math.pi / 2
            x = cx + 74 * math.cos(bb)
            y = cy + 74 * math.sin(bb)
            c.create_rectangle(x-4, y-4, x+4, y+4, fill=c3, outline="")

        # Inner ring
        c.create_oval(cx-52, cy-52, cx+52, cy+52,
                      outline=c1, width=1, dash=(3, 5))

        # Hexagon core housing
        hex_pts = []
        for i in range(6):
            ang = math.radians(60*i - 30)
            hex_pts += [cx + 38*math.cos(ang), cy + 38*math.sin(ang)]
        c.create_polygon(hex_pts, fill=DARK2, outline=c2, width=1)

        # Scan line
        scan_y = cy - 28 + (28 * 2 * ((self._wave_phase * 0.3) % 1))
        c.create_line(cx-28, scan_y, cx+28, scan_y, fill=c3, width=1)

        # Glow layers
        pulse = 18 + 3 * math.sin(self._wave_phase * 0.5)
        c.create_oval(cx-pulse-6, cy-pulse-6, cx+pulse+6, cy+pulse+6,
                      fill=BLUE3, outline="")
        c.create_oval(cx-pulse, cy-pulse, cx+pulse, cy+pulse,
                      fill=c2, outline="")
        c.create_oval(cx-14, cy-14, cx+14, cy+14, fill=c3, outline="")
        c.create_oval(cx-8, cy-8, cx+8, cy+8, fill=core_col, outline="")
        c.create_oval(cx-3, cy-3, cx+3, cy+3, fill=WHITE, outline="")

    def _draw_waveform(self):
        c = self.wave_canvas
        c.update_idletasks()
        w = c.winfo_width()
        if w < 10:
            w = 860
        h = 48
        c.delete("all")

        num_bars = 56
        bar_w = 4
        gap   = 2
        total = num_bars * (bar_w + gap)
        x_start = (w - total) // 2

        for i in range(num_bars):
            mid = num_bars / 2
            env = math.exp(-0.04 * (i - mid) ** 2)

            if self._mode in ("listen", "speak"):
                amp = env * 20 * (0.3 + 0.7 * abs(
                    math.sin(self._wave_phase * 3 + i * 0.4)))
            else:
                amp = env * 8 * (0.3 + 0.7 * abs(
                    math.sin(self._wave_phase * 0.8 + i * 0.3)))

            amp = max(2, amp)
            x = x_start + i * (bar_w + gap)
            bar_color = GREEN if self._mode == "listen" else \
                        AMBER  if self._mode == "think"  else BLUE2

            c.create_rectangle(x, h//2 - amp, x + bar_w, h//2 + amp,
                                fill=bar_color, outline="")

    def _update_clock(self):
        self.lbl_time.config(text=datetime.datetime.now().strftime("%H:%M:%S"))
        self.root.after(1000, self._update_clock)

    def _update_stats(self):
        try:
            cpu  = psutil.cpu_percent(interval=0)
            ram  = psutil.virtual_memory().percent
            disk = psutil.disk_usage("/").percent
            self.lbl_cpu.config(text=f"{cpu:.0f}%")
            self.lbl_ram.config(text=f"{ram:.0f}%")
            self.lbl_disk.config(text=f"{disk:.0f}%")
            self._update_bar(self.bar_cpu,  cpu)
            self._update_bar(self.bar_ram,  ram)
            self._update_bar(self.bar_disk, disk)
        except Exception:
            pass
        self.root.after(3000, self._update_stats)

    # ── STATE ───────────────────────────────────────────────────

    def set_mode(self, mode: str, status_text: str = ""):
        self._mode = mode
        labels = {
            "idle":   ("STANDBY",    BLUE2,  GREEN),
            "listen": ("LISTENING",  GREEN,  GREEN),
            "think":  ("PROCESSING", AMBER,  AMBER),
            "speak":  ("SPEAKING",   BLUE,   BLUE),
        }
        label, text_col, dot_col = labels.get(mode, labels["idle"])
        self.lbl_mode.config(text=label, fg=text_col)
        self.lbl_badge.config(text=f"● {label}", fg=dot_col)
        self.lbl_mic.config(fg=GREEN if mode == "listen" else BLUE_DIM)
        if status_text:
            self.lbl_status.config(text=status_text, fg=text_col)

    def _log(self, msg: str):
        def _do():
            self.log_text.config(state="normal")
            self.log_text.insert("end", msg + "\n")
            # Keep max 80 lines
            lines = int(self.log_text.index("end-1c").split(".")[0])
            if lines > 80:
                self.log_text.delete("1.0", f"{lines-80}.0")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.root.after(0, _do)

    def _log_cmd(self, cmd: str, resp: str):
        def _do():
            self.cmd_text.config(state="normal")
            ts = datetime.datetime.now().strftime("%H:%M")
            self.cmd_text.insert("end", f"[{ts}] > {cmd[:40]}\n")
            self.cmd_text.insert("end", f"       {resp[:50]}\n\n")
            self.cmd_text.see("end")
            self.cmd_text.config(state="disabled")
        self.root.after(0, _do)

    # ── MIC START ───────────────────────────────────────────────

    def _start_mic(self):
        self._log("[ mic ] Initialising microphone...")
        try:
            self.mic.start_wake_loop(self._on_wake)
            self._log(f'[ mic ] Listening for "{WAKE_WORD.upper()}"')
            self.set_mode("idle", f'Say  "{WAKE_WORD}"  to activate')
            self.tts.speak("JARVIS online. How can I assist, sir?")
        except Exception as e:
            self._log(f"[ mic ] ERROR: {e}")
            self.set_mode("idle", "Mic error — use text input below")

    # ── COMMAND DISPATCH ────────────────────────────────────────

    def _on_wake(self, command: str):
        """Called from background mic thread."""
        self.root.after(0, lambda: self._process_command(command))

    def _on_type_command(self, event=None):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self._process_command(text)

    def _process_command(self, command: str):
        if self._busy:
            self._log("[ sys ] Still processing — please wait")
            return
        self._busy = True

        self._log(f"[ usr ] {command}")
        self.set_mode("listen", f"Heard: {command}")

        def _run():
            try:
                self.root.after(0, lambda: self.set_mode("think", "Processing…"))
                self.brain._parser_ref = self.parser
                resp = handle_command(command, self.pc, self.brain,
                                       self.tts, self.mic, self)
                short = resp[:60] + ("…" if len(resp) > 60 else "")
                self.root.after(0, lambda: self._log(f"[ ai  ] {resp[:80]}"))
                self.root.after(0, lambda: self._log_cmd(command, resp))
                self.root.after(0, lambda: self.set_mode("idle",
                    f'Say  "{WAKE_WORD}"  to activate'))
            except Exception as e:
                self.root.after(0, lambda: self._log(f"[ err ] {e}"))
            finally:
                self._busy = False

        threading.Thread(target=_run, daemon=True).start()

    # ── QUIT ────────────────────────────────────────────────────

    def quit_app(self):
        self.root.after(0, self.root.destroy)

# ══════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════

def check_ollama():
    print("📡 Checking Ollama…")
    try:
        raw = ollama.list()
        names = []
        try:
            for m in raw.models:
                try:    names.append(m.model)
                except: names.append(str(m))
        except AttributeError:
            for m in raw.get("models", []):
                try:    names.append(m["name"])
                except: names.append(str(m))

        print(f"   Models: {', '.join(names) or 'none found'}")
        for mid, label in [(AI_MODEL, "AI"), (VISION_MODEL, "Vision")]:
            if not any(mid in x for x in names):
                print(f"⚠️  {label} model not found → ollama pull {mid}")
        print("✅ Ollama OK\n")
    except Exception as e:
        print(f"\n❌ Ollama unreachable: {e}")
        print("   Open a terminal and run:  ollama serve")
        msgbox.showerror("JARVIS — Ollama Error",
                         f"Cannot reach Ollama:\n{e}\n\nPlease run: ollama serve")
        sys.exit(1)

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║        JARVIS  Desktop  v3.0                         ║
║   Pure Tkinter | No Browser | No Ports | Python 3.14 Safe   ║
╚══════════════════════════════════════════════════════════════╝
""")
    check_ollama()

    root = tk.Tk()
    root.protocol("WM_DELETE_WINDOW", lambda: root.destroy())

    app = JARVISApp(root)
    root.mainloop()
