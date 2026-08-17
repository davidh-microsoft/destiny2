"""Add a title line and per-weapon //notes: source tags to the DIM wishlist.

DIM resets block notes on every blank line and every // comment, and checks
//notes: before the reset. So each weapon-version block is rewritten as:

    // <existing header comment(s)>
    //notes: <source>[: <role/notes>] tags:<mode>[#<tier>]
    dimwishlist:...            (all rolls for this block, contiguous, no blanks)

with a single blank line between blocks. The note is composed from:
  - the section source/mode:
      TIER S section    -> ("Aegis", "pve")
      PVP WEAPONS       -> ("Daltnix", "pvp")
      CRUCIBLEGUIDEBOOK -> ("CrucibleGuidebook", "pvp")
      FINNALD PVP       -> ("Finnald", "pvp")
  - an optional per-weapon "// tier:" line -> "#s"/"#a"/"#b" tag suffix
  - an optional per-weapon "// role:" line -> free-text note (Finnald), inserted
    before the trailing "tags:" delimiter.

DIM captures a block note up to the first "|" and stores the whole string, so
the "tags:" portion is kept last (our tooling reads the tag after "tags:").
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2] / "djsippycup-dim-wishlist.txt"
TITLE = "title:DJSippyCup - MoT (GHCP)"

TIER_S_BEGIN = "// BEGIN GENERATED TIER S WEAPONS"
PVP_BEGIN = "// BEGIN GENERATED PVP WEAPONS"
CG_BEGIN = "// BEGIN GENERATED CRUCIBLEGUIDEBOOK PVP"
FINNALD_BEGIN = "// BEGIN GENERATED FINNALD PVP"

# marker -> (source label, mode). Mode becomes the "tags:<mode>" value.
SECTION_META = {
    TIER_S_BEGIN: ("Aegis", "pve"),
    PVP_BEGIN: ("Daltnix", "pvp"),
    CG_BEGIN: ("CrucibleGuidebook", "pvp"),
    FINNALD_BEGIN: ("Finnald", "pvp"),
}

DEFAULT_META = ("Aegis", "pve")  # for a DECATUR-style block before any marker


def compose_note(source, mode, tier, role):
    note = source
    if role:
        note += f": {role}"
    note += f" tags:{mode}"
    if tier:
        note += f"#{tier}"
    return note


def main():
    text = REPO.read_text(encoding="utf-8")
    lines = text.split("\n")

    out = [TITLE]
    source, mode = DEFAULT_META
    tier = None
    role = None
    pending = []  # accumulated dimwishlist lines for the current block

    def flush():
        if pending:
            out.append(f"//notes: {compose_note(source, mode, tier, role)}")
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
            (marker for marker in SECTION_META if line.startswith(marker)), None
        )
        if matched_section:
            source, mode = SECTION_META[matched_section]
            tier = None
            role = None
        elif line.startswith("// tier:"):
            # "// tier:" marks a new weapon block; reset the per-weapon role so it
            # never leaks to a later weapon, then set this weapon's tier. Both
            # persist across the weapon's alternate-version sub-blocks (which have
            # no "// tier:" line of their own).
            tier = line.split(":", 1)[1].strip().lower() or None
            role = None
        elif line.startswith("// role:"):
            role = line.split(":", 1)[1].strip() or None
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
