# Developer Guide

This project is a small "Content Atomizer" application built with Next.js, Prisma and a Python helper script.  It takes YouTube videos, PDFs or plain text and turns them into shareable social media posts.

The instructions below walk through setting up the environment, understanding the code layout and running tests.

## Prerequisites

- **Node.js** (18 or newer) and `npm`
- **Python** (3.10+ recommended)
- `ffmpeg` for video processing
- Optionally, models for LLaMA and Whisper placed in `~/.cache/lm-studio/models` and `~/whisper_models`

## Installing dependencies

1. Install Node packages:
   ```bash
   npm install
   ```
2. Set up a Python virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Prepare the database. Prisma uses SQLite by default. Create an `.env` file with a `DATABASE_URL` variable, then push the schema:
   ```bash
   npx prisma db push
   ```
4. (Optional) Generate the Prisma client:
   ```bash
   npx prisma generate
   ```

## Running the development server

Start Next.js with:
```bash
npm run dev
```
Visit `http://localhost:3000` to use the web interface. From the page you can submit a YouTube link, upload a PDF or paste text. The backend API creates a job, spawns the Python script and polls until processing finishes. Generated clips and images are saved under `public/generated/`.

## Directory overview

- `src/app` – Next.js pages and API routes. The main API endpoint is `src/app/api/process/route.ts` which launches the Python script.
- `src/components` – React components (e.g. `SocialPostCard.tsx` for displaying results).
- `scripts/main.py` – The heavy lifting. Downloads and transcribes videos, parses PDFs, calls the LLaMA text generator and returns JSON results.
- `prisma/schema.prisma` – Database models `Job` and `Post`. Each job tracks user input and generated posts.
- `public/generated` – Media assets produced by the Python script.
- `tests` – Unit tests for Python helpers.

### Database schema

The project uses SQLite via Prisma. Two tables form the main data model:

- **Job** – records each content-processing request.
  - `id` *(string, primary key)* – unique identifier created by Prisma.
  - `inputType` *(string)* – `youtube`, `pdf` or `text`.
  - `inputData` *(string)* – URL, file path or text snippet.
  - `inputChecksum` *(string, optional)* – SHA256 of the input used to detect duplicate submissions.
  - `status` *(string)* – job state: `pending`, `processing`, `complete` or `failed`.
  - `error` *(string, optional)* – reason if the job fails.
  - `createdAt` and `updatedAt` timestamps.
- **Post** – stores each generated social media post.
  - `id` *(string, primary key)* – unique identifier.
  - `jobId` *(string)* – links back to the `Job` entry.
  - `content` *(string)* – post text.
  - `mediaPath` *(string, optional)* – path to video clips or images under `public/generated`.
  - `startTime` and `endTime` *(float, optional)* – clip boundaries for video posts.
  - `quoteSnippet` *(string, optional)* – excerpt from the source.
  - `pageNumber` *(integer, optional)* – PDF page reference.
  - `createdAt` timestamp.

The API creates a **Job** when a request begins and fills the **Post** table with results once the Python script completes.

### Major modules and functions

- **`scripts/main.py`** holds most of the backend logic. Key helpers include:
  - `convert_to_wav()` – converts a downloaded video into a mono 16 kHz WAV file for Whisper.
  - `transcribe_audio()` – runs the Whisper model and returns a transcript and segment timings.
  - `find_quote_timestamps()` – searches transcription segments to locate quoted phrases and returns their start and end times.
  - `extract_clip()` – uses ffmpeg to cut a short video clip for a given time window.
  - `parse_youtube()` – downloads YouTube videos, transcribes them and returns text plus segments.
  - `parse_pdf()` – extracts text and inline images from PDFs so posts can reference page numbers or images.
  - `generate_posts_from_text()` – sends content to the LLaMA model and parses the returned JSON posts.
  - The script's `__main__` block orchestrates these helpers according to the input type and prints JSON results.
- **`src/app/api/process/route.ts`** contains the Next.js API route. Its `POST` handler saves a job in the database, spawns `main.py`, then parses its output into `Post` records. The `GET` handler lets the frontend poll job status.
- The handler checks the SHA256 checksum of uploaded files (or the URL for YouTube inputs) and reuses existing jobs when a duplicate submission is detected.
- **`src/components/SocialPostCard.tsx`** renders each generated post and any associated media.

## Running the Python script directly

The script accepts three arguments:
```bash
python scripts/main.py <input_type> <input_data> <job_id>
```
`<input_type>` is `youtube`, `pdf` or `text`. `<input_data>` is a URL, file path or text. `<job_id>` can be any identifier (the web app generates one automatically).
If a YouTube video requires authentication, create a `.env` file in the project
root with `YTDLP_COOKIE_FILE` set to the path of a browser-exported cookies
file. The Python helper automatically loads `.env` if present. Consult the
[yt-dlp documentation](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp)
for tips on exporting cookies.
Example:
```bash
python scripts/main.py youtube https://www.youtube.com/watch?v=dQw4w9WgXcQ test123
```

Results are printed as JSON to standard output.

## Running tests

Python unit tests verify helper functions in `scripts/main.py`. Activate the virtual environment and run:
```bash
pytest
```
All current tests should pass.

## Building for production

For a production build of the Next.js app run:
```bash
npm run build
npm start
```

## Further resources

- [Next.js Documentation](https://nextjs.org/docs)
- [Prisma Documentation](https://www.prisma.io/docs)
- [Whisper](https://github.com/openai/whisper) and [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) libraries

This guide should give newcomers the steps required to install dependencies, run the application and understand where each piece of the code lives.
