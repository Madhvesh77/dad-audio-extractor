import os
import time
import random
import threading
import uuid
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Track job statuses for playlist downloads
job_status = {}

# ─── yt-dlp OPTIONS (anti-detection) ───────────────────────────────────────

def get_ydl_opts(output_template, extra_opts=None):
    """
    Returns yt-dlp options with anti-detection measures:
    - Impersonates a real browser (Chrome on Windows)
    - Uses realistic HTTP headers
    - Adds sleep intervals between downloads
    - Optionally loads cookies from browser
    """
    opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        # --- Anti-detection ---
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.youtube.com/",
        },
        # Impersonate Chrome browser (yt-dlp built-in feature)
        "impersonate": "chrome",
        # Randomized sleep between retries and requests
        "sleep_interval": 3,
        "max_sleep_interval": 8,
        "sleep_interval_requests": 2,
        # Retry logic
        "retries": 5,
        "fragment_retries": 5,
        # Suppress progress noise in server logs
        "quiet": True,
        "no_warnings": False,
        # Use cookies file if it exists (highly recommended)
        **({"cookiefile": "cookies.txt"} if os.path.exists("cookies.txt") else {}),
    }
    if extra_opts:
        opts.update(extra_opts)
    return opts


# ─── ROUTES ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/info", methods=["POST"])
def get_info():
    """Fetch metadata for a video or playlist without downloading."""
    data = request.get_json()
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    try:
        ydl_opts = {
            "quiet": True,
            "extract_flat": "in_playlist",  # Don't fetch full info for each video
            "skip_download": True,
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
            },
            **({"cookiefile": "cookies.txt"} if os.path.exists("cookies.txt") else {}),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if "entries" in info:
            # It's a playlist
            entries = [
                {
                    "id": e.get("id"),
                    "title": e.get("title", "Unknown"),
                    "url": e.get("url") or f"https://www.youtube.com/watch?v={e.get('id')}",
                    "duration": e.get("duration"),
                    "thumbnail": e.get("thumbnail"),
                }
                for e in info["entries"] if e
            ]
            return jsonify({
                "type": "playlist",
                "title": info.get("title", "Playlist"),
                "count": len(entries),
                "entries": entries,
            })
        else:
            # Single video
            return jsonify({
                "type": "video",
                "id": info.get("id"),
                "title": info.get("title", "Unknown"),
                "duration": info.get("duration"),
                "thumbnail": info.get("thumbnail"),
                "uploader": info.get("uploader"),
            })

    except yt_dlp.utils.DownloadError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500


@app.route("/download/single", methods=["POST"])
def download_single():
    """Download a single video's audio and return the MP3 file."""
    data = request.get_json()
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    # Unique filename to avoid collisions
    file_id = str(uuid.uuid4())
    output_template = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")

    try:
        opts = get_ydl_opts(output_template)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "audio")

        # Find the downloaded MP3
        mp3_path = os.path.join(DOWNLOAD_DIR, f"{file_id}.mp3")
        if not os.path.exists(mp3_path):
            return jsonify({"error": "MP3 file not found after conversion"}), 500

        safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()
        return send_file(
            mp3_path,
            as_attachment=True,
            download_name=f"{safe_title}.mp3",
            mimetype="audio/mpeg",
        )

    except yt_dlp.utils.DownloadError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500


@app.route("/download/playlist/start", methods=["POST"])
def start_playlist_download():
    """
    Start a background job to download all playlist videos.
    Returns a job_id to poll for status.
    """
    data = request.get_json()
    entries = data.get("entries", [])
    if not entries:
        return jsonify({"error": "No entries provided"}), 400

    job_id = str(uuid.uuid4())
    job_status[job_id] = {
        "total": len(entries),
        "completed": 0,
        "failed": 0,
        "files": [],   # list of {title, path}
        "done": False,
        "error": None,
    }

    def run_downloads():
        for i, entry in enumerate(entries):
            url = entry.get("url")
            title = entry.get("title", f"track_{i+1}")
            if not url:
                job_status[job_id]["failed"] += 1
                continue

            file_id = str(uuid.uuid4())
            output_template = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")
            try:
                opts = get_ydl_opts(output_template)
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.extract_info(url, download=True)

                mp3_path = os.path.join(DOWNLOAD_DIR, f"{file_id}.mp3")
                if os.path.exists(mp3_path):
                    job_status[job_id]["files"].append({
                        "title": title,
                        "path": mp3_path,
                        "file_id": file_id,
                    })
                    job_status[job_id]["completed"] += 1
                else:
                    job_status[job_id]["failed"] += 1

            except Exception as e:
                job_status[job_id]["failed"] += 1
                print(f"[ERROR] {title}: {e}")

            # ── Rate limit protection: random delay between downloads ──
            if i < len(entries) - 1:
                delay = random.uniform(4, 10)
                print(f"[WAIT] Sleeping {delay:.1f}s before next download...")
                time.sleep(delay)

        job_status[job_id]["done"] = True

    thread = threading.Thread(target=run_downloads, daemon=True)
    thread.start()

    return jsonify({"job_id": job_id, "total": len(entries)})


@app.route("/download/playlist/status/<job_id>")
def playlist_status(job_id):
    """Poll job progress."""
    status = job_status.get(job_id)
    if not status:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(status)


@app.route("/download/playlist/file/<job_id>/<file_id>")
def download_playlist_file(job_id, file_id):
    """Download a single completed file from a playlist job."""
    status = job_status.get(job_id)
    if not status:
        return jsonify({"error": "Job not found"}), 404

    entry = next((f for f in status["files"] if f["file_id"] == file_id), None)
    if not entry:
        return jsonify({"error": "File not ready yet"}), 404

    path = entry["path"]
    if not os.path.exists(path):
        return jsonify({"error": "File missing on disk"}), 404

    safe_title = "".join(c for c in entry["title"] if c.isalnum() or c in " _-").strip()
    return send_file(path, as_attachment=True, download_name=f"{safe_title}.mp3", mimetype="audio/mpeg")


if __name__ == "__main__":
    app.run(debug=True, port=5000)