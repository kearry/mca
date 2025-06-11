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

class StubLLM:
    def __init__(self, responses):
        self.responses = responses
        self.call_count = 0

    def create_chat_completion(self, *a, **k):
        resp = self.responses[self.call_count]
        self.call_count += 1
        return {"choices": [{"message": {"content": resp}}]}

class GeneratePostsTests(unittest.TestCase):
    def test_multiple_chunks_combined(self):
        stub = StubLLM([
            '[{"post_text": "first", "source_quote": "q1"}]',
            '[{"post_text": "second", "source_quote": "q2"}]',
        ])
        main.LLM_TEXT_GENERATOR = stub

        func = main.generate_posts_from_text
        system_prompt = func.__code__.co_consts[1]
        chars_per_token = func.__code__.co_consts[2]
        max_context_tokens = 4096 - (len(system_prompt) + 200)
        max_context_chars = max_context_tokens * chars_per_token

        context = "x" * (max_context_chars + 10)
        posts = main.generate_posts_from_text(context, "text")

        self.assertEqual(stub.call_count, 2)
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0]["post_text"], "first")
        self.assertEqual(posts[1]["post_text"], "second")

    def test_json_with_preamble(self):
        stub = StubLLM([
            "<think>\nHere is your data:\n[{\"post_text\": \"foo\", \"source_quote\": \"bar\"}]"
        ])
        main.LLM_TEXT_GENERATOR = stub
        posts = main.generate_posts_from_text("hello", "text")
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["post_text"], "foo")

    def test_json_wrapped_in_tags(self):
        stub = StubLLM([
            "<think>doing stuff</think>[{\"post_text\": \"tagged\", \"source_quote\": \"bar\"}]"
        ])
        main.LLM_TEXT_GENERATOR = stub
        posts = main.generate_posts_from_text("hello", "text")
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["post_text"], "tagged")

if __name__ == "__main__":
    unittest.main()
