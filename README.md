# Pixeldrain Downloader

**Pixeldrain Downloader** is a fast, safe, and user-friendly tool for downloading albums and files from [Pixeldrain](https://pixeldrain.com). It supports both **CLI and GUI**, parallel downloads, resume functionality, album queueing, speed limiting, and a modern dark-mode interface.

This application is designed to overcome common issues with Pixeldrain, including 403 errors, server rate limits, and interruptions.

---

## Features

- ✅ **Parallel Downloads** – safely download multiple files at the same time
- ✅ **Resume Interrupted Files** – automatically continue partially downloaded files
- ✅ **Auto-skip Already Downloaded Albums** – saves bandwidth and time
- ✅ **Album Queue Support** – download multiple albums in order
- ✅ **Speed Limiter / Bandwidth Cap** – prevent network saturation or server bans
- ✅ **CLI + GUI** – single entry file works in terminal or with a dark-mode GUI
- ✅ **Drag & Drop Support (GUI)** – simply drag Pixeldrain album links
- ✅ **Windows `.exe` Build Support** – easy distribution with PyInstaller
- ✅ **Safe & Resilient** – handles Pixeldrain 403 errors with retries

---

## Installation

### Requirements

- Python 3.11 or 3.12 (recommended)
- `requests` library
- `tqdm` library
- `tkinter` (built-in with Python)

Install dependencies:

```bash
pip install requests tqdm

Usage
-----

### CLI Mode

`   python pixeldrain_downloader.py  [ ...]   `

*   Downloads one or more albums from the command line

*   Automatically resumes partial downloads

*   Prints status for each album:


`   AlbumName: ok=5 skip=0 fail=0   `

### GUI Mode

Simply run the script **without arguments**:

`   python pixeldrain_downloader.py   `

*   Dark-mode interface

*   Enter or drag & drop Pixeldrain album URLs

*   Add multiple albums to the queue

*   Real-time download status updates


Folder Structure
----------------

Downloaded albums are saved in the downloads/ folder by default. Each album will have its own folder named after the album title.

`   downloads/  ├─ Album1/  │  ├─ file1.jpg  │  └─ file2.mp4  ├─ Album2/  │  ├─ file1.jpg  │  └─ file2.mp4   `

Advanced Configuration
----------------------

You can edit the following variables at the top of the script:

`   MAX_WORKERS = 3        # Parallel downloads  MAX_RETRIES = 5        # Retry attempts for failed downloads  RATE_DELAY = 0.3       # Delay between file downloads (seconds)  SPEED_LIMIT_KB = 512   # Max download speed per file (0 = unlimited)  BASE_DIR = "downloads" # Output folder   `

Building a Windows Executable
-----------------------------

You can build a .exe file with PyInstaller:

`   pip install pyinstaller  pyinstaller --onefile --windowed --icon=icon.ico pixeldrain_downloader.py   `

*   The output executable will be in the dist/ folder

*   Supports both CLI and GUI automatically


Why This Downloader is Better
-----------------------------

*   Handles Pixeldrain 403 errors with **retries and exponential backoff**

*   Safe parallel downloads without crashing

*   Resume support with .part temporary files

*   Auto-skips already downloaded files

*   Album queue support for multiple albums

*   Speed limiting to avoid server blocks


License
-------

This project is open-source and free to use under the MIT License.

Disclaimer
----------

Pixeldrain Downloader is designed for personal use. Please respect copyright laws and the terms of service of Pixeldrain. The developers are **not responsible for misuse**.

Contact
-------

For issues or feature requests, open an issue on this repository.