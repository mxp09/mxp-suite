"""Pruebas del núcleo sin red ni GUI.  Ejecutar:  python -m unittest discover tests"""
import unittest

from core import errors
from core.utils import parse_time_str


class CoreTests(unittest.TestCase):
    def test_parse_time(self):
        self.assertEqual(parse_time_str("01:02:03"), 3723)
        self.assertEqual(parse_time_str("2:05"), 125)
        self.assertEqual(parse_time_str("45"), 45)
        self.assertIsNone(parse_time_str(""))
        self.assertIsNone(parse_time_str("aa:bb"))

    def test_playlist_heuristic(self):
        from gui.app import App
        lp = App._looks_like_playlist
        self.assertTrue(lp("https://youtube.com/watch?v=x&list=PL123"))
        self.assertFalse(lp("https://youtube.com/watch?v=x&list=RDx"))  # Mix automático
        self.assertFalse(lp("https://youtube.com/watch?v=x"))

    def test_errors_classify_403(self):
        detail = errors.classify("HTTP Error 403: Forbidden")
        self.assertTrue(detail.full_text)
        self.assertTrue(detail.needs_cookies)


if __name__ == "__main__":
    unittest.main()
