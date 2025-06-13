# Content Atomizer

This repository contains a small Next.js application and Python helper script that turn YouTube videos, PDFs or text into short social media posts.

If you're setting up the project for development please read the [Developer Guide](./DEVELOPER_GUIDE.md) for step‑by‑step instructions on installing dependencies, running the app and understanding the code structure.

Below is a quick start summary.

## Quick start

1. Install Node and Python packages:
   ```bash
   npm install
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and edit any values as needed:
   ```bash
   cp .env.example .env
   ```
   The example lists variables such as `DATABASE_URL`, `YTDLP_COOKIE_FILE`,
   `YTDLP_VIDEO_FORMAT`, `GOOGLE_API_KEY` and `WHISPER_MODEL_PATH` used by the application.
3. Initialize the SQLite database with Prisma:
   ```bash
   npx prisma db push
   ```
4. Launch the development server:
   ```bash
   npm run dev
   ```

Open [http://localhost:3000](http://localhost:3000) to access the web interface. Upload a PDF, paste text or provide a YouTube URL and the backend will generate sample posts in `public/generated/`.

The server automatically detects duplicate submissions. When the same URL is
submitted again or an uploaded file matches a previously processed SHA256
checksum the existing posts are returned instead of reprocessing the content.

If downloading a YouTube video fails because authentication is required, set
`YTDLP_COOKIE_FILE` in your `.env` file (see `.env.example` for all supported
variables) to the path of a browser-exported cookies file. The helper script
automatically loads this file when present. See the
[yt-dlp cookies guide](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp)
for instructions on exporting cookies.

You can also reduce the size of downloaded videos by limiting the format used by
`yt_dlp`. Set `YTDLP_VIDEO_FORMAT` in your `.env` file to a format string (for
example `bestvideo[height<=720]+bestaudio/best[height<=720]`). This value
defaults to that 720p-limited string when unset.

To use the Gemini 2.5 Pro Preview model set `GOOGLE_API_KEY` in your `.env`.
The home page lets you pick either the local Phi model or Gemini from a drop‑down.

To use a custom Whisper transcription model specify `WHISPER_MODEL_PATH` in `.env`.

If you want to brand generated clips with a watermark image, place
`aiprepperWM.png` in the `public` folder or set the `WATERMARK_PATH`
environment variable to point to your own watermark file. The helper script will
overlay this image on the bottom right of each extracted clip.

For details on how the modules work, test commands and production deployment see the [Developer Guide](./DEVELOPER_GUIDE.md).
