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
    resolve_finnald_wishlist.py  # PvP: Finnald / Pride Eternal sheet (Weapon Database, Tier S/A/B)
    add_notes.py            # adds title + per-weapon //notes: source tags
    reorder_sections.py     # moves PvP sections above the PvE (Tier S) section
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
python resolve_finnald_wishlist.py --generate         # Finnald PvP section (Tier S/A/B)
python add_notes.py                                   # title + //notes: source tags
python reorder_sections.py                            # PvP sections above PvE
```

This pipeline is idempotent (re-running reproduces the file byte-for-byte). Run
any `resolve_*` script without `--generate` to only print a coverage report.

> **Note:** the current `djsippycup-dim-wishlist.txt` is **PvP-only** — the PvE
> (Aegis Tier S/A) section was removed on request. The tooling above still
> generates it, so running `resolve_tier_s_wishlist.py --generate` re-adds the
> Tier S section (then `add_notes.py` + `reorder_sections.py` place it after the
> PvP sections). All PvP scripts and `reorder_sections.py` work whether or not
> the Tier S section is present.

## Conventions

- Section order: PvP (Finnald, then Daltnix, then CrucibleGuidebook) precedes
  PvE (the Aegis Tier S section) so DIM matches PvP first.
- Sections are self-contained (no cross-section dedup). DIM dedups globally and
  keeps the first occurrence, so a roll shared by PvP and PvE is matched as PvP.
- Notes carry the source and, where the source has tiers, a `#<tier>` suffix:
  `Aegis tags:pve#s`/`#a` (PvE), `Daltnix tags:pvp` / `CrucibleGuidebook
  tags:pvp`, and `Finnald tags:pvp#s`/`#a`/`#b` (Finnald PvP sheet).
- Comments use `//`; rolls are ordered most-perks-first (DIM applies the first
  matching line).
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
  Tier S/A/B) parses the sheet's Barrel / Magazine / Column 1 / Column 2 /
  Origin Trait cells. It emits **perks-only** rolls under the per-column rule:
  barrel / magazine / origin are left genuinely optional (never gated), which
  keeps the section usable (~87k rolls) instead of exploding on every
  barrel×mag×origin combination. Weapon names, perks, barrels, mags and origins
  are resolved against the manifest with loose/shorthand and alias matching;
  reissue variants of the same weapon are merged (perks unioned, strongest tier
  kept) and anything unresolved is dropped.
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

