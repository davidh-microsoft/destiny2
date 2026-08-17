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
    resolve_finnald_wishlist.py  # PvP: Finnald / Pride Eternal sheet (Weapon Database, Tier S/A)
    build_wishlist.py       # assembles the final file: interleaves the PvP sources per weapon
    add_notes.py            # (legacy) title + per-weapon //notes: for the separate-section layout
    reorder_sections.py     # (legacy) orders the separate marked sections PvP-first
    pvp_weapons.json        # Daltnix weapon/perk spec
    cg_weapons_full.json    # r/CrucibleGuidebook weapon/perk spec
    data/
      google-sheets-destiny2/*.csv    # exported Endgame Analysis tabs (Tier S input)
      destiny2-endgame-analysis.xlsx  # workbook (name-cell light.gg hyperlinks)
      finnald-pvp-sheet/weapon-database.csv  # exported Finnald PvP Weapon Database tab
```

## Manifest

`manifest_util.manifest_db_path()` returns the extracted SQLite DB, unzipping
`manifest/manifest.content` into `manifest/world.sqlite` on first use. To refresh
to the latest Destiny 2 manifest (it changes with every game update):

```
python tools/wishlist/download_manifest.py   # rewrites manifest.content
```

## Regenerating the wishlist

Run from `tools/wishlist/`. `build_wishlist.py` is the assembler: it resolves
all three PvP sources in memory and writes the final `djsippycup-dim-wishlist.txt`
as a single **interleaved** section (see Conventions). Full rebuild:

```
cd tools/wishlist
python build_wishlist.py
```

This is idempotent (re-running reproduces the file byte-for-byte) and reads the
three source specs directly (`data/finnald-pvp-sheet/weapon-database.csv`,
`pvp_weapons.json`, `cg_weapons_full.json`). Run any `resolve_*` script without
`--generate` to print just that source's coverage report.

> **Legacy separate-section layout:** each `resolve_*_wishlist.py --generate`
> still rewrites its own marked section in place, and `add_notes.py` +
> `reorder_sections.py` produce the older layout with one section per source
> (and an optional PvE Tier S section). Do **not** mix these with
> `build_wishlist.py` output — `build_wishlist.py` emits a single
> `// … PVP INTERLEAVED` section and is the canonical build. The PvE
> (`resolve_tier_s_wishlist.py`) source is retained but not currently included.

## Conventions

- Layout: `build_wishlist.py` emits one interleaved section. Each weapon appears
  once; its rolls from all three PvP sources are merged, deduped by
  `(itemHash, sorted perks)`, and ordered by how many components they specify
  (barrels + magazines + perks), fullest first — DIM applies the first matching
  roll, so the most complete recommendation an item satisfies wins. Weapons are
  ordered by tier (S, A, then untiered) then name.
- Each weapon block has a single `//notes:` line that combines the sources it
  came from and keeps the Finnald Role/Notes text and tier tag, e.g.
  `Finnald + CrucibleGuidebook: <role/notes> tags:pvp#s`. DIM captures a block
  note up to the first `|` and has no structured tag parsing, so `tags:pvp#<tier>`
  is kept last (the Role/Notes text has `|`/`tags:` sanitized).
- Comments use `//`; rolls are ordered most-components-first (DIM applies the
  first matching line).
- Every item/perk hash is validated against the manifest sockets before use;
  perks that don't roll on a version are dropped, and fixed-roll exotics match
  via their intrinsic. Resolution edge cases are printed as warnings.
- PvE (Aegis) entries cover every non-empty perk subset (a weapon can roll
  multiple perks in the same column, so same-column combinations are included).
- PvP entries are tighter: each roll must include at least one perk from EACH
  trait column (grouped by the perk's actual manifest socket, not the spec's
  column layout), while still allowing multiple perks per column. Single-column-
  only rolls are dropped.
- The Finnald PvP source (`resolve_finnald_wishlist.py`, Weapon Database tab,
  Tier S/A) parses the sheet's Barrel / Magazine / Column 1 / Column 2 / Role /
  Notes cells. Rolls follow the per-column rule and add **optional barrel/mag
  prefix variants** (at most one barrel + one mag, with/without), so barrel/mag
  are recommended but never required. This is large by design (~1M rolls /
  ~100 MB). The sheet's Role / Notes text becomes each weapon's note. Weapon
  names, perks, barrels and mags are resolved against the manifest with
  loose/shorthand and alias matching; reissue variants of the same weapon are
  merged (perks unioned, strongest tier kept) and anything unresolved is
  dropped. Origin traits are not gated.
- PvP specs (`pvp_weapons.json` / `cg_weapons_full.json`) list trait perks under
  `columns`; a weapon may also carry optional `barrels` and `magazines` name
  lists, which are resolved and emitted as optional prefix variants (with/without,
  like the PvE resolver). Barrel/mag stay optional even under the PvP
  per-column rule.
- Origin Traits (PvE only, when the sheet lists one) are added as an optional
  prefix component alongside barrel/mag: each roll is generated with and without
  the origin trait, and once per resolved origin-trait hash when a name maps to
  several manifest copies. This roughly doubles the PvE entry count.
- `//notes:` block notes reset on any blank line or `//` comment, so each
  weapon's rolls are kept contiguous directly under its note.

