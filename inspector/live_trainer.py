"""Teach the inspector at runtime: confirm or correct a label so it learns (REST API).

Usage:
    # add/confirm a labeled exemplar (also updates the cache)
    python -m inspector.live_trainer add <image> "<label>" [--part "Bracket"]

    # attach feedback to the most recent inspection of an image and learn from it
    python -m inspector.live_trainer correct <image> "<true_label>" [note...]

Labels are free-form and per-part: a new part can introduce brand-new defect
categories. 'OK' is the reserved no-defect tag. Any add/correct rebuilds
knowledge/defect_kb.json so subsequent inspections use the new knowledge.
"""
from __future__ import annotations
import os
import sys

from . import knowledge_base as kb
from . import image_features as F


def _check_label(label):
    if not label or not str(label).strip():
        print("label must be a non-empty string (defect category, or 'OK' for no defect)")
        sys.exit(2)


def add(image, label, source="manual", part="default"):
    _check_label(label)
    kb.init_db()
    feat = F.extract(image)
    name = os.path.splitext(os.path.basename(image))[0]
    kb.add_exemplar(name, image, label, feat["vector"],
                    phash=feat["signals"].get("phash", ""), source=source, confirmed=1, part=part)
    cache = kb.rebuild_cache()
    print(f"learned: {name} -> {label} [part={part}]")
    print(f"part counts: {cache.get('parts', {}).get(part, {})}")


def correct(image, true_label, note="", part="default"):
    _check_label(true_label)
    kb.init_db()
    con = kb.connect()
    row = con.execute(
        "SELECT * FROM inspections WHERE name=? ORDER BY id DESC LIMIT 1",
        (os.path.basename(image),),
    ).fetchone()
    con.close()
    if row is not None:
        kb.add_feedback(row["id"], true_label, note)
        print(f"feedback saved for inspection #{row['id']} (was pred '{row['pred']}')")
    # learning from a correction == adding the corrected exemplar
    add(image, true_label, source="feedback", part=part)


def main(argv):
    if len(argv) < 3 or argv[0] not in ("add", "correct"):
        print(__doc__)
        return 1
    cmd, image, label = argv[0], argv[1], argv[2]
    part = "default"
    rest = argv[3:]
    if "--part" in rest:
        i = rest.index("--part")
        part = rest[i + 1] if i + 1 < len(rest) else "default"
        rest = rest[:i] + rest[i + 2:]
    note = " ".join(rest)
    if cmd == "add":
        add(image, label, part=part)
    else:
        correct(image, label, note, part=part)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
