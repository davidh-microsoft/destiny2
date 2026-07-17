import argparse
import csv
import itertools
import json
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from manifest_util import manifest_db_path

REPO_ROOT = HERE.parents[1]
DATA_DIR = HERE / "data"
SHEETS_DIR = DATA_DIR / "google-sheets-destiny2"
REPO_WISHLIST = REPO_ROOT / "djsippycup-dim-wishlist.txt"
REPORT_PATH = HERE / "tier-s-wishlist-resolution.json"
WORKBOOK_XLSX = DATA_DIR / "destiny2-endgame-analysis.xlsx"
GENERATED_BEGIN = "// BEGIN GENERATED TIER S WEAPONS"
GENERATED_END = "// END GENERATED TIER S WEAPONS"

WEAPON_TABS = [
    "Autos",
    "Bows",
    "HCs",
    "Pulses",
    "Scouts",
    "Sidearms",
    "SMGs",
    "BGLs",
    "Fusions",
    "Glaives",
    "Shotguns",
    "Snipers",
    "Rocket Sidearms",
    "Traces",
    "HGLs",
    "LFRs",
    "LMGs",
    "Rockets",
    "Swords",
    "Other",
    "Exotic Weapons",
]

WEAPON_BUCKET_HASHES = {1498876634, 2465295065, 953998645}

SELECTED_HASH_OVERRIDES = {
    # The Pantheon pools are supersets of the original Garden version.
    ("Autos", "Reckless Oracle", ""): [1992309064],
    # These sheet rows combine recommendations across multiple manifest versions.
    ("Rocket Sidearms", "Lotus-Eater", ""): [837298567, 924095500, 3922217119],
    ("Other", "Mint Retrograde", ""): [1715391576, 3285784871, 42435996],
}

FIXED_EXOTIC_PERKS = {
    "Tractor Cannon": [1210807262],
}


@dataclass
class SheetWeapon:
    tab: str
    sheet_row: int
    rank: str
    season: str
    name: str
    qualifier: str
    linked_item_hash: int | None
    barrels: list[str]
    magazines: list[str]
    perks: list[str]

    @property
    def components(self) -> list[str]:
        return dedupe(self.barrels + self.magazines + self.perks)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\u2019", "'").replace("\u2018", "'")
    return re.sub(r"\s+", " ", value).strip().casefold()


def split_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def dedupe(values):
    return list(dict.fromkeys(values))


def excel_column_name(one_based_index):
    name = ""
    while one_based_index:
        one_based_index, remainder = divmod(one_based_index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def read_name_links():
    spreadsheet_namespace = (
        "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    )
    office_relationship_namespace = (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    )
    namespaces = {
        "spreadsheet": spreadsheet_namespace,
        "relationship": office_relationship_namespace,
    }
    links = {}

    with ZipFile(WORKBOOK_XLSX) as workbook:
        workbook_xml = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
        relationship_xml = ElementTree.fromstring(
            workbook.read("xl/_rels/workbook.xml.rels")
        )
        workbook_relationships = {
            relationship.attrib["Id"]: relationship.attrib["Target"]
            for relationship in relationship_xml
        }
        sheet_targets = {
            sheet.attrib["name"]: workbook_relationships[
                sheet.attrib[f"{{{office_relationship_namespace}}}id"]
            ]
            for sheet in workbook_xml.find("spreadsheet:sheets", namespaces)
        }

        for tab in WEAPON_TABS:
            target = "xl/" + sheet_targets[tab].lstrip("/")
            worksheet = ElementTree.fromstring(workbook.read(target))
            hyperlinks = worksheet.find("spreadsheet:hyperlinks", namespaces)
            if hyperlinks is None:
                continue

            relationship_path = str(
                PurePosixPath(target).parent
                / "_rels"
                / f"{PurePosixPath(target).name}.rels"
            )
            sheet_relationships = {}
            if relationship_path in workbook.namelist():
                relationship_root = ElementTree.fromstring(
                    workbook.read(relationship_path)
                )
                sheet_relationships = {
                    relationship.attrib["Id"]: relationship.attrib.get("Target", "")
                    for relationship in relationship_root
                }

            for hyperlink in hyperlinks:
                reference = hyperlink.attrib.get("ref")
                relationship_id = hyperlink.attrib.get(
                    f"{{{office_relationship_namespace}}}id"
                )
                target_url = sheet_relationships.get(
                    relationship_id, hyperlink.attrib.get("location", "")
                )
                item_match = re.search(r"/items/(\d+)", target_url)
                if reference and item_match:
                    links[(tab, reference)] = int(item_match.group(1))

    return links


def read_sheet_weapons() -> list[SheetWeapon]:
    weapons = []
    name_links = read_name_links()
    for tab in WEAPON_TABS:
        with (SHEETS_DIR / f"{tab}.csv").open(
            newline="", encoding="utf-8-sig"
        ) as handle:
            rows = list(csv.reader(handle))

        headers = rows[1]
        indexes = {name: headers.index(name) for name in headers if name}
        name_column = excel_column_name(indexes["Name"] + 1)

        def get(row, column):
            index = indexes.get(column)
            return row[index].strip() if index is not None and index < len(row) else ""

        for sheet_row, row in enumerate(rows[2:], start=3):
            if get(row, "Tier") != "S":
                continue

            name_lines = split_lines(get(row, "Name"))
            weapons.append(
                SheetWeapon(
                    tab=tab,
                    sheet_row=sheet_row,
                    rank=get(row, "Rank"),
                    season=get(row, "Season"),
                    name=name_lines[0],
                    qualifier=" ".join(name_lines[1:]),
                    linked_item_hash=name_links.get(
                        (tab, f"{name_column}{sheet_row}")
                    ),
                    barrels=split_lines(get(row, "Barrel")),
                    magazines=split_lines(get(row, "Mag")),
                    perks=dedupe(
                        split_lines(get(row, "Perk 1"))
                        + split_lines(get(row, "Perk 2"))
                    ),
                )
            )
    return weapons


def load_manifest():
    connection = sqlite3.connect(str(manifest_db_path()))
    cursor = connection.cursor()

    items = {}
    items_by_name = defaultdict(list)
    for _, blob in cursor.execute("SELECT id, json FROM DestinyInventoryItemDefinition"):
        definition = json.loads(blob)
        item_hash = definition.get("hash")
        items[item_hash] = definition
        name = definition.get("displayProperties", {}).get("name")
        if name:
            items_by_name[normalize(name)].append(definition)

    plug_sets = {}
    for _, blob in cursor.execute("SELECT id, json FROM DestinyPlugSetDefinition"):
        definition = json.loads(blob)
        plug_sets[definition.get("hash")] = definition

    connection.close()
    return items, items_by_name, plug_sets


def entry_plug_hashes(entry, plug_sets):
    hashes = []
    for plug in entry.get("reusablePlugItems") or []:
        if plug.get("plugItemHash") and plug.get("currentlyCanRoll") is not False:
            hashes.append(plug["plugItemHash"])

    for key in ("randomizedPlugSetHash", "reusablePlugSetHash"):
        plug_set = plug_sets.get(entry.get(key))
        if not plug_set:
            continue
        for plug in plug_set.get("reusablePlugItems") or []:
            if plug.get("plugItemHash") and plug.get("currentlyCanRoll") is not False:
                hashes.append(plug["plugItemHash"])

    if entry.get("singleInitialItemHash"):
        hashes.append(entry["singleInitialItemHash"])
    return dedupe(hashes)


def candidate_socket_maps(candidate, items, plug_sets):
    socket_maps = []
    entries = (candidate.get("sockets") or {}).get("socketEntries") or []
    for socket_index, entry in enumerate(entries):
        names = defaultdict(list)
        for plug_hash in entry_plug_hashes(entry, plug_sets):
            plug = items.get(plug_hash)
            name = (plug or {}).get("displayProperties", {}).get("name")
            item_type_name = (plug or {}).get("itemTypeDisplayName") or ""
            if name and not item_type_name.startswith("Enhanced "):
                names[normalize(name)].append(plug_hash)
        socket_maps.append(
            {
                "socket_index": socket_index,
                "names": {key: dedupe(value) for key, value in names.items()},
            }
        )
    return socket_maps


def weapon_candidates(weapon, items_by_name):
    candidates = []
    for definition in items_by_name.get(normalize(weapon.name), []):
        inventory = definition.get("inventory") or {}
        if definition.get("itemType") != 3:
            continue
        if not inventory.get("isInstanceItem"):
            continue
        if inventory.get("bucketTypeHash") not in WEAPON_BUCKET_HASHES:
            continue
        candidates.append(definition)
    return candidates


def resolve_component(component, socket_maps):
    matches = []
    normalized = normalize(component)
    for socket_map in socket_maps:
        for plug_hash in socket_map["names"].get(normalized, []):
            matches.append(
                {
                    "socket_index": socket_map["socket_index"],
                    "hash": plug_hash,
                }
            )
    unique_hashes = dedupe(match["hash"] for match in matches)
    unique_sockets = dedupe(match["socket_index"] for match in matches)
    return unique_hashes, unique_sockets


def resolve_fallback_plug(candidate, items):
    entries = (candidate.get("sockets") or {}).get("socketEntries") or []
    if not entries:
        return None

    plug_hash = entries[0].get("singleInitialItemHash")
    plug = items.get(plug_hash)
    name = (plug or {}).get("displayProperties", {}).get("name")
    if not plug_hash or not name:
        return None
    return {"hash": plug_hash, "name": name}


def dedupe_candidates(candidates):
    return list({candidate["hash"]: candidate for candidate in candidates}.values())


def resolve_weapon(weapon, items, items_by_name, plug_sets):
    candidate_results = []
    for candidate in weapon_candidates(weapon, items_by_name):
        socket_maps = candidate_socket_maps(candidate, items, plug_sets)
        resolved = {}
        missing = []
        ambiguous_components = {}
        for component in weapon.components:
            hashes, sockets = resolve_component(component, socket_maps)
            if not hashes:
                missing.append(component)
            else:
                resolved[component] = {
                    "hashes": hashes,
                    "sockets": sockets,
                }
                if len(hashes) != 1:
                    ambiguous_components[component] = hashes

        candidate_results.append(
            {
                "hash": candidate["hash"],
                "index": candidate.get("index"),
                "collectibleHash": candidate.get("collectibleHash"),
                "iconWatermark": candidate.get("iconWatermark"),
                "coverage": len(weapon.components) - len(missing),
                "missing": missing,
                "ambiguous_components": ambiguous_components,
                "resolved": resolved,
                "fallback_plug": resolve_fallback_plug(candidate, items),
            }
        )

    candidate_results.sort(
        key=lambda result: (
            -result["coverage"],
            len(result["ambiguous_components"]),
            -(result["index"] or 0),
            result["hash"],
        )
    )

    complete = [result for result in candidate_results if not result["missing"]]
    override_hashes = SELECTED_HASH_OVERRIDES.get(
        (weapon.tab, weapon.name, weapon.qualifier)
    )
    if override_hashes:
        by_hash = {result["hash"]: result for result in candidate_results}
        base_candidates = [by_hash[item_hash] for item_hash in override_hashes]
    else:
        base_candidates = complete

    by_hash = {result["hash"]: result for result in candidate_results}
    linked_candidate = by_hash.get(weapon.linked_item_hash)
    selected_candidates = dedupe_candidates(
        ([linked_candidate] if linked_candidate else []) + base_candidates
    )

    return {
        "tab": weapon.tab,
        "sheet_row": weapon.sheet_row,
        "rank": weapon.rank,
        "season": weapon.season,
        "name": weapon.name,
        "qualifier": weapon.qualifier,
        "linked_item_hash": weapon.linked_item_hash,
        "barrels": weapon.barrels,
        "magazines": weapon.magazines,
        "perks": weapon.perks,
        "candidate_count": len(candidate_results),
        "complete_candidate_count": len(complete),
        "selected_candidates": selected_candidates,
        "candidates": candidate_results,
    }


def resolve_all():
    weapons = read_sheet_weapons()
    items, items_by_name, plug_sets = load_manifest()
    results = [
        resolve_weapon(weapon, items, items_by_name, plug_sets) for weapon in weapons
    ]
    REPORT_PATH.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return results


def print_report(results):
    resolved = [result for result in results if result["selected_candidates"]]
    unresolved = [result for result in results if not result["selected_candidates"]]
    print(f"Tier S rows: {len(results)}")
    print(f"Resolved rows: {len(resolved)}")
    print(f"Unresolved rows: {len(unresolved)}")
    print(
        "Selected item hashes: "
        f"{sum(len(result['selected_candidates']) for result in resolved)}"
    )
    print(f"Report: {REPORT_PATH}")

    for result in unresolved:
        print(
            f"{result['tab']} | {result['name']} | {result['qualifier']} | "
            f"candidates={result['candidate_count']} "
            f"complete={result['complete_candidate_count']}"
        )
        for candidate in result["candidates"][:5]:
            print(
                f"  {candidate['hash']} coverage={candidate['coverage']} "
                f"missing={candidate['missing']} "
                f"ambiguous={candidate['ambiguous_components']}"
            )


def hash_options(component_names, resolved):
    options = []
    for name in component_names:
        component = resolved.get(name)
        if component:
            options.extend(component["hashes"])
    return dedupe(options)


def expand_named_perk_subset(perk_names, resolved):
    hash_groups = [resolved[name]["hashes"] for name in perk_names]
    return itertools.product(*hash_groups)


def roll_variants(barrel_hashes, magazine_hashes):
    variants = []
    variants.extend(
        [barrel_hash, magazine_hash]
        for barrel_hash in barrel_hashes
        for magazine_hash in magazine_hashes
    )
    variants.extend([barrel_hash] for barrel_hash in barrel_hashes)
    variants.extend([magazine_hash] for magazine_hash in magazine_hashes)
    variants.append([])
    return variants


def component_summary(names, resolved):
    parts = []
    for name in names:
        component = resolved.get(name)
        if component:
            parts.append(f"{name}={'|'.join(map(str, component['hashes']))}")
    return "; ".join(parts)


def generate_candidate_block(result, candidate):
    item_hash = candidate["hash"]
    resolved = candidate["resolved"]
    item_hash_source = (
        "sheet link"
        if item_hash == result["linked_item_hash"]
        else "manifest conflict"
    )
    supported_barrels = [name for name in result["barrels"] if name in resolved]
    supported_magazines = [
        name for name in result["magazines"] if name in resolved
    ]
    supported_perks = [name for name in result["perks"] if name in resolved]

    lines = [
        f"// {result['tab']}: {result['name']}"
        + (f" ({result['qualifier']})" if result["qualifier"] else ""),
        f"// itemHash={item_hash} ({item_hash_source})",
    ]

    if supported_barrels:
        lines.append(
            f"// barrels: {component_summary(supported_barrels, resolved)}"
        )
    if supported_magazines:
        lines.append(
            f"// magazines: {component_summary(supported_magazines, resolved)}"
        )
    if supported_perks:
        lines.append(f"// perks: {component_summary(supported_perks, resolved)}")

    unsupported = [
        component
        for component in result["barrels"] + result["magazines"] + result["perks"]
        if component not in resolved
    ]
    if unsupported:
        lines.append(
            "// unavailable on this item version: " + ", ".join(unsupported)
        )
    lines.append("")

    if not supported_perks:
        fixed_perks = FIXED_EXOTIC_PERKS.get(result["name"])
        if fixed_perks:
            fallback_hashes = fixed_perks
            fallback_name = "fixed intrinsic"
        elif candidate["fallback_plug"]:
            fallback_hashes = [candidate["fallback_plug"]["hash"]]
            fallback_name = candidate["fallback_plug"]["name"]
        else:
            raise ValueError(f"No perks available for {result['name']} ({item_hash})")
        lines.append(
            f"// no listed perks are available on this item version; "
            f"matching {fallback_name}={fallback_hashes[0]}"
        )
        lines.append("")
        lines.append(
            f"dimwishlist:item={item_hash}&perks="
            + ",".join(map(str, fallback_hashes))
        )
        lines.append("")
        return lines

    barrel_hashes = hash_options(supported_barrels, resolved)
    magazine_hashes = hash_options(supported_magazines, resolved)
    variants = roll_variants(barrel_hashes, magazine_hashes)

    for perk_count in range(len(supported_perks), 0, -1):
        for perk_names in itertools.combinations(supported_perks, perk_count):
            for perk_hashes in expand_named_perk_subset(perk_names, resolved):
                for prefix_hashes in variants:
                    hashes = dedupe(list(prefix_hashes) + list(perk_hashes))
                    lines.append(
                        f"dimwishlist:item={item_hash}&perks="
                        + ",".join(map(str, hashes))
                    )
            lines.append("")
    return lines


def validate_selected_results(results):
    errors = []
    for result in results:
        selected = result["selected_candidates"]
        if not selected:
            errors.append(f"No selected item hash: {result['tab']} / {result['name']}")
            continue

        if result["linked_item_hash"] and result["linked_item_hash"] not in {
            candidate["hash"] for candidate in selected
        }:
            errors.append(
                f"Sheet-linked hash not selected for {result['name']}: "
                f"{result['linked_item_hash']}"
            )

        if not result["perks"]:
            if result["name"] not in FIXED_EXOTIC_PERKS:
                errors.append(f"No fixed exotic mapping: {result['name']}")
            continue

        covered = set()
        for candidate in selected:
            covered.update(candidate["resolved"])
            supported_perks = [
                perk for perk in result["perks"] if perk in candidate["resolved"]
            ]
            if not supported_perks and not candidate["fallback_plug"]:
                errors.append(
                    f"No supported perks for {result['name']} / {candidate['hash']}"
                )

        missing = [
            component
            for component in result["barrels"]
            + result["magazines"]
            + result["perks"]
            if component not in covered
        ]
        if missing:
            errors.append(
                f"Selected hashes do not cover {result['name']}: {missing}"
            )

    if errors:
        raise ValueError("\n".join(errors))


def roll_key(line):
    item_hash = int(line.split("item=", 1)[1].split("&", 1)[0])
    perk_hashes = tuple(
        sorted(
            {
                int(value)
                for value in line.split("&perks=", 1)[1].split("#", 1)[0].split(",")
            }
        )
    )
    return item_hash, perk_hashes


def generate_wishlist(results):
    validate_selected_results(results)
    original = REPO_WISHLIST.read_text(encoding="utf-8")
    # Replace the Tier S section in place, preserving content before and after
    # so section order is stable. Append at the end if markers are absent.
    if GENERATED_BEGIN in original:
        before = original.split(GENERATED_BEGIN, 1)[0].rstrip("\n")
        tail = original.split(GENERATED_BEGIN, 1)[1]
        after = tail.split(GENERATED_END, 1)[1] if GENERATED_END in tail else ""
    else:
        before = original.rstrip("\n")
        after = ""
    after = after.strip("\n")

    outside = before + "\n" + after
    existing_roll_keys = {
        roll_key(line)
        for line in outside.splitlines()
        if line.startswith("dimwishlist:")
    }
    generated_roll_keys = set()
    block_count = 0

    section = [GENERATED_BEGIN, ""]
    for result in results:
        for candidate in result["selected_candidates"]:
            block = generate_candidate_block(result, candidate)
            filtered_block = []
            for line in block:
                if line.startswith("dimwishlist:"):
                    key = roll_key(line)
                    if key in existing_roll_keys or key in generated_roll_keys:
                        continue
                    generated_roll_keys.add(key)
                filtered_block.append(line)
            section.extend(filtered_block)
            block_count += 1

    while section and section[-1] == "":
        section.pop()
    section.append(GENERATED_END)

    parts = [before, "", "\n".join(section)]
    if after:
        parts += ["", after]
    REPO_WISHLIST.write_text("\n".join(parts).rstrip("\n") + "\n", encoding="utf-8")
    print(f"Generated item blocks: {block_count}")
    print(f"Generated unique wishlist entries: {len(generated_roll_keys)}")
    print(f"Wishlist: {REPO_WISHLIST}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    results = resolve_all()
    print_report(results)
    if args.generate:
        generate_wishlist(results)


if __name__ == "__main__":
    main()
