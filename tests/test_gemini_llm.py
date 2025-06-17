import os
import sys
import types
import importlib.util
from pathlib import Path
import unittest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
MODULE_PATH = SCRIPT_DIR / "main.py"

os.environ.setdefault("GOOGLE_API_KEY", "dummy")

class StubResponse:
    def __init__(self):
        self.candidates = [types.SimpleNamespace(finish_reason=2)]
        self.prompt_feedback = types.SimpleNamespace(block_reason="SAFETY")
    @property
    def text(self):
        raise RuntimeError("Invalid operation: The `response.text` quick accessor requires the response to contain a valid Part")

class StubModel:
    def generate_content(self, *a, **k):
        return StubResponse()

stub_genai = types.ModuleType("generativeai")
stub_genai.GenerativeModel = lambda *a, **k: StubModel()
stub_genai.configure = lambda *a, **k: None
google_pkg = types.ModuleType("google")
google_pkg.generativeai = stub_genai

sys.modules.setdefault("google", google_pkg)
sys.modules.setdefault("google.generativeai", stub_genai)
sys.modules.setdefault("llama_cpp", types.SimpleNamespace(Llama=lambda *a, **k: object()))
sys.modules.setdefault("whisper", types.SimpleNamespace(load_model=lambda *a, **k: types.SimpleNamespace(transcribe=lambda *a, **k: {})))

spec = importlib.util.spec_from_file_location("main", MODULE_PATH)
main = importlib.util.module_from_spec(spec)
sys.modules["main"] = main
spec.loader.exec_module(main)

class GeminiLLMResponseTests(unittest.TestCase):
    def test_blocked_response_raises_error(self):
        llm = main.GeminiLLM()
        with self.assertRaises(RuntimeError) as ctx:
            llm.create_chat_completion([{"content": "hi"}], 0.0, 5)
        msg = str(ctx.exception)
        self.assertIn("blocked", msg)
        self.assertIn("finish_reason", msg)

if __name__ == "__main__":
    unittest.main()
