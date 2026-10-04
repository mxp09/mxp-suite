"""
Exportación de una transcripción a todos los formatos habituales.

Cada exportador recibe la lista de tramos ya segmentados (párrafo, frase,
palabra o subtítulo), así que la granularidad de los timestamps la decide el
usuario y es la misma lógica para todos los formatos.
"""

import csv
import html
import io
import json
import os
from typing import Callable, Dict, List

from core.transcription.model import Span, Transcript, split_lines

GRANULARITIES = {"Párrafo": "paragraph", "Frase": "sentence", "Palabra": "word", "Subtítulo": "subtitle"}


def ts(seconds: float, sep: str = ",", hours: bool = True) -> str:
    """Segundos -> 00:01:02,345 (SRT) / 00:01:02.345 (VTT) / 01:02 (lectura)."""
    ms = int(round(max(0.0, seconds) * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    if not hours:  # lectura: con décimas, que por palabra el segundo entero no basta
        return (f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}") + f".{ms // 100}"
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _label(span: Span, speakers: bool) -> str:
    return f"{span.speaker}: " if speakers and span.speaker else ""


def to_txt(t: Transcript, spans: List[Span], stamps: bool, speakers: bool) -> str:
    if not stamps:
        return "\n\n".join(_label(p, speakers) + p.text for p in t.paragraphs()) + "\n"
    return "\n".join(f"[{ts(s.start, hours=False)}] {_label(s, speakers)}{s.text}" for s in spans) + "\n"


def to_md(t: Transcript, spans: List[Span], stamps: bool, speakers: bool) -> str:
    lines = [f"# {t.source or 'Transcripción'}", ""]
    for s in (spans if stamps else t.paragraphs()):
        prefix = f"**[{ts(s.start, hours=False)}]** " if stamps else ""
        who = f"**{s.speaker}:** " if speakers and s.speaker else ""
        lines += [prefix + who + s.text, ""]
    return "\n".join(lines)


def to_srt(t: Transcript, spans: List[Span], stamps: bool, speakers: bool) -> str:
    blocks = [f"{i}\n{ts(s.start)} --> {ts(max(s.end, s.start + 0.3))}\n{split_lines(_label(s, speakers) + s.text)}"
              for i, s in enumerate(spans, 1)]
    return "\n\n".join(blocks) + "\n"


def to_vtt(t: Transcript, spans: List[Span], stamps: bool, speakers: bool) -> str:
    blocks = [f"{ts(s.start, '.')} --> {ts(max(s.end, s.start + 0.3), '.')}\n"
              + (f"<v {s.speaker}>" if speakers and s.speaker else "") + split_lines(s.text)
              for s in spans]
    return "WEBVTT\n\n" + "\n\n".join(blocks) + "\n"


def to_lrc(t: Transcript, spans: List[Span], stamps: bool, speakers: bool) -> str:
    def lrc_ts(sec):
        m, s = divmod(max(0.0, sec), 60)
        return f"[{int(m):02d}:{s:05.2f}]"
    return "\n".join(lrc_ts(s.start) + _label(s, speakers) + s.text for s in spans) + "\n"


def _table(t: Transcript, spans: List[Span], delimiter: str) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")
    writer.writerow(["inicio", "fin", "inicio_s", "fin_s", "hablante", "texto"])
    for s in spans:
        writer.writerow([ts(s.start), ts(s.end), f"{s.start:.3f}", f"{s.end:.3f}", s.speaker or "", s.text])
    return buffer.getvalue()


def to_csv(t, spans, stamps, speakers):
    return "\ufeff" + _table(t, spans, ",")   # BOM: Excel abre bien los acentos


def to_tsv(t, spans, stamps, speakers):
    return _table(t, spans, "\t")


def to_json(t: Transcript, spans: List[Span], stamps: bool, speakers: bool) -> str:
    return json.dumps({
        "source": t.source, "language": t.language, "duration": round(t.duration, 3),
        "segments": [{
            "start": round(s.start, 3), "end": round(s.end, 3), "speaker": s.speaker, "text": s.text,
            "words": [{"start": round(w.start, 3), "end": round(w.end, 3), "word": w.text.strip(),
                       "probability": round(w.prob, 3)} for w in s.words],
        } for s in spans],
    }, ensure_ascii=False, indent=2)


def to_html(t: Transcript, spans: List[Span], stamps: bool, speakers: bool) -> str:
    """HTML autónomo: cada palabra lleva su tiempo; con el audio al lado, clic = saltar ahí."""
    audio = ""
    if t.audio_path and os.path.isfile(t.audio_path):
        audio = f'<audio id="a" controls src="file:///{html.escape(t.audio_path.replace(os.sep, "/"))}"></audio>'
    rows = []
    for s in spans:
        words = "".join(f'<span data-t="{w.start:.2f}">{html.escape(w.text)}</span>' for w in s.words) \
            if s.text_override is None else html.escape(s.text)
        who = f"<b>{html.escape(s.speaker)}:</b> " if speakers and s.speaker else ""
        stamp = f'<time data-t="{s.start:.2f}">{ts(s.start, hours=False)}</time> ' if stamps else ""
        rows.append(f"<p>{stamp}{who}{words}</p>")
    return f"""<!doctype html><html lang="{t.language or 'es'}"><meta charset="utf-8">
<title>{html.escape(t.source or 'Transcripción')}</title>
<style>body{{background:#000;color:#F2F2F2;font:16px/1.7 Segoe UI,sans-serif;max-width:780px;margin:40px auto;padding:0 16px}}
h1{{color:#FFE600;font-size:22px}}time{{color:#FFE600;font-size:13px;cursor:pointer;margin-right:6px}}
span[data-t]:hover{{background:#1F1C00;cursor:pointer}}audio{{width:100%;margin-bottom:16px}}</style>
<h1>{html.escape(t.source or 'Transcripción')}</h1>{audio}
{''.join(rows)}
<script>document.addEventListener('click',e=>{{const t=e.target.dataset.t,a=document.getElementById('a');if(t&&a){{a.currentTime=+t;a.play()}}}})</script>
</html>"""


def save_docx(t: Transcript, spans: List[Span], stamps: bool, speakers: bool, path: str):
    from docx import Document
    from docx.shared import Pt, RGBColor
    doc = Document()
    doc.add_heading(t.source or "Transcripción", level=1)
    meta = doc.add_paragraph(f"Idioma: {t.language}  ·  Duración: {ts(t.duration, hours=False)}  ·  MXP Downloader")
    meta.runs[0].font.size = Pt(9)
    for s in (spans if stamps else t.paragraphs()):
        p = doc.add_paragraph()
        if stamps:
            run = p.add_run(f"[{ts(s.start, hours=False)}] ")
            run.font.color.rgb = RGBColor(0x80, 0x80, 0x80)
            run.font.size = Pt(9)
        if speakers and s.speaker:
            p.add_run(f"{s.speaker}: ").bold = True
        p.add_run(s.text)
    doc.save(path)


def save_pdf(t: Transcript, spans: List[Span], stamps: bool, speakers: bool, path: str):
    from fpdf import FPDF
    pdf = FPDF()
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    # Segoe UI viene con todo Windows y cubre acentos, ñ y demás.
    fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    pdf.add_font("ui", "", os.path.join(fonts, "segoeui.ttf"))
    pdf.add_font("ui", "B", os.path.join(fonts, "segoeuib.ttf"))
    pdf.set_font("ui", "B", 16)
    pdf.multi_cell(0, 9, t.source or "Transcripción", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("ui", "", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(0, 6, f"Idioma: {t.language}  ·  Duración: {ts(t.duration, hours=False)}  ·  MXP Downloader", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    for s in (spans if stamps else t.paragraphs()):
        line = ""
        if stamps:
            line += f"[{ts(s.start, hours=False)}]  "
        if speakers and s.speaker:
            line += f"{s.speaker}: "
        pdf.set_text_color(20, 20, 20)
        pdf.set_font("ui", "", 11)
        pdf.multi_cell(0, 6.5, line + s.text, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    pdf.output(path)


TEXT_FORMATS: Dict[str, Callable] = {
    "txt": to_txt, "md": to_md, "srt": to_srt, "vtt": to_vtt, "lrc": to_lrc,
    "csv": to_csv, "tsv": to_tsv, "json": to_json, "html": to_html,
}
BINARY_FORMATS = {"docx": save_docx, "pdf": save_pdf}
ALL_FORMATS = list(TEXT_FORMATS) + list(BINARY_FORMATS)
# Subtítulos con frases enteras de 30 s no sirven: por defecto, cortes de subtítulo.
DEFAULT_GRANULARITY = {"srt": "subtitle", "vtt": "subtitle", "lrc": "subtitle"}


def export(t: Transcript, fmt: str, path: str, granularity: str = "sentence",
           stamps: bool = True, speakers: bool = True):
    spans = t.spans(granularity)
    if fmt in BINARY_FORMATS:
        BINARY_FORMATS[fmt](t, spans, stamps, speakers, path)
    else:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(TEXT_FORMATS[fmt](t, spans, stamps, speakers))
