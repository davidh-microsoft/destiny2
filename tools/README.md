# Wishlist tooling

Scripts and data used to generate `djsippycup-dim-wishlist.txt`, plus a stored
copy of the Destiny 2 manifest so everything is reproducible in future runs.

Requires Python 3.10+ (uses only the standard library).

## Layout

```
tools/
  manifest/
    manifest.content        # zip-wrapped SQLite manifest (committed, ~34 MB)
    world.sqlite            # extracted DB (gitignored; created on demand)
  wishlist/
    manifest_util.py        # resolves/extracts the manifest DB
    download_manifest.py    # fetches the current manifest from Bungie
    resolve_tier_s_wishlist.py   # PvE: Tier S weapons from the Endgame Analysis sheet
    resolve_pvp_wishlist.py      # PvP: Daltnix video + r/CrucibleGuidebook
    add_notes.py            # adds title + per-weapon //notes: source tags
    pvp_weapons.json        # Daltnix weapon/perk spec
    cg_weapons_full.json    # r/CrucibleGuidebook weapon/perk spec
    data/
      google-sheets-destiny2/*.csv    # exported Endgame Analysis tabs (Tier S input)
      destiny2-endgame-analysis.xlsx  # workbook (name-cell light.gg hyperlinks)
```

## Manifest

`manifest_util.manifest_db_path()` returns the extracted SQLite DB, unzipping
`manifest/manifest.content` into `manifest/world.sqlite` on first use. To refresh
to the latest Destiny 2 manifest (it changes with every game update):

```
python tools/wishlist/download_manifest.py   # rewrites manifest.content
```

## Regenerating the wishlist

Run from `tools/wishlist/`. Each `resolve_*` script rewrites only its own marked
section of `../../djsippycup-dim-wishlist.txt`; `add_notes.py` must be run last.
Generation order matters (each section is appended after the previous one):

```
cd tools/wishlist
python resolve_tier_s_wishlist.py --generate          # PvE (Aegis) section
python resolve_pvp_wishlist.py --generate             # Daltnix PvP section
python resolve_pvp_wishlist.py --generate \
    --weapons cg_weapons_full.json \
    --report cg-full-resolution.json \
    --begin "// BEGIN GENERATED CRUCIBLEGUIDEBOOK PVP" \
    --end   "// END GENERATED CRUCIBLEGUIDEBOOK PVP"   # CrucibleGuidebook PvP section
python add_notes.py                                   # title + //notes: source tags
```

Run without `--generate` to only resolve hashes and print a coverage report.

## Conventions

- Comments use `//`; rolls are ordered most-perks-first (DIM applies the first
  matching line).
- Every item/perk hash is validated against the manifest sockets before use.
- Entries cover every non-empty perk subset (a weapon can roll multiple perks in
  the same column, so same-column combinations are included).
- `//notes:` block notes reset on any blank line or `//` comment, so each
  weapon's rolls are kept contiguous directly under its note.
