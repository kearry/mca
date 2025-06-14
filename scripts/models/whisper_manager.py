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
        """Find actual whisper.cpp executable (not OpenAI Whisper CLI)."""
        if self.whisper_cpp_path:
            return self.whisper_cpp_path
            
        print("🔍 Searching for whisper-cli/whisper.cpp binary...", file=sys.stderr)
        
        # Try common locations for whisper.cpp/whisper-cli
        possible_paths = [
            "/opt/homebrew/bin/whisper-cli",  # Homebrew's new binary name
            "/usr/local/bin/whisper-cli",
            "whisper-cli",
            "/opt/homebrew/bin/whisper-cpp",  # Homebrew's old binary name  
            "/usr/local/bin/whisper-cpp",
            "whisper-cpp",
            "/usr/local/bin/whisper.cpp",
            "/opt/homebrew/bin/whisper.cpp",
            "whisper.cpp",
            "/usr/local/bin/main",  # whisper.cpp is sometimes named "main"
            "/opt/homebrew/bin/main",
            "main"
        ]
        
        for path in possible_paths:
            try:
                print(f"🔍 Checking: {path}", file=sys.stderr)
                result = subprocess.run([path, "--help"], capture_output=True, text=True, timeout=5)
                # Check if this is actually whisper.cpp (not OpenAI Whisper CLI)
                if result.returncode == 0:
                    help_text = result.stdout + result.stderr
                    # Look for whisper.cpp specific flags
                    if any(flag in help_text for flag in ["--model", "-m", "ggml", "whisper.cpp"]):
                        self.whisper_cpp_path = path
                        logging.info("Found whisper.cpp/whisper-cli at: %s", path)
                        print(f"✅ Found whisper binary: {path}", file=sys.stderr)
                        return path
                    else:
                        print(f"❌ {path} is not whisper.cpp (probably OpenAI Whisper CLI)", file=sys.stderr)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                print(f"❌ {path} not found", file=sys.stderr)
                continue
        
        logging.info("whisper.cpp binary not found, will use OpenAI Whisper")
        print("❌ No whisper.cpp binary found, will fall back to OpenAI Whisper", file=sys.stderr)
        return None

    def load_whisper(self):
        """Initialize whisper - either whisper.cpp or fallback to OpenAI Whisper."""
        if self.whisper_model is None:
            model_path = WHISPER_MODEL_PATH if os.path.exists(WHISPER_MODEL_PATH) else None
            
            logging.info("Loading Whisper model %s", model_path or WHISPER_MODEL_NAME)
            print("🚀 WHISPER SETUP STARTING...", file=sys.stderr)
            print(f"📁 Model path from env: {WHISPER_MODEL_PATH}", file=sys.stderr)
            print(f"📁 Model file exists: {os.path.exists(WHISPER_MODEL_PATH) if WHISPER_MODEL_PATH else 'No path set'}", file=sys.stderr)
            
            # Try whisper.cpp first if we have a GGUF model AND the actual binary
            whisper_cpp = self.find_whisper_cpp()
            if whisper_cpp and model_path and (model_path.endswith('.gguf') or model_path.endswith('.ggml') or model_path.endswith('.bin')):
                print(f"🎯 USING WHISPER.CPP!", file=sys.stderr)
                print(f"   Binary: {whisper_cpp}", file=sys.stderr)
                print(f"   Model: {model_path}", file=sys.stderr)
                self.whisper_model = {'type': 'whisper_cpp', 'path': whisper_cpp, 'model': model_path}
                logging.info("Whisper.cpp setup complete")
                print("✅ Whisper.cpp ready for FAST transcription!", file=sys.stderr)
                return self.whisper_model
            
            # Fallback to OpenAI Whisper
            print("🐌 FALLING BACK TO OPENAI WHISPER...", file=sys.stderr)
            if model_path and model_path.endswith('.gguf'):
                print("⚠️  Note: GGUF model found but whisper.cpp not available, using standard model", file=sys.stderr)
            elif not whisper_cpp:
                print("⚠️  Reason: whisper.cpp binary not found", file=sys.stderr)
            elif not model_path:
                print("⚠️  Reason: no model file found", file=sys.stderr)
            
            import whisper
            
            # Use standard model name when falling back (don't try to load GGUF with OpenAI Whisper)
            model_name = WHISPER_MODEL_NAME
            
            try:
                self.whisper_model = whisper.load_model(model_name)
            except Exception as e:
                if "weights_only" in str(e).lower() or "WeightsUnpickler" in str(e):
                    logging.warning("Fixing PyTorch 2.6 weights_only issue for OpenAI Whisper")
                    print("🔧 Fixing PyTorch 2.6 compatibility...", file=sys.stderr)
                    
                    # Apply the weights_only=False fix
                    import torch
                    orig_load = torch.load
                    def _patched_load(*args, **kwargs):
                        kwargs.setdefault("weights_only", False)
                        return orig_load(*args, **kwargs)
                    torch.load = _patched_load
                    
                    try:
                        self.whisper_model = whisper.load_model(model_name)
                        print("✅ PyTorch compatibility fix applied successfully", file=sys.stderr)
                    finally:
                        torch.load = orig_load
                else:
                    raise
            
            logging.info("OpenAI Whisper model loaded: %s", model_name)
            print(f"✅ OpenAI Whisper loaded: {model_name} (will be slower)", file=sys.stderr)
            
        return self.whisper_model

    def get_audio_duration(self, wav_path):
        """Get the actual duration of the audio file for validation."""
        try:
            probe_cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(wav_path)]
            result = subprocess.run(probe_cmd, capture_output=True, text=True)
            duration = float(result.stdout.strip()) if result.stdout.strip() else 0
            if duration > 0:
                print(f"🎵 AUDIO FILE DURATION: {duration:.1f}s ({duration/60:.1f} minutes)", file=sys.stderr)
                return duration
            else:
                raise RuntimeError("ffprobe returned zero duration")
        except Exception as e:
            print(f"⚠️  Could not determine audio duration with ffprobe: {e}", file=sys.stderr)

        # Fallback to Python wave module if ffprobe fails
        try:
            import wave
            with wave.open(str(wav_path), 'rb') as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                duration = frames / float(rate)
            print(f"🎵 AUDIO FILE DURATION (wave): {duration:.1f}s ({duration/60:.1f} minutes)", file=sys.stderr)
            return duration
        except Exception as e:
            print(f"⚠️  Could not determine audio duration using wave: {e}", file=sys.stderr)
            return 0

    def validate_and_fix_timestamps(self, segments, audio_duration):
        """Validate segment timestamps against actual audio duration and fix if needed."""
        if not segments or audio_duration <= 0:
            return segments
        
        # Find max timestamp in segments
        max_timestamp = 0
        for segment in segments:
            end_time = segment.get('end', 0)
            if end_time > max_timestamp:
                max_timestamp = end_time
        
        print(f"🔍 TIMESTAMP VALIDATION:", file=sys.stderr)
        print(f"   Audio duration: {audio_duration:.1f}s", file=sys.stderr)
        print(f"   Max segment timestamp: {max_timestamp:.1f}s", file=sys.stderr)
        
        # If all timestamps are essentially zero, estimate sequential timings
        if max_timestamp < audio_duration * 0.05:
            print("   ❌ INVALID TIMESTAMPS! Segments appear to have no timing information", file=sys.stderr)
            print("   🔧 Estimating timestamps from text length...", file=sys.stderr)

            fixed_segments = []
            current = 0.0
            for segment in segments:
                text = segment.get('text', '').strip()
                if not text:
                    continue
                # Rough duration estimate ~2.5 words per second
                words = len(text.split())
                duration = max(1.0, words / 2.5)
                start = current
                end = start + duration
                current = end
                fixed_segments.append({
                    'start': start,
                    'end': end,
                    'text': text,
                })

            print(f"   ✅ Estimated timestamps for {len(fixed_segments)} segments", file=sys.stderr)
            return fixed_segments

        # Check if timestamps are reasonable (within 10% tolerance)
        if max_timestamp > audio_duration * 1.1:
            print(f"   ❌ INVALID TIMESTAMPS! Segments extend {max_timestamp - audio_duration:.1f}s beyond audio", file=sys.stderr)
            print("   🔧 Attempting to fix by scaling timestamps...", file=sys.stderr)
            
            # Scale all timestamps to fit within audio duration
            scale_factor = (audio_duration * 0.95) / max_timestamp
            print(f"   Scale factor: {scale_factor:.3f}", file=sys.stderr)
            
            fixed_segments = []
            for segment in segments:
                fixed_segment = segment.copy()
                if 'start' in fixed_segment and fixed_segment['start'] is not None:
                    fixed_segment['start'] = fixed_segment['start'] * scale_factor
                if 'end' in fixed_segment and fixed_segment['end'] is not None:
                    fixed_segment['end'] = fixed_segment['end'] * scale_factor
                fixed_segments.append(fixed_segment)
            
            # Verify fix
            new_max = max(seg.get('end', 0) for seg in fixed_segments)
            print(f"   ✅ Fixed! New max timestamp: {new_max:.1f}s", file=sys.stderr)
            return fixed_segments
        else:
            print(f"   ✅ Timestamps look valid", file=sys.stderr)
            return segments

    def transcribe_audio(self, wav_path):
        """Transcribe audio using either whisper.cpp or OpenAI Whisper."""
        model = self.load_whisper()
        
        # Get audio duration for validation
        audio_duration = self.get_audio_duration(wav_path)
        
        # Check if we're using whisper.cpp
        if isinstance(model, dict) and model.get('type') == 'whisper_cpp':
            print("🚀 ATTEMPTING WHISPER.CPP TRANSCRIPTION...", file=sys.stderr)
            try:
                result = self._transcribe_with_whisper_cpp(wav_path, model)
                if result is not None:
                    print("✅ WHISPER.CPP TRANSCRIPTION SUCCESSFUL!", file=sys.stderr)
                    # Validate and fix timestamps
                    if 'segments' in result:
                        result['segments'] = self.validate_and_fix_timestamps(result['segments'], audio_duration)
                    return result
                # If result is None, fall through to OpenAI Whisper
                print("⚠️  WHISPER.CPP RETURNED NULL - FALLING BACK TO OPENAI WHISPER", file=sys.stderr)
            except Exception as e:
                print(f"❌ WHISPER.CPP FAILED ({e}) - FALLING BACK TO OPENAI WHISPER", file=sys.stderr)
                logging.warning("whisper.cpp failed, falling back: %s", str(e))
            
            # Load OpenAI Whisper as fallback
            print("🔄 Loading OpenAI Whisper as fallback...", file=sys.stderr)
            import whisper
            try:
                model_name = WHISPER_MODEL_NAME
                fallback_model = whisper.load_model(model_name)
            except Exception as e:
                if "weights_only" in str(e).lower() or "WeightsUnpickler" in str(e):
                    # Apply PyTorch 2.6 fix
                    print("🔧 Applying PyTorch 2.6 fix...", file=sys.stderr)
                    import torch
                    orig_load = torch.load
                    def _patched_load(*args, **kwargs):
                        kwargs.setdefault("weights_only", False)
                        return orig_load(*args, **kwargs)
                    torch.load = _patched_load
                    try:
                        fallback_model = whisper.load_model(model_name)
                    finally:
                        torch.load = orig_load
                else:
                    raise
            
            result = self._transcribe_with_openai_whisper(wav_path, fallback_model)
        else:
            print("🐌 USING OPENAI WHISPER DIRECTLY (NO WHISPER.CPP AVAILABLE)", file=sys.stderr)
            result = self._transcribe_with_openai_whisper(wav_path, model)
        
        # Validate and fix timestamps for OpenAI Whisper results too
        if result and 'segments' in result:
            result['segments'] = self.validate_and_fix_timestamps(result['segments'], audio_duration)
        
        return result

    def _transcribe_with_whisper_cpp(self, wav_path, model_config):
        """Transcribe using whisper.cpp executable."""
        whisper_path = model_config['path']
        model_path = model_config['model']
        
        logging.info("transcribe_audio: using whisper.cpp on %s", wav_path)
        print("⚡ TRANSCRIBING WITH WHISPER.CPP (FAST!)...", file=sys.stderr)
        
        # Create temporary directory for output
        with tempfile.TemporaryDirectory() as temp_dir:
            # Determine if this is whisper-cli (Homebrew) or whisper.cpp (built from source)
            is_whisper_cli = "whisper-cli" in whisper_path or "whisper-cpp" in whisper_path
            
            if is_whisper_cli:
                # Homebrew whisper-cli format
                output_file = os.path.join(temp_dir, "output")
                cmd = [
                    whisper_path,
                    "--model", model_path,
                    "--output-json",  # Enable JSON output
                    "--output-file", output_file,  # Output file prefix
                    "--no-prints",  # Reduce verbose output
                    wav_path  # Audio file as positional argument
                ]
                print(f"🎯 Using whisper-cli (Homebrew) format", file=sys.stderr)
            else:
                # Original whisper.cpp format
                cmd = [
                    whisper_path,
                    "--model", model_path,
                    "--output_format", "json",  # Note the underscore
                    "--output_dir", temp_dir,
                    "--threads", "4",
                    wav_path  # Audio file as positional argument
                ]
                print(f"🎯 Using original whisper.cpp format", file=sys.stderr)
            
            logging.info("Running whisper command: %s", ' '.join(cmd))
            print(f"💻 Command: {' '.join(cmd)}", file=sys.stderr)
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                
                if result.returncode != 0:
                    error_msg = result.stderr.strip()
                    logging.error("whisper command failed: %s", error_msg)
                    print(f"❌ WHISPER.CPP ERROR: {error_msg}", file=sys.stderr)
                    
                    # Check for common issues that suggest incompatible model
                    if any(phrase in error_msg.lower() for phrase in [
                        "failed to initialize whisper context",
                        "invalid model",
                        "unsupported model",
                        "model format"
                    ]):
                        print("⚠️  MODEL INCOMPATIBLE - will fall back to OpenAI Whisper", file=sys.stderr)
                        # Return None to trigger fallback to OpenAI Whisper
                        return None
                    
                    raise RuntimeError(f"whisper command failed: {error_msg}")
                
                # Look for JSON output file
                if is_whisper_cli:
                    # whisper-cli creates output.json
                    json_path = output_file + ".json"
                    if not os.path.exists(json_path):
                        all_files = os.listdir(temp_dir)
                        logging.error("Expected JSON file not found: %s. Files in temp dir: %s", json_path, all_files)
                        raise RuntimeError(f"whisper-cli did not create expected JSON file: {json_path}")
                else:
                    # Original whisper.cpp creates various named files
                    json_files = [f for f in os.listdir(temp_dir) if f.endswith('.json')]
                    if not json_files:
                        all_files = os.listdir(temp_dir)
                        logging.error("No JSON output found. Files in temp dir: %s", all_files)
                        raise RuntimeError(f"whisper did not produce JSON output. Found files: {all_files}")
                    json_path = os.path.join(temp_dir, json_files[0])
                
                with open(json_path, 'r') as f:
                    whisper_result = json.load(f)
                
                print(f"🔍 DEBUG: whisper.cpp JSON structure: {type(whisper_result)}", file=sys.stderr)
                
                # Convert whisper.cpp JSON format to OpenAI Whisper format
                segments = []
                full_text = ""
                
                try:
                    # Handle different JSON structures that whisper.cpp might produce
                    if isinstance(whisper_result, dict):
                        # Check for common whisper.cpp JSON structures
                        if 'transcription' in whisper_result:
                            transcription_data = whisper_result['transcription']
                        elif 'segments' in whisper_result:
                            transcription_data = whisper_result['segments']
                        elif 'result' in whisper_result:
                            transcription_data = whisper_result['result']
                        else:
                            transcription_data = whisper_result
                        
                        if isinstance(transcription_data, list):
                            # Array of segments
                            for segment in transcription_data:
                                if isinstance(segment, dict):
                                    text = segment.get('text', '').strip()
                                    
                                    # Handle different timestamp formats more robustly
                                    start_time = segment.get('start', 0)
                                    end_time = segment.get('end', 0)
                                    
                                    # Some versions use different field names
                                    if 'timestamps' in segment:
                                        timestamps = segment['timestamps']
                                        from_time = timestamps.get('from', start_time)
                                        to_time = timestamps.get('to', end_time)
                                        
                                        # Convert to float safely, handling both ms and seconds
                                        try:
                                            start_time = float(from_time) / 1000.0 if isinstance(from_time, (int, float)) and from_time > 1000 else float(from_time)
                                        except (ValueError, TypeError):
                                            start_time = 0.0
                                        
                                        try:
                                            end_time = float(to_time) / 1000.0 if isinstance(to_time, (int, float)) and to_time > 1000 else float(to_time)
                                        except (ValueError, TypeError):
                                            end_time = 0.0
                                    else:
                                        # Convert start/end times safely and ensure they're reasonable
                                        try:
                                            start_time = float(start_time)
                                            # Check for obviously wrong timestamps (like negative or way too large)
                                            if start_time < 0:
                                                start_time = 0.0
                                        except (ValueError, TypeError):
                                            start_time = 0.0
                                        
                                        try:
                                            end_time = float(end_time)
                                            # Check for obviously wrong timestamps
                                            if end_time < start_time:
                                                end_time = start_time + 1.0  # Default 1 second duration
                                        except (ValueError, TypeError):
                                            end_time = start_time + 1.0
                                    
                                    if text:
                                        segments.append({
                                            'start': start_time,
                                            'end': end_time,
                                            'text': text
                                        })
                                        full_text += text + " "
                        elif isinstance(transcription_data, dict):
                            # Single object with text
                            text = transcription_data.get('text', '')
                            if text:
                                segments.append({
                                    'start': 0.0,
                                    'end': 0.0,
                                    'text': text.strip()
                                })
                                full_text = text.strip()
                    elif isinstance(whisper_result, list):
                        # Direct array of segments
                        for segment in whisper_result:
                            if isinstance(segment, dict):
                                text = segment.get('text', '').strip()
                                if text:
                                    # Convert start/end times safely
                                    try:
                                        start_time = float(segment.get('start', 0))
                                        if start_time < 0:
                                            start_time = 0.0
                                    except (ValueError, TypeError):
                                        start_time = 0.0
                                    
                                    try:
                                        end_time = float(segment.get('end', 0))
                                        if end_time < start_time:
                                            end_time = start_time + 1.0
                                    except (ValueError, TypeError):
                                        end_time = start_time + 1.0
                                    
                                    segments.append({
                                        'start': start_time,
                                        'end': end_time,
                                        'text': text
                                    })
                                    full_text += text + " "
                    
                    full_text = full_text.strip()
                    
                    if not full_text:
                        # Fallback - try to extract any text we can find
                        logging.warning("No text found in structured format, trying fallback extraction")
                        full_text = str(whisper_result).replace('{', '').replace('}', '').replace('[', '').replace(']', '').strip()
                        if full_text and len(full_text) > 10:  # Some reasonable minimum
                            segments = [{'start': 0.0, 'end': 0.0, 'text': full_text}]
                        else:
                            raise RuntimeError("No transcription text found in whisper output")
                    
                except Exception as parse_error:
                    print(f"❌ JSON PARSING ERROR: {parse_error}", file=sys.stderr)
                    print(f"🔍 Raw JSON: {json.dumps(whisper_result, indent=2)[:500]}...", file=sys.stderr)
                    raise RuntimeError(f"Failed to parse whisper.cpp JSON output: {parse_error}")
                
                # Debug timestamp ranges
                if segments:
                    min_time = min(seg.get('start', 0) for seg in segments)
                    max_time = max(seg.get('end', 0) for seg in segments)
                    print(f"🔍 WHISPER.CPP TIMESTAMP RANGE: {min_time:.1f}s - {max_time:.1f}s", file=sys.stderr)
                
                logging.info("whisper transcription complete: %d chars, %d segments", 
                           len(full_text), len(segments))
                print(f"✅ WHISPER.CPP SUCCESS: {len(full_text)} characters, {len(segments)} segments", file=sys.stderr)
                
                return {
                    'text': full_text,
                    'segments': segments
                }
                
            except subprocess.TimeoutExpired:
                raise RuntimeError("whisper command timed out")
            except Exception as e:
                logging.error("whisper command error: %s", str(e))
                raise RuntimeError(f"whisper command failed: {str(e)}")

    def _transcribe_with_openai_whisper(self, wav_path, model):
        """Transcribe using OpenAI Whisper."""
        logging.info("transcribe_audio: using OpenAI Whisper on %s", wav_path)
        print("🐌 TRANSCRIBING WITH OPENAI WHISPER (SLOWER)...", file=sys.stderr)
        
        result = model.transcribe(wav_path)
        logging.info("transcribe_audio: finished")
        
        # Debug timestamp ranges for OpenAI Whisper too
        if isinstance(result, dict) and 'segments' in result:
            segments = result['segments']
            if segments:
                min_time = min(seg.get('start', 0) for seg in segments)
                max_time = max(seg.get('end', 0) for seg in segments)
                print(f"🔍 OPENAI WHISPER TIMESTAMP RANGE: {min_time:.1f}s - {max_time:.1f}s", file=sys.stderr)
        
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
