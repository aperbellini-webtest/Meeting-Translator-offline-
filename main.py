import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import queue
import time
import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
import argostranslate.translate
from collections import deque
import os
from datetime import datetime
import logging

# -------------------------- LOGGING (silence Argos/Stanza warnings) --------------------------
logging.getLogger("stanza").setLevel(logging.ERROR)
logging.getLogger("argostranslate").setLevel(logging.ERROR)

# -------------------------- CONFIGURATION --------------------------
SAMPLE_RATE = 16000
BUFFER_DURATION = 5.0
ENERGY_THRESHOLD = 0.008
MIN_BUFFER_SECONDS = 1.5

LANGUAGES = {
    "German": "de",
    "English": "en",
    "Italian": "it"
}
FLAGS = {"de": "🇩🇪", "en": "🇬🇧", "it": "🇮🇹"}
WHISPER_MODELS = ["tiny", "base", "small"]  # medium removed: too slow for real-time


class TranslatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Meeting Translator (offline)")
        self.root.geometry("950x750")
        self.root.configure(bg='black')

        self._buffer_lock = threading.Lock()
        self.audio_buffer = deque(maxlen=int(BUFFER_DURATION * SAMPLE_RATE * 2))
        self.last_chunk_time = time.time()
        self.buffer_processed = False

        self.device_id = None
        self.stream = None
        self.running = True
        self.is_listening = False
        self.speech_started = False
        self.whisper_model = None
        self.whisper_loading = False

        self.audio_queue = queue.Queue()
        self.result_queue = queue.Queue()

        self.source_language = tk.StringVar(value="German")
        self.target_language = tk.StringVar(value="Italian")
        self.whisper_model_name = tk.StringVar(value="small")

        self._setup_gui()
        self._start_stream()
        self._start_worker_thread()
        self.root.after(100, self._poll_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Load Whisper in background without blocking the GUI
        self._load_whisper_async("small")

    # --------------------- WHISPER LOADING ---------------------
    def _load_whisper_async(self, model_name):
        self.whisper_loading = True
        self.btn_start.config(state="disabled")
        self.status_label.config(
            text=f"⏳ Loading Whisper model '{model_name}'...", fg="yellow"
        )

        def _load():
            try:
                # faster-whisper: uses ctranslate2, no PyTorch
                model = WhisperModel(model_name, device="cpu", compute_type="int8")
                self.whisper_model = model
                self.root.after(0, self._on_whisper_loaded, model_name)
            except Exception as e:
                self.root.after(0, self._on_whisper_error, str(e))

        threading.Thread(target=_load, daemon=True).start()

    def _on_whisper_loaded(self, model_name):
        self.whisper_loading = False
        print(f"✅ Whisper model '{model_name}' loaded (faster-whisper)")
        self._check_argos_models()
        self.btn_start.config(state="normal")
        self.status_label.config(text="⏸️ Ready. Press Start.", fg="gray")

    def _on_whisper_error(self, error):
        self.whisper_loading = False
        print(f"❌ Error loading Whisper: {error}")
        self.status_label.config(text=f"❌ Model error: {error[:50]}", fg="red")

    def _on_model_change(self, event=None):
        name = self.whisper_model_name.get()
        if self.is_listening:
            self._stop()
        self.whisper_model = None
        self._load_whisper_async(name)

    def _check_argos_models(self):
        installed = argostranslate.translate.get_installed_languages()
        codes = [l.code for l in installed]
        print(f"✅ Argos languages installed: {codes}")
        for src, tgt in [("de", "en"), ("en", "it"), ("en", "de"), ("it", "en")]:
            if src in codes and tgt in codes:
                print(f"   ✓ {src} → {tgt} available")

    # --------------------- GUI ---------------------
    def _setup_gui(self):
        top_frame = tk.Frame(self.root, bg='black')
        top_frame.pack(pady=10, fill="x", padx=10)

        # Row 1: Source, Target, Model
        row1 = tk.Frame(top_frame, bg='black')
        row1.pack(fill="x", pady=2)

        tk.Label(row1, text="Source:", font=("Helvetica", 11, "bold"),
                 bg='black', fg='white').pack(side="left", padx=5)

        self.combo_source = ttk.Combobox(row1, textvariable=self.source_language,
                     values=list(LANGUAGES.keys()), state="readonly", width=12)
        self.combo_source.pack(side="left", padx=5)
        self.combo_source.bind("<<ComboboxSelected>>", self._on_source_change)

        tk.Label(row1, text="→ Target:", font=("Helvetica", 11, "bold"),
                 bg='black', fg='white').pack(side="left", padx=10)

        self.combo_target = ttk.Combobox(row1, textvariable=self.target_language,
                     state="readonly", width=12)
        self.combo_target.pack(side="left", padx=5)
        self._update_target_combo()

        tk.Label(row1, text="| Model:", font=("Helvetica", 11, "bold"),
                 bg='black', fg='white').pack(side="left", padx=10)

        self.combo_model = ttk.Combobox(row1, textvariable=self.whisper_model_name,
                     values=WHISPER_MODELS, state="readonly", width=8)
        self.combo_model.pack(side="left", padx=5)
        self.combo_model.bind("<<ComboboxSelected>>", self._on_model_change)

        # Row 2: Device
        row2 = tk.Frame(top_frame, bg='black')
        row2.pack(fill="x", pady=2)

        tk.Label(row2, text="Device:", font=("Helvetica", 11, "bold"),
                 bg='black', fg='white').pack(side="left", padx=5)

        device_list = ["🎤 Microphone"]
        for dev in sd.query_devices():
            if dev['max_input_channels'] > 0:
                device_list.append(dev['name'])

        self.device_combobox = ttk.Combobox(row2, values=device_list, width=30)
        self.device_combobox.set("🎤 Microphone")
        self.device_combobox.pack(side="left", padx=5)
        self.device_combobox.bind("<<ComboboxSelected>>", self._on_device_change)

        # Row 3: Buttons
        row3 = tk.Frame(top_frame, bg='black')
        row3.pack(fill="x", pady=8)

        self.btn_start = tk.Button(row3, text="▶️ Start", command=self._start,
                                    bg="lightgreen", width=10, state="disabled")
        self.btn_start.pack(side="left", padx=5)

        self.btn_stop = tk.Button(row3, text="⏹️ Stop", command=self._stop,
                                   bg="lightcoral", width=10, state="disabled")
        self.btn_stop.pack(side="left", padx=5)

        tk.Button(row3, text="💾 Export", command=self._export_history,
                  width=12).pack(side="left", padx=5)

        tk.Button(row3, text="🗑️ Clear", command=self._clear_history_with_confirm,
                  width=10).pack(side="left", padx=5)

        self.processing_label = tk.Label(row3, text="", font=("Helvetica", 10),
                                          bg='black', fg='cyan')
        self.processing_label.pack(side="left", padx=15)

        # History
        tk.Label(self.root, text="📜 CONVERSATION HISTORY",
                 font=("Helvetica", 14, "bold"), bg='black', fg='white').pack(pady=5)

        self.history = scrolledtext.ScrolledText(self.root, wrap=tk.WORD,
                                                  font=("Helvetica", 13), height=25,
                                                  bg='black', fg='white',
                                                  insertbackground='white')
        self.history.pack(fill="both", padx=10, pady=5, expand=True)
        self.history.tag_config("source", foreground="white",
                                font=("Helvetica", 13, "bold"))
        self.history.tag_config("target", foreground="white")
        self.history.tag_config("error", foreground="orange")
        self.history.tag_config("separator", foreground="gray")
        self.history.config(state='disabled')

        self.status_label = tk.Label(self.root, text="⏳ Initializing...",
                                      font=("Helvetica", 10), bg='black', fg="yellow")
        self.status_label.pack(pady=5)

    # --------------------- LANGUAGE ---------------------
    def _on_source_change(self, event=None):
        self._update_target_combo()

    def _update_target_combo(self):
        source = self.source_language.get()
        options = [l for l in LANGUAGES.keys() if l != source]
        self.combo_target.config(values=options)
        if self.target_language.get() == source or self.target_language.get() not in options:
            self.target_language.set(options[0])

    # --------------------- ACTIONS ---------------------
    def _start(self):
        if self.whisper_model is None:
            return
        print("▶️ Listening started")
        self.is_listening = True
        self.speech_started = False
        with self._buffer_lock:
            self.buffer_processed = False
            self.audio_buffer.clear()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.status_label.config(text="🔴 Listening...", fg="red")
        self.last_chunk_time = time.time()

    def _stop(self):
        print("⏹️ Listening stopped")
        self.is_listening = False
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.status_label.config(text="⏸️ Paused", fg="gray")
        with self._buffer_lock:
            if len(self.audio_buffer) > 0 and not self.buffer_processed:
                self._process_buffer_locked()
            self.audio_buffer.clear()

    def _on_device_change(self, event):
        selected = self.device_combobox.get()
        if selected == "🎤 Microphone":
            self.device_id = None
        else:
            for dev in sd.query_devices():
                if dev['name'] == selected:
                    self.device_id = dev['index']
                    break
        print(f"🔁 Device: {selected} (ID: {self.device_id})")
        self._start_stream()

    def _clear_history(self):
        self.history.config(state='normal')
        self.history.delete('1.0', tk.END)
        self.history.config(state='disabled')
        print("🗑️ History cleared")

    def _clear_history_with_confirm(self):
        content = self.history.get('1.0', tk.END).strip()
        if not content:
            return
        if messagebox.askyesno("Confirm", "Clear the entire history?"):
            self._clear_history()

    # --------------------- AUDIO STREAM ---------------------
    def _start_stream(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype='float32',
            callback=self._audio_callback,
            blocksize=480,
            device=self.device_id
        )
        self.stream.start()
        print("🎙️ Audio stream started")

    def _audio_callback(self, indata, frames, time_info, status):
        if not self.is_listening:
            return

        energy = np.sqrt(np.mean(indata**2))

        with self._buffer_lock:
            if energy > ENERGY_THRESHOLD:
                indata_int16 = (indata * 32768).astype(np.int16)
                self.audio_buffer.extend(indata_int16.tobytes())
                self.last_chunk_time = time.time()
                self.speech_started = True
                self.buffer_processed = False
            else:
                if (self.speech_started
                        and not self.buffer_processed
                        and len(self.audio_buffer) > 0
                        and time.time() - self.last_chunk_time >= 0.5):
                    self._process_buffer_locked()

            if (not self.buffer_processed
                    and len(self.audio_buffer) >= self.audio_buffer.maxlen * 0.95):
                self._process_buffer_locked()

    def _process_buffer_locked(self):
        """Must be called with _buffer_lock already acquired."""
        if self.buffer_processed:
            return
        min_bytes = int(MIN_BUFFER_SECONDS * SAMPLE_RATE * 2)
        if len(self.audio_buffer) < min_bytes:
            return

        self.buffer_processed = True
        audio_bytes = bytes(self.audio_buffer)
        self.audio_buffer.clear()
        self.last_chunk_time = time.time()
        print(f"📤 Buffer sent ({len(audio_bytes)} bytes)")

        lang_src = LANGUAGES[self.source_language.get()]
        lang_tgt = LANGUAGES[self.target_language.get()]
        self.audio_queue.put((audio_bytes, lang_src, lang_tgt))

    # --------------------- WORKER ---------------------
    def _start_worker_thread(self):
        def worker():
            while self.running:
                try:
                    audio_bytes, lang_src, lang_tgt = self.audio_queue.get(timeout=0.5)

                    if self.whisper_model is None:
                        print("⚠️ Model not loaded yet, discarding chunk")
                        continue

                    self.root.after(0, self._set_processing, True)

                    audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

                    print("🔄 Transcribing...")
                    # faster-whisper: returns an iterator of segments
                    segments, info = self.whisper_model.transcribe(
                        audio_np, language=lang_src, beam_size=1
                    )
                    source_text = " ".join([seg.text for seg in segments]).strip()

                    if not source_text:
                        print("   (no text recognized)")
                        self.root.after(0, self._set_processing, False)
                        continue

                    print(f"📝 {lang_src.upper()}: {source_text}")

                    translation = None
                    try:
                        translation = argostranslate.translate.translate(
                            source_text, lang_src, lang_tgt
                        )
                    except Exception as e:
                        print(f"⚠️ Argos translation error: {e}")

                    self.result_queue.put((lang_src, source_text, lang_tgt, translation))
                    self.root.after(0, self._set_processing, False)

                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"❌ Worker error: {e}")
                    import traceback
                    traceback.print_exc()
                    self.root.after(0, self._set_processing, False)

        threading.Thread(target=worker, daemon=True).start()

    def _set_processing(self, active):
        if active:
            self.processing_label.config(text="⚙️ Processing...")
        else:
            self.processing_label.config(text="")

    # --------------------- GUI POLL ---------------------
    def _poll_queue(self):
        try:
            while True:
                lang_src, source_text, lang_tgt, translation = self.result_queue.get_nowait()

                flag_src = FLAGS.get(lang_src, "")
                flag_tgt = FLAGS.get(lang_tgt, "")

                self.history.config(state='normal')
                self.history.insert(tk.END, f"{flag_src} {source_text}\n", "source")

                if translation is None:
                    self.history.insert(tk.END, f"   {flag_tgt} ⚠️ (translation unavailable)\n", "error")
                    self.status_label.config(text="⚠️ Translation failed", fg="orange")
                else:
                    self.history.insert(tk.END, f"   {flag_tgt} {translation}\n", "target")
                    self.status_label.config(text=f"📝 {str(translation)[:40]}", fg="green")

                self.history.insert(tk.END, "-" * 70 + "\n", "separator")
                self.history.config(state='disabled')
                self.history.see(tk.END)
                self.root.update_idletasks()

        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    # --------------------- EXPORT ---------------------
    def _export_history(self):
        content = self.history.get('1.0', tk.END).strip()
        if not content:
            print("⚠️ No history to export")
            self.status_label.config(text="⚠️ No history", fg="orange")
            return

        archive_dir = os.path.expanduser("~/Documents/Traduttore_riunioni/archivio")
        try:
            os.makedirs(archive_dir, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Error", f"Cannot create archive folder:\n{e}")
            return

        timestamp = datetime.now().strftime("%d_%m_%y_%H%M")
        default_name = f"meeting_{timestamp}.txt"
        file_path = os.path.join(archive_dir, default_name)

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ Saved to: {file_path}")
            self.status_label.config(text=f"✅ Saved: {default_name}", fg="green")
            os.system(f'open "{archive_dir}"')
        except Exception as e:
            print(f"❌ Save error: {e}")
            self.status_label.config(text=f"❌ Error: {str(e)[:30]}", fg="red")
            messagebox.showerror("Save error", f"Cannot save file:\n{e}")
            return

        if messagebox.askyesno("Export complete", f"Saved: {default_name}\n\nClear the history?"):
            self._clear_history()

    # --------------------- CLOSE ---------------------
    def _on_close(self):
        self.running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = TranslatorApp(root)
    root.mainloop()
