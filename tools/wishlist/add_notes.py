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
FINNALD_BEGIN = "// BEGIN GENERATED FINNALD PVP"

AEGIS = "Aegis tags:pve"
DALTNIX = "Daltnix tags:pvp"
CG = "CrucibleGuidebook tags:pvp"
FINNALD = "Finnald tags:pvp"

# Sections whose per-weapon "// tier:" lines append a #<tier> suffix to the note.
SECTION_NOTES = {
    TIER_S_BEGIN: AEGIS,
    PVP_BEGIN: DALTNIX,
    CG_BEGIN: CG,
    FINNALD_BEGIN: FINNALD,
}


def main():
    text = REPO.read_text(encoding="utf-8")
    lines = text.split("\n")

    out = [TITLE]
    section_base = AEGIS  # base note for the current section
    current_note = AEGIS  # section_base, plus a #<tier> suffix when present
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
        matched_section = next(
            (marker for marker in SECTION_NOTES if line.startswith(marker)), None
        )
        if matched_section:
            section_base = SECTION_NOTES[matched_section]
            current_note = section_base
        elif line.startswith("// tier:"):
            # per-weapon tier (S/A/B) -> append #s / #a / #b to the section note
            tier = line.split(":", 1)[1].strip().lower()
            current_note = f"{section_base}#{tier}"
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
