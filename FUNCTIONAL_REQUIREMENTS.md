# Functional Requirements

This document summarizes the primary functional capabilities provided by the application in this repository.

## 1. Input Handling
- The web interface allows a user to submit content in three forms:
  - **YouTube URL** – the system downloads and transcribes the video.
  - **PDF document** – the user can upload a PDF file for parsing.
  - **Plain text** – the user can paste raw text into a textarea.
- The selected input type and associated data are sent via `POST /api/process`.

## 2. Job Tracking
- Each submission creates a `Job` entry in the SQLite database with the input type, a summary of the input data and a processing status.
- `GET /api/process?jobId=<id>` allows the client to poll the status (`pending`, `processing`, `complete`, or `failed`).
- When the Python script finishes, the job status is updated and any generated posts are stored in related `Post` records.
- the Python script allows intelligent handling of re-submitted jobs

## 3. Content Processing Pipeline
- The backend spawns `scripts/main.py` with arguments specifying the input type, input data and job ID.
- For **YouTube** inputs the script:
  1. Downloads the video using `yt_dlp` (optionally with cookies from `YTDLP_COOKIE_FILE`).
  2. Converts the video to WAV audio via `ffmpeg` and transcribes it with Whisper.
  3. Generates social media posts with LLaMA using the transcript text.
  4. Locates quoted segments in the transcript, extracts short video clips and stores them under `public/generated/`.
- For **PDF** inputs the script:
  1. Extracts text and inline images from each page.
  2. Sends the combined text to LLaMA to generate posts.
  3. Associates any relevant page images with a post when the post references a page number.
- For **Plain text** inputs the script simply forwards the text to LLaMA to generate posts.
- The script emits a JSON payload of posts on success or a JSON error message on failure.

## 4. Social Media Post Format
- Each generated post contains:
  - Post text (`post_text`).
  - Source quote (`source_quote`).
  - Optional `media_path` to a video clip or image saved under `public/generated/`.
  - Optional `start_time` and `end_time` for video clips.
  - Optional `page_number` when derived from a PDF.
- The Next.js frontend displays posts using `SocialPostCard`, showing quotes and media when present.

## 5. Error Handling
- If the Python runtime is missing or the script fails, the job status is marked as `failed` and the error message is stored.
- The frontend presents any error messages returned by the API to the user.
- The frontend has a page that displays old jobs and their status, jobs may be submitted here

## 6. Testing
- Python unit tests under `tests/` verify helper functions such as `find_quote_timestamps` and `generate_posts_from_text`.
- Running `pytest` should result in all tests passing.

## 7. LLM and Chunking Details
- The `generate_posts_from_text()` helper sends content to the LLaMA text generator and parses the JSON response.
- Each chunk is passed along with a system prompt that instructs the model to output **only** a JSON array.
- Every array object must include `post_text` and `source_quote` fields and may include a `page_number` when processing PDFs.
- Long inputs are automatically split into chunks that fit within the 4k token context window. Each chunk is processed sequentially and the resulting posts are combined.

