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

If downloading a YouTube video fails because authentication is required, create
a `.env` file in the project root and set `YTDLP_COOKIE_FILE` to the path of a
browser-exported cookies file. The helper script automatically loads this file
when present. See the [yt-dlp cookies guide](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp)
for instructions on exporting cookies.

For details on how the modules work, test commands and production deployment see the [Developer Guide](./DEVELOPER_GUIDE.md).
