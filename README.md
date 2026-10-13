# 🎧 Meeting Translator (offline)

A macOS desktop application that listens to German conversations and translates them in real time into Italian and English — **fully offline, zero cost, complete privacy**.

![Screenshot](screenshot.png)
*(optional: add a screenshot of the app window)*

---

## ✨ Features

- 🎙️ **Real-time listening** from microphone (in-person meetings) or system audio (Google Meet, Zoom, Teams) via BlackHole
- 🧠 **Whisper transcription** using `faster-whisper` (no PyTorch, ~250 MB lighter than `openai-whisper`)
- 🌍 **Offline translation with Argos Translate** — no rate limits, no internet required, full privacy
- 🔄 **3 languages supported**: Italian, English, German (with automatic pivoting through English)
- 📜 **Scrollable history** with white text on black background
- 💾 **Export history** to `.txt` file with automatic cleanup
- 🎛️ **Whisper model selection** from the GUI (tiny / base / small)
- 🖥️ **Always-on-top window**, ideal during meetings
- 🚀 **No dependency on online services**

---

## 📋 Requirements

- **macOS** 12 (Monterey) or newer — tested on MacBook Air M4, 16 GB, macOS 27
- **Python 3.11** (recommended; earlier versions may not support `faster-whisper`)
- **Working microphone**
- **Tkinter** (usually bundled with Python; on Homebrew you need `python-tk`)
- **No internet connection** required after setup

---

## 🛠️ Installation

### 1. Clone the repository

```bash
cd ~/Documents
git clone https://github.com/aperbellini-webtest/Meeting-Translator-offline-.git
cd Meeting-Translator-offline-
```

If you already have the files locally, skip this step.

### 2. Install Homebrew (if you don't have it)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 3. Install Python 3.11 and Tkinter

```bash
brew install python@3.11 python-tk@3.11
```

### 4. Create a virtual environment

```bash
python3.11 -m venv venv
source venv/bin/activate
```

### 5. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 6. Install Argos Translate models (one-time, ~400 MB)

```bash
argospm update
argospm install translate-de_en
argospm install translate-en_de
argospm install translate-en_it
argospm install translate-it_en
```

> **Note**: pivoting (e.g. DE → IT passing through EN) is handled automatically by Argos.

### 7. (Optional) Install BlackHole for virtual meetings

Only if you want to translate audio from Google Meet / Zoom / Teams:

```bash
brew install blackhole-2ch
```

Then configure the "Multi-Output" device — see [Google Meet setup](#-google-meet-setup).

---

## ▶️ Running the app

### Option 1 — From Terminal

```bash
cd ~/Documents/Traduttore_riunioni
source venv/bin/activate
python main.py
```

### Option 2 — Desktop launcher (recommended)

Create `~/Desktop/Avvia_Traduttore.command`:

```bash
nano ~/Desktop/Avvia_Traduttore.command
```

Content:

```bash
#!/bin/bash
cd ~/Documents/Traduttore_riunioni
source venv/bin/activate
python main.py
```

Save (`Ctrl+O`, `Enter`, `Ctrl+X`) and make it executable:

```bash
chmod +x ~/Desktop/Avvia_Traduttore.command
```

Now you can launch the app by **double-clicking** the `.command` file on your Desktop.

---

## 🎯 Usage

### In-person meeting

1. Launch the app (double-click the Desktop launcher).
2. In the **Audio Source** dropdown, select `🎤 Microphone` (or the specific microphone name).
3. Select **Source** and **Target** languages (e.g. German → Italian).
4. Choose the Whisper model (`small` is the default — good balance).
5. Click **▶️ Start**.
6. Translations appear automatically in the history panel.
7. Click **⏹️ Stop** to pause.
8. Click **💾 Export** to save the history to a `.txt` file.

### Google Meet / Zoom / Teams meeting

See the next section.

---

## 🎥 Google Meet setup

To translate a virtual meeting, you need to capture the **outgoing** audio of your Mac (not the microphone). On macOS this requires **BlackHole**, a free virtual audio driver.

### Step 1: Install BlackHole

```bash
brew install blackhole-2ch
```

Or download from: https://github.com/ExistentialAudio/BlackHole

Restart your Mac after installation.

### Step 2: Create a Multi-Output device

1. Open **Applications → Utilities → Audio MIDI Setup**.
2. Click the **+** at the bottom left → **Create Multi-Output Device**.
3. Check:
   - ✅ **BlackHole 2ch**
   - ✅ **Built-in Output** (or your headphones/speakers)
4. Rename it to **"Meet + BlackHole"** (double-click the name).
5. (Optional) Set this as your system audio output (right-click → "Use this device for sound output").

### Step 3: Configure Google Meet

1. Join the meeting.
2. Click the gear icon (Settings) → **Audio**.
3. Set:
   - **Microphone**: your physical microphone (e.g. "MacBook Air Microphone")
   - **Speakers**: **Meet + BlackHole** (the Multi-Output device from Step 2)

This way:
- Your colleagues hear you (physical microphone).
- The outgoing audio is duplicated: you hear it AND it goes to BlackHole.

### Step 4: Configure the translator

1. Launch `Avvia_Traduttore.command`.
2. In the **Audio Source** dropdown, select **BlackHole 2ch**.
3. Click **▶️ Start**.
4. Start the Google Meet meeting.
5. Translations appear in real time.

### Audio flow diagram

```
Google Meet (speakers → Multi-Output)
    ├──→ Built-in Output (you hear)
    └──→ BlackHole 2ch
              └──→ Meeting Translator (input)
                        └──→ Whisper → Argos → GUI
```

### ⚠️ Important notes for Google Meet

- **Do not select "Multi-Output" as microphone in Meet**: otherwise others would hear an echo (their own audio sent back).
- **Volume**: if audio is too low, increase system volume. `ENERGY_THRESHOLD = 0.008` is already very sensitive.
- **Latency**: Whisper `small` takes 1-3 seconds to transcribe. For faster response use `base` model (change `whisper_model_name` default from `"small"` to `"base"`).
- **Privacy**: after export, history is cleared from the GUI. Data is not stored anywhere else.

---

## 🎛️ Customization

In `main.py` you can tweak:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `SAMPLE_RATE` | `16000` | Sampling rate (Whisper requires 16 kHz) |
| `BUFFER_DURATION` | `5.0` | Max seconds of audio before forcing a translation |
| `ENERGY_THRESHOLD` | `0.008` | Voice detection threshold. Increase if too much noise is captured |
| `MIN_BUFFER_SECONDS` | `1.5` | Minimum audio duration to trigger a translation |
| `WHISPER_MODELS` | `["tiny", "base", "small"]` | Models available in the dropdown |
| `LANGUAGES` | `{"German": "de", "English": "en", "Italian": "it"}` | Languages supported by the UI |

### Whisper models

| Model | Accuracy | Speed | RAM | Notes |
|-------|----------|-------|-----|-------|
| `tiny` | Low | Very fast | ~500 MB | For testing only |
| `base` | Medium | Fast | ~1 GB | Good for podcasts |
| `small` | High | Good | ~2 GB | **Recommended** |
| `medium` | Very high | Slow | ~5 GB | Not real-time |

---

## 📁 Project structure

```
Meeting-Translator-offline-/
├── main.py                  # Main application code
├── README.md                # This file
├── README.it.md             # (Optional) Italian version
├── requirements.txt         # Python dependencies
├── .gitignore               # Files ignored by Git
├── LICENSE                  # MIT License
├── venv/                    # Virtual environment (NOT tracked)
├── archivio/                # Exported .txt files (NOT tracked)
└── screenshot.png           # Screenshot (optional)
```

---

## 🐛 Troubleshooting

### ❌ `ModuleNotFoundError: No module named '_tkinter'`

```bash
brew install python-tk@3.11
rm -rf venv
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### ❌ `ModuleNotFoundError: No module named 'torch'`

`torch` is required by Argos (via Stanza). Reinstall:

```bash
pip install torch
```

### ❌ `Server Error: You made too many requests`

You shouldn't see this anymore (we use Argos, not Google). If you do, you're running an old version with `deep-translator`.

### ❌ The microphone doesn't work

- **System Settings → Privacy & Security → Microphone** → enable **Terminal**.
- Try selecting the microphone manually from the dropdown.

### ❌ No translation during a virtual meeting

- In Google Meet, verify speakers are set to "Meet + BlackHole".
- In the translator, select **BlackHole 2ch** as audio source.

### ❌ Crash when launching a PyInstaller-built `.app`

Don't compile with PyInstaller: `torch` doesn't package easily. **Use the `.command` launcher** or **Platypus** to create a lightweight `.app` (1 MB).

### ❌ The app is slow

- Use `base` instead of `small` from the model dropdown.
- Close other heavy apps.
- Check the Mac isn't in low-power mode.

### ❌ The app doesn't launch from Desktop

- Right-click the `.command` file → **Open** (bypasses Gatekeeper the first time).
- Verify permissions: `chmod +x ~/Desktop/Avvia_Traduttore.command`.

---

## 📊 Known limitations

- **No speaker diarization** (identifying who is speaking): technically complex, requires heavy models.
- **`medium` model not included** in the dropdown: too slow for real-time on M4 Air.
- **macOS only**: uses `os.system("open ...")` and BlackHole, both macOS-specific.
- **Only 3 languages**: Italian, English, German. To add more, edit the `LANGUAGES` dictionary and install the corresponding Argos models.
- **PyInstaller builds don't work**: `torch` cannot be packaged easily. Use the `.command` launcher instead.

---

## 🗺️ Roadmap (future ideas)

- [ ] Add French and Spanish
- [ ] Auto-save every N minutes
- [ ] Export to `.srt` format (with timestamps)
- [ ] Custom icon for the launcher
- [ ] Windows/Linux support
- [ ] Speaker diarization (advanced)

---

## 🤝 Contributing

Pull requests welcome. For major changes, please open an issue first to discuss what you'd like to change.

---

## 📜 License

MIT — see the [LICENSE](LICENSE) file for details.

---

## 🙏 Credits

- [OpenAI Whisper](https://github.com/openai/whisper) — transcription model
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — optimized PyTorch-free implementation
- [Argos Translate](https://github.com/argosopentech/argos-translate) — offline translation
- [SoundDevice](https://github.com/spatialaudio/python-sounddevice) — audio capture
- [BlackHole](https://github.com/ExistentialAudio/BlackHole) — audio loopback on macOS

---

## 📋 Quick reference

| Task | How |
|------|-----|
| **Quick launch** | Double-click `Avvia_Traduttore.command` on Desktop |
| **Microphone** | Select `🎤 Microphone` in the app |
| **Google Meet** | Install BlackHole → create Multi-Output → select `BlackHole 2ch` in the app |
| **Export** | Click **💾 Export** → saves `.txt` → history cleared automatically |

---

*Built to translate German meetings in real time — offline, free, private.* 🇩🇪 → 🇮🇹 🇬🇧