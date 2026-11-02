=====================================================
  J.A.R.V.I.S.  Personal AI System  v5.0
  Holographic HUD | British neural voice | Ollama AI
=====================================================

SETUP (once)
------------
  pip install -r requirements.txt
  ollama pull qwen2.5:3b      (7b if you have a GPU / 32 GB RAM)
  ollama pull moondream       (light vision model for screen scan)

RUN
---
  ollama serve            (or SETUP_AND_RUN.bat)
  python JARVIS_FULL.py   (or BUILD_EXE.bat → JARVIS.exe on Desktop)

TALKING TO JARVIS
-----------------
  "Jarvis, open chrome"         wake word + command
  "Jarvis" … "Yes, sir?" …      then the command
  Click the core / F2           talk without the wake word
  Ctrl+Alt+J                    talk from ANY app (global hotkey)
  Esc / STOP / "stop"           stop speaking
  F11 / ◈ HOLO / "go holographic"
                                floating transparent orb, always on top
                                click = talk, double-click = full HUD,
                                drag = move, right-click = menu

JARVIS FEATURES
---------------
  Boot sequence        real start-up checks (AI, mic, voice, weather)
  Greeting             time-of-day + weather on start
  "daily briefing"     time, weather, system status, timers
  Weather              "what's the weather" · "will it rain today"
                       "weather in Tokyo"   (city set in Settings)
  Timers               "set a timer for 10 minutes"
                       "set a 5 minute timer for pasta"
                       "how much time is left" · "cancel all timers"
  Reminders            "remind me in 20 minutes to stretch"
                       "remind me to call mom in an hour"
  Protocols            "activate work protocol" · "gaming mode"
                       "focus mode" · "list protocols"
                       Edit them in jarvis_config.json:
                         "protocols": { "work": ["open vs code", ...] }
  Proactive alerts     low battery, CPU/RAM overload, late-night nudge
  Voice                Neural British voice (en-GB-RyanNeural, needs
                       internet) — falls back to Windows voice offline
  Small talk           "you up?" · "thank you" · "who are you" · "help"

PC COMMANDS (examples)
----------------------
  APPS     open spotify · close chrome · switch to notepad · minimize all
  FILES    open downloads · open folder C:\Projects · create folder test
  SYSTEM   system status · set volume to 40 · mute · brightness 70
           lock · restart · shut down the computer · cancel shutdown
  BROWSER  search for python tutorial · play lofi on youtube
           go to github.com · new tab · go back
  NETWORK  what is my ip · wifi off · ping google.com
  KEYS     press ctrl shift esc · type hello world · next track
  VISION   what's on my screen
  AI       anything else → Ollama, spoken sentence-by-sentence

MIC NOT WORKING?  (Settings ⚙)
-----------------------------
  1. Pick your device. Bluetooth headsets (e.g. WH-1000XM4): try the
     "MME" entry first, then "Windows DirectSound".
  2. Speak and watch the live meter — it must cross the gold line.
  3. Google mishears "Jarvis"? Add what it hears to Wake words.
  4. Check jarvis.log (Settings → Open log).
=====================================================
