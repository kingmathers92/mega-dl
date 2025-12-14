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

# ================= CONFIG =================
HEADERS = {"User-Agent": "PixeldrainDownloader/3.0"}
MAX_WORKERS = 3
MAX_RETRIES = 5
RATE_DELAY = 0.3
SPEED_LIMIT_KB = 512  # 0 = unlimited
BASE_DIR = "downloads"
# =========================================

# ---------- HELPERS ----------
def extract_album_id(url):
    p = urlparse(url)
    parts = p.path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "l":
        return parts[1]
    raise ValueError("Invalid Pixeldrain album URL")

def safe_name(name):
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    return name.strip() or "Pixeldrain Album"

def get_album(album_id):
    r = requests.get(f"https://pixeldrain.com/api/list/{album_id}", headers=HEADERS)
    r.raise_for_status()
    j = r.json()
    return safe_name(j.get("name") or j.get("title") or f"Album_{album_id}"), j["files"]

# ---------- DOWNLOAD ----------
def download_file(file, out_dir):
    fid, name, size = file["id"], file["name"], file.get("size", 0)
    path = os.path.join(out_dir, name)
    part = path + ".part"

    if os.path.exists(path) and size and os.path.getsize(path) == size:
        return "skipped"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            headers = HEADERS.copy()
            downloaded = 0
            if os.path.exists(part):
                downloaded = os.path.getsize(part)
                headers["Range"] = f"bytes={downloaded}-"

            r = requests.get(
                f"https://pixeldrain.com/api/file/{fid}",
                headers=headers,
                stream=True,
                timeout=60,
            )

            if r.status_code == 403:
                raise Exception("403")

            r.raise_for_status()
            mode = "ab" if downloaded else "wb"

            with open(part, mode) as f, tqdm(
                total=size if size else None,
                initial=downloaded,
                unit="B",
                unit_scale=True,
                desc=name,
                leave=False,
            ) as bar:
                start = time.time()
                bytes_this_sec = 0

                for chunk in r.iter_content(8192):
                    if not chunk:
                        continue
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

        except Exception:
            wait = 2 ** attempt
            print(f"⚠ retry {attempt}/{MAX_RETRIES} for {name} in {wait}s")
            time.sleep(wait)

    return "failed"

# ---------- ALBUM ----------
def download_album(url):
    album_id = extract_album_id(url)
    album_name, files = get_album(album_id)
    out_dir = os.path.join(BASE_DIR, album_name)
    os.makedirs(out_dir, exist_ok=True)

    with ThreadPoolExecutor(MAX_WORKERS) as ex:
        results = list(ex.map(lambda f: download_file(f, out_dir), files))

    return f"{album_name}: ok={results.count('downloaded')} skip={results.count('skipped')} fail={results.count('failed')}"

# ---------- QUEUE ----------
album_queue = queue.Queue()

def queue_worker(status_cb=print):
    while True:
        url = album_queue.get()
        if url is None:
            break
        try:
            status_cb(download_album(url))
        except Exception as e:
            status_cb(f"Error: {e}")
        album_queue.task_done()

# ================= CLI =================
def cli():
    for url in sys.argv[1:]:
        album_queue.put(url)
    threading.Thread(target=queue_worker, daemon=True).start()
    album_queue.join()

# ================= GUI =================
def gui():
    import tkinter as tk
    from tkinter import ttk, messagebox

    root = tk.Tk()
    root.title("Pixeldrain Downloader")
    root.geometry("480x260")
    root.configure(bg="#121212")

    style = ttk.Style()
    style.theme_use("default")
    style.configure("TButton", background="#1e1e1e", foreground="white")
    style.configure("TLabel", background="#121212", foreground="white")

    status = tk.StringVar(value="Idle")

    def add_album():
        url = entry.get().strip()
        if not url:
            return
        album_queue.put(url)
        entry.delete(0, "end")
        status.set("Queued")

    def worker():
        queue_worker(lambda s: status.set(s))

    ttk.Label(root, text="Pixeldrain Album URL").pack(pady=10)
    entry = ttk.Entry(root, width=60)
    entry.pack()
    ttk.Button(root, text="Add to Queue", command=add_album).pack(pady=10)
    ttk.Label(root, textvariable=status).pack(pady=10)

    threading.Thread(target=worker, daemon=True).start()
    root.mainloop()

# ================= ENTRY =================
if __name__ == "__main__":
    if len(sys.argv) > 1:
        cli()
    else:
        gui()
