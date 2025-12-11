import os
import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from urllib.parse import urlparse

HEADERS = {
    "User-Agent": "PixeldrainAlbumDownloader/2.0"
}

MAX_WORKERS = 4      # safe parallelism
RATE_DELAY = 0.2    # polite delay

def extract_album_id(url: str) -> str:
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "l":
        return parts[1]
    raise ValueError("Invalid Pixeldrain album URL")

def safe_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    return name.strip() or "Pixeldrain Album"

def get_album_data(album_id: str):
    url = f"https://pixeldrain.com/api/list/{album_id}"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()

    album_name = data.get("name") or data.get("title") or f"Album_{album_id}"
    return safe_name(album_name), data.get("files", [])

def download_file(file, output_dir):
    file_id = file["id"]
    name = file["name"]
    size = file.get("size", 0)

    path = os.path.join(output_dir, name)
    temp_path = path + ".part"

    downloaded = 0
    headers = HEADERS.copy()

    if os.path.exists(path) and os.path.getsize(path) == size:
        return "skipped"

    if os.path.exists(temp_path):
        downloaded = os.path.getsize(temp_path)
        headers["Range"] = f"bytes={downloaded}-"

    url = f"https://pixeldrain.com/api/file/{file_id}"
    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        r.raise_for_status()
        mode = "ab" if downloaded else "wb"

        with open(temp_path, mode) as f, tqdm(
            total=size,
            initial=downloaded,
            unit="B",
            unit_scale=True,
            desc=name,
            leave=False
        ) as bar:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
                    bar.update(len(chunk))

    os.replace(temp_path, path)
    time.sleep(RATE_DELAY)
    return "downloaded"

def download_album(album_url: str, base_dir="downloads"):
    album_id = extract_album_id(album_url)
    album_name, files = get_album_data(album_id)

    output_dir = os.path.join(base_dir, album_name)
    os.makedirs(output_dir, exist_ok=True)

    # auto-skip album
    if all(
        os.path.exists(os.path.join(output_dir, f["name"]))
        and os.path.getsize(os.path.join(output_dir, f["name"])) == f.get("size", 0)
        for f in files
    ):
        return f"Album '{album_name}' already downloaded"

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(download_file, f, output_dir) for f in files]
        for future in as_completed(futures):
            results.append(future.result())

    return f"Album '{album_name}' completed"
