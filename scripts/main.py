import sys
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse
import wave  # For checking audio properties
from difflib import SequenceMatcher
import logging
import sqlite3

# Load environment variables from an optional .env file so users can
# configure settings like YTDLP_COOKIE_FILE without exporting them
# manually each time. If python-dotenv isn't installed we simply skip
# loading the file.
try:  # pragma: no cover - optional dependency
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

# --- LLM & Whisper Model Imports ---
from llama_cpp import Llama
import whisper

# --- Configuration ---
MODEL_DIRECTORY = os.path.expanduser("~/.cache/lm-studio/models")

# LLaMA-style text generator model
# Default to the DeepSeek-R1 1.5B model downloaded by LM Studio.
LLM_MODEL_PATH = os.path.join(
    MODEL_DIRECTORY,
    "unsloth/DeepSeek-R1-Distill-Qwen-1.5B-GGUF/DeepSeek-R1-Distill-Qwen-1.5B-Q8_0.gguf",
)

# Whisper model identifier or path accepted by the openai-whisper library. We
# default to the "base.en" model name but also allow specifying a path to a
# locally downloaded model file. When a local path is provided, the helper will
# load that file directly.
WHISPER_MODEL_NAME = "base.en"
# Use a locally downloaded model if available.  The load_model helper accepts a
# path to a model file so we expand the user's home directory and provide that
# path.
WHISPER_MODEL_PATH = os.path.expanduser("~/whisper_models/base.en.pt")


# Folder where generated media assets are stored under the repository root
PUBLIC_FOLDER = Path(__file__).resolve().parents[1] / "public" / "generated"
PUBLIC_FOLDER.mkdir(exist_ok=True, parents=True)

# --- Helpers to reuse existing output ---
def _get_db_path() -> str | None:
    """Return the absolute path of the SQLite database if available."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return None
    if db_url.startswith("file:"):
        db_url = db_url[5:]
    if db_url.startswith("./"):
        root = Path(__file__).resolve().parents[1]
        db_url = str(root / db_url[2:])
    return db_url


def load_existing_posts(job_id: str) -> list[dict]:
    """Load posts for *job_id* from the database if present."""
    db_path = _get_db_path()
    if not db_path or not os.path.exists(db_path):
        return []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT content, mediaPath, quoteSnippet, startTime, endTime, pageNumber FROM Post WHERE jobId = ?",
            (job_id,),
        )
        rows = cur.fetchall()
        conn.close()
    except Exception as exc:  # pragma: no cover - DB access is optional
        logging.error("Failed loading existing posts: %s", exc)
        return []

    posts = []
    for row in rows:
        post = {
            "post_text": row["content"],
            "media_path": row["mediaPath"],
            "quote_snippet": row["quoteSnippet"],
            "start_time": row["startTime"],
            "end_time": row["endTime"],
            "page_number": row["pageNumber"],
        }
        posts.append({k: v for k, v in post.items() if v is not None})
    return posts

# --- Debug logging ---
_log_path = os.getenv("LLM_DEBUG_LOG", "llm_debug.log")
logging.basicConfig(filename=_log_path, level=logging.DEBUG,
                    format="%(asctime)s %(levelname)s %(message)s")

# --- Model Initialization ---
LLM_TEXT_GENERATOR = None
WHISPER_TRANSCRIBER = None


def load_llm():
    """Initialize and return the global LLM text generator."""
    global LLM_TEXT_GENERATOR
    if LLM_TEXT_GENERATOR is None:
        LLM_TEXT_GENERATOR = Llama(
            model_path=LLM_MODEL_PATH,
            n_gpu_layers=-1,
            n_ctx=4096,
            verbose=True,
            chat_format="chatml",
        )
    return LLM_TEXT_GENERATOR


def load_whisper():
    """Initialize and return the global Whisper transcriber."""
    global WHISPER_TRANSCRIBER
    if WHISPER_TRANSCRIBER is None:
        model_path = WHISPER_MODEL_PATH if os.path.exists(WHISPER_MODEL_PATH) else WHISPER_MODEL_NAME
        WHISPER_TRANSCRIBER = whisper.load_model(model_path)
    return WHISPER_TRANSCRIBER

# --- Audio & Video Parsers ---
def convert_to_wav(video_path, job_id):
    audio_output_path = PUBLIC_FOLDER / f"{job_id}_audio.wav"
    command = [
        'ffmpeg', '-i', str(video_path),
        '-ar', '16000',      # 16kHz
        '-ac', '1',          # mono
        '-c:a', 'pcm_s16le', # 16-bit PCM
        '-y', str(audio_output_path)
    ]
    try:
        print("Converting video to WAV for Whisper...", file=sys.stderr)
        subprocess.run(command, check=True, capture_output=True, text=True)
        print("Conversion successful.", file=sys.stderr)
        return str(audio_output_path)
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg error: {e.stderr}", file=sys.stderr)
        raise RuntimeError(f"FFmpeg failed: {e.stderr}")

def transcribe_audio(wav_path: str) -> dict:
    """Run Whisper on the provided WAV file and return the full result dict."""
    whisper_model = load_whisper()
    result = whisper_model.transcribe(wav_path)
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        return {"text": result, "segments": []}
    # Fallback if a sequence of segments is returned
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

import re

# Remove paired <think>...</think> blocks that some LLMs prepend.
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

def _extract_json(text: str):
    """Extract the first JSON object or array found in *text*."""
    decoder = json.JSONDecoder()
    text = text.strip()
    # Remove any <think>...</think> commentary that may precede the JSON
    text = _THINK_TAG_RE.sub("", text)
    text = text.replace("<think>", "")   # handle stray opening tag
    text = text.replace("</think>", "")  # handle stray closing tag
    # Remove Markdown-style code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n", "", text)
        if text.endswith("```"):
            text = text[:-3]

    for idx, ch in enumerate(text):
        if ch in "[{":
            try:
                obj, _ = decoder.raw_decode(text[idx:])
                return obj
            except json.JSONDecodeError:
                continue
    raise ValueError("No JSON object found in LLM output.")

def _normalize(text: str) -> str:
    """Normalize text for fuzzy matching."""
    return re.sub(r"[^a-z0-9\s]", "", text.lower())


def deduplicate_posts(posts: list[dict]) -> list[dict]:
    """Remove posts that share the same ``source_quote``."""
    seen = set()
    unique = []
    for post in posts:
        quote = post.get("source_quote")
        if quote and quote in seen:
            continue
        if quote:
            seen.add(quote)
        unique.append(post)
    return unique

def find_quote_timestamps(segments, quote, *, window: int = 20, threshold: float = 0.6):
    """Return start/end times and the snippet most similar to the quote.

    The search considers windows of ``window`` segments, building up candidate
    snippets and comparing them to the normalized quote using ``SequenceMatcher``
    similarity. The best scoring snippet is returned if its ratio meets or
    exceeds ``threshold``. Otherwise ``(None, None, None)`` is returned.
    """
    if not quote:
        return None, None, None

    target = _normalize(quote)
    best_ratio = 0.0
    best_result = (None, None, None)
    n = len(segments)

    for i in range(n):
        combined = ""
        start = None
        end = None
        for j in range(window):
            if i + j >= n:
                break
            seg = segments[i + j]
            if start is None:
                start = seg.get("start")
            end = seg.get("end", end)
            if combined:
                combined += " "
            combined += seg.get("text", "")

            ratio = SequenceMatcher(None, _normalize(combined), target).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_result = (start, end, combined.strip())

    if best_ratio >= threshold:
        return best_result
    return None, None, None

def extract_clip(video_path, start, end, output_path):
    """Use ffmpeg to cut a clip from the video."""
    command = [
        "ffmpeg",
        "-ss",
        str(start),
        "-to",
        str(end),
        "-i",
        str(video_path),
        "-c",
        "copy",
        "-y",
        str(output_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg clip error: {e.stderr}", file=sys.stderr)
        return False

def parse_youtube(url, job_id):
    import yt_dlp
    from yt_dlp.utils import DownloadError

    class _Logger:
        def debug(self, msg):
            pass
        def warning(self, msg):
            pass
        def error(self, msg):
            print(msg, file=sys.stderr)

    print("Downloading YouTube video...", file=sys.stderr)
    video_path = PUBLIC_FOLDER / f"{job_id}_full.mp4"
    ydl_opts = {
        'format': 'bv+ba/b',
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
    print(f"Downloaded to: {video_path}", file=sys.stderr)

    wav_path = convert_to_wav(video_path, job_id)

    print("Transcribing audio...", file=sys.stderr)
    transcript_result = transcribe_audio(wav_path)
    transcript_text = transcript_result.get("text", "")
    segments = transcript_result.get("segments", [])
    print("Transcription complete.", file=sys.stderr)

    return transcript_text, str(video_path), segments

def parse_pdf(file_path, job_id):
    import fitz
    doc = fitz.open(file_path)
    full_text = ""
    image_paths = []
    for page_num, page in enumerate(doc):
        full_text += f"\n\n--- Page {page_num + 1} ---\n\n"
        full_text += page.get_text("text")
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            img_filename = f"{job_id}_page{page_num + 1}_img{img_index}.{image_ext}"
            img_path = PUBLIC_FOLDER / img_filename
            with open(img_path, "wb") as f:
                f.write(image_bytes)
            image_paths.append({"path": f"/generated/{img_filename}", "page": page_num + 1})
    return full_text, image_paths

# --- LLM Post Generation ---
def generate_posts_from_text(context, source_type):
    system_prompt_template = """You are a viral social media content creator. Your task is to analyze the provided text and extract key quotes, ideas, and concepts.
For each extracted item, create a short, engaging social media post.
You MUST provide your output as a valid JSON array of objects.
Respond with ONLY the JSON text – no Markdown, explanations or other prose. If you cannot generate content, return an empty JSON array `[]`.
Each object in the array must have the following keys:
- "post_text": A string containing the social media post content (max 280 characters), including relevant hashtags.
- "source_quote": The exact quote or phrase from the source text that inspired the post.
- Each `source_quote` value must be unique across the array; do not repeat the same quote for multiple posts.

If the source is a PDF and the input includes page number markers (e.g., "--- Page 5 ---"), you MUST also include:
- "page_number": The integer page number where the content was found.

The input text may be a chunk of a larger document. Focus on extracting relevant information from this specific chunk.

Here is an example of the required output format:
[
  {
    "post_text": "Mind-blowing insight! The key to success is not just hard work, but smart work. #Productivity #Success",
    "source_quote": "The key to success is not just hard work, but smart work"
  }
"""

    # Estimate tokens per character roughly
    chars_per_token = 4
    output_token_buffer = 1024
    # Max tokens for the content after accounting for system prompt, user prompt, and output
    max_context_tokens = 4096 - (len(system_prompt_template) + output_token_buffer)
    max_context_chars = max_context_tokens * chars_per_token

    llm = load_llm()
    all_posts = []
    # Split context into chunks
    for i in range(0, len(context), max_context_chars):
        chunk = context[i:i + max_context_chars]

        messages = [
            {"role": "system", "content": system_prompt_template},
            {
                "role": "user",
                "content": (
                    f"Here is the content from a {source_type}. "
                    f"Please generate the JSON array now:\n\n{chunk}"
                ),
            },
        ]

        logging.debug("LLM INPUT: %s", json.dumps(messages, ensure_ascii=False))

        chat_completion = llm.create_chat_completion(
            messages=messages,
            temperature=0.2,
            max_tokens=output_token_buffer,
        )

        response_content = chat_completion['choices'][0]['message']['content']
        logging.debug("LLM OUTPUT: %s", response_content)
        print("--- RAW LLM OUTPUT ---", file=sys.stderr)
        print(response_content, file=sys.stderr)
        print("--- END RAW LLM OUTPUT ---", file=sys.stderr)

        try:
            data = _extract_json(response_content)
            if isinstance(data, dict) and len(data) == 1 and isinstance(list(data.values())[0], list):
                posts = list(data.values())[0]
            else:
                posts = data
            all_posts.extend(posts)
        except Exception as e:
            # Propagate a clear error so the caller can fail the job instead of
            # continuing with empty results.
            error_msg = f"Failed to parse LLM output: {e}. Raw output: {response_content}"
            print(f"Error parsing JSON output: {e}", file=sys.stderr)
            print(f"Raw output: {response_content}", file=sys.stderr)
            raise ValueError(error_msg)

    return all_posts

# --- Main Execution ---
if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(json.dumps({"status": "failed", "error": "Internal error: Incorrect script arguments."}), file=sys.stderr)
        sys.exit(1)

    input_type = sys.argv[1]
    input_data = sys.argv[2]
    job_id = sys.argv[3]

    existing_posts = load_existing_posts(job_id)
    existing_media = list(PUBLIC_FOLDER.glob(f"{job_id}_*"))
    if existing_posts or existing_media:
        print(json.dumps({"status": "complete", "posts": existing_posts}))
        sys.exit(0)

    load_llm()
    load_whisper()

    results = []
    try:
        if input_type == "youtube":
            transcript_text, full_video_path, segments = parse_youtube(input_data, job_id)
            if not transcript_text.strip():
                raise ValueError("Transcription failed or video contains no speech.")
            posts_data = generate_posts_from_text(transcript_text, "YouTube video")
            posts_data = deduplicate_posts(posts_data)
            for idx, post in enumerate(posts_data):
                quote = post.get("source_quote")
                start, end, snippet = find_quote_timestamps(segments, quote)
                if start is not None and end is not None:
                    post["start_time"] = start
                    post["end_time"] = end
                    if snippet:
                        post["quote_snippet"] = snippet
                    clip_filename = f"{job_id}_clip{idx + 1}.mp4"
                    clip_path = PUBLIC_FOLDER / clip_filename
                    if extract_clip(full_video_path, start, end, clip_path):
                        post["media_path"] = f"/generated/{clip_filename}"
                if "media_path" not in post:
                    post["media_path"] = f"/generated/{Path(full_video_path).name}"
            results = posts_data

        elif input_type == "pdf":
            text, image_paths = parse_pdf(input_data, job_id)
            posts_data = generate_posts_from_text(text, "PDF document")
            posts_data = deduplicate_posts(posts_data)
            for post in posts_data:
                page = post.get('page_number')
                if page:
                    relevant_image = next((img for img in image_paths if img['page'] == page), None)
                    if relevant_image:
                        post['media_path'] = relevant_image['path']
            results = posts_data

        elif input_type == "text":
            results = deduplicate_posts(generate_posts_from_text(input_data, "text document"))

        print(json.dumps({"status": "complete", "posts": results}))

    except Exception as e:
        import traceback
        error_message = f"An unexpected error occurred: {str(e)}"
        print(json.dumps({"status": "failed", "error": error_message}), file=sys.stderr)
        sys.exit(1)
