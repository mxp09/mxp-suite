"""
Página "Transcribir": audio, video o URL -> texto con timestamps, 100 % local.

Los trabajos se procesan de uno en uno (whisper ya usa todos los núcleos) y
aparecen en la misma cola que las descargas, con id "tr-..." para que la app
sepa a quién mandar la cancelación.
"""

import os
import re
import threading
import tkinter.messagebox as messagebox
import uuid
from tkinter import filedialog

import customtkinter as ctk

from core.transcription import engine, exporters
from core.utils import validate_url
from gui.icons import icon
from gui.studio import PageHeader
from gui.theme import Colors, Fonts, Radius, Spacing
from mxp_common import transcriber

LINE_RE = re.compile(r"^\[[^\]]*\]\s?(.*)$")
FORMAT_LABELS = {"txt": "TXT", "docx": "Word (DOCX)", "pdf": "PDF", "srt": "SRT (subtítulos)",
                 "vtt": "VTT (subtítulos web)", "md": "Markdown", "html": "HTML interactivo",
                 "json": "JSON (con palabras)", "csv": "CSV (Excel)", "tsv": "TSV", "lrc": "LRC (letras)"}
MEDIA_TYPES = [("Audio y video", "*.mp3 *.wav *.m4a *.flac *.ogg *.opus *.aac *.wma *.mp4 *.mkv "
                                 "*.mov *.avi *.webm *.wmv *.m4v"), ("Todos los archivos", "*.*")]


def _menu(master, values, width, **kw):
    return ctk.CTkOptionMenu(
        master, values=values, width=width, height=32, font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
        fg_color=Colors.BG_TERTIARY, button_color=Colors.BG_TERTIARY, button_hover_color=Colors.BG_HOVER,
        dropdown_fg_color=Colors.BG_SECONDARY, dropdown_hover_color=Colors.BG_HOVER,
        dropdown_text_color=Colors.TEXT_PRIMARY, text_color=Colors.TEXT_PRIMARY,
        corner_radius=Radius.SM, **kw)


def _label(master, text):
    return ctk.CTkLabel(master, text=text, text_color=Colors.TEXT_MUTED, font=(Fonts.FAMILY, Fonts.SIZE_TINY, "bold"))


def _card(master):
    return ctk.CTkFrame(master, fg_color=Colors.BG_SECONDARY, corner_radius=Radius.MD,
                        border_width=1, border_color=Colors.BORDER)


class TranscriberPage(ctk.CTkFrame):
    def __init__(self, master, progress_panel, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.progress_panel = progress_panel
        self.jobs = []                 # [{"id", "source", ...}] pendientes
        self.cancels = {}              # id -> threading.Event
        self.worker = None
        self.transcript = None

        PageHeader(self, "Transcribir", "Audio, video o enlace a texto con timestamps. Gratis y en tu PC.").pack(
            fill="x", pady=(0, Spacing.LG))

        # ── Origen ──
        source = _card(self)
        source.pack(fill="x")
        row = ctk.CTkFrame(source, fg_color="transparent")
        row.pack(fill="x", padx=Spacing.MD, pady=Spacing.MD)
        self.source_entry = ctk.CTkEntry(row, placeholder_text="Pega un enlace o arrastra aquí un audio o video...",
                                         height=40, border_width=0, fg_color="transparent",
                                         text_color=Colors.TEXT_PRIMARY, font=(Fonts.FAMILY, Fonts.SIZE_BODY))
        self.source_entry.pack(side="left", fill="x", expand=True)
        self.source_entry.bind("<Return>", lambda e: self._enqueue())
        ctk.CTkButton(row, text="Elegir archivos", height=36, width=140, corner_radius=Radius.SM,
                      fg_color=Colors.BG_TERTIARY, hover_color=Colors.BG_HOVER, text_color=Colors.TEXT_PRIMARY,
                      image=icon("folder-open", Colors.TEXT_PRIMARY, 16),
                      command=self._pick_files).pack(side="left", padx=Spacing.SM)
        self.go_btn = ctk.CTkButton(row, text="Transcribir", height=36, width=140, corner_radius=Radius.SM,
                                    fg_color=Colors.ACCENT_PRIMARY, hover_color=Colors.BUTTON_HOVER,
                                    text_color=Colors.BUTTON_TEXT, font=(Fonts.FAMILY, Fonts.SIZE_BODY, "bold"),
                                    image=icon("file-text", Colors.BUTTON_TEXT, 16), command=self._enqueue)
        self.go_btn.pack(side="left")
        try:
            from tkinterdnd2 import DND_FILES
            for widget in (source, self.source_entry):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass

        # ── Opciones ──
        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.pack(fill="x", pady=(Spacing.MD, 0))
        for col, title in enumerate(("Modelo", "Idioma", "Nombres propios y términos (opcional)")):
            _label(opts, title).grid(row=0, column=col, sticky="w", padx=(0, Spacing.MD))
        self.model_menu = _menu(opts, ["—"], 230)
        self.model_menu.grid(row=1, column=0, sticky="w", padx=(0, Spacing.MD))
        self.lang_menu = _menu(opts, list(engine.LANGUAGES), 200)
        self.lang_menu.set("Español")
        self.lang_menu.grid(row=1, column=1, sticky="w", padx=(0, Spacing.MD))
        self.prompt_entry = ctk.CTkEntry(opts, placeholder_text="MXP, Proel, Panamá...", height=32,
                                         fg_color=Colors.BG_TERTIARY, border_width=0,
                                         text_color=Colors.TEXT_PRIMARY, corner_radius=Radius.SM)
        self.prompt_entry.grid(row=1, column=2, sticky="ew")
        opts.grid_columnconfigure(2, weight=1)

        extra = ctk.CTkFrame(self, fg_color="transparent")
        extra.pack(fill="x", pady=(Spacing.SM, 0))
        self.translate_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(extra, text="Traducir al inglés", variable=self.translate_var,
                        font=(Fonts.FAMILY, Fonts.SIZE_SMALL), text_color=Colors.TEXT_SECONDARY,
                        fg_color=Colors.ACCENT_PRIMARY, hover_color=Colors.ACCENT_GOLD,
                        checkmark_color=Colors.BUTTON_TEXT, border_color=Colors.BORDER_LIGHT).pack(side="left")
        ctk.CTkButton(extra, text="Gestionar modelos", height=28, width=150, corner_radius=Radius.SM,
                      fg_color="transparent", border_width=1, border_color=Colors.BORDER_LIGHT,
                      hover_color=Colors.BG_HOVER, text_color=Colors.TEXT_SECONDARY,
                      image=icon("settings", Colors.TEXT_SECONDARY, 14),
                      command=self._open_models).pack(side="right")
        self.notice = ctk.CTkLabel(self, text="", anchor="w", justify="left", wraplength=640,
                                   font=(Fonts.FAMILY, Fonts.SIZE_SMALL), text_color=Colors.WARNING)

        # ── Resultado (oculto hasta la primera transcripción) ──
        self.result = _card(self)
        head = ctk.CTkFrame(self.result, fg_color="transparent")
        head.pack(fill="x", padx=Spacing.MD, pady=(Spacing.MD, Spacing.SM))
        self.result_title = ctk.CTkLabel(head, text="", anchor="w", text_color=Colors.TEXT_PRIMARY,
                                         font=(Fonts.FAMILY, Fonts.SIZE_BODY, "bold"))
        self.result_title.pack(side="left")
        self.result_meta = ctk.CTkLabel(head, text="", text_color=Colors.TEXT_MUTED,
                                        font=(Fonts.FAMILY, Fonts.SIZE_TINY))
        self.result_meta.pack(side="right")

        find = ctk.CTkFrame(self.result, fg_color="transparent")
        find.pack(fill="x", padx=Spacing.MD)
        self.find_entry = ctk.CTkEntry(find, placeholder_text="Buscar", width=170, height=28,
                                       fg_color=Colors.BG_DARK, border_color=Colors.BORDER_LIGHT)
        self.find_entry.pack(side="left")
        self.replace_entry = ctk.CTkEntry(find, placeholder_text="Reemplazar por", width=170, height=28,
                                          fg_color=Colors.BG_DARK, border_color=Colors.BORDER_LIGHT)
        self.replace_entry.pack(side="left", padx=Spacing.SM)
        ctk.CTkButton(find, text="Reemplazar todo", width=130, height=28, corner_radius=Radius.SM,
                      fg_color=Colors.BG_TERTIARY, hover_color=Colors.BG_HOVER,
                      command=self._replace_all).pack(side="left")

        self.editor = ctk.CTkTextbox(self.result, height=300, wrap="word", fg_color=Colors.BG_DARK,
                                     text_color=Colors.TEXT_PRIMARY, font=(Fonts.FAMILY, Fonts.SIZE_BODY),
                                     border_width=1, border_color=Colors.BORDER, corner_radius=Radius.SM)
        self.editor.pack(fill="both", expand=True, padx=Spacing.MD, pady=(Spacing.SM, 0))
        ctk.CTkLabel(self.result, text="Puedes corregir el texto directamente; no borres los [tiempos] ni las líneas.",
                     anchor="w", text_color=Colors.TEXT_MUTED, font=(Fonts.FAMILY, Fonts.SIZE_TINY)).pack(
            fill="x", padx=Spacing.MD, pady=(2, Spacing.SM))
        self.editor.tag_config("stamp", foreground=Colors.ACCENT_YELLOW)
        self.editor.tag_config("hit", background=Colors.ACCENT_SOFT)

        export = ctk.CTkFrame(self.result, fg_color="transparent")
        export.pack(fill="x", padx=Spacing.MD, pady=(0, Spacing.SM))
        _label(export, "Formato").grid(row=0, column=0, sticky="w")
        _label(export, "Timestamps por").grid(row=0, column=1, sticky="w", padx=Spacing.SM)
        self.format_menu = _menu(export, list(FORMAT_LABELS.values()), 190, command=self._on_format)
        self.format_menu.grid(row=1, column=0, sticky="w")
        self.gran_menu = _menu(export, list(exporters.GRANULARITIES), 130)
        self.gran_menu.set("Frase")
        self.gran_menu.grid(row=1, column=1, sticky="w", padx=Spacing.SM)
        self.stamps_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(export, text="Incluir timestamps", variable=self.stamps_var,
                        font=(Fonts.FAMILY, Fonts.SIZE_SMALL), text_color=Colors.TEXT_SECONDARY,
                        fg_color=Colors.ACCENT_PRIMARY, hover_color=Colors.ACCENT_GOLD,
                        checkmark_color=Colors.BUTTON_TEXT, border_color=Colors.BORDER_LIGHT).grid(
            row=1, column=2, padx=Spacing.SM)
        buttons = ctk.CTkFrame(self.result, fg_color="transparent")
        buttons.pack(fill="x", padx=Spacing.MD, pady=(0, Spacing.MD))
        for text, icon_name, cmd, primary in (("Exportar", "device-floppy", self._export_one, True),
                                              ("Exportar todos", "file-export", self._export_all, False),
                                              ("Copiar texto", "copy", self._copy, False)):
            ctk.CTkButton(buttons, text=text, height=32, width=110 if primary else 120, corner_radius=Radius.SM,
                          fg_color=Colors.ACCENT_PRIMARY if primary else Colors.BG_TERTIARY,
                          hover_color=Colors.BUTTON_HOVER if primary else Colors.BG_HOVER,
                          text_color=Colors.BUTTON_TEXT if primary else Colors.TEXT_PRIMARY,
                          image=icon(icon_name, Colors.BUTTON_TEXT if primary else Colors.TEXT_PRIMARY, 14),
                          command=cmd).pack(side="right", padx=(Spacing.SM, 0))

        self.refresh_models()
        threading.Thread(target=self._repair_engine, daemon=True).start()

    # ── Motor y modelos ──
    def _repair_engine(self):
        """Si el motor falta (instalación vieja o dañada) se repara solo en segundo plano."""
        if transcriber.whisper_cli():
            return
        self.after(0, self._show_notice, "Instalando el motor de transcripción...")
        try:
            ok = transcriber.ensure_engine()
        except Exception as exc:
            ok = False
            self.after(0, self._show_notice, f"No se pudo instalar el motor de transcripción: {exc}")
        if ok:
            self.after(0, self.refresh_models)

    def _show_notice(self, text: str):
        if text:
            self.notice.configure(text=text)
            if self.result.winfo_ismapped():
                self.notice.pack(fill="x", pady=(Spacing.SM, 0), before=self.result)
            else:
                self.notice.pack(fill="x", pady=(Spacing.SM, 0))
        else:
            self.notice.pack_forget()

    def refresh_models(self):
        installed = transcriber.installed_models()
        labels = [self._model_label(k) for k in installed]
        self.model_menu.configure(values=labels or ["Sin modelos"])
        preferred = transcriber.DEFAULT_MODEL if transcriber.DEFAULT_MODEL in installed else (installed or [None])[-1]
        self.model_menu.set(self._model_label(preferred) if preferred else "Sin modelos")
        if not installed:
            self._show_notice("No hay ningún modelo descargado. Pulsa «Gestionar modelos» para elegir uno.")
        elif transcriber.whisper_cli():
            self._show_notice("")

    @staticmethod
    def _model_label(key):
        m = transcriber.MODELS[key]
        return f"{m[3]} ({transcriber.human_size(m[1])})"

    def _selected_model(self):
        label = self.model_menu.get()
        return next((k for k in transcriber.MODELS if self._model_label(k) == label), None)

    def _open_models(self):
        ModelsDialog(self, on_change=self.refresh_models)

    # ── Entrada ──
    def set_url(self, url: str):
        self.source_entry.delete(0, "end")
        self.source_entry.insert(0, url)

    def _on_drop(self, event):
        paths = [a or b for a, b in re.findall(r"{([^}]+)}|(\S+)", event.data)]
        self._add_jobs([p for p in paths if os.path.isfile(p)])

    def _pick_files(self):
        self._add_jobs(list(filedialog.askopenfilenames(title="Elige audios o videos", filetypes=MEDIA_TYPES)))

    def _enqueue(self):
        source = self.source_entry.get().strip().strip('"')
        if not source:
            return self._pick_files()
        if not (validate_url(source) or os.path.isfile(source)):
            self._show_notice("Eso no es un enlace válido ni un archivo que exista.")
            return
        self.source_entry.delete(0, "end")
        self._add_jobs([source])

    def _add_jobs(self, sources):
        model = self._selected_model()
        if not sources:
            return
        if not model:
            self._show_notice("Primero descarga un modelo en «Gestionar modelos».")
            return
        if not transcriber.whisper_cli():
            self._show_notice("El motor de transcripción aún se está instalando. Espera unos segundos.")
            return
        self._show_notice("")
        for source in sources:
            job = {"id": "tr-" + uuid.uuid4().hex, "source": source, "model": model,
                   "lang": engine.LANGUAGES[self.lang_menu.get()], "translate": self.translate_var.get(),
                   "prompt": self.prompt_entry.get()}
            self.jobs.append(job)
            self.cancels[job["id"]] = threading.Event()
            self.progress_panel.add_job(job["id"], "Transcribir: " + os.path.basename(source.rstrip("/\\")))
            self.progress_panel.update_progress(job["id"], status="En espera", percent=0)
        if not (self.worker and self.worker.is_alive()):
            self.worker = threading.Thread(target=self._work, daemon=True)
            self.worker.start()

    # ── Trabajo en segundo plano ──
    def _work(self):
        while self.jobs:
            job = self.jobs.pop(0)
            jid, cancel = job["id"], self.cancels.get(job["id"])
            if cancel is None or cancel.is_set():
                continue

            def progress(msg, pct, jid=jid):
                self.after(0, self.progress_panel.update_progress, jid, msg, pct)

            try:
                result = engine.transcribe(job["source"], job["model"], job["lang"], job["translate"],
                                           job["prompt"], progress, cancel)
                self.after(0, self._on_done, jid, result)
            except engine.Cancelled:
                self.after(0, self.progress_panel.remove_job, jid)
            except Exception as exc:
                self.after(0, self.progress_panel.update_progress, jid, f"Error: {exc}", 0)
            self.cancels.pop(jid, None)

    def cancel(self, job_id: str):
        """Llamado por la app desde el ✕ de la tarjeta de la cola."""
        event = self.cancels.get(job_id)
        if event:
            event.set()
        self.jobs = [j for j in self.jobs if j["id"] != job_id]
        self.progress_panel.remove_job(job_id)

    def _on_done(self, job_id, result):
        self.progress_panel.update_progress(job_id, status="¡Transcripción completada!", percent=100)
        self.after(4000, lambda: self.progress_panel.remove_job(job_id))
        from core.utils import show_windows_notification
        show_windows_notification("Transcripción lista", result.source)
        self.show_result(result)

    # ── Resultado y edición ──
    def show_result(self, t):
        self.transcript = t
        self.result_title.configure(text=t.source[:70])
        minutes = t.duration / 60
        self.result_meta.configure(text=f"{len(t.words)} palabras  ·  {minutes:.1f} min  ·  idioma: {t.language}")
        self.editor.configure(state="normal")
        self.editor.delete("1.0", "end")
        for sentence in t.sentences():
            self.editor.insert("end", f"[{exporters.ts(sentence.start, hours=False)}]", "stamp")
            self.editor.insert("end", f" {sentence.text}\n")
        if not self.result.winfo_ismapped():
            self.result.pack(fill="both", expand=True, pady=(Spacing.LG, Spacing.LG))

    def _sync_edits(self) -> bool:
        lines = [ln for ln in self.editor.get("1.0", "end").splitlines() if ln.strip()]
        texts = [(LINE_RE.match(ln) or [None, ln])[1] for ln in lines]
        if self.transcript.apply_sentence_edits(texts):
            return True
        messagebox.showwarning("Edición no aplicada",
                               "Se añadieron o borraron líneas, así que no se pueden casar con sus tiempos. "
                               "Se exporta el texto original.", parent=self)
        self.transcript.apply_sentence_edits([s.text for s in self.transcript.sentences()])
        return False

    def _replace_all(self):
        needle, repl = self.find_entry.get(), self.replace_entry.get()
        if not needle:
            return
        content = self.editor.get("1.0", "end-1c")
        count = content.count(needle)
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", content.replace(needle, repl))
        self.show_result_tags()
        self._show_notice(f"{count} reemplazo(s).")

    def show_result_tags(self):
        """Vuelve a pintar en amarillo los [tiempos] tras editar el texto en bloque."""
        for i, line in enumerate(self.editor.get("1.0", "end").splitlines(), start=1):
            match = re.match(r"^\[[^\]]*\]", line)
            if match:
                self.editor.tag_add("stamp", f"{i}.0", f"{i}.{match.end()}")

    def _current_format(self):
        label = self.format_menu.get()
        return next(k for k, v in FORMAT_LABELS.items() if v == label)

    def _on_format(self, _label):
        fmt = self._current_format()
        if fmt in exporters.DEFAULT_GRANULARITY:
            self.gran_menu.set("Subtítulo")

    def _export_one(self):
        if not self.transcript:
            return
        self._sync_edits()
        fmt = self._current_format()
        base = os.path.splitext(self.transcript.source)[0] or "transcripcion"
        path = filedialog.asksaveasfilename(title="Exportar transcripción", defaultextension="." + fmt,
                                            initialfile=re.sub(r'[<>:"/\\|?*]', "", base)[:120] + "." + fmt,
                                            filetypes=[(FORMAT_LABELS[fmt], "*." + fmt)])
        if path:
            self._run_export([(fmt, path)])

    def _export_all(self):
        if not self.transcript:
            return
        self._sync_edits()
        folder = filedialog.askdirectory(title="Carpeta donde guardar todos los formatos")
        if not folder:
            return
        base = re.sub(r'[<>:"/\\|?*]', "", os.path.splitext(self.transcript.source)[0])[:120] or "transcripcion"
        self._run_export([(fmt, os.path.join(folder, f"{base}.{fmt}")) for fmt in exporters.ALL_FORMATS])

    def _run_export(self, targets):
        gran = exporters.GRANULARITIES[self.gran_menu.get()]
        done = []
        for fmt, path in targets:
            g = gran if len(targets) == 1 else exporters.DEFAULT_GRANULARITY.get(fmt, gran)
            try:
                exporters.export(self.transcript, fmt, path, g, self.stamps_var.get())
                done.append(path)
            except Exception as exc:
                messagebox.showerror("Error al exportar", f"{os.path.basename(path)}: {exc}", parent=self)
        if done:
            self._show_notice(f"Exportado: {len(done)} archivo(s) en {os.path.dirname(done[0])}")
            os.startfile(os.path.dirname(done[0]))

    def _copy(self):
        if not self.transcript:
            return
        self._sync_edits()
        self.clipboard_clear()
        self.clipboard_append(self.transcript.text)
        self._show_notice("Texto copiado al portapapeles.")


class ModelsDialog(ctk.CTkToplevel):
    """Descargar o borrar modelos, con el peso de cada uno bien visible."""

    def __init__(self, master, on_change):
        super().__init__(master)
        self.title("Modelos de transcripción")
        self.geometry("640x640")
        self.configure(fg_color=Colors.BG_DARK)
        self.transient(master.winfo_toplevel())
        self.on_change = on_change
        self.cancel = threading.Event()
        self.protocol("WM_DELETE_WINDOW", self._close)
        ctk.CTkLabel(self, text="Modelos de transcripción", text_color=Colors.TEXT_PRIMARY,
                     font=(Fonts.FAMILY, 18, "bold")).pack(anchor="w", padx=Spacing.LG, pady=(Spacing.LG, 0))
        ctk.CTkLabel(self, text="Los marcados como pesados ocupan más de 1 GB y tardan en descargarse.",
                     text_color=Colors.TEXT_SECONDARY, font=(Fonts.FAMILY, Fonts.SIZE_SMALL)).pack(
            anchor="w", padx=Spacing.LG)
        self.list = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                           scrollbar_button_color=Colors.BG_TERTIARY)
        self.status = ctk.CTkLabel(self, text="", text_color=Colors.ACCENT_YELLOW, font=(Fonts.FAMILY, Fonts.SIZE_SMALL))
        self.status.pack(anchor="w", padx=Spacing.LG)
        self.list.pack(fill="both", expand=True, padx=Spacing.LG, pady=Spacing.MD)
        self.busy = False
        self._render()

    def _render(self):
        for w in self.list.winfo_children():
            w.destroy()
        installed = transcriber.installed_models()
        for key, (_file, size, _sha, label, desc) in transcriber.MODELS.items():
            row = _card(self.list)
            row.pack(fill="x", pady=3)
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=Spacing.MD, pady=Spacing.SM)
            heavy = "  ⚠ pesado" if size >= transcriber.HEAVY_BYTES else ""
            ctk.CTkLabel(info, text=f"{label}  ·  {transcriber.human_size(size)}{heavy}", anchor="w",
                         text_color=Colors.WARNING if heavy else Colors.TEXT_PRIMARY,
                         font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold")).pack(fill="x")
            ctk.CTkLabel(info, text=desc, anchor="w", text_color=Colors.TEXT_MUTED,
                         font=(Fonts.FAMILY, Fonts.SIZE_TINY)).pack(fill="x")
            if key in installed:
                ctk.CTkButton(row, text="Borrar", width=90, height=28, fg_color="transparent", border_width=1,
                              border_color=Colors.BORDER_LIGHT, hover_color=Colors.BG_HOVER,
                              text_color=Colors.TEXT_SECONDARY,
                              command=lambda k=key: self._delete(k)).pack(side="right", padx=Spacing.MD)
            else:
                ctk.CTkButton(row, text="Descargar", width=110, height=28, fg_color=Colors.ACCENT_PRIMARY,
                              hover_color=Colors.BUTTON_HOVER, text_color=Colors.BUTTON_TEXT,
                              command=lambda k=key: self._download(k)).pack(side="right", padx=Spacing.MD)

    def _delete(self, key):
        if messagebox.askyesno("Borrar modelo", f"¿Borrar {transcriber.MODELS[key][3]}?", parent=self):
            os.remove(transcriber.model_path(key))
            self._render()
            self.on_change()

    def _download(self, key):
        if self.busy:
            return
        size = transcriber.MODELS[key][1]
        if size >= transcriber.HEAVY_BYTES and not messagebox.askyesno(
                "Modelo pesado", f"Este modelo pesa {transcriber.human_size(size)}. Tardará según tu conexión "
                                 "y ocupará ese espacio en disco. ¿Descargarlo?", parent=self):
            return
        self.busy = True

        def work():
            try:
                ok = transcriber.download_model(
                    key, lambda m, p: self.after(0, lambda: self.status.configure(text=f"{m} ({p:.0f} %)")),
                    self.cancel)
                msg = "Modelo listo." if ok else "Descarga cancelada."
            except Exception as exc:
                msg = f"Error: {exc}"
            self.busy = False
            if not self.cancel.is_set():
                self.after(0, lambda: (self.status.configure(text=msg), self._render(), self.on_change()))

        threading.Thread(target=work, daemon=True).start()

    def _close(self):
        self.cancel.set()
        self.destroy()
