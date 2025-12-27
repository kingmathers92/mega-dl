import os
import re
import sys
import time
import queue
import threading
import requests
import random
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import tkinter as tk
from tkinter import ttk, messagebox
from mega import Mega
import argparse
import zipfile

# =============================
# CONFIGURATION
# =============================
HEADERS = {"User-Agent": "MultiHostDownloader/1.0"}
MAX_WORKERS = os.cpu_count() // 2 or 3
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
    def __init__(self, url, proxies=None):
        self.url = url
        self.proxies = proxies

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
    def __init__(self, url, proxies=None):
        super().__init__(url, proxies)
        parsed = urlparse(url)
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "l":
            self.album_id = parts[1]
        else:
            raise ValueError("Invalid Pixeldrain URL")

    def get_album_name(self):
        r = requests.get(f"https://pixeldrain.com/api/list/{self.album_id}", headers=HEADERS, proxies=self.proxies)
        r.raise_for_status()
        j = r.json()
        return safe_name(j.get("name") or j.get("title") or f"Pixeldrain_{self.album_id}")

    def get_files(self):
        r = requests.get(f"https://pixeldrain.com/api/list/{self.album_id}", headers=HEADERS, proxies=self.proxies)
        r.raise_for_status()
        j = r.json()
        return j.get("files", [])

    def download_file(self, file, output_dir):
        file_id = file["id"]
        name = file["name"]
        size = file.get("size", 0)

        path = os.path.join(output_dir, name)
        temp_path = path + ".part"

        # Check if existing file matches size
        if os.path.exists(path) and size > 0 and os.path.getsize(path) == size:
            return "skipped"

        attempt = 0
        while attempt < MAX_RETRIES:
            try:
                headers = HEADERS.copy()
                headers["User-Agent"] = f"PixeldrainDownloader/2.1-{random.randint(1000,9999)}"
                downloaded = 0

                if os.path.exists(temp_path):
                    downloaded = os.path.getsize(temp_path)
                    headers["Range"] = f"bytes={downloaded}-"

                url = f"https://pixeldrain.com/api/file/{file_id}"
                with requests.get(url, headers=headers, stream=True, timeout=60, proxies=self.proxies) as r:
                    r.raise_for_status()
                    total_size = size if size > 0 else int(r.headers.get("Content-Length", 0)) + downloaded
                    mode = "ab" if downloaded else "wb"

                    with open(temp_path, mode) as f, tqdm(
                        total=total_size,
                        initial=downloaded,
                        unit="B",
                        unit_scale=True,
                        desc=name,
                        leave=False
                    ) as bar:
                        for chunk in r.iter_content(8192):
                            if chunk:
                                start_time = time.time()
                                f.write(chunk)
                                bar.update(len(chunk))
                                elapsed = time.time() - start_time
                                if SPEED_LIMIT_KB > 0:
                                    expected_time = len(chunk) / (SPEED_LIMIT_KB * 1024)
                                    if elapsed < expected_time:
                                        time.sleep(expected_time - elapsed)

                os.replace(temp_path, path)
                time.sleep(RATE_DELAY + random.uniform(0.1, 0.5))
                return "downloaded"

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    wait = 60 + random.uniform(10, 20)  # Longer for rate limit
                    print(f"\n⚠ Rate limit (429) on {name}, waiting {wait:.1f}s")
                    time.sleep(wait)
                else:
                    attempt += 1
                    wait = 2 ** attempt + random.uniform(0.5, 1.5)
                    print(f"\n⚠ HTTP error on {name}, retry {attempt}/{MAX_RETRIES} in {wait:.1f}s")
                    time.sleep(wait)
            except Exception as e:
                attempt += 1
                wait = 2 ** attempt + random.uniform(0.5, 1.5)
                print(f"\n❌ Error downloading {name}: {e}, retry {attempt}/{MAX_RETRIES} in {wait:.1f}s")
                time.sleep(wait)

        print(f"\n❌ Gave up on {name}")
        return "failed"

# -----------------------------
# Bunkr Adapter
# -----------------------------
class BunkrAdapter(SiteAdapter):
    def __init__(self, url, proxies=None):
        super().__init__(url, proxies)
        self.album_id = url.rstrip("/").split("/")[-1]

    def get_album_name(self):
        r = requests.get(self.url, headers=HEADERS, proxies=self.proxies)
        return safe_name(f"Bunkr_{self.album_id}")

    def get_files(self):
        r = requests.get(self.url, headers=HEADERS, proxies=self.proxies)
        r.raise_for_status()
        links = re.findall(r'https://files\.bunkr\.\w+/[^\s"\']+', r.text)
        files = [{"id": l.split("/")[-1], "name": l.split("/")[-1], "size": 0, "url": l} for l in links]
        return files

    def download_file(self, file, output_dir):
        url = file["url"]
        name = file["name"]
        path = os.path.join(output_dir, name)
        temp_path = path + ".part"

        # Check existing file size with HEAD request
        try:
            head = requests.head(url, headers=HEADERS, proxies=self.proxies)
            size = int(head.headers.get("Content-Length", 0))
            if os.path.exists(path) and os.path.getsize(path) == size:
                return "skipped"
        except Exception:
            size = 0

        attempt = 0
        while attempt < MAX_RETRIES:
            try:
                headers = HEADERS.copy()
                downloaded = 0

                if os.path.exists(temp_path):
                    downloaded = os.path.getsize(temp_path)
                    headers["Range"] = f"bytes={downloaded}-"

                with requests.get(url, headers=headers, stream=True, timeout=60, proxies=self.proxies) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get("Content-Length", 0)) + downloaded
                    mode = "ab" if downloaded else "wb"

                    with open(temp_path, mode) as f, tqdm(
                        total=total_size,
                        initial=downloaded,
                        unit="B",
                        unit_scale=True,
                        desc=name,
                        leave=False
                    ) as bar:
                        for chunk in r.iter_content(8192):
                            if chunk:
                                start_time = time.time()
                                f.write(chunk)
                                bar.update(len(chunk))
                                elapsed = time.time() - start_time
                                if SPEED_LIMIT_KB > 0:
                                    expected_time = len(chunk) / (SPEED_LIMIT_KB * 1024)
                                    if elapsed < expected_time:
                                        time.sleep(expected_time - elapsed)

                os.replace(temp_path, path)
                time.sleep(RATE_DELAY + random.uniform(0.1, 0.5))
                return "downloaded"

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    wait = 60 + random.uniform(10, 20)  # Longer for rate limit
                    print(f"\n⚠ Rate limit (429) on {name}, waiting {wait:.1f}s")
                    time.sleep(wait)
                else:
                    attempt += 1
                    wait = 2 ** attempt + random.uniform(0.5, 1.5)
                    print(f"\n⚠ HTTP error on {name}, retry {attempt}/{MAX_RETRIES} in {wait:.1f}s")
                    time.sleep(wait)
            except Exception as e:
                attempt += 1
                wait = 2 ** attempt + random.uniform(0.5, 1.5)
                print(f"\n❌ Error downloading {name}: {e}, retry {attempt}/{MAX_RETRIES} in {wait:.1f}s")
                time.sleep(wait)

        print(f"\n❌ Gave up on {name}")
        return "failed"

# -----------------------------
# K00 Adapter
# -----------------------------
class K00Adapter(SiteAdapter):
    def __init__(self, url, proxies=None):
        super().__init__(url, proxies)
        self.album_id = url.rstrip("/").split("/")[-1]

    def get_album_name(self):
        return safe_name(f"K00_{self.album_id}")

    def get_files(self):
        r = requests.get(self.url, headers=HEADERS, proxies=self.proxies)
        links = re.findall(r'https://k00\.fr/[^\s"\']+', r.text)
        files = [{"id": l.split("/")[-1], "name": l.split("/")[-1], "size": 0, "url": l} for l in links]
        return files

    def download_file(self, file, output_dir):
        url = file["url"]
        name = file["name"]
        path = os.path.join(output_dir, name)
        temp_path = path + ".part"

        # Check existing file size with HEAD request
        try:
            head = requests.head(url, headers=HEADERS, proxies=self.proxies)
            size = int(head.headers.get("Content-Length", 0))
            if os.path.exists(path) and os.path.getsize(path) == size:
                return "skipped"
        except Exception:
            size = 0

        attempt = 0
        while attempt < MAX_RETRIES:
            try:
                headers = HEADERS.copy()
                downloaded = 0

                if os.path.exists(temp_path):
                    downloaded = os.path.getsize(temp_path)
                    headers["Range"] = f"bytes={downloaded}-"

                with requests.get(url, headers=headers, stream=True, timeout=60, proxies=self.proxies) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get("Content-Length", 0)) + downloaded
                    mode = "ab" if downloaded else "wb"

                    with open(temp_path, mode) as f, tqdm(
                        total=total_size,
                        initial=downloaded,
                        unit="B",
                        unit_scale=True,
                        desc=name,
                        leave=False
                    ) as bar:
                        for chunk in r.iter_content(8192):
                            if chunk:
                                start_time = time.time()
                                f.write(chunk)
                                bar.update(len(chunk))
                                elapsed = time.time() - start_time
                                if SPEED_LIMIT_KB > 0:
                                    expected_time = len(chunk) / (SPEED_LIMIT_KB * 1024)
                                    if elapsed < expected_time:
                                        time.sleep(expected_time - elapsed)

                os.replace(temp_path, path)
                time.sleep(RATE_DELAY + random.uniform(0.1, 0.5))
                return "downloaded"

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    wait = 60 + random.uniform(10, 20)  # Longer for rate limit
                    print(f"\n⚠ Rate limit (429) on {name}, waiting {wait:.1f}s")
                    time.sleep(wait)
                else:
                    attempt += 1
                    wait = 2 ** attempt + random.uniform(0.5, 1.5)
                    print(f"\n⚠ HTTP error on {name}, retry {attempt}/{MAX_RETRIES} in {wait:.1f}s")
                    time.sleep(wait)
            except Exception as e:
                attempt += 1
                wait = 2 ** attempt + random.uniform(0.5, 1.5)
                print(f"\n❌ Error downloading {name}: {e}, retry {attempt}/{MAX_RETRIES} in {wait:.1f}s")
                time.sleep(wait)

        print(f"\n❌ Gave up on {name}")
        return "failed"

# -----------------------------
# SingleFile Adapter
# -----------------------------
class SingleFileAdapter(SiteAdapter):
    def __init__(self, url, proxies=None):
        super().__init__(url, proxies)
        self.name = urlparse(url).path.split("/")[-1] or "file"

    def get_album_name(self):
        return safe_name(f"Single_{self.name}")

    def get_files(self):
        return [{"id": self.name, "name": self.name, "size": 0, "url": self.url}]

    def download_file(self, file, output_dir):
        url = file["url"]
        name = file["name"]
        path = os.path.join(output_dir, name)
        temp_path = path + ".part"

        try:
            head = requests.head(url, headers=HEADERS, proxies=self.proxies)
            size = int(head.headers.get("Content-Length", 0))
            if os.path.exists(path) and os.path.getsize(path) == size:
                return "skipped"
        except Exception:
            size = 0

        attempt = 0
        while attempt < MAX_RETRIES:
            try:
                headers = HEADERS.copy()
                downloaded = 0

                if os.path.exists(temp_path):
                    downloaded = os.path.getsize(temp_path)
                    headers["Range"] = f"bytes={downloaded}-"

                with requests.get(url, headers=headers, stream=True, timeout=60, proxies=self.proxies) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get("Content-Length", 0)) + downloaded
                    mode = "ab" if downloaded else "wb"

                    with open(temp_path, mode) as f, tqdm(
                        total=total_size,
                        initial=downloaded,
                        unit="B",
                        unit_scale=True,
                        desc=name,
                        leave=False
                    ) as bar:
                        for chunk in r.iter_content(8192):
                            if chunk:
                                start_time = time.time()
                                f.write(chunk)
                                bar.update(len(chunk))
                                elapsed = time.time() - start_time
                                if SPEED_LIMIT_KB > 0:
                                    expected_time = len(chunk) / (SPEED_LIMIT_KB * 1024)
                                    if elapsed < expected_time:
                                        time.sleep(expected_time - elapsed)

                os.replace(temp_path, path)
                time.sleep(RATE_DELAY + random.uniform(0.1, 0.5))
                return "downloaded"

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    wait = 60 + random.uniform(10, 20)  # Longer for rate limit
                    print(f"\n⚠ Rate limit (429) on {name}, waiting {wait:.1f}s")
                    time.sleep(wait)
                else:
                    attempt += 1
                    wait = 2 ** attempt + random.uniform(0.5, 1.5)
                    print(f"\n⚠ HTTP error on {name}, retry {attempt}/{MAX_RETRIES} in {wait:.1f}s")
                    time.sleep(wait)
            except Exception as e:
                attempt += 1
                wait = 2 ** attempt + random.uniform(0.5, 1.5)
                print(f"\n❌ Error downloading {name}: {e}, retry {attempt}/{MAX_RETRIES} in {wait:.1f}s")
                time.sleep(wait)

        print(f"\n❌ Gave up on {name}")
        return "failed"

# -----------------------------
# AnonFiles Adapter
# -----------------------------
class AnonFilesAdapter(SiteAdapter):
    def __init__(self, url, proxies=None):
        super().__init__(url, proxies)
        parsed = urlparse(url)
        self.file_id = parsed.path.strip("/").split("/")[-1]

    def get_album_name(self):
        return safe_name(f"AnonFiles_{self.file_id}")

    def get_files(self):
        r = requests.get(f"https://api.anonfiles.com/v2/file/{self.file_id}/info", headers=HEADERS, proxies=self.proxies)
        r.raise_for_status()
        j = r.json()
        if not j.get("status"):
            raise ValueError("Invalid AnonFiles URL")
        file_info = j["data"]["file"]
        return [{"id": self.file_id, "name": file_info["metadata"]["name"], "size": file_info["metadata"]["size"]["bytes"], "url": file_info["url"]["full"]}]

    def download_file(self, file, output_dir):
        # Reuse SingleFileAdapter's download logic for consistency
        single_adapter = SingleFileAdapter(file["url"], proxies=self.proxies)
        return single_adapter.download_file(file, output_dir)

# -----------------------------
# Mega Adapter
# -----------------------------
class MegaAdapter(SiteAdapter):
    def __init__(self, url, proxies=None):
        super().__init__(url, proxies)
        # Note: Mega may not support proxies directly; handle if needed
        self.mega = Mega().login_anonymous()

    def get_album_name(self):
        # For simplicity, use URL hash as name
        parsed = urlparse(self.url)
        return safe_name(f"Mega_{parsed.fragment or 'file'}")

    def get_files(self):
        # Mega URLs are typically single files/folders; assume single for now
        return [{"id": "mega_file", "name": os.path.basename(self.url), "size": 0, "url": self.url}]

    def download_file(self, file, output_dir):
        name = file["name"]
        path = os.path.join(output_dir, name)
        if os.path.exists(path):
            return "skipped"
        try:
            self.mega.download_url(self.url, dest_path=output_dir)
            return "downloaded"
        except Exception as e:
            print(f"\n❌ Error downloading {name} from Mega: {e}")
            return "failed"

# =============================
# ADAPTER FACTORY
# =============================
BUNKR_DOMAINS = [
    "bunkr.me",
    "bunkr.cr",
    "bunkr.site",
    "bunkr.si",
    "bunkr.fi"
]

def get_adapter(url, proxies=None):
    parsed = urlparse(url)
    netloc = parsed.netloc
    path_parts = parsed.path.strip("/").split("/")
    if "pixeldrain.com" in netloc:
        if len(path_parts) >= 2 and path_parts[0] == "l":
            return PixeldrainAdapter(url, proxies=proxies)
        elif len(path_parts) >= 2 and path_parts[0] == "u":
            return SingleFileAdapter(url, proxies=proxies)  # Single file on Pixeldrain
    elif netloc in BUNKR_DOMAINS:
        return BunkrAdapter(url, proxies=proxies)
    elif "k00.fr" in netloc:
        return K00Adapter(url, proxies=proxies)
    elif "anonfiles.com" in netloc:
        return AnonFilesAdapter(url, proxies=proxies)
    elif "mega.nz" in netloc or "mega.co.nz" in netloc:
        return MegaAdapter(url, proxies=proxies)
    else:
        # Fallback to single file if direct link (e.g., https://example.com/file.ext)
        if parsed.path.endswith(('.zip', '.mp4', '.jpg', '.png', '.pdf')):  # Add more extensions as needed
            return SingleFileAdapter(url, proxies=proxies)
        raise ValueError("Site not supported yet")

# =============================
# ALBUM QUEUE & WORKER
# =============================
album_queue = queue.Queue()

def queue_worker(status_cb=print, unzip=False, proxies=None, max_workers=MAX_WORKERS):
    while True:
        url = album_queue.get()
        if url is None:
            break
        try:
            adapter = get_adapter(url, proxies=proxies)
            album_name = adapter.get_album_name()
            files = adapter.get_files()
            output_dir = os.path.join(BASE_DIR, album_name)
            os.makedirs(output_dir, exist_ok=True)

            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                results = list(ex.map(lambda f: adapter.download_file(f, output_dir), files))

            if unzip:
                for file in files:
                    path = os.path.join(output_dir, file["name"])
                    if path.endswith(".zip") and os.path.exists(path):
                        with zipfile.ZipFile(path, "r") as z:
                            z.extractall(output_dir)
                        os.remove(path)  # Optional: remove zip after extract

            status_cb(f"Album '{album_name}' done: {results.count('downloaded')} downloaded, {results.count('skipped')} skipped")
        except Exception as e:
            status_cb(f"Error: {e}")
        album_queue.task_done()

# =============================
# CLI
# =============================
def cli_mode():
    parser = argparse.ArgumentParser(description="MultiHost Downloader CLI")
    parser.add_argument("--max-workers", type=int, default=MAX_WORKERS, help="Max concurrent downloads")
    parser.add_argument("--proxy", help="Proxy URL (e.g., http://proxy:port)")
    parser.add_argument("urls", nargs="*", help="Album or file URLs")
    parser.add_argument("--file", help="Text file with URLs (one per line)")
    parser.add_argument("--unzip", action="store_true", help="Unzip downloaded .zip files")
    args = parser.parse_args()

    proxies = {"http": args.proxy, "https": args.proxy} if args.proxy else None

    urls = args.urls
    if args.file:
        with open(args.file, "r") as f:
            urls.extend([line.strip() for line in f if line.strip()])

    for url in urls:
        album_queue.put(url)

    threading.Thread(target=queue_worker, args=(print, args.unzip, proxies, args.max_workers), daemon=True).start()  # Pass unzip flag
    album_queue.join()

# =============================
# GUI
# =============================

def gui_mode():
    root = tk.Tk()
    root.title("MultiHostDownloader")
    root.geometry("480x400")

    tk.Label(root, text="Drag & drop album URLs here", bg="#121212", fg="#ffffff", font=("Arial", 12)).pack(pady=20)

    status = tk.StringVar(value="Idle")
    tk.Label(root, textvariable=status, bg="#121212", fg="#e0c9a6").pack(pady=10)

    entry = tk.Entry(root, width=50)
    entry.pack(pady=10)

    queue_list = tk.Listbox(root, height=5, width=50)
    queue_list.pack(pady=10)

    progress = ttk.Progressbar(root, mode="indeterminate")
    progress.pack(pady=10)

    pause_event = threading.Event()
    pause_event.set()

    def add_album():
        url = entry.get().strip()
        if url:
            album_queue.put(url)
            queue_list.insert(tk.END, url)
            status.set(f"Queued: {url}")
            entry.delete(0, tk.END)

    tk.Button(root, text="Add to Queue", command=add_album, bg="#1f4e5f", fg="#ffffff").pack(pady=5)

    def pause_resume():
        if pause_event.is_set():
            pause_event.clear()
            status.set("Paused")
        else:
            pause_event.set()
            status.set("Resumed")

    tk.Button(root, text="Pause/Resume", command=pause_resume, bg="#1f4e5f", fg="#ffffff").pack(pady=5)

    def worker_with_progress(status_cb):
        progress.start()
        queue_worker(status_cb)
        progress.stop()

    threading.Thread(target=worker_with_progress, args=(lambda s: status.set(s),), daemon=True).start()

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