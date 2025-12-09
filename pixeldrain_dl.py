import os
import sys
import time
import re
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

def safe_folder_name(name: str) -> str:
    """
    Make folder name safe for Windows/Linux/macOS
    """
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.strip()
    return name if name else "Pixeldrain Album"

def get_album_data(album_id: str):
    url = f"https://pixeldrain.com/api/list/{album_id}"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data["name"], data["files"]

def download_file(file, output_dir):
    file_id = file["id"]
    name = file["name"]
    size = file["size"]

    path = os.path.join(output_dir, name)

    if os.path.exists(path):
        return

    url = f"https://pixeldrain.com/api/file/{file_id}"

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
        print("Usage: python pixeldrain_dl.py <album_url>")
        sys.exit(1)

    album_url = sys.argv[1]

    try:
        album_id = extract_album_id(album_url)
    except ValueError as e:
        print(e)
        sys.exit(1)

    print("Fetching album info...")
    album_name, files = get_album_data(album_id)

    safe_name = safe_folder_name(album_name)
    output_dir = os.path.join("downloads", safe_name)
    os.makedirs(output_dir, exist_ok=True)

    print(f"\nAlbum: {album_name}")
    print(f"Files: {len(files)}")
    print(f"Saving to: {output_dir}\n")

    for file in files:
        download_file(file, output_dir)
        time.sleep(0.5)  # polite rate limit

    print("\n✅ Download completed successfully")

if __name__ == "__main__":
    main()
