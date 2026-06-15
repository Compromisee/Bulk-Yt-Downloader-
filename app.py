import os, uuid, threading, json, time, re
from flask import Flask, render_template, request, jsonify, send_from_directory, Response
from concurrent.futures import ThreadPoolExecutor
import yt_dlp

app = Flask(__name__)
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

executor = ThreadPoolExecutor(max_workers=6)

# In-memory job store
jobs = {}  # job_id -> {status, progress, filename, error, title}

# ─────────────── helpers ───────────────

def sanitize(s):
    return re.sub(r'[^\w\s\-.]', '', s)[:80]

def ydl_opts_base(fmt, quality, job_id, outtmpl):
    hooks = [lambda d: progress_hook(d, job_id)]
    video_quality = quality  # e.g. "1080", "720", "480", "360", "best"

    if fmt == "mp3":
        return {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "progress_hooks": hooks,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "quiet": True, "no_warnings": True,
        }
    elif fmt == "mkv":
        vq = f"bestvideo[height<={video_quality}]+bestaudio/best[height<={video_quality}]" if video_quality != "best" else "bestvideo+bestaudio/best"
        return {
            "format": vq,
            "outtmpl": outtmpl,
            "progress_hooks": hooks,
            "merge_output_format": "mkv",
            "quiet": True, "no_warnings": True,
        }
    else:  # mp4 default
        vq = f"bestvideo[height<={video_quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={video_quality}][ext=mp4]/best" if video_quality != "best" else "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        return {
            "format": vq,
            "outtmpl": outtmpl,
            "progress_hooks": hooks,
            "merge_output_format": "mp4",
            "quiet": True, "no_warnings": True,
        }

def progress_hook(d, job_id):
    if job_id not in jobs:
        return
    if d["status"] == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        downloaded = d.get("downloaded_bytes", 0)
        pct = int((downloaded / total) * 100) if total else 0
        speed = d.get("speed", 0) or 0
        eta = d.get("eta", 0) or 0
        jobs[job_id].update({
            "status": "downloading",
            "progress": pct,
            "speed": f"{speed/1024/1024:.1f} MB/s" if speed else "--",
            "eta": f"{eta}s" if eta else "--",
        })
    elif d["status"] == "finished":
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["progress"] = 99

def do_download(job_id, urls, fmt, quality, playlist_items=None):
    try:
        jobs[job_id]["status"] = "downloading"
        jobs[job_id]["progress"] = 0

        outtmpl = os.path.join(DOWNLOAD_DIR, f"{job_id}_%(title)s.%(ext)s")
        opts = ydl_opts_base(fmt, quality, job_id, outtmpl)

        if playlist_items:
            opts["playlist_items"] = playlist_items

        files_before = set(os.listdir(DOWNLOAD_DIR))

        with yt_dlp.YoutubeDL(opts) as ydl:
            info_list = []
            for url in urls:
                info = ydl.extract_info(url, download=True)
                if info:
                    info_list.append(info)

        files_after = set(os.listdir(DOWNLOAD_DIR))
        new_files = list(files_after - files_before)

        jobs[job_id].update({
            "status": "done",
            "progress": 100,
            "files": new_files,
            "count": len(new_files),
        })
    except Exception as e:
        jobs[job_id].update({"status": "error", "error": str(e), "progress": 0})

# ─────────────── routes ───────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/search")
def search():
    q = request.args.get("q", "").strip()
    limit = int(request.args.get("limit", 12))
    if not q:
        return jsonify({"error": "No query"}), 400
    try:
        opts = {
            "quiet": True, "no_warnings": True,
            "extract_flat": True, "skip_download": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            results = ydl.extract_info(f"ytsearch{limit}:{q}", download=False)
        entries = results.get("entries", []) if results else []
        videos = []
        for e in entries:
            if not e:
                continue
            videos.append({
                "id": e.get("id",""),
                "title": e.get("title",""),
                "channel": e.get("channel") or e.get("uploader",""),
                "duration": e.get("duration_string") or fmt_dur(e.get("duration")),
                "thumbnail": e.get("thumbnail") or f"https://i.ytimg.com/vi/{e.get('id','')}/hqdefault.jpg",
                "views": fmt_views(e.get("view_count")),
                "url": f"https://www.youtube.com/watch?v={e.get('id','')}",
            })
        return jsonify({"results": videos})
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

@app.route("/api/channel_info")
def channel_info():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL"}), 400
    try:
        opts = {
            "quiet": True, "no_warnings": True,
            "extract_flat": True, "skip_download": True,
            "playlistend": 30,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            return jsonify({"error": "Could not fetch channel"}), 400
        entries = info.get("entries", []) or []
        # flatten nested playlists
        flat = []
        for e in entries:
            if e and e.get("_type") == "playlist":
                for sub in (e.get("entries") or []):
                    if sub:
                        flat.append(sub)
            elif e:
                flat.append(e)
        videos = []
        for e in flat[:50]:
            if not e:
                continue
            vid_id = e.get("id","")
            videos.append({
                "id": vid_id,
                "title": e.get("title",""),
                "channel": e.get("channel") or info.get("channel") or info.get("uploader",""),
                "duration": e.get("duration_string") or fmt_dur(e.get("duration")),
                "thumbnail": e.get("thumbnail") or f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg",
                "views": fmt_views(e.get("view_count")),
                "url": f"https://www.youtube.com/watch?v={vid_id}" if vid_id else e.get("url",""),
            })
        return jsonify({
            "channel": info.get("channel") or info.get("uploader",""),
            "channel_id": info.get("channel_id",""),
            "thumbnail": info.get("thumbnail",""),
            "description": (info.get("description") or "")[:200],
            "videos": videos,
            "url": url,
        })
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

@app.route("/api/playlist_info")
def playlist_info():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL"}), 400
    try:
        opts = {
            "quiet": True, "no_warnings": True,
            "extract_flat": True, "skip_download": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            return jsonify({"error": "Not found"}), 400
        entries = info.get("entries", []) or []
        videos = []
        for e in entries:
            if not e:
                continue
            vid_id = e.get("id","")
            videos.append({
                "id": vid_id,
                "title": e.get("title",""),
                "channel": e.get("channel") or e.get("uploader",""),
                "duration": e.get("duration_string") or fmt_dur(e.get("duration")),
                "thumbnail": e.get("thumbnail") or f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg",
                "url": f"https://www.youtube.com/watch?v={vid_id}" if vid_id else e.get("url",""),
            })
        return jsonify({
            "title": info.get("title","Playlist"),
            "count": len(videos),
            "videos": videos,
            "url": url,
        })
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

@app.route("/api/video_info")
def video_info():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL"}), 400
    try:
        opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        fmts = []
        seen = set()
        for f in (info.get("formats") or []):
            h = f.get("height")
            ext = f.get("ext","")
            if h and ext in ("mp4","webm") and h not in seen:
                seen.add(h)
                fmts.append({"height": h, "ext": ext})
        fmts.sort(key=lambda x: x["height"], reverse=True)
        return jsonify({
            "id": info.get("id",""),
            "title": info.get("title",""),
            "channel": info.get("channel") or info.get("uploader",""),
            "duration": info.get("duration_string") or fmt_dur(info.get("duration")),
            "thumbnail": info.get("thumbnail",""),
            "views": fmt_views(info.get("view_count")),
            "formats": fmts,
            "url": url,
        })
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

@app.route("/api/download", methods=["POST"])
def start_download():
    data = request.json or {}
    urls = data.get("urls", [])
    fmt = data.get("format", "mp4")
    quality = data.get("quality", "1080")
    playlist_items = data.get("playlist_items")

    if not urls:
        return jsonify({"error": "No URLs provided"}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "queued", "progress": 0,
        "files": [], "count": 0, "error": None,
        "speed": "--", "eta": "--",
    }
    executor.submit(do_download, job_id, urls, fmt, quality, playlist_items)
    return jsonify({"job_id": job_id})

@app.route("/api/job/<job_id>")
def job_status(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Not found"}), 404
    return jsonify(jobs[job_id])

@app.route("/api/jobs")
def all_jobs():
    return jsonify(jobs)

@app.route("/downloads/<path:filename>")
def serve_file(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)

@app.route("/api/files")
def list_files():
    files = []
    for f in os.listdir(DOWNLOAD_DIR):
        fp = os.path.join(DOWNLOAD_DIR, f)
        if os.path.isfile(fp):
            files.append({
                "name": f,
                "size": fmt_size(os.path.getsize(fp)),
                "modified": int(os.path.getmtime(fp)),
            })
    files.sort(key=lambda x: x["modified"], reverse=True)
    return jsonify({"files": files})

@app.route("/api/delete_file", methods=["POST"])
def delete_file():
    data = request.json or {}
    name = data.get("name","")
    fp = os.path.join(DOWNLOAD_DIR, name)
    if os.path.isfile(fp) and fp.startswith(DOWNLOAD_DIR):
        os.remove(fp)
        return jsonify({"ok": True})
    return jsonify({"error": "Not found"}), 404

# ─────────────── utils ───────────────

def fmt_dur(secs):
    if not secs:
        return ""
    secs = int(secs)
    h, r = divmod(secs, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def fmt_views(v):
    if not v:
        return ""
    v = int(v)
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M views"
    if v >= 1_000:
        return f"{v/1_000:.0f}K views"
    return f"{v} views"

def fmt_size(b):
    for u in ["B","KB","MB","GB"]:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
