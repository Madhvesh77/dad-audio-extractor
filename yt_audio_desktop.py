import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import time
import random
import yt_dlp

class YTAudioApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YT Audio Downloader")
        self.root.geometry("600x500")
        self.root.resizable(False, False)
        self.root.configure(bg="#0d0d0d")

        self.download_dir = os.path.expanduser("~/Downloads")
        self.is_downloading = False
        self.build_ui()

    def build_ui(self):
        BG = "#0d0d0d"
        SURFACE = "#161616"
        ACCENT = "#c8f53d"
        TEXT = "#f0f0f0"
        MUTED = "#6b6b6b"

        # Title
        tk.Label(self.root, text="YT Audio Downloader",
                 bg=BG, fg=ACCENT,
                 font=("Courier", 18, "bold")).pack(pady=(30, 4))
        tk.Label(self.root, text="paste a youtube link · get an mp3",
                 bg=BG, fg=MUTED, font=("Courier", 10)).pack(pady=(0, 24))

        # URL input
        url_frame = tk.Frame(self.root, bg=SURFACE, bd=1, relief="flat")
        url_frame.pack(padx=40, fill="x")
        self.url_var = tk.StringVar()
        tk.Entry(url_frame, textvariable=self.url_var,
                 bg=SURFACE, fg=TEXT, insertbackground=TEXT,
                 font=("Courier", 10), bd=0,
                 relief="flat", width=55).pack(
                     side="left", padx=12, pady=12, fill="x", expand=True)
        tk.Button(url_frame, text="✕", bg=SURFACE, fg=MUTED,
                  font=("Courier", 10), bd=0, relief="flat",
                  command=lambda: self.url_var.set(""),
                  cursor="hand2").pack(side="right", padx=8)

        # Save folder row
        folder_frame = tk.Frame(self.root, bg=BG)
        folder_frame.pack(padx=40, pady=(12, 0), fill="x")
        tk.Label(folder_frame, text="Save to:", bg=BG, fg=MUTED,
                 font=("Courier", 9)).pack(side="left")
        self.folder_label = tk.Label(folder_frame, text=self.download_dir,
                                      bg=BG, fg=TEXT, font=("Courier", 9),
                                      cursor="hand2")
        self.folder_label.pack(side="left", padx=(6, 0))
        self.folder_label.bind("<Button-1>", self.choose_folder)
        tk.Label(folder_frame, text="(click to change)", bg=BG, fg=MUTED,
                 font=("Courier", 9)).pack(side="left", padx=(4, 0))

        # Download button
        self.dl_btn = tk.Button(self.root, text="▼  Download MP3",
                                 bg=ACCENT, fg="#0d0d0d",
                                 font=("Courier", 12, "bold"),
                                 bd=0, relief="flat", padx=24, pady=12,
                                 cursor="hand2",
                                 command=self.start_download)
        self.dl_btn.pack(pady=24)

        # Status label
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = tk.Label(self.root, textvariable=self.status_var,
                                      bg=BG, fg=MUTED,
                                      font=("Courier", 9),
                                      wraplength=520, justify="center")
        self.status_label.pack()

        # Progress bar
        style = ttk.Style()
        style.theme_use("default")
        style.configure("green.Horizontal.TProgressbar",
                         troughcolor="#1e1e1e", background=ACCENT,
                         thickness=6, borderwidth=0)
        self.progress = ttk.Progressbar(self.root, length=520,
                                         mode="determinate",
                                         style="green.Horizontal.TProgressbar")
        self.progress.pack(padx=40, pady=(12, 0))

        # Log box
        log_frame = tk.Frame(self.root, bg="#111", bd=1, relief="flat")
        log_frame.pack(padx=40, pady=16, fill="both", expand=True)
        self.log = tk.Text(log_frame, bg="#111", fg="#555",
                           font=("Courier", 8), bd=0, relief="flat",
                           state="disabled", height=8, wrap="word")
        self.log.pack(padx=8, pady=8, fill="both", expand=True)

    def choose_folder(self, event=None):
        folder = filedialog.askdirectory(initialdir=self.download_dir)
        if folder:
            self.download_dir = folder
            self.folder_label.config(text=folder)

    def log_msg(self, msg, color="#555"):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def set_status(self, msg, color="#6b6b6b"):
        self.status_var.set(msg)
        self.status_label.config(fg=color)

    def start_download(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Please paste a YouTube URL first.")
            return
        if self.is_downloading:
            return
        self.is_downloading = True
        self.dl_btn.config(state="disabled", text="Downloading...")
        self.progress["value"] = 0
        threading.Thread(target=self.run_download, args=(url,), daemon=True).start()

    def run_download(self, url):
        self.set_status("Fetching info...", "#c8f53d")
        self.log_msg(f"URL: {url}")

        cookies_path = os.path.join(os.path.dirname(__file__), "cookies.txt")

        # Detect if playlist
        is_playlist = "list=" in url and "watch?v=" not in url

        def progress_hook(d):
            if d["status"] == "downloading":
                raw = d.get("_percent_str", "0%").strip()
                try:
                    pct = float(raw.replace("%", "").strip())
                    self.progress["value"] = pct
                    self.set_status(
                        f"Downloading... {raw}  |  {d.get('_speed_str','').strip()}",
                        "#c8f53d"
                    )
                except:
                    pass
            elif d["status"] == "finished":
                self.set_status("Converting to MP3...", "#c8f53d")
                self.log_msg(f"✓ Converted: {os.path.basename(d['filename'])}", "#5cf5b0")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(self.download_dir, "%(title)s.%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
            },
            "impersonate": "chrome",
            "sleep_interval": 3,
            "max_sleep_interval": 8,
            "retries": 5,
            "progress_hooks": [progress_hook],
            "quiet": True,
            **({"cookiefile": cookies_path} if os.path.exists(cookies_path) else {}),
        }

        # For playlists, add delay between tracks
        if is_playlist:
            ydl_opts["sleep_interval_requests"] = random.randint(4, 10)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

            if is_playlist:
                count = len(info.get("entries", []))
                self.set_status(f"✓ Done! {count} tracks saved to {self.download_dir}", "#5cf5b0")
                self.log_msg(f"✓ Playlist complete: {count} tracks", "#5cf5b0")
            else:
                title = info.get("title", "audio")
                self.set_status(f"✓ Saved: {title}", "#5cf5b0")
                self.log_msg(f"✓ Done: {title}", "#5cf5b0")

            self.progress["value"] = 100

        except yt_dlp.utils.DownloadError as e:
            self.set_status(f"Error: {str(e)[:80]}", "#ff5c5c")
            self.log_msg(f"✗ {e}", "#ff5c5c")
        except Exception as e:
            self.set_status(f"Unexpected error: {str(e)[:80]}", "#ff5c5c")
            self.log_msg(f"✗ {e}", "#ff5c5c")
        finally:
            self.is_downloading = False
            self.dl_btn.config(state="normal", text="▼  Download MP3")


if __name__ == "__main__":
    root = tk.Tk()
    app = YTAudioApp(root)
    root.mainloop()