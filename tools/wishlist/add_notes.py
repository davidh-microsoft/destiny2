"""Add a title line and per-weapon //notes: source tags to the DIM wishlist.

DIM resets block notes on every blank line and every // comment, and checks
//notes: before the reset. So each weapon-version block is rewritten as:

    // <existing header comment(s)>
    //notes: <source> tags:<tag>
    dimwishlist:...            (all rolls for this block, contiguous, no blanks)

with a single blank line between blocks. Notes are chosen by section:
  - TIER S section (incl. DECATUR 02) -> "Aegis tags:pve"
  - PVP WEAPONS section (Daltnix)     -> "Daltnix tags:pvp"
  - CRUCIBLEGUIDEBOOK section          -> "CrucibleGuidebook tags:pvp"
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2] / "djsippycup-dim-wishlist.txt"
TITLE = "title:DJSippyCup - MoT (GHCP)"

TIER_S_BEGIN = "// BEGIN GENERATED TIER S WEAPONS"
PVP_BEGIN = "// BEGIN GENERATED PVP WEAPONS"
CG_BEGIN = "// BEGIN GENERATED CRUCIBLEGUIDEBOOK PVP"

AEGIS = "Aegis tags:pve"
DALTNIX = "Daltnix tags:pvp"
CG = "CrucibleGuidebook tags:pvp"


def main():
    text = REPO.read_text(encoding="utf-8")
    lines = text.split("\n")

    out = [TITLE]
    current_note = AEGIS  # DECATUR block before the first marker
    pending = []          # accumulated dimwishlist lines for the current block

    def flush():
        if pending:
            out.append(f"//notes: {current_note}")
            out.extend(pending)
            out.append("")
            pending.clear()

    for line in lines:
        if line.startswith("//notes:"):
            # drop any pre-existing notes lines (idempotent re-runs)
            continue
        if line.startswith("dimwishlist:"):
            pending.append(line)
            continue
        if line == "":
            # blanks only separated cosmetic groups; drop (blocks end on comments)
            continue
        # any non-roll, non-blank line (comments, markers, title/description)
        flush()
        if line.startswith(TIER_S_BEGIN):
            current_note = AEGIS
        elif line.startswith(PVP_BEGIN):
            current_note = DALTNIX
        elif line.startswith(CG_BEGIN):
            current_note = CG
        # skip an existing title line if present (we already added ours)
        if line.startswith("title:"):
            continue
        out.append(line)
    flush()

    # collapse any accidental multiple trailing blanks
    while len(out) >= 2 and out[-1] == "" and out[-2] == "":
        out.pop()
    if out[-1] != "":
        out.append("")

    REPO.write_text("\n".join(out), encoding="utf-8")
    print("Rewrote", REPO)


if __name__ == "__main__":
    main()
