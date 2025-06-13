import os
import sys
import logging
import subprocess
import json
import tempfile

# Whisper configuration for whisper.cpp
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL_NAME", "base.en")
_default_path = os.path.expanduser("~/.cache/lm-studio/models/FL33TW00D-HF/distil-whisper-large-v3/distil-large-v3_q8_0.gguf")
WHISPER_MODEL_PATH = os.path.expanduser(os.getenv("WHISPER_MODEL_PATH", _default_path))

class WhisperManager:
    def __init__(self):
        self.whisper_model = None
        self.whisper_cpp_path = None

    def find_whisper_cpp(self):
        """Find whisper.cpp executable."""
        if self.whisper_cpp_path:
            return self.whisper_cpp_path
            
        # Try common locations for whisper.cpp
        possible_paths = [
            "/usr/local/bin/whisper",
            "/opt/homebrew/bin/whisper", 
            "/usr/bin/whisper",
            "whisper",  # In PATH
            "/usr/local/bin/whisper.cpp",
            "/opt/homebrew/bin/whisper.cpp",
            "whisper.cpp"
        ]
        
        for path in possible_paths:
            try:
                result = subprocess.run([path, "--help"], capture_output=True, text=True)
                if result.returncode == 0:
                    self.whisper_cpp_path = path
                    logging.info("Found whisper.cpp at: %s", path)
                    return path
            except FileNotFoundError:
                continue
        
        return None

    def load_whisper(self):
        """Initialize whisper - either whisper.cpp or fallback to OpenAI Whisper."""
        if self.whisper_model is None:
            model_path = WHISPER_MODEL_PATH if os.path.exists(WHISPER_MODEL_PATH) else None
            
            logging.info("Loading Whisper model %s", model_path or WHISPER_MODEL_NAME)
            print("Loading Whisper model...", file=sys.stderr)
            
            # Try whisper.cpp first if we have a GGUF model
            whisper_cpp = self.find_whisper_cpp()
            if whisper_cpp and model_path and model_path.endswith('.gguf'):
                print(f"Using whisper.cpp with GGUF model: {model_path}", file=sys.stderr)
                self.whisper_model = {'type': 'whisper_cpp', 'path': whisper_cpp, 'model': model_path}
                logging.info("Whisper.cpp setup complete")
                print("Whisper.cpp ready", file=sys.stderr)
                return self.whisper_model
            
            # Fallback to OpenAI Whisper
            print("Using OpenAI Whisper (fallback)...", file=sys.stderr)
            import whisper
            
            try:
                # Use standard model name if GGUF not available
                model_name = WHISPER_MODEL_NAME if not model_path or model_path.endswith('.gguf') else model_path
                self.whisper_model = whisper.load_model(model_name)
            except Exception as e:
                if "weights_only" in str(e).lower():
                    logging.warning("Retrying with weights_only=False due to PyTorch 2.6 change")
                    import torch
                    orig_load = torch.load
                    def _patched_load(*args, **kwargs):
                        kwargs.setdefault("weights_only", False)
                        return orig_load(*args, **kwargs)
                    torch.load = _patched_load
                    try:
                        self.whisper_model = whisper.load_model(model_name)
                    finally:
                        torch.load = orig_load
                else:
                    raise
            
            logging.info("OpenAI Whisper model loaded")
            print("OpenAI Whisper loaded", file=sys.stderr)
            
        return self.whisper_model

    def transcribe_audio(self, wav_path):
        """Transcribe audio using either whisper.cpp or OpenAI Whisper."""
        model = self.load_whisper()
        
        # Check if we're using whisper.cpp
        if isinstance(model, dict) and model.get('type') == 'whisper_cpp':
            return self._transcribe_with_whisper_cpp(wav_path, model)
        else:
            return self._transcribe_with_openai_whisper(wav_path, model)

    def _transcribe_with_whisper_cpp(self, wav_path, model_config):
        """Transcribe using whisper.cpp executable."""
        whisper_path = model_config['path']
        model_path = model_config['model']
        
        logging.info("transcribe_audio: using whisper.cpp on %s", wav_path)
        print("Transcribing with whisper.cpp...", file=sys.stderr)
        
        # Create temporary file for output
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as temp_file:
            temp_json_path = temp_file.name
        
        try:
            # Run whisper.cpp with JSON output
            cmd = [
                whisper_path,
                '-m', model_path,
                '-f', wav_path,
                '-oj',  # Output JSON
                '-of', temp_json_path.replace('.json', ''),  # Output file prefix
                '--no-prints'  # Reduce verbose output
            ]
            
            logging.info("Running whisper.cpp: %s", ' '.join(cmd))
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                logging.error("whisper.cpp failed: %s", result.stderr)
                raise RuntimeError(f"whisper.cpp failed: {result.stderr}")
            
            # Read the JSON output
            json_file = temp_json_path
            if not os.path.exists(json_file):
                # Try alternative naming
                json_file = temp_json_path.replace('.json', '') + '.json'
            
            if os.path.exists(json_file):
                with open(json_file, 'r') as f:
                    whisper_result = json.load(f)
                
                # Convert to OpenAI Whisper format
                segments = []
                for segment in whisper_result.get('transcription', []):
                    segments.append({
                        'start': segment.get('timestamps', {}).get('from', 0) / 1000.0,
                        'end': segment.get('timestamps', {}).get('to', 0) / 1000.0,
                        'text': segment.get('text', '').strip()
                    })
                
                full_text = ' '.join(seg['text'] for seg in segments if seg['text'].strip())
                
                logging.info("whisper.cpp transcription complete: %d chars, %d segments", 
                           len(full_text), len(segments))
                
                return {
                    'text': full_text,
                    'segments': segments
                }
            else:
                raise RuntimeError("whisper.cpp did not produce expected JSON output")
                
        finally:
            # Cleanup temp files
            for ext in ['.json', '.txt', '.srt', '.vtt']:
                temp_path = temp_json_path.replace('.json', ext)
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

    def _transcribe_with_openai_whisper(self, wav_path, model):
        """Transcribe using OpenAI Whisper."""
        logging.info("transcribe_audio: using OpenAI Whisper on %s", wav_path)
        print("Transcribing with OpenAI Whisper...", file=sys.stderr)
        
        result = model.transcribe(wav_path)
        logging.info("transcribe_audio: finished")
        
        if isinstance(result, dict):
            return result
        elif isinstance(result, str):
            return {"text": result, "segments": []}
        else:
            return {
                "text": " ".join(getattr(seg, "text", str(seg)) for seg in result),
                "segments": [
                    {
                        "start": getattr(seg, "start", None),
                        "end": getattr(seg, "end", None),
                        "text": getattr(seg, "text", str(seg)),
                    }
                    for seg in result
                ],
            }