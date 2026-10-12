# 🎧 Meeting Translator (offline)

A macOS desktop app that listens to German speech and translates it in real time to Italian and English — **fully offline, zero cost, complete privacy**.

![Screenshot](screenshot.png)
*(optional: add a screenshot of the app window)*

---

## ✨ Features

- 🎙️ **Real-time listening** from microphone (in-person meetings) or system audio (Google Meet, Zoom, Teams) via BlackHole
- 🧠 **Whisper transcription** (`faster-whisper` backend — no PyTorch, much lighter)
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

---

## 🛠️ Installation

### 1. Clone the repository

```bash
cd ~/Documents
git clone https://github.com/YOUR-USERNAME/Traduttore_riunioni.git
cd Traduttore_riunioni
