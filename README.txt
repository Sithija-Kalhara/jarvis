=====================================================
  J.A.R.V.I.S.  Desktop Assistant  v4.0
  Wake word + push-to-talk | Ollama AI | PC control
=====================================================

FILES
-----
  JARVIS_FULL.py      Main app (single file)
  requirements.txt    Python packages
  SETUP_AND_RUN.bat   Install packages + start Ollama + run
  BUILD_EXE.bat       Build JARVIS.exe onto your Desktop

  Created at runtime (next to the script / EXE):
  jarvis_config.json  Your settings (mic device, sensitivity, voice, models)
  jarvis_memory.json  Conversation history
  jarvis.log          Log — check this first if the mic misbehaves

REQUIREMENTS
------------
  - Python 3.10+  (3.12 / 3.14 fine)
  - Ollama:  ollama serve
             ollama pull qwen2.5:7b
             ollama pull llava:latest
  - Internet (speech recognition uses Google STT)
  - A microphone

TALKING TO JARVIS
-----------------
  "Jarvis open chrome"          wake word + command in one go
  "Jarvis"  ...  "Yes, sir?"  ... "open chrome"
  Mic button / F2               talk without the wake word
  Esc / STOP / "Jarvis stop"    stop speaking
  MUTE MIC                      pause listening (typing still works)

MIC NOT WORKING? (Settings ⚙)
-----------------------------
  1. Pick your device. Bluetooth headsets (e.g. WH-1000XM4):
     try the "MME" entry first, then "Windows DirectSound".
  2. Speak and watch the live meter. It must cross the amber line.
     Not crossing  -> raise Sensitivity.
     Always green  -> lower Sensitivity (noisy room).
  3. Google keeps mishearing "Jarvis"? Add what it hears
     (shown under the reactor as  heard: "..." ) to Wake words.
  4. Or untick "Require wake word" for always-listening mode.

COMMANDS (examples)
-------------------
  APPS     open spotify · close chrome · switch to notepad · minimize all
  FILES    open downloads · open folder C:\Projects · create folder test
           find file report · list files in documents
  SYSTEM   system status · set volume to 40 · volume up · mute
           brightness 70 · lock · restart · shut down the computer
           cancel shutdown · sleep · take a screenshot
  BROWSER  search for python tutorial · play lofi on youtube
           go to github.com · new tab · close tab · go back
  NETWORK  what is my ip · wifi off · show wifi networks · ping google.com
  KEYS     press ctrl shift esc · type hello world · scroll down · next track
  VISION   what's on my screen · analyze the screen
  AI       anything else → Ollama (e.g. "explain recursion")
  MISC     what time is it · clear history · goodbye
=====================================================
