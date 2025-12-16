import os
import re
import sys
import time
import queue
import threading
import requests
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import tkinter as tk
from tkinter import ttk, messagebox

# =============================
# CONFIGURATION
# =============================
HEADERS = {"User-Agent": "MultiHostDownloader/1.0"}
MAX_WORKERS = 3
MAX_RETRIES = 5
RATE_DELAY = 0.3
SPEED_LIMIT_KB = 512  # 0 = unlimited
BASE_DIR = "downloads"

# =============================
# UTILITIES
# =============================
def safe_name(name):
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    return name.strip() or "Album"

# =============================
# SITE ADAPTERS
# =============================

class SiteAdapter:
    def get_album_name(self):
        raise NotImplementedError

    def get_files(self):
        raise NotImplementedError

    def download_file(self, file, output_dir):
        raise NotImplementedError

# -----------------------------
# Pixeldrain Adapter
# -----------------------------
class PixeldrainAdapter(SiteAdapter):
    def __init__(self, url):
        self.url = url
        parsed = urlparse(url)
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "l":
            self.album_id = parts[1]
        else:
            raise ValueError("Invalid Pixeldrain URL")

    def get_album_name(self):
        r = requests.get(f"https://pixeldrain.com/api/list/{self.album_id}", headers=HEADERS)
        r.raise_for_status()
        j = r.json()
        return safe_name(j.get("name") or j.get("title") or f"Pixeldrain_{self.album_id}")

    def get_files(self):
        r = requests.get(f"https://pixeldrain.com/api/list/{self.album_id}", headers=HEADERS)
        r.raise_for_status()
        j = r.json()
        return j.get("files", [])

    def download_file(self, file, output_dir):
        fid, name, size = file["id"], file["name"], file.get("size", 0)
        path = os.path.join(output_dir, name)
        part = path + ".part"

        for attempt in range(MAX_RETRIES):
            try:
                headers = HEADERS.copy()
                downloaded = 0
                if os.path.exists(part):
                    downloaded = os.path.getsize(part)
                    headers["Range"] = f"bytes={downloaded}-"

                url = f"https://pixeldrain.com/api/file/{fid}"
                with requests.get(url, headers=headers, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    mode = "ab" if downloaded else "wb"
                    bytes_this_sec = 0
                    start = time.time()
                    with open(part, mode) as f, tqdm(
                        total=size, initial=downloaded, unit="B", unit_scale=True, desc=name, leave=False
                    ) as bar:
                        for chunk in r.iter_content(8192):
                            if chunk:
                                f.write(chunk)
                                bar.update(len(chunk))
                                if SPEED_LIMIT_KB > 0:
                                    bytes_this_sec += len(chunk)
                                    elapsed = time.time() - start
                                    if elapsed < 1 and bytes_this_sec > SPEED_LIMIT_KB * 1024:
                                        time.sleep(1 - elapsed)
                                        start = time.time()
                                        bytes_this_sec = 0

                os.replace(part, path)
                time.sleep(RATE_DELAY)
                return "downloaded"
            except Exception as e:
                if attempt + 1 == MAX_RETRIES:
                    return f"failed ({e})"
                time.sleep(2 ** attempt)

# -----------------------------
# Bunkr Adapter
# -----------------------------
class BunkrAdapter(SiteAdapter):
    def __init__(self, url):
        self.url = url
        self.album_id = url.rstrip("/").split("/")[-1]

    def get_album_name(self):
        r = requests.get(self.url, headers=HEADERS)
        return safe_name(f"Bunkr_{self.album_id}")

    def get_files(self):
        # Simplified: scrape for file links
        r = requests.get(self.url, headers=HEADERS)
        links = re.findall(r'https://files\.bunkr\.me/[^\s"\']+', r.text)
        files = [{"id": l.split("/")[-1], "name": l.split("/")[-1], "size": 0, "url": l} for l in links]
        return files

    def download_file(self, file, output_dir):
        url = file["url"]
        name = file["name"]
        path = os.path.join(output_dir, name)
        if os.path.exists(path):
            return "skipped"
        with requests.get(url, headers=HEADERS, stream=True) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(8192):
                    if chunk:
                        f.write(chunk)
        return "downloaded"

# -----------------------------
# K00 Adapter
# -----------------------------
class K00Adapter(SiteAdapter):
    def __init__(self, url):
        self.url = url
        self.album_id = url.rstrip("/").split("/")[-1]

    def get_album_name(self):
        return safe_name(f"K00_{self.album_id}")

    def get_files(self):
        r = requests.get(self.url, headers=HEADERS)
        links = re.findall(r'https://k00\.fr/[^\s"\']+', r.text)
        files = [{"id": l.split("/")[-1], "name": l.split("/")[-1], "size": 0, "url": l} for l in links]
        return files

    def download_file(self, file, output_dir):
        url = file["url"]
        name = file["name"]
        path = os.path.join(output_dir, name)
        if os.path.exists(path):
            return "skipped"
        with requests.get(url, headers=HEADERS, stream=True) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(8192):
                    if chunk:
                        f.write(chunk)
        return "downloaded"

# -----------------------------
# Future: Adapters for AnonFiles, File.io, MediaFire, Mega, Zippyshare, Dropbox
# -----------------------------
# Can implement similar classes as above

# =============================
# ADAPTER FACTORY
# =============================
def get_adapter(url):
    if "pixeldrain.com" in url:
        return PixeldrainAdapter(url)
    elif "bunkr.me" in url:
        return BunkrAdapter(url)
    elif "k00.fr" in url:
        return K00Adapter(url)
    else:
        raise ValueError("Site not supported yet")

# =============================
# ALBUM QUEUE & WORKER
# =============================
album_queue = queue.Queue()

def queue_worker(status_cb=print):
    while True:
        url = album_queue.get()
        if url is None:
            break
        try:
            adapter = get_adapter(url)
            album_name = adapter.get_album_name()
            files = adapter.get_files()
            output_dir = os.path.join(BASE_DIR, album_name)
            os.makedirs(output_dir, exist_ok=True)

            with ThreadPoolExecutor(MAX_WORKERS) as ex:
                results = list(ex.map(lambda f: adapter.download_file(f, output_dir), files))
            status_cb(f"Album '{album_name}' done: {results.count('downloaded')} downloaded, {results.count('skipped')} skipped")
        except Exception as e:
            status_cb(f"Error: {e}")
        album_queue.task_done()

# =============================
# CLI
# =============================
def cli_mode():
    for url in sys.argv[1:]:
        album_queue.put(url)
    threading.Thread(target=queue_worker, daemon=True).start()
    album_queue.join()

# =============================
# GUI
# =============================
def gui_mode():
    root = tk.Tk()
    root.title("MultiHost Downloader")
    root.geometry("480x260")
    root.configure(bg="#121212")

    tk.Label(root, text="Drag & drop album URLs here", bg="#121212", fg="#ffffff", font=("Arial", 12)).pack(pady=20)

    status = tk.StringVar(value="Idle")
    tk.Label(root, textvariable=status, bg="#121212", fg="#e0c9a6").pack(pady=10)

    entry = tk.Entry(root, width=50)
    entry.pack(pady=10)

    def add_album():
        url = entry.get().strip()
        if url:
            album_queue.put(url)
            status.set(f"Queued: {url}")
            entry.delete(0, tk.END)

    tk.Button(root, text="Add to Queue", command=add_album, bg="#1f4e5f", fg="#ffffff").pack(pady=10)

    threading.Thread(target=queue_worker, args=(lambda s: status.set(s),), daemon=True).start()

    root.mainloop()

# =============================
# ENTRY POINT
# =============================
if __name__ == "__main__":
    os.makedirs(BASE_DIR, exist_ok=True)
    if len(sys.argv) > 1:
        cli_mode()
    else:
        gui_mode()
