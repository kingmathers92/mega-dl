import os
import sys
import time
import requests
from urllib.parse import urlparse
from tqdm import tqdm

HEADERS = {
    "User-Agent": "PixeldrainAlbumDownloader/1.0"
}

def extract_album_id(url: str) -> str:
    """
    Extract album ID from:
    https://pixeldrain.com/l/XXXXXX
    """
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "l":
        return parts[1]
    raise ValueError("Invalid Pixeldrain album URL")

def get_album_files(album_id: str):
    url = f"https://pixeldrain.com/api/list/{album_id}"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()["files"]

def download_file(file, output_dir):
    file_id = file["id"]
    name = file["name"]
    size = file["size"]

    url = f"https://pixeldrain.com/api/file/{file_id}"
    path = os.path.join(output_dir, name)

    if os.path.exists(path):
        return  # skip existing files

    with requests.get(url, headers=HEADERS, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(path, "wb") as f, tqdm(
            total=size,
            unit="B",
            unit_scale=True,
            desc=name,
            leave=False
        ) as bar:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    bar.update(len(chunk))

def main():
    if len(sys.argv) != 2:
        print("Usage: pixeldrain_dl <album_url>")
        sys.exit(1)

    album_url = sys.argv[1]
    album_id = extract_album_id(album_url)

    output_dir = f"downloads/{album_id}"
    os.makedirs(output_dir, exist_ok=True)

    print(f"Fetching album {album_id}...")
    files = get_album_files(album_id)
    print(f"Found {len(files)} files\n")

    for file in files:
        download_file(file, output_dir)
        time.sleep(0.5)  # rate limit (polite & safe)

    print("\n✅ All downloads complete")

if __name__ == "__main__":
    main()
