import os
import sys
import json
import subprocess
import logging
from pathlib import Path
import re
from difflib import SequenceMatcher

class YouTubeProcessor:
    def __init__(self, public_folder, watermark_path):
        self.public_folder = public_folder
        self.watermark_path = watermark_path

    def fetch_youtube_transcript(self, url, languages=("en",)):
        """Return transcript text and segment timings if YouTube provides them."""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except Exception:
            logging.info("youtube_transcript_api not installed")
            return None, None

        video_id = None
        m = re.search(r"(?:v=|/)([0-9A-Za-z_-]{11})(?:[?&]|$)", url)
        if m:
            video_id = m.group(1)
        if not video_id:
            logging.info("Could not extract video id from %s", url)
            return None, None

        try:
            transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = None
            for lang in languages:
                try:
                    transcript = transcripts.find_manually_created_transcript([lang])
                    break
                except Exception:
                    pass
            if transcript is None:
                for lang in languages:
                    try:
                        transcript = transcripts.find_generated_transcript([lang])
                        break
                    except Exception:
                        pass
            if transcript is None:
                return None, None
            items = transcript.fetch()
            segments = [
                {"start": it["start"], "end": it["start"] + it["duration"], "text": it["text"]}
                for it in items
            ]
            text = " ".join(it["text"] for it in items)
            return text, segments
        except Exception as e:
            logging.info("fetch_youtube_transcript failed: %s", e)
            return None, None

    def convert_to_wav(self, video_path, job_id):
        audio_output_path = self.public_folder / f"{job_id}_audio.wav"
        command = [
            'ffmpeg', '-i', str(video_path),
            '-ar', '16000',      # 16kHz
            '-ac', '1',          # mono
            '-y', str(audio_output_path)
        ]
        try:
            logging.info("convert_to_wav: running ffmpeg %s", ' '.join(command))
            print("Converting video to WAV for Whisper...", file=sys.stderr)
            subprocess.run(command, check=True, capture_output=True, text=True)
            print("Conversion successful.", file=sys.stderr)
            logging.info("convert_to_wav: wrote %s", audio_output_path)
            return str(audio_output_path)
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg error: {e.stderr}", file=sys.stderr)
            logging.error("convert_to_wav failed: %s", e.stderr)
            raise RuntimeError(f"FFmpeg failed: {e.stderr}")

    def process(self, url, job_id, whisper_manager):
        """Process a YouTube URL and return transcript text, video path, and segments."""
        import yt_dlp
        from yt_dlp.utils import DownloadError

        class _Logger:
            def debug(self, msg): pass
            def warning(self, msg): pass
            def error(self, msg): print(msg, file=sys.stderr)

        logging.info("YouTubeProcessor: checking transcripts for %s", url)
        print("Checking for existing transcripts...", file=sys.stderr)
        transcript_text, segments = self.fetch_youtube_transcript(url)

        logging.info("YouTubeProcessor: downloading %s", url)
        print("Downloading YouTube video...", file=sys.stderr)
        video_path = self.public_folder / f"{job_id}_full.mp4"
        video_format = os.getenv(
            "YTDLP_VIDEO_FORMAT",
            "bestvideo[height<=720]+bestaudio/best[height<=720]",
        )
        logging.info("YouTubeProcessor: using format %s", video_format)
        ydl_opts = {
            'format': video_format,
            'outtmpl': str(video_path),
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4',
            'logger': _Logger(),
        }
        cookie_file = os.getenv("YTDLP_COOKIE_FILE")
        if cookie_file and os.path.exists(cookie_file):
            print(f"Using cookies from {cookie_file}", file=sys.stderr)
            ydl_opts['cookiefile'] = cookie_file

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download([url])
            except DownloadError as e:
                message = str(e)
                if "Sign in to confirm" in message:
                    message += (
                        "\nSet the YTDLP_COOKIE_FILE environment variable to the "
                        "path of a browser-exported cookies file so yt_dlp can "
                        "authenticate."
                    )
                raise RuntimeError(f"Failed to download video: {message}")
        
        logging.info("YouTubeProcessor: downloaded to %s", video_path)
        print(f"Downloaded to: {video_path}", file=sys.stderr)

        if not transcript_text:
            wav_path = self.convert_to_wav(video_path, job_id)

            logging.info("YouTubeProcessor: transcribing")
            print("Transcribing audio...", file=sys.stderr)
            transcript_result = whisper_manager.transcribe_audio(wav_path)
            transcript_text = transcript_result.get("text", "")
            segments = transcript_result.get("segments", [])
            logging.info(
                "YouTubeProcessor: transcription complete (%d chars, %d segments)",
                len(transcript_text),
                len(segments),
            )
            print("Transcription complete.", file=sys.stderr)
        else:
            logging.info(
                "YouTubeProcessor: using existing transcript (%d chars, %d segments)",
                len(transcript_text),
                len(segments),
            )

        # Save segments for later clip extraction
        segments_file = self.public_folder / f"{job_id}_segments.json"
        with open(segments_file, "w") as f:
            json.dump(segments, f)

        return transcript_text, str(video_path), segments

    def extract_clip(self, video_path, start, end, output_path, padding=1.0):
        """Extract a clip from video_path between start and end times with padding."""
        # Add padding to prevent audio clipping
        padded_start = max(0, start - padding)
        padded_end = end + padding
        
        logging.info("extract_clip: original times %.1f-%.1f, padded %.1f-%.1f", 
                    start, end, padded_start, padded_end)
        
        # Use input seeking for better performance and precision
        command = [
            "ffmpeg",
            "-ss", str(padded_start),  # Input seek to approximate position
            "-i", str(video_path)
        ]

        if self.watermark_path and os.path.exists(self.watermark_path):
            command += [
                "-i", str(self.watermark_path),
                "-filter_complex", 
                f"[1:v]scale=400:-1[wm];[0:v][wm]overlay=0:0",
                "-map", "0:a?",
            ]

        # Calculate duration for more precise cutting
        duration = padded_end - padded_start
        
        command += [
            "-t", str(duration),  # Duration instead of end time for better precision
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",      # Faster encoding
            "-crf", "23",           # Good quality balance
            "-movflags", "+faststart",
            "-avoid_negative_ts", "make_zero",  # Handle timing issues
            "-y", str(output_path),
        ]
        
        try:
            logging.info("extract_clip: ffmpeg %s", ' '.join(command))
            print(f"Extracting clip {padded_start:.1f}s - {padded_end:.1f}s...", file=sys.stderr)
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            logging.info("extract_clip: wrote %s", output_path)
            print("Clip extracted successfully", file=sys.stderr)
            return True
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg clip error: {e.stderr}", file=sys.stderr)
            logging.error("extract_clip failed: %s", e.stderr)
            return False

    def find_quote_timestamps(self, segments, quote, window=20, threshold=0.55, context_padding=2.0):
        """Return start/end times and the snippet most similar to the quote with better context."""
        logging.debug("find_quote_timestamps: searching for '%s'", quote)
        if not quote:
            return None, None, None

        def normalize(text):
            return re.sub(r"[^a-z0-9\s]", "", text.lower())

        target = normalize(quote)
        best_ratio = 0.0
        best_result = (None, None, None)
        n = len(segments)

        # Try different window sizes for better matching
        for window_size in [window, window + 5, window - 5]:
            if window_size <= 0:
                continue
                
            for i in range(n):
                combined = ""
                start = None
                end = None
                
                for j in range(window_size):
                    if i + j >= n:
                        break
                    seg = segments[i + j]
                    if start is None:
                        start = seg.get("start")
                    end = seg.get("end", end)
                    if combined:
                        combined += " "
                    combined += seg.get("text", "")

                    # Check match at each step for partial matches
                    ratio = SequenceMatcher(None, normalize(combined), target).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        # Add context padding to the timestamps
                        padded_start = max(0, start - context_padding) if start else None
                        padded_end = (end + context_padding) if end else None
                        best_result = (padded_start, padded_end, combined.strip())

        if best_ratio >= threshold:
            logging.debug("find_quote_timestamps: found %s-%s (score %.2f)", 
                         best_result[0], best_result[1], best_ratio)
            print(f"Found quote match: {best_ratio:.2f} confidence", file=sys.stderr)
            return best_result
        
        logging.debug("find_quote_timestamps: no match (best score: %.2f)", best_ratio)
        print(f"Quote not found (best match: {best_ratio:.2f})", file=sys.stderr)
        return None, None, None