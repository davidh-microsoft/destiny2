"""Download the current Destiny 2 world manifest (zip-wrapped SQLite).

Fetches the manifest metadata from the public Bungie endpoint, downloads the
English ``mobileWorldContentPaths`` file, and saves it as
``tools/manifest/manifest.content``. No API key is required for these public
content files.
"""
import json
import sys
import urllib.request
from pathlib import Path

MANIFEST_ENDPOINT = "https://www.bungie.net/Platform/Destiny2/Manifest/"
BUNGIE = "https://www.bungie.net"
UA = "Mozilla/5.0 (destiny2-wishlist-tools)"

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "manifest"


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def download_manifest(dest_dir: Path = DEFAULT_DIR, language: str = "en") -> Path:
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    meta = json.loads(_get(MANIFEST_ENDPOINT).decode("utf-8"))
    version = meta["Response"]["version"]
    path = meta["Response"]["mobileWorldContentPaths"][language]
    print(f"Manifest version {version}; downloading {path}")
    data = _get(BUNGIE + path)
    out = dest_dir / "manifest.content"
    out.write_bytes(data)
    (dest_dir / "manifest.version.txt").write_text(version, encoding="utf-8")
    extracted = dest_dir / "world.sqlite"
    if extracted.exists():
        extracted.unlink()  # invalidate stale extraction
    print(f"Saved {out} ({len(data) / 1_000_000:.1f} MB)")
    return out


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    download_manifest(target)
