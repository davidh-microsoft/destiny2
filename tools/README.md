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
    resolve_tier_s_wishlist.py   # PvE: Tier S + Tier A weapons from the Endgame Analysis sheet
    resolve_pvp_wishlist.py      # PvP: Daltnix video + r/CrucibleGuidebook
    add_notes.py            # adds title + per-weapon //notes: source tags
    reorder_sections.py     # moves PvP sections above the PvE (Tier S) section
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
section in place (preserving the other sections), so they can be run in any
order. `add_notes.py` then applies the title and notes, and
`reorder_sections.py` puts the PvP sections first. Full rebuild:

```
cd tools/wishlist
python resolve_tier_s_wishlist.py --generate          # PvE (Aegis) section, incl. DECATUR 02
python resolve_pvp_wishlist.py --generate             # Daltnix PvP section
python resolve_pvp_wishlist.py --generate \
    --weapons cg_weapons_full.json \
    --report cg-full-resolution.json \
    --begin "// BEGIN GENERATED CRUCIBLEGUIDEBOOK PVP" \
    --end   "// END GENERATED CRUCIBLEGUIDEBOOK PVP"   # CrucibleGuidebook PvP section
python add_notes.py                                   # title + //notes: source tags
python reorder_sections.py                            # PvP sections above PvE
```

This pipeline is idempotent (re-running reproduces the file byte-for-byte). Run
any `resolve_*` script without `--generate` to only print a coverage report.

## Conventions

- Section order: PvP (Daltnix, then CrucibleGuidebook) precedes PvE (the Aegis
  Tier S + Tier A weapons, which include DECATUR 02) so DIM matches PvP first.
- Sections are self-contained (no cross-section dedup). DIM dedups globally and
  keeps the first occurrence, so a roll shared by PvP and PvE is matched as PvP.
- Notes carry the source and, for PvE, the sheet tier: `Aegis tags:pve#s`
  (Tier S) or `Aegis tags:pve#a` (Tier A); PvP notes are `Daltnix tags:pvp` /
  `CrucibleGuidebook tags:pvp`.
- Comments use `//`; rolls are ordered most-perks-first (DIM applies the first
  matching line).
- Every item/perk hash is validated against the manifest sockets before use;
  perks that don't roll on a version are dropped, and fixed-roll exotics match
  via their intrinsic. Resolution edge cases are printed as warnings.
- Entries cover every non-empty perk subset (a weapon can roll multiple perks in
  the same column, so same-column combinations are included).
- Origin Traits (PvE only, when the sheet lists one) are added as an optional
  prefix component alongside barrel/mag: each roll is generated with and without
  the origin trait, and once per resolved origin-trait hash when a name maps to
  several manifest copies. This roughly doubles the PvE entry count.
- `//notes:` block notes reset on any blank line or `//` comment, so each
  weapon's rolls are kept contiguous directly under its note.

