import sys
import json
import os
import logging
import sqlite3
from pathlib import Path

# Ensure local modules are importable when loaded as a library
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Load environment variables from an optional .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Import our processors and managers
from processors.youtube_processor import YouTubeProcessor
from processors.pdf_processor import PDFProcessor  
from processors.text_processor import TextProcessor
from models.llm_manager import LLMManager
from models.whisper_manager import WhisperManager

# Configuration
PUBLIC_FOLDER = Path(__file__).resolve().parents[1] / "public" / "generated"
PUBLIC_FOLDER.mkdir(exist_ok=True, parents=True)


def find_quote_timestamps(segments, quote, window=20, threshold=0.55, context_padding=0.0):
    """Convenience wrapper for YouTubeProcessor.find_quote_timestamps."""
    yt = YouTubeProcessor(PUBLIC_FOLDER, WATERMARK_PATH)
    start, end, snippet = yt.find_quote_timestamps(
        segments,
        quote,
        window=window,
        threshold=threshold,
        context_padding=context_padding,
    )
    if start is None and snippet:
        start = 0.0
    return start, end, snippet


def load_llm(backend: str | None = None):
    """Thin wrapper around LLMManager.load_llm so tests can stub it."""
    return llm_manager.load_llm(backend)


def generate_posts_from_text(context: str, source_type: str, llm_backend: str = None):
    """Generate high-quality social media posts with enhanced prompting."""
    system_prompt = """You are creating authentic, engaging social media posts from source material.

Your posts should:
- Sound natural and conversational (avoid "mind-blowing" or "game-changing" clichés)
- Vary in style - some can be questions, observations, quick tips, or thought starters
- Stay under 280 characters total
- Use minimal emojis (0-2 max, only when they add value)
- Feel like something a real person would share, not marketing copy

Extract meaningful insights and present them in diverse ways:
- "Ever notice how..."
- "Quick thought on..."
- "This changed my perspective:"
- "Worth remembering:"
- Or just state the insight directly

You MUST provide your output as a valid JSON array of objects with ONLY the JSON text.
Each object must have:
- "post_text": The complete social media post (under 280 chars)
- "source_quote": The exact phrase from source that inspired this post
- Each source_quote must be unique

For PDFs with page markers, also include:
- "page_number": The page number as an integer

Examples of good variety:
[
  {
    "post_text": "The most successful people aren't just working harder - they're working smarter. Focus on leverage, not just effort. #productivity",
    "source_quote": "The key to success is not just hard work, but smart work"
  },
  {
    "post_text": "Quick reminder: your attention is your most valuable resource. Where you focus determines your reality. #mindfulness #focus",
    "source_quote": "What you pay attention to becomes your experience"
  },
  {
    "post_text": "Ever wonder why some habits stick and others don't? It's about environment design, not willpower. #habits",
    "source_quote": "Environment is the invisible hand that shapes human behavior"
  }
]"""

    chars_per_token = 4
    output_token_buffer = 1024
    base_context_tokens = 8192
    max_context_tokens = base_context_tokens - (len(system_prompt) + output_token_buffer)
    max_context_chars = max_context_tokens * chars_per_token

    logging.info("generate_posts_from_text: %d chars from %s using %s", len(context), source_type, llm_backend or "default")
    print(f"🤖 Generating viral social media posts using {llm_backend or 'default'} model...", file=sys.stderr)

    llm = load_llm(llm_backend)  # Pass the backend parameter
    all_posts = []

    for i in range(0, len(context), max_context_chars):
        chunk = context[i:i + max_context_chars]
        logging.debug("generate_posts_from_text: processing chunk %d-%d", i, i + len(chunk))

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Extract the most VIRAL quotes from this {source_type}. Focus on controversial, surprising, or valuable insights that people will want to share:\n\n{chunk}"
            }
        ]

        logging.debug("LLM INPUT: %s", json.dumps(messages, ensure_ascii=False))

        chat_completion = llm.create_chat_completion(
            messages=messages,
            temperature=0.4,
            max_tokens=output_token_buffer,
        )

        response_content = chat_completion['choices'][0]['message']['content']
        logging.debug("LLM OUTPUT: %s", response_content)
        print("--- RAW LLM OUTPUT ---", file=sys.stderr)
        print(response_content, file=sys.stderr)
        print("--- END RAW LLM OUTPUT ---", file=sys.stderr)

        try:
            data = llm_manager.extract_json(response_content)
            if isinstance(data, dict):
                if len(data) == 1 and isinstance(list(data.values())[0], list):
                    posts = list(data.values())[0]
                elif "post_text" in data and "source_quote" in data:
                    posts = [data]
                else:
                    raise ValueError("JSON object does not contain expected structure")
            elif isinstance(data, list):
                posts = data
            else:
                raise ValueError("JSON output must be a list of objects")

            if any(not isinstance(p, dict) for p in posts):
                raise ValueError("JSON array must contain objects")

            valid_posts = []
            for post in posts:
                if isinstance(post, dict) and "post_text" in post and "source_quote" in post:
                    valid_posts.append(post)
                else:
                    logging.warning("Skipping invalid post: %s", post)

            all_posts.extend(valid_posts)
            print(f"Extracted {len(valid_posts)} posts from chunk", file=sys.stderr)

        except Exception as e:
            error_msg = f"Failed to parse LLM output: {e}. Raw output: {response_content}"
            print(f"Error parsing JSON output: {e}", file=sys.stderr)
            logging.warning("Chunk processing failed: %s", error_msg)
            raise ValueError(error_msg)

    final_posts = deduplicate_posts(all_posts)
    logging.info("generate_posts_from_text: produced %d final posts", len(final_posts))
    print(f"Generated {len(final_posts)} viral posts", file=sys.stderr)

    return final_posts


def deduplicate_posts(posts: list[dict]) -> list[dict]:
    """Expose LLMManager.deduplicate_posts for tests."""
    return llm_manager.deduplicate_posts(posts)

WATERMARK_PATH = os.getenv(
    "WATERMARK_PATH",
    str(Path(__file__).resolve().parents[1] / "public" / "aiprepperWM.png"),
)

# Debug logging
_log_path = os.getenv("LLM_DEBUG_LOG", "llm_debug.log")
logging.basicConfig(filename=_log_path, level=logging.DEBUG,
                    format="%(asctime)s %(levelname)s %(message)s")
logging.info("Logging initialized at %s", _log_path)

# Global managers
llm_manager = LLMManager()
whisper_manager = WhisperManager()

def save_transcript_simple(job_id: str, transcript: str):
    """Save transcript with simple, direct approach."""
    print(f"💾 SAVING TRANSCRIPT: {len(transcript)} chars for job {job_id}", file=sys.stderr)
    
    # Get database path with multiple fallback locations
    db_url = os.getenv("DATABASE_URL")
    if db_url.startswith("file:"):
        db_url = db_url[5:]
    
    # Try multiple possible locations for the database
    project_root = Path(__file__).resolve().parents[1]
    possible_paths = [
        str(project_root / db_url.lstrip("./")),  # PROJECT_ROOT/dev.db
        str(project_root / "prisma" / db_url.lstrip("./")),  # PROJECT_ROOT/prisma/dev.db  
        db_url if os.path.isabs(db_url) else None,  # Absolute path if provided
    ]
    
    db_path = None
    for path in possible_paths:
        if path and os.path.exists(path):
            db_path = path
            print(f"💾 Found database at: {db_path}", file=sys.stderr)
            break
    
    if not db_path:
        print(f"❌ Database not found. Tried:", file=sys.stderr)
        for path in possible_paths:
            if path:
                print(f"   - {path} (exists: {os.path.exists(path)})", file=sys.stderr)
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Update transcript
        cursor.execute("UPDATE Job SET transcript = ? WHERE id = ?", (transcript, job_id))
        rows_updated = cursor.rowcount
        conn.commit()
        conn.close()
        
        print(f"💾 DATABASE UPDATE: {rows_updated} rows affected", file=sys.stderr)
        
        if rows_updated > 0:
            print("✅ TRANSCRIPT SAVED TO DATABASE", file=sys.stderr)
            return True
        else:
            print("❌ NO ROWS UPDATED - JOB NOT FOUND?", file=sys.stderr)
            return False
            
    except Exception as e:
        print(f"❌ DATABASE ERROR: {e}", file=sys.stderr)
        return False

def load_existing_posts(job_id: str) -> list[dict]:
    """Load posts for job_id from the database if present."""
    logging.info("load_existing_posts: job_id=%s", job_id)
    
    # Use same database path resolution as save_transcript_simple
    db_url = os.getenv("DATABASE_URL")
    if db_url.startswith("file:"):
        db_url = db_url[5:]
    
    project_root = Path(__file__).resolve().parents[1]
    possible_paths = [
        str(project_root / db_url.lstrip("./")),  # PROJECT_ROOT/dev.db
        str(project_root / "prisma" / db_url.lstrip("./")),  # PROJECT_ROOT/prisma/dev.db  
        db_url if os.path.isabs(db_url) else None,  # Absolute path if provided
    ]
    
    db_path = None
    for path in possible_paths:
        if path and os.path.exists(path):
            db_path = path
            break
    
    if not db_path:
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
    except Exception as exc:
        logging.error("load_existing_posts error: %s", exc)
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
    logging.info("load_existing_posts: loaded %d posts", len(posts))
    return posts

def cleanup_old_files(days=30):
    """Clean up files older than specified days."""
    import time
    cutoff = time.time() - (days * 24 * 60 * 60)
    cleaned = 0
    for file_path in PUBLIC_FOLDER.glob("*"):
        try:
            if file_path.stat().st_mtime < cutoff:
                file_path.unlink()
                cleaned += 1
        except Exception as e:
            logging.warning("Failed to delete old file %s: %s", file_path, e)
    if cleaned > 0:
        logging.info("Cleaned up %d old files", cleaned)
        print(f"Cleaned up {cleaned} old files", file=sys.stderr)

def process_clip_request(job_id, post_id, quote):
    """Handle clip extraction request."""
    youtube_processor = YouTubeProcessor(PUBLIC_FOLDER, WATERMARK_PATH)
    
    segments_file = PUBLIC_FOLDER / f"{job_id}_segments.json"
    video_path = PUBLIC_FOLDER / f"{job_id}_full.mp4"
    
    if not segments_file.exists() or not video_path.exists():
        raise RuntimeError("Required files not found.")
    
    with open(segments_file, "r") as f:
        segments = json.load(f)

    start, end, snippet = youtube_processor.find_quote_timestamps(segments, quote)
    if start is None or end is None:
        raise RuntimeError("Quote not found.")

    clip_path = PUBLIC_FOLDER / f"{post_id}.mp4"
    if not youtube_processor.extract_clip(video_path, start, end, clip_path):
        raise RuntimeError("Clip extraction failed.")

    result = {
        "status": "complete",
        "media_path": f"/generated/{post_id}.mp4",
        "start_time": start,
        "end_time": end,
    }
    if snippet:
        result["quote_snippet"] = snippet

    return result

def process_content(input_type, input_data, job_id, llm_backend):
    """Main content processing function."""
    print(f"🚀 PROCESSING: {input_type} for job {job_id}", file=sys.stderr)
    
    # Check for existing posts first
    existing_posts = load_existing_posts(job_id)
    existing_media = list(PUBLIC_FOLDER.glob(f"{job_id}_*"))
    if existing_posts or existing_media:
        logging.info("Reusing existing output for job %s", job_id)
        print("Found existing results, reusing...", file=sys.stderr)
        return {"status": "complete", "posts": existing_posts}

    # Clean up old files periodically
    cleanup_old_files()

    # Load models
    llm_manager.load_llm(llm_backend)
    whisper_manager.load_whisper()

    # Initialize processors
    youtube_processor = YouTubeProcessor(PUBLIC_FOLDER, WATERMARK_PATH)
    pdf_processor = PDFProcessor(PUBLIC_FOLDER)
    text_processor = TextProcessor()

    results = []
    transcript_text = ""
    
    print(f"📝 STARTING CONTENT PROCESSING...", file=sys.stderr)
    
    if input_type == "youtube":
        print("📺 Processing YouTube video...", file=sys.stderr)
        transcript_text, full_video_path, segments = youtube_processor.process(
            input_data, job_id, whisper_manager
        )
        if not transcript_text.strip():
            raise ValueError("Transcription failed or video contains no speech.")
        
        print(f"📝 GOT TRANSCRIPT: {len(transcript_text)} characters", file=sys.stderr)
        posts_data = llm_manager.generate_posts_from_text(transcript_text, "YouTube video", llm_backend)
        results = posts_data

    elif input_type == "pdf":
        print("📄 Processing PDF...", file=sys.stderr)
        transcript_text, image_paths = pdf_processor.process(input_data, job_id)
        
        print(f"📝 GOT PDF TEXT: {len(transcript_text)} characters", file=sys.stderr)
        posts_data = llm_manager.generate_posts_from_text(transcript_text, "PDF document", llm_backend)
        
        # Associate images with posts based on page numbers
        for post in posts_data:
            page = post.get('page_number')
            if page:
                relevant_image = next((img for img in image_paths if img['page'] == page), None)
                if relevant_image:
                    post['media_path'] = relevant_image['path']
        results = posts_data

    elif input_type == "text":
        print("📝 Processing text...", file=sys.stderr)
        transcript_text = text_processor.process(input_data, job_id)
        
        print(f"📝 GOT TEXT: {len(transcript_text)} characters", file=sys.stderr)
        results = llm_manager.generate_posts_from_text(transcript_text, "text document", llm_backend)

    # SAVE TRANSCRIPT - This is the key part!
    if transcript_text and transcript_text.strip():
        print("💾 ATTEMPTING TO SAVE TRANSCRIPT...", file=sys.stderr)
        
        # Save to database
        db_success = save_transcript_simple(job_id, transcript_text)
        
        # Also save to file as backup
        transcript_file = PUBLIC_FOLDER / f"{job_id}_transcript.txt"
        try:
            with open(transcript_file, "w", encoding="utf-8") as f:
                f.write(transcript_text)
            print(f"📁 BACKUP FILE SAVED: {transcript_file}", file=sys.stderr)
        except Exception as e:
            print(f"📁 BACKUP FILE ERROR: {e}", file=sys.stderr)
        
        if db_success:
            print("✅ TRANSCRIPT SAVE COMPLETE", file=sys.stderr)
        else:
            print("⚠️  DATABASE SAVE FAILED (but backup file created)", file=sys.stderr)
    else:
        print("❌ NO TRANSCRIPT TO SAVE", file=sys.stderr)

    logging.info("Processing complete for job %s", job_id)
    print("🎉 PROCESSING COMPLETE!", file=sys.stderr)
    return {"status": "complete", "posts": results}

if __name__ == "__main__":
    logging.info("script start: %s", sys.argv)
    
    if len(sys.argv) < 2:
        print(json.dumps({"status": "failed", "error": "Internal error: Incorrect script arguments."}), file=sys.stderr)
        sys.exit(1)

    input_type = sys.argv[1]

    # Handle clip extraction requests
    if input_type == "clip":
        if len(sys.argv) < 5:
            print(json.dumps({"status": "failed", "error": "Internal error: Incorrect script arguments."}), file=sys.stderr)
            sys.exit(1)
        
        job_id = sys.argv[2]
        post_id = sys.argv[3]
        quote = sys.argv[4]

        try:
            result = process_clip_request(job_id, post_id, quote)
            print(json.dumps(result))
            sys.exit(0)
        except Exception as e:
            error_msg = str(e)
            logging.error("clip extraction error: %s", error_msg)
            print(json.dumps({"status": "failed", "error": error_msg}), file=sys.stderr)
            sys.exit(1)

    # Handle content processing requests
    if len(sys.argv) < 4:
        print(json.dumps({"status": "failed", "error": "Internal error: Incorrect script arguments."}), file=sys.stderr)
        sys.exit(1)

    input_data = sys.argv[2]
    job_id = sys.argv[3]
    llm_backend = sys.argv[4] if len(sys.argv) >= 5 else "phi"

    try:
        result = process_content(input_type, input_data, job_id, llm_backend)
        print(json.dumps(result))
        sys.exit(0)
    except Exception as e:
        import traceback
        error_message = f"An unexpected error occurred: {str(e)}"
        logging.error("script error: %s", error_message)
        logging.error("traceback: %s", traceback.format_exc())
        print(json.dumps({"status": "failed", "error": error_message}), file=sys.stderr)
        sys.exit(1)