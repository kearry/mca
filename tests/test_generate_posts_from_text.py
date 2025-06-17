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
        main.load_llm = lambda: stub

        func = main.generate_posts_from_text
        system_prompt = func.__code__.co_consts[1]
        chars_per_token = func.__code__.co_consts[2]
        output_token_buffer = func.__code__.co_consts[3]
        base_context_tokens = func.__code__.co_consts[4]
        max_context_tokens = base_context_tokens - (
            len(system_prompt) + output_token_buffer
        )
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
        main.load_llm = lambda: stub
        posts = main.generate_posts_from_text("hello", "text")
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["post_text"], "foo")

    def test_json_wrapped_in_tags(self):
        stub = StubLLM([
            "<think>doing stuff</think>[{\"post_text\": \"tagged\", \"source_quote\": \"bar\"}]"
        ])
        main.load_llm = lambda: stub
        posts = main.generate_posts_from_text("hello", "text")
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["post_text"], "tagged")

    def test_stray_closing_tag(self):
        stub = StubLLM([
            '[{\"post_text\": \"tagless\", \"source_quote\": \"bar\"}]</think>'
        ])
        main.load_llm = lambda: stub
        posts = main.generate_posts_from_text("hello", "text")
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["post_text"], "tagless")

    def test_instruction_echo_with_example_array(self):
        output = ("You are a bot. Return an empty JSON array [] if you cannot comply. "
            "Actual data: [{\"post_text\": \"ok\", \"source_quote\": \"q\"}]")
        stub = StubLLM([output])
        main.load_llm = lambda: stub
        posts = main.generate_posts_from_text("hello", "text")
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["post_text"], "ok")

    def test_invalid_json_shape_dict(self):
        stub = StubLLM(['{"foo": "bar"}'])
        main.load_llm = lambda: stub
        with self.assertRaises(ValueError):
            main.generate_posts_from_text("hello", "text")

    def test_invalid_json_shape_array_elements(self):
        stub = StubLLM(['["a", "b"]'])
        main.load_llm = lambda: stub
        with self.assertRaises(ValueError):
            main.generate_posts_from_text("hello", "text")

    def test_single_post_object(self):
        stub = StubLLM(['{"post_text": "solo", "source_quote": "q"}'])
        main.load_llm = lambda: stub
        posts = main.generate_posts_from_text("hello", "text")
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["post_text"], "solo")

    def test_truncated_array_returns_complete_objects(self):
        stub = StubLLM([
            '[{"post_text": "a", "source_quote": "q1"}, {"post_text": "b", "source_quote": "q2"}'
        ])
        main.load_llm = lambda: stub
        posts = main.generate_posts_from_text("hello", "text")
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[1]["post_text"], "b")

    def test_truncated_array_mid_object(self):
        stub = StubLLM([
            '[{"post_text": "a", "source_quote": "q1"}, {"post_text": "b"'
        ])
        main.load_llm = lambda: stub
        posts = main.generate_posts_from_text("hello", "text")
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["post_text"], "a")


    def test_deduplicate_posts_by_quote(self):
        posts = [
            {"post_text": "a", "source_quote": "same"},
            {"post_text": "b", "source_quote": "same"},
            {"post_text": "c", "source_quote": "other"},
        ]
        result = main.deduplicate_posts(posts)
        self.assertEqual(len(result), 2)
        quotes = {p["source_quote"] for p in result}
        self.assertEqual(quotes, {"same", "other"})

if __name__ == "__main__":
    unittest.main()
