import os
import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from urllib.parse import urlparse

HEADERS = {
    "User-Agent": "PixeldrainAlbumDownloader/2.1"
}

MAX_WORKERS = 3        # 🔴 4 is borderline, 3 is safe
MAX_RETRIES = 5
RATE_DELAY = 0.3      # polite delay

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

    # Already done
    if os.path.exists(path) and size > 0 and os.path.getsize(path) == size:
        return "skipped"

    attempt = 0
    while attempt < MAX_RETRIES:
        try:
            headers = HEADERS.copy()
            downloaded = 0

            if os.path.exists(temp_path):
                downloaded = os.path.getsize(temp_path)
                headers["Range"] = f"bytes={downloaded}-"

            url = f"https://pixeldrain.com/api/file/{file_id}"
            with requests.get(url, headers=headers, stream=True, timeout=60) as r:
                if r.status_code == 403:
                    raise requests.exceptions.HTTPError("403")

                r.raise_for_status()

                mode = "ab" if downloaded else "wb"
                with open(temp_path, mode) as f, tqdm(
                    total=size if size > 0 else None,
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

        except requests.exceptions.HTTPError:
            attempt += 1
            wait = 2 ** attempt
            print(f"\n⚠ 403 on {name}, retry {attempt}/{MAX_RETRIES} in {wait}s")
            time.sleep(wait)

        except Exception as e:
            print(f"\n❌ Error downloading {name}: {e}")
            return "failed"

    print(f"\n❌ Gave up on {name}")
    return "failed"

def download_album(album_url: str, base_dir="downloads"):
    album_id = extract_album_id(album_url)
    album_name, files = get_album_data(album_id)

    output_dir = os.path.join(base_dir, album_name)
    os.makedirs(output_dir, exist_ok=True)

    # Auto-skip album
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
            try:
                results.append(future.result())
            except Exception as e:
                #  SAFETY NET — should never crash now
                print(f"\n❌ Thread error: {e}")

    ok = results.count("downloaded")
    skipped = results.count("skipped")
    failed = results.count("failed")

    return (
        f"Album '{album_name}' completed\n"
        f"Downloaded: {ok}, Skipped: {skipped}, Failed: {failed}"
    )
