import sys
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse
import wave  # For checking audio properties

# --- LLM & Whisper Model Imports ---
from llama_cpp import Llama
from whispercpp import Whisper  # FIXED

# --- Configuration ---
MODEL_DIRECTORY = os.path.expanduser("~/.cache/lm-studio/models")

# LLaMA-style text generator model
LLM_MODEL_PATH = os.path.join(MODEL_DIRECTORY, "lmstudio-community/Qwen3-1.7B-GGUF/Qwen3-1.7B-Q8_0.gguf")

# Whisper model identifier or path accepted by whispercpp.  We default to the
# "base.en" model name but also allow specifying a path to a local GGUF file.
# When a local path is provided, the helper will load that file directly.
WHISPER_MODEL_NAME = "base.en"
# Use a locally downloaded GGUF model if available.  The from_pretrained helper
# accepts a path to the GGUF file so we expand the user's home directory and
# provide that path.
WHISPER_MODEL_PATH = os.path.expanduser("~/whisper_models/ggml-base.en.bin")

PUBLIC_FOLDER = Path("./public/generated")
PUBLIC_FOLDER.mkdir(exist_ok=True, parents=True)

# --- Model Initialization ---
LLM_TEXT_GENERATOR = Llama(
    model_path=LLM_MODEL_PATH,
    n_gpu_layers=-1,
    n_ctx=4096,
    verbose=True,
    chat_format="qwen"
)

# The whispercpp library provides a helper to load the pretrained model by
# name which handles any required downloads and conversions.
# Initialize the Whisper transcriber using the recommended helper. We supply
# the local model path so the script uses the already downloaded GGUF file.
WHISPER_TRANSCRIBER = Whisper.from_pretrained(WHISPER_MODEL_PATH)


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

def parse_youtube(url, job_id):
    import yt_dlp

    print("Downloading YouTube video...", file=sys.stderr)
    video_path = PUBLIC_FOLDER / f"{job_id}_full.mp4"
    ydl_opts = {
        'format': 'bv+ba/b',
        'outtmpl': str(video_path),
        'quiet': True,
        'merge_output_format': 'mp4',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    print(f"Downloaded to: {video_path}", file=sys.stderr)

    wav_path = convert_to_wav(video_path, job_id)

    print("Transcribing audio...", file=sys.stderr)
    transcription = WHISPER_TRANSCRIBER.transcribe(wav_path)
    transcript_text = transcription["text"]
    print("Transcription complete.", file=sys.stderr)
    
    return transcript_text, str(video_path)

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
    system_prompt = """You are a viral social media content creator. Your task is to analyze the provided text and extract key quotes, ideas, and concepts.
For each extracted item, create a short, engaging social media post.
You MUST provide your output as a valid JSON array of objects.
Do not output any other text, explanations, or markdown formatting. Your entire response must be only the raw JSON.
Each object in the array must have the following keys:
- "post_text": A string containing the social media post content (max 280 characters), including relevant hashtags.
- "source_quote": The exact quote or phrase from the source text that inspired the post.
If the source is a PDF with page numbers (e.g., "--- Page 5 ---"), you MUST also include:
- "page_number": The integer page number where the content was found.
Here is an example of the required output format:
[
  {
    "post_text": "Mind-blowing insight! The key to success is not just hard work, but smart work. #Productivity #Success",
    "source_quote": "The key to success is not just hard work, but smart work"
  }
]
"""
    chat_completion = LLM_TEXT_GENERATOR.create_chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Here is the content from a {source_type}. Please generate the JSON array now:\n\n{context}"},
        ],
        temperature=0.2,
        max_tokens=2048,
    )
    
    response_content = chat_completion['choices'][0]['message']['content']
    print("--- RAW LLM OUTPUT ---", file=sys.stderr)
    print(response_content, file=sys.stderr)
    print("--- END RAW LLM OUTPUT ---", file=sys.stderr)

    try:
        if response_content.strip().startswith("```json"):
            response_content = response_content.strip()[7:-3]
        json_start_index = response_content.find('[')
        if json_start_index == -1:
            json_start_index = response_content.find('{')
        response_content = response_content[json_start_index:]
        data = json.loads(response_content)
        if isinstance(data, dict) and len(data) == 1 and isinstance(list(data.values())[0], list):
            return list(data.values())[0]
        return data
    except Exception as e:
        print(f"Error parsing JSON output: {e}", file=sys.stderr)
        print(f"Raw output: {response_content}", file=sys.stderr)
        return []

# --- Main Execution ---
if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(json.dumps({"status": "failed", "error": "Internal error: Incorrect script arguments."}), file=sys.stderr)
        sys.exit(1)
        
    input_type = sys.argv[1]
    input_data = sys.argv[2]
    job_id = sys.argv[3]

    results = []
    try:
        if input_type == "youtube":
            transcript_text, full_video_path = parse_youtube(input_data, job_id)
            if not transcript_text.strip():
                raise ValueError("Transcription failed or video contains no speech.")
            posts_data = generate_posts_from_text(transcript_text, "YouTube video")
            if posts_data:
                posts_data[0]['media_path'] = f"/generated/{Path(full_video_path).name}"
            results = posts_data

        elif input_type == "pdf":
            text, image_paths = parse_pdf(input_data, job_id)
            posts_data = generate_posts_from_text(text, "PDF document")
            for post in posts_data:
                page = post.get('page_number')
                if page:
                    relevant_image = next((img for img in image_paths if img['page'] == page), None)
                    if relevant_image:
                        post['media_path'] = relevant_image['path']
            results = posts_data

        elif input_type == "text":
            results = generate_posts_from_text(input_data, "text document")

        print(json.dumps({"status": "complete", "posts": results}))

    except Exception as e:
        import traceback
        error_message = f"An unexpected error occurred: {str(e)}"
        print(json.dumps({"status": "failed", "error": error_message}), file=sys.stderr)
        sys.exit(1)
