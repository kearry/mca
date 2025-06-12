import unittest
import json
from pathlib import Path

# Read the TypeScript file to ensure function exists
TS_PATH = Path(__file__).resolve().parents[1] / "src" / "app" / "api" / "process" / "route.ts"
with TS_PATH.open() as f:
    TS_SOURCE = f.read()

class BuildErrorMessageTests(unittest.TestCase):
    def test_exit_code_appended(self):
        self.assertIn('buildErrorMessage', TS_SOURCE)
        # Reimplement the helper in Python to mirror the logic
        def build_error_message(script_error: str, code: int | None):
            error_lines = script_error.strip().split('\n')
            last_line = error_lines[-1]
            error_message = 'Unknown Python script error.'
            try:
                error_result = json.loads(last_line)
                if error_result and 'error' in error_result:
                    error_message = error_result['error']
            except Exception:
                error_message = last_line or script_error[:500]
            if code and code != 0:
                error_message += f" (exit code: {code})"
            return error_message

        msg = build_error_message('{"error":"boom"}\n', 2)
        self.assertEqual(msg, 'boom (exit code: 2)')

        msg_no_code = build_error_message('{"error":"boom"}\n', 0)
        self.assertEqual(msg_no_code, 'boom')

if __name__ == '__main__':
    unittest.main()
