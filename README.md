# MegaDL

MegaDL is a fast, safe, and user-friendly tool for downloading albums from multiple file hosting services

*(Future support for: AnonFiles, File.io, MediaFire, Mega.nz, Zippyshare, Dropbox/Google Drive public links)*

It supports **parallel downloads**, **resume**, **album queueing**, **speed limiting**, and a **dark-mode GUI**.

## Features

- ✅ Parallel downloads (safe & fast)
- ✅ Resume interrupted files
- ✅ Auto-skip already downloaded files
- ✅ Album queue support
- ✅ Speed limiter / bandwidth cap
- ✅ CLI + GUI (drag & drop)
- ✅ Dark-mode GUI
- ✅ Windows `.exe` build ready

## Installation
```bash
pip install -r requirements.txt
```

## Usage
### CLI Mode
```bash
def python mega_dl.py <album_url1> <album_url2> ...
```
### GUI Mode
```bash
def python mega_dl.py  # then drag & drop album URLs to add to the queue.
```
*Supports adding multiple albums to the queue and real-time download progress.*

## Folder Structure Example
```plaintext
downloads/
├─ PixeldrainAlbum/
│  ├─ file1.jpg
│  └─ file2.mp4
├─ BunkrAlbum/
│  ├─ file1.jpg
│  └─ file2.mp4
```

## Adding New Sites
Create a new adapter class implementing:
```python
def get_album_name(self): ...
def get_files(self): ...
def download_file(self, file, output_dir): ...
```
Then add it to the `get_adapter(url)` factory.

## Building Windows Executable
```bash
git install pyinstaller
pip install pyinstaller
pyinstaller --onefile --windowed --icon=icon.ico multihost_downloader.py
defaults to using PyInstaller for packaging.
```
## License
MIT License. Use responsibly.

## Disclaimer
For personal use only. Respect copyright and terms of service of hosting sites.