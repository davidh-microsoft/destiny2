"""Locate (and if necessary materialise) the Destiny 2 manifest database.

The raw, zip-wrapped manifest is committed at ``tools/manifest/manifest.content``.
The extracted SQLite database (~340 MB) is gitignored and produced on demand.
If the committed content is missing, the current manifest is downloaded from
Bungie via :mod:`download_manifest`.
"""
from pathlib import Path
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
MANIFEST_DIR = REPO_ROOT / "tools" / "manifest"
CONTENT = MANIFEST_DIR / "manifest.content"
EXTRACTED = MANIFEST_DIR / "world.sqlite"


def _extract(content: Path, target: Path) -> None:
    with ZipFile(content) as archive:
        names = archive.namelist()
        if not names:
            raise RuntimeError(f"{content} is not a valid manifest archive")
        with archive.open(names[0]) as src, target.open("wb") as dst:
            dst.write(src.read())


def manifest_db_path() -> Path:
    """Return a path to an extracted SQLite manifest, creating it if needed."""
    if EXTRACTED.exists():
        return EXTRACTED
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    if not CONTENT.exists():
        # Fall back to downloading the current manifest.
        from download_manifest import download_manifest

        download_manifest(MANIFEST_DIR)
    _extract(CONTENT, EXTRACTED)
    return EXTRACTED


if __name__ == "__main__":
    print(manifest_db_path())
