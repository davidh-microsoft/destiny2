"""Generate DIM PvP rolls from Finnald's / Pride Eternal Destiny 2 PvP sheet.

Source: the "Weapon Database" tab of Finnald's PvP spreadsheet, exported to
``data/finnald-pvp-sheet/weapon-database.csv``. Each row lists a weapon with
Barrel / Magazine / Column 1 / Column 2 / Origin Trait recommendations and a
Tier. Only Tier S, A and B rows are used.

Like the CrucibleGuidebook PvP generator, rolls follow the PvP per-column rule:
every roll must include at least one perk from EACH trait column (grouped by the
perk's actual manifest socket), while barrel / magazine / origin trait are
optional prefix variants (at most one from each group, with/without). Weapon
names, perks, barrels, mags and origins are resolved against the manifest;
anything that does not roll on the current weapon version is dropped.

Run from ``tools/wishlist``:

    python resolve_finnald_wishlist.py            # coverage report only
    python resolve_finnald_wishlist.py --generate # write the FINNALD section
"""
import argparse
import csv
import itertools
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from resolve_pvp_wishlist import (  # noqa: E402
    WEAPON_BUCKET_HASHES,
    candidate_weapons,
    dedupe,
    entry_plug_hashes,
    load_manifest,
    normalize,
    roll_key,
)

REPO_ROOT = HERE.parents[1]
CSV_PATH = HERE / "data" / "finnald-pvp-sheet" / "weapon-database.csv"
REPO_WISHLIST = REPO_ROOT / "djsippycup-dim-wishlist.txt"
BEGIN = "// BEGIN GENERATED FINNALD PVP"
END = "// END GENERATED FINNALD PVP"

TIERS = ("S", "A", "B")
TIER_RANK = {"S": 0, "A": 1, "B": 2}

# Socket kinds (itemTypeDisplayName) that are never a barrel/mag-equivalent slot.
COSMETIC_KINDS = {
    "",
    "Shader",
    "Weapon Mod",
    "Memento",
    "Combat Flair",
    "Restore Defaults",
    "Tracker",
    "Intrinsic",
}

# Sheet weapon names that are misspelled relative to the manifest.
# Keys are ``loose()``-normalized (lowercase, no spaces/punctuation).
NAME_ALIASES = {
    "glaciocasm": "Glacioclasm",
    "eyasaluna": "Eyasluna",
    "willfulharmatia": "Willful Hamartia",
    "fimbulwintersnitch": "Fimbulwinter Stitch",
    "mykelsreverance": "Mykel's Reverence",
    "sherpardswatch": "Shepherd's Watch",
    "appetance": "Appetence",
}


def loose(value: str) -> str:
    """Aggressive normalization for shorthand matching (no diacritics/punct)."""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def strip_parenthetical(name: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()


def split_cell(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


# --------------------------------------------------------------------------- #
# Sheet reading
# --------------------------------------------------------------------------- #
def read_sheet_weapons():
    rows = list(csv.reader(CSV_PATH.open(newline="", encoding="utf-8-sig")))
    header = rows[1]
    index = {name: i for i, name in enumerate(header) if name}

    def cell(row, column):
        i = index.get(column)
        return row[i].strip() if i is not None and i < len(row) else ""

    # Merge rows that describe the same base weapon (sheet lists reissue
    # variants separately); union their perks/barrels/mags/origins and keep the
    # strongest tier.
    merged: dict[str, dict] = {}
    order: list[str] = []
    for row in rows[2:]:
        name = cell(row, "Name")
        tier = cell(row, "Tier")
        if not name or tier not in TIERS:
            continue
        base = strip_parenthetical(name)
        key = loose(base)
        if key not in merged:
            merged[key] = {
                "name": base,
                "type": cell(row, "Type").replace("\n", " "),
                "tier": tier,
                "barrels": [],
                "magazines": [],
                "perks_1": [],
                "perks_2": [],
                "origins": [],
            }
            order.append(key)
        weapon = merged[key]
        if TIER_RANK[tier] < TIER_RANK[weapon["tier"]]:
            weapon["tier"] = tier
        weapon["barrels"] += split_cell(cell(row, "Barrel"))
        weapon["magazines"] += split_cell(cell(row, "Magazine"))
        weapon["perks_1"] += split_cell(cell(row, "Column 1"))
        weapon["perks_2"] += split_cell(cell(row, "Column 2"))
        weapon["origins"] += split_cell(cell(row, "Origin Trait"))

    weapons = []
    for key in order:
        w = merged[key]
        for field in ("barrels", "magazines", "perks_1", "perks_2", "origins"):
            w[field] = dedupe(w[field])
        w["perks"] = dedupe(w["perks_1"] + w["perks_2"])
        weapons.append(w)
    return weapons


# --------------------------------------------------------------------------- #
# Manifest resolution
# --------------------------------------------------------------------------- #
def build_loose_weapon_index(items_by_name):
    index = defaultdict(list)
    for defs in items_by_name.values():
        for definition in defs:
            name = definition.get("displayProperties", {}).get("name", "")
            index[loose(name)].append(definition)
    return index


def find_candidates(name, items_by_name, loose_index):
    alias = NAME_ALIASES.get(loose(strip_parenthetical(name)))
    lookup = alias or name
    candidates = candidate_weapons(lookup, items_by_name)
    if candidates:
        return candidates
    base = strip_parenthetical(lookup)
    if base != lookup:
        candidates = candidate_weapons(base, items_by_name)
        if candidates:
            return candidates
    return [
        definition
        for definition in loose_index.get(loose(base), [])
        if definition.get("itemType") == 3
        and (definition.get("inventory") or {}).get("isInstanceItem")
        and (definition.get("inventory") or {}).get("bucketTypeHash")
        in WEAPON_BUCKET_HASHES
    ]


def socket_layout(candidate, items, plug_sets):
    """Classify a weapon's sockets into trait/origin/barrel/mag groups."""
    sockets = (candidate.get("sockets") or {}).get("socketEntries") or []
    parsed = []
    for idx, entry in enumerate(sockets):
        by_name = defaultdict(list)
        by_loose = defaultdict(list)
        kinds = Counter()
        for plug_hash in entry_plug_hashes(entry, plug_sets):
            plug = items.get(plug_hash)
            if not plug:
                continue
            kind = plug.get("itemTypeDisplayName") or ""
            if kind.startswith("Enhanced "):
                continue
            name = plug.get("displayProperties", {}).get("name")
            if not name:
                continue
            kinds[kind] += 1
            by_name[normalize(name)].append(plug_hash)
            by_loose[loose(name)].append(plug_hash)
        if not kinds:
            continue
        parsed.append(
            {
                "idx": idx,
                "kind": kinds.most_common(1)[0][0],
                "names": {k: dedupe(v) for k, v in by_name.items()},
                "loose": {k: dedupe(v) for k, v in by_loose.items()},
            }
        )

    trait_sockets = [s for s in parsed if s["kind"] == "Trait"]
    origin_sockets = [s for s in parsed if s["kind"] == "Origin Trait"]
    first_trait = min((s["idx"] for s in trait_sockets), default=99)
    pre = sorted(
        (
            s
            for s in parsed
            if 0 < s["idx"] < first_trait and s["kind"] not in COSMETIC_KINDS
        ),
        key=lambda s: s["idx"],
    )
    barrel_socket = pre[0] if len(pre) >= 1 else None
    magazine_socket = pre[1] if len(pre) >= 2 else None
    return trait_sockets, barrel_socket, magazine_socket, origin_sockets


def match_exact(token, sockets):
    key = normalize(token)
    hits = []
    for socket in sockets:
        for plug_hash in socket["names"].get(key, []):
            hits.append((socket["idx"], plug_hash))
    return hits


def match_loose(token, sockets):
    key = loose(token)
    if not key:
        return []
    hits = []
    for socket in sockets:
        if key in socket["loose"]:
            hits += [(socket["idx"], h) for h in socket["loose"][key]]
        else:
            for candidate_key, plug_hashes in socket["loose"].items():
                if len(key) >= 4 and (
                    candidate_key.startswith(key) or key.startswith(candidate_key)
                ):
                    hits += [(socket["idx"], h) for h in plug_hashes]
    return dedupe(hits)


def resolve_perk(token, trait_sockets):
    return match_exact(token, trait_sockets) or match_loose(token, trait_sockets)


def resolve_weapon(weapon, items, items_by_name, plug_sets, loose_index):
    candidates = find_candidates(weapon["name"], items_by_name, loose_index)
    if not candidates:
        return {**weapon, "selected": [], "reason": "no manifest candidate"}

    resolved_candidates = []
    for candidate in candidates:
        traits = socket_layout(candidate, items, plug_sets)[0]
        perk_hashes = {}
        socket_of = {}
        for perk in weapon["perks"]:
            hits = resolve_perk(perk, traits)
            if hits:
                perk_hashes[perk] = dedupe(h for _, h in hits)
                socket_of[perk] = hits[0][0]
        resolved_candidates.append(
            {
                "hash": candidate["hash"],
                "index": candidate.get("index") or 0,
                "coverage": len(perk_hashes),
                "perk_hashes": perk_hashes,
                "socket_of": socket_of,
            }
        )

    best = max((c["coverage"] for c in resolved_candidates), default=0)
    selected = [c for c in resolved_candidates if c["coverage"] == best and best > 0]
    selected.sort(key=lambda c: (-c["index"], c["hash"]))
    reason = "" if selected else "no listed perks roll on any version"
    return {**weapon, "selected": selected, "reason": reason}


# --------------------------------------------------------------------------- #
# Roll generation
# --------------------------------------------------------------------------- #
def nonempty_subsets(values):
    for size in range(len(values), 0, -1):
        yield from itertools.combinations(values, size)


def candidate_block(weapon, candidate, position):
    item_hash = candidate["hash"]
    perk_hashes = candidate["perk_hashes"]
    supported = [p for p in weapon["perks"] if p in perk_hashes]

    columns = defaultdict(list)
    for perk in supported:
        columns[candidate["socket_of"][perk]].append(perk)
    perk_columns = [columns[idx] for idx in sorted(columns)]

    label = f"// itemHash={item_hash}"
    if position > 0:
        label += " (alternate item version)"
    lines = [label]
    lines.append(
        "// perks: "
        + "; ".join(f"{p}={'|'.join(map(str, perk_hashes[p]))}" for p in supported)
    )
    lines.append("")

    # Perks only: a perks-only roll matches the weapon regardless of which
    # barrel / magazine / origin it rolled, so those stay genuinely optional
    # (they are never gated) without exploding the file with every combination.
    name_combos = [
        [perk for subset in chosen for perk in subset]
        for chosen in itertools.product(
            *[list(nonempty_subsets(col)) for col in perk_columns]
        )
    ]
    name_combos.sort(key=lambda names: -len(names))

    for names in name_combos:
        for hash_choice in itertools.product(*[perk_hashes[n] for n in names]):
            combined = dedupe(list(hash_choice))
            yield lines, (
                f"dimwishlist:item={item_hash}&perks="
                + ",".join(map(str, combined))
            )
    return


def generate_weapon_lines(weapon):
    header = [
        f"// {weapon['type']}: {weapon['name']} [Tier {weapon['tier']}]",
        f"// tier: {weapon['tier']}",
    ]
    blocks = []
    for position, candidate in enumerate(weapon["selected"]):
        block_lines = None
        rolls = []
        for lines, roll in candidate_block(weapon, candidate, position):
            block_lines = lines
            rolls.append(roll)
        if block_lines:
            blocks.append((block_lines, rolls))
    if not blocks:
        return []
    out = list(header)
    for block_lines, rolls in blocks:
        out += block_lines + rolls + [""]
    return out


# --------------------------------------------------------------------------- #
# Wishlist assembly
# --------------------------------------------------------------------------- #
def generate_wishlist(weapons):
    original = REPO_WISHLIST.read_text(encoding="utf-8")
    if BEGIN in original:
        before = original.split(BEGIN, 1)[0].rstrip("\n")
        tail = original.split(BEGIN, 1)[1]
        after = tail.split(END, 1)[1] if END in tail else ""
    else:
        before = original.rstrip("\n")
        after = ""
    after = after.strip("\n")

    seen_rolls = set()
    section = [BEGIN, "// Source: Finnald / Pride Eternal Destiny 2 PvP Spreadsheet "
               "(Weapon Database tab, Tier S/A/B). Perks/barrels/mags/origins "
               "resolved to the current manifest; unavailable ones dropped.", ""]
    block_count = 0
    for weapon in weapons:
        if not weapon["selected"]:
            continue
        lines = generate_weapon_lines(weapon)
        filtered = []
        for line in lines:
            if line.startswith("dimwishlist:"):
                key = roll_key(line)
                if key in seen_rolls:
                    continue
                seen_rolls.add(key)
            filtered.append(line)
        # drop weapons whose rolls were all duplicates
        if any(l.startswith("dimwishlist:") for l in filtered):
            section.extend(filtered)
            block_count += 1

    while section and section[-1] == "":
        section.pop()
    section.append(END)

    parts = [before, "", "\n".join(section)]
    if after:
        parts += ["", after]
    REPO_WISHLIST.write_text("\n".join(parts).rstrip("\n") + "\n", encoding="utf-8")
    print(f"Weapon blocks: {block_count}")
    print(f"Unique rolls: {len(seen_rolls)}")
    print(f"Wishlist: {REPO_WISHLIST}")


def print_report(results):
    resolved = [r for r in results if r["selected"]]
    unresolved = [r for r in results if not r["selected"]]
    print(f"Sheet weapons (S/A/B, deduped): {len(results)}")
    print(f"Resolved: {len(resolved)} | unresolved: {len(unresolved)}")
    by_tier = Counter(r["tier"] for r in resolved)
    print("Resolved by tier:", dict(sorted(by_tier.items(), key=lambda kv: kv[0])))
    if unresolved:
        print("Unresolved weapons:")
        for r in unresolved:
            print(f"  - {r['name']} ({r['reason']})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()

    weapons = read_sheet_weapons()
    items, items_by_name, plug_sets = load_manifest()
    loose_index = build_loose_weapon_index(items_by_name)
    results = [
        resolve_weapon(w, items, items_by_name, plug_sets, loose_index) for w in weapons
    ]
    print_report(results)
    if args.generate:
        generate_wishlist(results)


if __name__ == "__main__":
    main()
