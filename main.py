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

# -------------------------- LOGGING (silenzia warning Argos/Stanza) --------------------------
logging.getLogger("stanza").setLevel(logging.ERROR)
logging.getLogger("argostranslate").setLevel(logging.ERROR)

# -------------------------- CONFIGURAZIONE --------------------------
SAMPLE_RATE = 16000
BUFFER_DURATION = 5.0
ENERGY_THRESHOLD = 0.008
MIN_BUFFER_SECONDS = 1.5

LINGUE = {
    "Tedesco": "de",
    "Inglese": "en",
    "Italiano": "it"
}
BANDIERE = {"de": "🇩🇪", "en": "🇬🇧", "it": "🇮🇹"}
MODELLI_WHISPER = ["tiny", "base", "small"]  # medium rimosso: troppo lento per real-time


class TraduttoreApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Traduttore Riunioni (offline)")
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

        self.lingua_sorgente = tk.StringVar(value="Tedesco")
        self.lingua_target = tk.StringVar(value="Italiano")
        self.modello_whisper = tk.StringVar(value="small")

        self._setup_gui()
        self._start_stream()
        self._start_worker_thread()
        self.root.after(100, self._poll_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Carica Whisper in background senza bloccare la GUI
        self._carica_whisper_async("small")

    # --------------------- CARICAMENTO WHISPER ---------------------
    def _carica_whisper_async(self, nome_modello):
        self.whisper_loading = True
        self.btn_start.config(state="disabled")
        self.status_label.config(
            text=f"⏳ Caricamento modello Whisper '{nome_modello}'...", fg="yellow"
        )

        def _load():
            try:
                # faster-whisper: usa ctranslate2, no PyTorch
                modello = WhisperModel(nome_modello, device="cpu", compute_type="int8")
                self.whisper_model = modello
                self.root.after(0, self._on_whisper_loaded, nome_modello)
            except Exception as e:
                self.root.after(0, self._on_whisper_error, str(e))

        threading.Thread(target=_load, daemon=True).start()

    def _on_whisper_loaded(self, nome_modello):
        self.whisper_loading = False
        print(f"✅ Modello Whisper '{nome_modello}' caricato (faster-whisper)")
        self._verifica_modelli_argos()
        self.btn_start.config(state="normal")
        self.status_label.config(text="⏸️ Pronto. Premi Avvia.", fg="gray")

    def _on_whisper_error(self, errore):
        self.whisper_loading = False
        print(f"❌ Errore caricamento Whisper: {errore}")
        self.status_label.config(text=f"❌ Errore modello: {errore[:50]}", fg="red")

    def _on_modello_change(self, event=None):
        nome = self.modello_whisper.get()
        if self.is_listening:
            self._stop()
        self.whisper_model = None
        self._carica_whisper_async(nome)

    def _verifica_modelli_argos(self):
        lingue_installate = argostranslate.translate.get_installed_languages()
        codici = [l.code for l in lingue_installate]
        print(f"✅ Lingue Argos installate: {codici}")
        for src, tgt in [("de", "en"), ("en", "it"), ("en", "de"), ("it", "en")]:
            if src in codici and tgt in codici:
                print(f"   ✓ {src} → {tgt} disponibile")

    # --------------------- GUI ---------------------
    def _setup_gui(self):
        top_frame = tk.Frame(self.root, bg='black')
        top_frame.pack(pady=10, fill="x", padx=10)

        # Riga 1: Sorgente, Target, Modello
        row1 = tk.Frame(top_frame, bg='black')
        row1.pack(fill="x", pady=2)

        tk.Label(row1, text="Sorgente:", font=("Helvetica", 11, "bold"),
                 bg='black', fg='white').pack(side="left", padx=5)

        self.combo_sorgente = ttk.Combobox(row1, textvariable=self.lingua_sorgente,
                     values=list(LINGUE.keys()), state="readonly", width=12)
        self.combo_sorgente.pack(side="left", padx=5)
        self.combo_sorgente.bind("<<ComboboxSelected>>", self._on_lingua_sorgente_change)

        tk.Label(row1, text="→ Target:", font=("Helvetica", 11, "bold"),
                 bg='black', fg='white').pack(side="left", padx=10)

        self.combo_target = ttk.Combobox(row1, textvariable=self.lingua_target,
                     state="readonly", width=12)
        self.combo_target.pack(side="left", padx=5)
        self._aggiorna_combo_target()

        tk.Label(row1, text="| Modello:", font=("Helvetica", 11, "bold"),
                 bg='black', fg='white').pack(side="left", padx=10)

        self.combo_modello = ttk.Combobox(row1, textvariable=self.modello_whisper,
                     values=MODELLI_WHISPER, state="readonly", width=8)
        self.combo_modello.pack(side="left", padx=5)
        self.combo_modello.bind("<<ComboboxSelected>>", self._on_modello_change)

        # Riga 2: Dispositivo
        row2 = tk.Frame(top_frame, bg='black')
        row2.pack(fill="x", pady=2)

        tk.Label(row2, text="Dispositivo:", font=("Helvetica", 11, "bold"),
                 bg='black', fg='white').pack(side="left", padx=5)

        device_list = ["🎤 Microfono"]
        for dev in sd.query_devices():
            if dev['max_input_channels'] > 0:
                device_list.append(dev['name'])

        self.device_combobox = ttk.Combobox(row2, values=device_list, width=30)
        self.device_combobox.set("🎤 Microfono")
        self.device_combobox.pack(side="left", padx=5)
        self.device_combobox.bind("<<ComboboxSelected>>", self._on_device_change)

        # Riga 3: Pulsanti
        row3 = tk.Frame(top_frame, bg='black')
        row3.pack(fill="x", pady=8)

        self.btn_start = tk.Button(row3, text="▶️ Avvia", command=self._start,
                                    bg="lightgreen", width=10, state="disabled")
        self.btn_start.pack(side="left", padx=5)

        self.btn_stop = tk.Button(row3, text="⏹️ Ferma", command=self._stop,
                                   bg="lightcoral", width=10, state="disabled")
        self.btn_stop.pack(side="left", padx=5)

        tk.Button(row3, text="💾 Esporta", command=self._export_history,
                  width=12).pack(side="left", padx=5)

        tk.Button(row3, text="🗑️ Pulisci", command=self._clear_history_con_conferma,
                  width=10).pack(side="left", padx=5)

        self.elaborazione_label = tk.Label(row3, text="", font=("Helvetica", 10),
                                            bg='black', fg='cyan')
        self.elaborazione_label.pack(side="left", padx=15)

        # Cronologia
        tk.Label(self.root, text="📜 CRONOLOGIA CONVERSAZIONE",
                 font=("Helvetica", 14, "bold"), bg='black', fg='white').pack(pady=5)

        self.history = scrolledtext.ScrolledText(self.root, wrap=tk.WORD,
                                                  font=("Helvetica", 13), height=25,
                                                  bg='black', fg='white',
                                                  insertbackground='white')
        self.history.pack(fill="both", padx=10, pady=5, expand=True)
        self.history.tag_config("sorgente", foreground="white",
                                font=("Helvetica", 13, "bold"))
        self.history.tag_config("target", foreground="white")
        self.history.tag_config("errore", foreground="orange")
        self.history.tag_config("separatore", foreground="gray")
        self.history.config(state='disabled')

        self.status_label = tk.Label(self.root, text="⏳ Inizializzazione...",
                                      font=("Helvetica", 10), bg='black', fg="yellow")
        self.status_label.pack(pady=5)

    # --------------------- LINGUA ---------------------
    def _on_lingua_sorgente_change(self, event=None):
        self._aggiorna_combo_target()

    def _aggiorna_combo_target(self):
        sorgente = self.lingua_sorgente.get()
        opzioni = [l for l in LINGUE.keys() if l != sorgente]
        self.combo_target.config(values=opzioni)
        if self.lingua_target.get() == sorgente or self.lingua_target.get() not in opzioni:
            self.lingua_target.set(opzioni[0])

    # --------------------- AZIONI ---------------------
    def _start(self):
        if self.whisper_model is None:
            return
        print("▶️ Ascolto avviato")
        self.is_listening = True
        self.speech_started = False
        with self._buffer_lock:
            self.buffer_processed = False
            self.audio_buffer.clear()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.status_label.config(text="🔴 Ascolto attivo...", fg="red")
        self.last_chunk_time = time.time()

    def _stop(self):
        print("⏹️ Ascolto fermato")
        self.is_listening = False
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.status_label.config(text="⏸️ In pausa", fg="gray")
        with self._buffer_lock:
            if len(self.audio_buffer) > 0 and not self.buffer_processed:
                self._process_buffer_locked()
            self.audio_buffer.clear()

    def _on_device_change(self, event):
        selected = self.device_combobox.get()
        if selected == "🎤 Microfono":
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
        print("🗑️ Cronologia pulita")

    def _clear_history_con_conferma(self):
        content = self.history.get('1.0', tk.END).strip()
        if not content:
            return
        if messagebox.askyesno("Conferma", "Vuoi cancellare tutta la cronologia?"):
            self._clear_history()

    # --------------------- STREAM AUDIO ---------------------
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
        print("🎙️ Stream audio avviato")

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
        """Deve essere chiamata con _buffer_lock già acquisito."""
        if self.buffer_processed:
            return
        min_bytes = int(MIN_BUFFER_SECONDS * SAMPLE_RATE * 2)
        if len(self.audio_buffer) < min_bytes:
            return

        self.buffer_processed = True
        audio_bytes = bytes(self.audio_buffer)
        self.audio_buffer.clear()
        self.last_chunk_time = time.time()
        print(f"📤 Buffer inviato ({len(audio_bytes)} bytes)")

        lingua_src = LINGUE[self.lingua_sorgente.get()]
        lingua_tgt = LINGUE[self.lingua_target.get()]
        self.audio_queue.put((audio_bytes, lingua_src, lingua_tgt))

    # --------------------- WORKER ---------------------
    def _start_worker_thread(self):
        def worker():
            while self.running:
                try:
                    audio_bytes, lingua_src, lingua_tgt = self.audio_queue.get(timeout=0.5)

                    if self.whisper_model is None:
                        print("⚠️ Modello non ancora caricato, chunk scartato")
                        continue

                    self.root.after(0, self._set_elaborazione, True)

                    audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

                    print("🔄 Trascrizione in corso...")
                    # faster-whisper: restituisce un iteratore di segmenti
                    segments, info = self.whisper_model.transcribe(
                        audio_np, language=lingua_src, beam_size=1
                    )
                    testo_sorgente = " ".join([seg.text for seg in segments]).strip()

                    if not testo_sorgente:
                        print("   (nessun testo riconosciuto)")
                        self.root.after(0, self._set_elaborazione, False)
                        continue

                    print(f"📝 {lingua_src.upper()}: {testo_sorgente}")

                    traduzione = None
                    try:
                        traduzione = argostranslate.translate.translate(
                            testo_sorgente, lingua_src, lingua_tgt
                        )
                    except Exception as e:
                        print(f"⚠️ Errore traduzione Argos: {e}")

                    self.result_queue.put((lingua_src, testo_sorgente, lingua_tgt, traduzione))
                    self.root.after(0, self._set_elaborazione, False)

                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"❌ Worker error: {e}")
                    import traceback
                    traceback.print_exc()
                    self.root.after(0, self._set_elaborazione, False)

        threading.Thread(target=worker, daemon=True).start()

    def _set_elaborazione(self, attiva):
        if attiva:
            self.elaborazione_label.config(text="⚙️ Elaborazione...")
        else:
            self.elaborazione_label.config(text="")

    # --------------------- POLL GUI ---------------------
    def _poll_queue(self):
        try:
            while True:
                lingua_src, testo_sorgente, lingua_tgt, traduzione = self.result_queue.get_nowait()

                bandiera_src = BANDIERE.get(lingua_src, "")
                bandiera_tgt = BANDIERE.get(lingua_tgt, "")

                self.history.config(state='normal')
                self.history.insert(tk.END, f"{bandiera_src} {testo_sorgente}\n", "sorgente")

                if traduzione is None:
                    self.history.insert(tk.END, f"   {bandiera_tgt} ⚠️ (traduzione non disponibile)\n", "errore")
                    self.status_label.config(text="⚠️ Traduzione fallita", fg="orange")
                else:
                    self.history.insert(tk.END, f"   {bandiera_tgt} {traduzione}\n", "target")
                    self.status_label.config(text=f"📝 {str(traduzione)[:40]}", fg="green")

                self.history.insert(tk.END, "-" * 70 + "\n", "separatore")
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
            print("⚠️ Nessuna cronologia")
            self.status_label.config(text="⚠️ Nessuna cronologia", fg="orange")
            return

        archivio_dir = os.path.expanduser("~/Documents/Traduttore_riunioni/archivio")
        try:
            os.makedirs(archivio_dir, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile creare la cartella archivio:\n{e}")
            return

        timestamp = datetime.now().strftime("%d_%m_%y_%H%M")
        default_name = f"riunione_{timestamp}.txt"
        file_path = os.path.join(archivio_dir, default_name)

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ Salvato in: {file_path}")
            self.status_label.config(text=f"✅ Salvato: {default_name}", fg="green")
            os.system(f'open "{archivio_dir}"')
        except Exception as e:
            print(f"❌ Errore salvataggio: {e}")
            self.status_label.config(text=f"❌ Errore: {str(e)[:30]}", fg="red")
            messagebox.showerror("Errore salvataggio", f"Impossibile salvare il file:\n{e}")
            return

        if messagebox.askyesno("Export completato", f"Salvato: {default_name}\n\nVuoi cancellare la cronologia?"):
            self._clear_history()

    # --------------------- CHIUSURA ---------------------
    def _on_close(self):
        self.running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = TraduttoreApp(root)
    root.mainloop()