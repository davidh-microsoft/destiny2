"""Assemble the DIM wishlist, interleaving the three PvP sources per weapon.

Instead of three separate source sections (Finnald, Daltnix, CrucibleGuidebook),
this builds a single section where each weapon appears once and its rolls from
all three sources are merged, deduped, and ordered by how many components they
specify (barrels + magazines + perks), fullest first. DIM applies the first
matching roll, so the most complete recommendation an item satisfies wins.

Each weapon block gets one block note that combines the sources it came from,
keeping the Finnald Role/Notes text and the tier tag, e.g.:

    // Gnawing Hunger [Tier S]
    //notes: Finnald + CrucibleGuidebook: <role/notes> tags:pvp#s
    dimwishlist:item=...&perks=...   (rolls, fullest first)

This replaces resolve_*_wishlist.py --generate + add_notes.py +
reorder_sections.py for producing djsippycup-dim-wishlist.txt. The individual
resolvers still run standalone (with --generate / reports) for debugging.

Run from tools/wishlist:  python build_wishlist.py
"""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import resolve_finnald_wishlist as finnald  # noqa: E402
import resolve_pvp_wishlist as pvp  # noqa: E402

REPO_WISHLIST = HERE.parents[1] / "djsippycup-dim-wishlist.txt"
TITLE = "title:DJSippyCup - MoT (GHCP)"
BEGIN = "// BEGIN GENERATED PVP INTERLEAVED"
END = "// END GENERATED PVP INTERLEAVED"
SECTION_NOTE = (
    "// Source: interleaved per weapon across Finnald / Daltnix / "
    "CrucibleGuidebook; rolls ordered by matching barrels+mags+perks "
    "(fullest first). Notes combine the sources; Finnald Role/Notes kept."
)

# Canonical display/priority order for the source labels in each note.
CANON_SOURCES = ["Finnald", "Daltnix", "CrucibleGuidebook"]
TIER_RANK = {"s": 0, "a": 1, "b": 2, "": 3, None: 3}


def roll_hashes(line):
    """The hash list of a dimwishlist line, or [] for a bare-item line."""
    if "&perks=" not in line:
        return []
    body = line.split("&perks=", 1)[1].split("#", 1)[0]
    return [int(x) for x in body.split(",") if x]


def dimwishlist_lines(lines):
    return [l for l in lines if l.startswith("dimwishlist:")]


class Weapon:
    __slots__ = ("display", "sources", "tier", "role", "rolls")

    def __init__(self, display):
        self.display = display
        self.sources = set()
        self.tier = None
        self.role = None
        self.rolls = {}  # (item_hash, sorted-unique perk tuple) -> line


def add_weapon(weapons, name, source, tier, role, lines):
    key = pvp.normalize(name)
    weapon = weapons.get(key)
    if weapon is None:
        weapon = Weapon(name)
        weapons[key] = weapon
    weapon.sources.add(source)
    if source == "Finnald":
        weapon.display = name  # prefer the sheet's display name
        if tier:
            weapon.tier = tier
        if role:
            weapon.role = role
    for line in dimwishlist_lines(lines):
        hashes = roll_hashes(line)
        item_hash = int(line.split("item=", 1)[1].split("&", 1)[0])
        key_perks = tuple(sorted(set(hashes)))
        weapon.rolls.setdefault((item_hash, key_perks), line)


def collect():
    items, items_by_name, plug_sets = pvp.load_manifest()
    weapons = {}

    # Finnald (Weapon Database, Tier S/A) -- has tier + role.
    sheet = finnald.read_sheet_weapons()
    loose_index = finnald.build_loose_weapon_index(items_by_name)
    for w in sheet:
        result = finnald.resolve_weapon(w, items, items_by_name, plug_sets, loose_index)
        if not result["selected"]:
            continue
        add_weapon(
            weapons,
            result["name"],
            "Finnald",
            result.get("tier"),
            result.get("role"),
            finnald.generate_weapon_lines(result),
        )

    # Daltnix video + r/CrucibleGuidebook (JSON specs) -- no tier/role.
    for spec_path, source in (
        (pvp.WEAPONS, "Daltnix"),
        (HERE / "cg_weapons_full.json", "CrucibleGuidebook"),
    ):
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
        for w in spec["weapons"]:
            result = pvp.resolve_weapon(w, items, items_by_name, plug_sets)
            if not result["selected"]:
                continue
            add_weapon(
                weapons,
                result["name"],
                source,
                None,
                None,
                pvp.generate_weapon_block(result),
            )
    return weapons


def compose_note(weapon):
    sources = " + ".join(s for s in CANON_SOURCES if s in weapon.sources)
    note = sources
    if weapon.role:
        note += f": {weapon.role}"
    note += " tags:pvp"
    if weapon.tier:
        note += f"#{weapon.tier.lower()}"
    return note


def component_count(line):
    return len(roll_hashes(line))


def weapon_block(weapon):
    header = f"// {weapon.display}"
    if weapon.tier:
        header += f" [Tier {weapon.tier.upper()}]"
    ordered = sorted(weapon.rolls.values(), key=lambda l: (-component_count(l), l))
    return [header, f"//notes: {compose_note(weapon)}", *ordered, ""]


def build():
    weapons = collect()
    order = sorted(
        weapons.values(),
        key=lambda w: (TIER_RANK.get(w.tier, 3), w.display.casefold()),
    )

    section = [BEGIN, SECTION_NOTE, ""]
    total_rolls = 0
    for weapon in order:
        block = weapon_block(weapon)
        section.extend(block)
        total_rolls += sum(1 for l in block if l.startswith("dimwishlist:"))
    while section and section[-1] == "":
        section.pop()
    section.append(END)

    REPO_WISHLIST.write_text(
        TITLE + "\n\n" + "\n".join(section).rstrip("\n") + "\n", encoding="utf-8"
    )

    source_counts = Counter()
    for weapon in weapons.values():
        source_counts[" + ".join(s for s in CANON_SOURCES if s in weapon.sources)] += 1
    print(f"Weapons (merged): {len(weapons)}")
    print(f"Unique rolls: {total_rolls}")
    print("Weapons by source combination:")
    for combo, count in sorted(source_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {count:>4}  {combo}")
    print(f"Wishlist: {REPO_WISHLIST}")


if __name__ == "__main__":
    build()
