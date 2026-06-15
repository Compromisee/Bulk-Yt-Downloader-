# Bulk Yt Downlaoder YouTube Downloader

A sleek, YouTube-style bulk downloader built with Flask + yt-dlp.

## Features
- **Search Videos** — Search YouTube directly, add to cart or download instantly
- **Channel Browser** — Enter any channel URL/@handle, browse & bulk download
- **Playlist Downloader** — Paste a playlist URL, pick items or download all
- **URL Download** — Paste one or many video URLs for bulk download
- **Download Cart** — Add videos from anywhere, then bulk download in one click
- **Formats:** MP4, MKV, MP3
- **Quality:** 4K, 1080p, 720p, 480p, 360p, Best Available
- **Multithreading** — 6 concurrent downloads via ThreadPoolExecutor
- **Real-time progress** — Live speed, ETA, and progress bars
- **File Manager** — Browse, download, and delete your files

## Install & Run

```bash
pip install flask yt-dlp
python run.py
# Open http://localhost:5000
```

## Requirements
- Python 3.8+
- flask
- yt-dlp
- ffmpeg (for MP4/MKV merging and MP3 conversion)

Install ffmpeg:
- **macOS:** `brew install ffmpeg`
- **Ubuntu/Debian:** `sudo apt install ffmpeg`
- **Windows:** Download from https://ffmpeg.org
Plz follow my progress!!
