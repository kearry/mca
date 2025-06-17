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
2. Initialize the SQLite database with Prisma:
   ```bash
   npx prisma db push
   ```
3. Launch the development server:
   ```bash
   npm run dev
   ```

Open [http://localhost:3000](http://localhost:3000) to access the web interface. Upload a PDF, paste text or provide a YouTube URL and the backend will generate sample posts in `public/generated/`.

The server automatically detects duplicate submissions. When the same URL is
submitted again or an uploaded file matches a previously processed SHA256
checksum the existing posts are returned instead of reprocessing the content.

If downloading a YouTube video fails because authentication is required, create
a `.env` file in the project root and set `YTDLP_COOKIE_FILE` to the path of a
browser-exported cookies file. The helper script automatically loads this file
when present. See the [yt-dlp cookies guide](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp)
for instructions on exporting cookies.

You can also reduce the size of downloaded videos by limiting the format used by
`yt_dlp`. Set `YTDLP_VIDEO_FORMAT` in your environment to a format string (for
example `bestvideo[height<=720]+bestaudio/best[height<=720]`). This value
defaults to that 720p-limited string when unset.

To use the Gemini 2.5 Flash Preview (model `gemini-2.5-flash-preview-05-20`) set `GOOGLE_API_KEY` in your environment.
The home page lets you pick from Gemini or one of the local models (Phi or DeepSeek‑R1) using a drop‑down.

If you want to brand generated clips with a watermark image, place
`aiprepperWM.png` in the `public` folder or set the `WATERMARK_PATH`
environment variable to point to your own watermark file. The helper script will
overlay this image on the bottom right of each extracted clip.

For details on how the modules work, test commands and production deployment see the [Developer Guide](./DEVELOPER_GUIDE.md).
