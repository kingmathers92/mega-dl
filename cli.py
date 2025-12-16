import sys
from mega_dl import download_album

if len(sys.argv) != 2:
    print("Usage: pixeldrain_dl <album_url>")
    sys.exit(1)

print(download_album(sys.argv[1]))
