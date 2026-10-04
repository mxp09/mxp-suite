"""Segmentación y exportadores sin motor ni red.  python -m unittest discover tests"""
import os
import tempfile
import unittest

from core.transcription.engine import parse_whisper_json
from core.transcription import exporters
from core.transcription.model import Transcript, split_lines


def tok(text, a, b):
    return {"text": text, "offsets": {"from": a, "to": b}, "p": 0.9}


SAMPLE = {"transcription": [
    {"tokens": [tok("[_BEG_]", 0, 0), tok(" Hola", 0, 400), tok(",", 400, 450), tok(" qué", 500, 700),
                tok(" tal", 700, 900), tok(".", 900, 950)]},
    {"tokens": [tok(" Bien", 3000, 3300), tok(" gra", 3300, 3500), tok("cias", 3500, 3800), tok(".", 3800, 3850)]},
]}


class TranscriptionTests(unittest.TestCase):
    def setUp(self):
        self.t = Transcript(parse_whisper_json(SAMPLE), language="es", source="demo", duration=4)

    def test_words_join_subword_tokens(self):
        self.assertEqual([w.text.strip() for w in self.t.words], ["Hola,", "qué", "tal.", "Bien", "gracias."])
        self.assertAlmostEqual(self.t.words[4].start, 3.3)
        self.assertAlmostEqual(self.t.words[4].end, 3.85)

    def test_sentences_and_paragraphs(self):
        self.assertEqual([s.text for s in self.t.sentences()], ["Hola, qué tal.", "Bien gracias."])
        self.assertEqual(len(self.t.paragraphs()), 2)   # pausa de 2 s > PAUSE_PARAGRAPH

    def test_edits_survive_export(self):
        self.assertTrue(self.t.apply_sentence_edits(["Hola, ¿qué tal?", "Bien gracias."]))
        srt = exporters.to_srt(self.t, self.t.spans("subtitle"), True, False)
        self.assertIn("00:00:00,000 --> 00:00:00,950\nHola, ¿qué tal?", srt)
        self.assertFalse(self.t.apply_sentence_edits(["solo una"]))

    def test_split_lines(self):
        self.assertEqual(split_lines("corto"), "corto")
        self.assertIn("\n", split_lines("una frase bastante larga que no cabe en una sola línea de sub"))

    def test_every_format_writes(self):
        with tempfile.TemporaryDirectory() as d:
            for fmt in exporters.ALL_FORMATS:
                path = os.path.join(d, "x." + fmt)
                exporters.export(self.t, fmt, path, "word")
                self.assertGreater(os.path.getsize(path), 0, fmt)


if __name__ == "__main__":
    unittest.main()
