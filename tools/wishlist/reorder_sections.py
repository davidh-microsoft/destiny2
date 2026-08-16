"""Reorder the wishlist so PvP sections precede the PvE (Tier S) section.

DIM applies the first matching roll in file order, so PvP rolls must come first
to win when a weapon matches both a PvP and a PvE roll. Canonical order:

    title
    // BEGIN GENERATED FINNALD PVP ... END              (Finnald sheet, PvP)
    // BEGIN GENERATED PVP WEAPONS ... END              (Daltnix, PvP)
    // BEGIN GENERATED CRUCIBLEGUIDEBOOK PVP ... END     (CrucibleGuidebook, PvP)
    // BEGIN GENERATED TIER S WEAPONS ... END            (PvE, optional)

Whole sections are moved verbatim, so every //notes: line stays directly above
its contiguous rolls and DIM parsing is unaffected. Each section is optional
(the PvE Tier S section may be absent); present sections keep the order above.
Idempotent.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2] / "djsippycup-dim-wishlist.txt"

PVP = ("// BEGIN GENERATED PVP WEAPONS", "// END GENERATED PVP WEAPONS")
CG = ("// BEGIN GENERATED CRUCIBLEGUIDEBOOK PVP", "// END GENERATED CRUCIBLEGUIDEBOOK PVP")
FINNALD = ("// BEGIN GENERATED FINNALD PVP", "// END GENERATED FINNALD PVP")
TIER_S = ("// BEGIN GENERATED TIER S WEAPONS", "// END GENERATED TIER S WEAPONS")

SECTION_ORDER = (FINNALD, PVP, CG, TIER_S)


def _find(lines, marker):
    for i, line in enumerate(lines):
        if line.startswith(marker):
            return i
    return None


def _section(lines, markers):
    begin = _find(lines, markers[0])
    end = _find(lines, markers[1])
    if begin is None and end is None:
        return None
    if begin is None or end is None:
        raise SystemExit(f"incomplete section markers: {markers}")
    return begin, end, lines[begin : end + 1]


def main():
    lines = REPO.read_text(encoding="utf-8").split("\n")
    title = lines[0]

    marked = {0}
    sections = {}
    for markers in SECTION_ORDER:
        found = _section(lines, markers)
        if found is None:
            continue
        begin, end, block = found
        sections[markers[0]] = block
        marked.update(range(begin, end + 1))

    # Every roll must live inside one of the marked sections.
    stray = [l for i, l in enumerate(lines) if i not in marked and l.startswith("dimwishlist:")]
    if stray:
        raise SystemExit(f"{len(stray)} roll(s) outside marked sections: {stray[:2]}")

    out = [title, ""]
    for markers in SECTION_ORDER:
        if markers[0] in sections:
            out += sections[markers[0]] + [""]

    REPO.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")
    print("Reordered (PvP first) ->", REPO)


if __name__ == "__main__":
    main()
