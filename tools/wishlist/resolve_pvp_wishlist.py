import json
import sqlite3
import unicodedata
import re
import sys
from itertools import combinations as _combinations
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from manifest_util import manifest_db_path

REPO_ROOT = HERE.parents[1]
WEAPONS = HERE / "pvp_weapons.json"
REPORT = HERE / "pvp-resolution.json"
REPO_WISHLIST = REPO_ROOT / "djsippycup-dim-wishlist.txt"
PVP_BEGIN = "// BEGIN GENERATED PVP WEAPONS"
PVP_END = "// END GENERATED PVP WEAPONS"

WEAPON_BUCKET_HASHES = {1498876634, 2465295065, 953998645}
# Trait perk socket category (randomized weapon perks) and intrinsic category
TRAIT_SOCKET_CATEGORY = 4241085061
INTRINSIC_SOCKET_CATEGORY = 3956125808


def normalize(value):
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\u2019", "'").replace("\u2018", "'")
    return re.sub(r"\s+", " ", value).strip().casefold()


def dedupe(values):
    return list(dict.fromkeys(values))


def load_manifest():
    con = sqlite3.connect(str(manifest_db_path()))
    cur = con.cursor()
    items = {}
    items_by_name = defaultdict(list)
    for _, blob in cur.execute("SELECT id, json FROM DestinyInventoryItemDefinition"):
        d = json.loads(blob)
        items[d.get("hash")] = d
        name = d.get("displayProperties", {}).get("name")
        if name:
            items_by_name[normalize(name)].append(d)
    plugsets = {}
    for _, blob in cur.execute("SELECT id, json FROM DestinyPlugSetDefinition"):
        d = json.loads(blob)
        plugsets[d.get("hash")] = d
    con.close()
    return items, items_by_name, plugsets


def entry_plug_hashes(entry, plugsets):
    hashes = []
    for p in entry.get("reusablePlugItems") or []:
        if p.get("plugItemHash"):
            hashes.append(p["plugItemHash"])
    for key in ("randomizedPlugSetHash", "reusablePlugSetHash"):
        ps = plugsets.get(entry.get(key))
        if ps:
            for p in ps.get("reusablePlugItems") or []:
                if p.get("plugItemHash") and p.get("currentlyCanRoll") is not False:
                    hashes.append(p["plugItemHash"])
    if entry.get("singleInitialItemHash"):
        hashes.append(entry["singleInitialItemHash"])
    return dedupe(hashes)


def candidate_weapons(name, items_by_name):
    out = []
    for d in items_by_name.get(normalize(name), []):
        inv = d.get("inventory") or {}
        if d.get("itemType") != 3:
            continue
        if not inv.get("isInstanceItem"):
            continue
        if inv.get("bucketTypeHash") not in WEAPON_BUCKET_HASHES:
            continue
        out.append(d)
    return out


def socket_perk_maps(candidate, items, plugsets):
    """Return list of dicts per trait socket: {normalized perk name: [hashes]}."""
    maps = []
    sockets = (candidate.get("sockets") or {}).get("socketEntries") or []
    categories = (candidate.get("sockets") or {}).get("socketCategories") or []
    trait_indexes = set()
    for cat in categories:
        if cat.get("socketCategoryHash") == TRAIT_SOCKET_CATEGORY:
            trait_indexes.update(cat.get("socketIndexes") or [])
    for idx in sorted(trait_indexes):
        if idx >= len(sockets):
            continue
        entry = sockets[idx]
        names = defaultdict(list)
        for h in entry_plug_hashes(entry, plugsets):
            plug = items.get(h)
            if not plug:
                continue
            typ = plug.get("itemTypeDisplayName") or ""
            if typ.startswith("Enhanced "):
                continue
            nm = plug.get("displayProperties", {}).get("name")
            if nm:
                names[normalize(nm)].append(h)
        maps.append({"socket_index": idx, "names": {k: dedupe(v) for k, v in names.items()}})
    return maps


def intrinsic_hash(candidate, items, plugsets):
    sockets = (candidate.get("sockets") or {}).get("socketEntries") or []
    categories = (candidate.get("sockets") or {}).get("socketCategories") or []
    for cat in categories:
        if cat.get("socketCategoryHash") == INTRINSIC_SOCKET_CATEGORY:
            for idx in cat.get("socketIndexes") or []:
                if idx < len(sockets):
                    h = sockets[idx].get("singleInitialItemHash")
                    if h:
                        plug = items.get(h)
                        return {"hash": h, "name": (plug or {}).get("displayProperties", {}).get("name")}
    return None


def resolve_perk(perk_name, perk_maps):
    hits = []
    n = normalize(perk_name)
    for m in perk_maps:
        for h in m["names"].get(n, []):
            hits.append({"socket_index": m["socket_index"], "hash": h})
    hashes = dedupe(x["hash"] for x in hits)
    sockets = dedupe(x["socket_index"] for x in hits)
    return hashes, sockets


def resolve_weapon(weapon, items, items_by_name, plugsets):
    columns = weapon.get("columns") or []
    all_perks = [p for col in columns for p in col]
    candidates = []
    for cand in candidate_weapons(weapon["name"], items_by_name):
        pmaps = socket_perk_maps(cand, items, plugsets)
        resolved = {}
        missing = []
        for perk in all_perks:
            hashes, sockets = resolve_perk(perk, pmaps)
            if hashes:
                resolved[perk] = {"hashes": hashes, "sockets": sockets}
            else:
                missing.append(perk)
        candidates.append({
            "hash": cand["hash"],
            "index": cand.get("index"),
            "collectibleHash": cand.get("collectibleHash"),
            "coverage": len(all_perks) - len(missing),
            "missing": missing,
            "resolved": resolved,
            "intrinsic": intrinsic_hash(cand, items, plugsets),
            "typeName": cand.get("itemTypeDisplayName"),
        })
    candidates.sort(key=lambda c: (-c["coverage"], -(c["index"] or 0), c["hash"]))
    total = len(all_perks)
    if weapon.get("exotic") and not columns:
        # fixed exotic: pick the primary obtainable version (highest index)
        selected = [candidates[0]] if candidates else []
    elif total:
        best = max((c["coverage"] for c in candidates), default=0)
        selected = [c for c in candidates if c["coverage"] == best and best > 0]
    else:
        selected = candidates[:1] if candidates else []
    return {
        "rank": weapon["rank"],
        "name": weapon["name"],
        "exotic": weapon.get("exotic", False),
        "random": bool(weapon.get("columns")) and weapon.get("random", True),
        "columns": columns,
        "candidate_count": len(candidates),
        "selected": selected,
        "candidates": candidates,
    }


def roll_key(line):
    item_hash = int(line.split("item=", 1)[1].split("&", 1)[0])
    perk_hashes = tuple(sorted({int(v) for v in line.split("&perks=", 1)[1].split("#", 1)[0].split(",")}))
    return item_hash, perk_hashes


def perk_subset_hash_lists(perk_names, resolved):
    """Yield deduped hash lists for the product of hash choices for the given perk names."""
    import itertools
    groups = [resolved[name]["hashes"] for name in perk_names]
    for combo in itertools.product(*groups):
        yield dedupe(list(combo))


def column_perk_combos(columns, resolved):
    """Column-aware combos grouped by ACTUAL trait socket, most-specific first.

    Regroups the supported perks by the socket index they actually resolve to,
    so no entry ever contains two perks from the same in-game column, regardless
    of how the input spec grouped them.
    """
    import itertools
    by_socket = {}
    order = []
    for col in columns:
        for perk in col:
            if perk not in resolved:
                continue
            socket_index = resolved[perk]["sockets"][0]
            if socket_index not in by_socket:
                by_socket[socket_index] = []
                order.append(socket_index)
            if perk not in by_socket[socket_index]:
                by_socket[socket_index].append(perk)
    groups = [by_socket[si] for si in sorted(order)]
    for size in range(len(groups), 0, -1):
        for chosen in itertools.combinations(range(len(groups)), size):
            for pick in itertools.product(*(groups[i] for i in chosen)):
                yield list(pick)


def generate_weapon_block(result):
    name = result["name"]
    columns = result["columns"]
    lines = []
    lines.append(f"// #{result['rank']} {name}")

    if result["exotic"] and not columns:
        # Fixed exotic: single entry per selected item using its exotic intrinsic
        for cand in result["selected"]:
            intr = cand["intrinsic"]
            lines.append(f"// itemHash={cand['hash']} (exotic, fixed roll)")
            if intr and intr.get("hash"):
                lines.append(f"dimwishlist:item={cand['hash']}&perks={intr['hash']}")
            else:
                lines.append(f"dimwishlist:item={cand['hash']}")
        lines.append("")
        return lines

    all_perks = [p for col in columns for p in col]
    for position, cand in enumerate(result["selected"]):
        resolved = cand["resolved"]
        supported = [p for p in all_perks if p in resolved]
        label = f"// itemHash={cand['hash']}"
        if result["exotic"]:
            label += " (exotic, random rolls)"
        elif position > 0:
            label += " (alternate item version)"
        lines.append(label)
        perk_summary = "; ".join(
            f"{p}={'|'.join(map(str, resolved[p]['hashes']))}" for p in supported
        )
        lines.append(f"// perks: {perk_summary}")
        lines.append("")
        # Every non-empty subset of the recommended perks, most-perks-first, so
        # DIM (first match wins) flags the fullest combination present. This
        # matches the PvE "all combinations (individual and combined)" rule.
        for size in range(len(supported), 0, -1):
            for names in _combinations(supported, size):
                for hash_list in perk_subset_hash_lists(names, resolved):
                    lines.append(
                        f"dimwishlist:item={cand['hash']}&perks=" + ",".join(map(str, hash_list))
                    )
            lines.append("")
    return lines


def generate_wishlist(results, source, begin_marker, end_marker):
    original = REPO_WISHLIST.read_text(encoding="utf-8")
    base = original.split(begin_marker, 1)[0].rstrip()
    existing_keys = {roll_key(l) for l in base.splitlines() if l.startswith("dimwishlist:")}
    generated_keys = set()

    out = [base, "", begin_marker, f"// Source: {source}", ""]
    for result in results:
        block = generate_weapon_block(result)
        filtered = []
        for line in block:
            if line.startswith("dimwishlist:"):
                key = roll_key(line)
                if key in existing_keys or key in generated_keys:
                    continue
                generated_keys.add(key)
            filtered.append(line)
        out.extend(filtered)
    while out and out[-1] == "":
        out.pop()
    out.extend(["", end_marker, ""])
    REPO_WISHLIST.write_text("\n".join(out), encoding="utf-8")
    print(f"Generated entries: {len(generated_keys)}")
    print(f"Wishlist: {REPO_WISHLIST}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--weapons", default=str(WEAPONS))
    parser.add_argument("--report", default=str(REPORT))
    parser.add_argument("--begin", default=PVP_BEGIN)
    parser.add_argument("--end", default=PVP_END)
    args = parser.parse_args()
    spec = json.loads(Path(args.weapons).read_text(encoding="utf-8"))
    items, items_by_name, plugsets = load_manifest()
    results = [resolve_weapon(w, items, items_by_name, plugsets) for w in spec["weapons"]]
    Path(args.report).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Weapons: {len(results)}")
    for r in results:
        sel = r["selected"]
        if not sel:
            print(f"  !! NO CANDIDATE: {r['name']}")
            continue
        first = sel[0]
        total = sum(len(c) for c in r["columns"])
        if r["exotic"] and not r["columns"]:
            tag = "exotic-fixed intrinsic=" + str((first["intrinsic"] or {}).get("hash"))
        else:
            tag = f"cov={first['coverage']}/{total}"
        hashes = ",".join(str(c["hash"]) for c in sel)
        line = f"  {r['rank']:>2} {r['name']:<24} hashes={hashes:<26} {first['typeName']:<16} {tag}"
        if first["missing"]:
            line += f"  MISSING={first['missing']}"
        print(line)
    print(f"Report: {args.report}")
    if args.generate:
        generate_wishlist(results, spec["source"], args.begin, args.end)


if __name__ == "__main__":
    main()
