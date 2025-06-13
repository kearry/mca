import os
import sys
import logging
import whisper

# Whisper configuration
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL_NAME", "base.en")
_default_path = os.path.expanduser("~/whisper_models/base.en.pt")
WHISPER_MODEL_PATH = os.path.expanduser(os.getenv("WHISPER_MODEL_PATH", _default_path))

class WhisperManager:
    def __init__(self):
        self.whisper_model = None

    def load_whisper(self):
        """Initialize and return the global Whisper transcriber."""
        if self.whisper_model is None:
            model_path = WHISPER_MODEL_PATH if os.path.exists(WHISPER_MODEL_PATH) else WHISPER_MODEL_NAME
            logging.info("Loading Whisper model %s", model_path)
            print("Loading Whisper model...", file=sys.stderr)
            self.whisper_model = whisper.load_model(model_path)
            logging.info("Whisper model loaded")
            print("Whisper model loaded", file=sys.stderr)
        return self.whisper_model