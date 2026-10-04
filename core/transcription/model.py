"""
Modelo de una transcripción y su segmentación en frases, párrafos y subtítulos.

Todo parte de las PALABRAS con su tiempo: a partir de ahí se arma cualquier
granularidad sin volver a transcribir (eso es lo que permite exportar con
timestamps por palabra, por frase o por párrafo desde el mismo resultado).
"""

from dataclasses import dataclass, field
from typing import List, Optional

SENTENCE_END = (".", "?", "!", "…", "。", "？", "！")
PAUSE_SENTENCE = 1.0      # s de silencio que cierran una frase aunque no haya punto
PAUSE_PARAGRAPH = 1.5     # s de silencio que abren párrafo nuevo
MAX_SENTENCE_WORDS = 40
PARAGRAPH_SENTENCES = 5
SUB_MAX_CHARS = 42        # por línea; 2 líneas por subtítulo (norma habitual)
SUB_MAX_SECONDS = 7.0


@dataclass
class Word:
    start: float
    end: float
    text: str             # incluye el espacio inicial si lo trae (" hola")
    prob: float = 1.0
    speaker: Optional[str] = None


@dataclass
class Span:
    """Un tramo de texto con tiempos: frase, párrafo o subtítulo."""
    start: float
    end: float
    words: List[Word] = field(default_factory=list)
    text_override: Optional[str] = None   # texto editado por el usuario

    @property
    def text(self) -> str:
        if self.text_override is not None:
            return self.text_override
        return "".join(w.text for w in self.words).strip()

    @property
    def speaker(self) -> Optional[str]:
        speakers = [w.speaker for w in self.words if w.speaker]
        return max(set(speakers), key=speakers.count) if speakers else None


@dataclass
class Transcript:
    words: List[Word]
    language: str = ""
    source: str = ""          # título visible (nombre de archivo o título del vídeo)
    audio_path: str = ""      # audio local original, si lo hay (para el HTML interactivo)
    duration: float = 0.0
    _sentences: Optional[List[Span]] = None

    # ── Granularidades ──
    def sentences(self) -> List[Span]:
        """Frases: se cierran en puntuación final, en pausas largas o por longitud."""
        if self._sentences is not None:
            return self._sentences
        out, current = [], []
        for i, word in enumerate(self.words):
            current.append(word)
            nxt = self.words[i + 1] if i + 1 < len(self.words) else None
            ends = word.text.strip().endswith(SENTENCE_END)
            pause = nxt is not None and nxt.start - word.end >= PAUSE_SENTENCE
            speaker_change = nxt is not None and nxt.speaker != word.speaker
            if nxt is None or ends or pause or speaker_change or len(current) >= MAX_SENTENCE_WORDS:
                out.append(Span(current[0].start, current[-1].end, current))
                current = []
        self._sentences = out
        return out

    def paragraphs(self) -> List[Span]:
        """Párrafos: grupos de frases, cortados por pausas largas o cambio de hablante."""
        out, group = [], []
        sentences = self.sentences()
        for i, sentence in enumerate(sentences):
            group.append(sentence)
            nxt = sentences[i + 1] if i + 1 < len(sentences) else None
            if (nxt is None or nxt.start - sentence.end >= PAUSE_PARAGRAPH
                    or nxt.speaker != sentence.speaker or len(group) >= PARAGRAPH_SENTENCES):
                span = Span(group[0].start, group[-1].end, [w for s in group for w in s.words])
                if any(s.text_override is not None for s in group):
                    span.text_override = " ".join(s.text for s in group)
                out.append(span)
                group = []
        return out

    def word_spans(self) -> List[Span]:
        return [Span(w.start, w.end, [w]) for w in self.words]

    def subtitles(self) -> List[Span]:
        """Subtítulos: máx. 2 líneas de 42 caracteres y 7 s, sin partir frases si se puede."""
        out = []
        for sentence in self.sentences():
            if sentence.text_override is not None:
                out.append(sentence)   # frase editada: se respeta entera
                continue
            current = []
            for word in sentence.words:
                candidate = "".join(w.text for w in current + [word]).strip()
                too_long = len(candidate) > SUB_MAX_CHARS * 2
                too_slow = current and word.end - current[0].start > SUB_MAX_SECONDS
                if current and (too_long or too_slow):
                    out.append(Span(current[0].start, current[-1].end, current))
                    current = []
                current.append(word)
            if current:
                out.append(Span(current[0].start, current[-1].end, current))
        return out

    def spans(self, granularity: str) -> List[Span]:
        return {"paragraph": self.paragraphs, "sentence": self.sentences,
                "word": self.word_spans, "subtitle": self.subtitles}[granularity]()

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.paragraphs())

    def apply_sentence_edits(self, texts: List[str]) -> bool:
        """Aplica textos editados frase a frase. False si no cuadra el número de frases."""
        sentences = self.sentences()
        if len(texts) != len(sentences):
            return False
        for sentence, text in zip(sentences, texts):
            text = text.strip()
            sentence.text_override = None if text == "".join(w.text for w in sentence.words).strip() else text
        return True


def split_lines(text: str, width: int = SUB_MAX_CHARS) -> str:
    """Parte un subtítulo en 2 líneas equilibradas por el espacio más centrado."""
    if len(text) <= width:
        return text
    middle = len(text) // 2
    spaces = [i for i, c in enumerate(text) if c == " "]
    if not spaces:
        return text
    cut = min(spaces, key=lambda i: abs(i - middle))
    return text[:cut] + "\n" + text[cut + 1:]
