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
            try:
                self.whisper_model = whisper.load_model(model_path)
            except Exception as e:
                if "weights_only" in str(e).lower():
                    logging.warning(
                        "Retrying Whisper load with weights_only=False due to PyTorch 2.6 change"
                    )
                    import torch
                    orig_load = torch.load

                    def _patched_load(*args, **kwargs):
                        kwargs.setdefault("weights_only", False)
                        return orig_load(*args, **kwargs)

                    torch.load = _patched_load
                    try:
                        self.whisper_model = whisper.load_model(model_path)
                    finally:
                        torch.load = orig_load
                else:
                    raise
            logging.info("Whisper model loaded")
            print("Whisper model loaded", file=sys.stderr)
        return self.whisper_model
