import sys
import types
import importlib.util
from pathlib import Path
import unittest

# Load the main.py module from the scripts directory
SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
MODULE_PATH = SCRIPT_DIR / "main.py"
# Stub heavy optional dependencies so importing main.py doesn't fail
sys.modules.setdefault("llama_cpp", types.SimpleNamespace(Llama=lambda *a, **k: object()))
sys.modules.setdefault("whisper", types.SimpleNamespace(load_model=lambda *a, **k: types.SimpleNamespace(transcribe=lambda *a, **k: {})))

spec = importlib.util.spec_from_file_location("main", MODULE_PATH)
main = importlib.util.module_from_spec(spec)
sys.modules["main"] = main
spec.loader.exec_module(main)

find_quote_timestamps = main.find_quote_timestamps


class FindQuoteTimestampTests(unittest.TestCase):
    def test_exact_match_across_segments(self):
        segments = [
            {"start": 0.0, "end": 1.0, "text": "The quick brown fox"},
            {"start": 1.0, "end": 2.0, "text": "jumps over the lazy dog"},
            {"start": 2.0, "end": 3.0, "text": "and runs away"},
        ]
        quote = "quick brown fox jumps over the lazy dog"
        start, end, snippet = find_quote_timestamps(segments, quote)
        self.assertEqual(start, 0.0)
        self.assertEqual(end, 2.0)
        self.assertIn("quick brown fox jumps over the lazy dog", snippet.lower())

    def test_paraphrased_quote_matches(self):
        segments = [
            {"start": 0.0, "end": 1.0, "text": "Machine learning enables computers"},
            {"start": 1.0, "end": 2.0, "text": "to learn from data and make predictions"},
        ]
        quote = "machine learning lets computers learn from data to make predictions"
        start, end, snippet = find_quote_timestamps(segments, quote)
        self.assertEqual(start, 0.0)
        self.assertEqual(end, 2.0)
        self.assertIsNotNone(snippet)

    def test_no_match_returns_none(self):
        segments = [
            {"start": 0.0, "end": 1.0, "text": "Hello world"},
            {"start": 1.0, "end": 2.0, "text": "Another segment"},
        ]
        quote = "this quote does not exist"
        start, end, snippet = find_quote_timestamps(segments, quote)
        self.assertIsNone(start)
        self.assertIsNone(end)
        self.assertIsNone(snippet)


if __name__ == "__main__":
    unittest.main()
