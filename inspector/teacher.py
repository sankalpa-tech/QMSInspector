"""Teach ALL parts from their reviews/<part>.json files into the learning DB.

ONE generic teacher for every part. It auto-discovers every reviews/*.json and
loads each entry as a confirmed exemplar (feature vector + perceptual hash for
kNN / near-duplicate recall), records any human corrections, then rebuilds the
knowledge cache. Adding a new part needs NO new code -- just a new
reviews/<part>.json (+ its images).

Pipeline:
    reviews/<part>.json  ->  teacher  ->  inspection_memory.db  ->  model_builder  ->  best.pt

Image resolution per entry (in order):
    1. entry["image"] if it exists on disk  (in-repo parts)
    2. else <LEGACY_AES_DIR>/<base>.jpg      (external parts, e.g. Bearing Cup)

Human corrections (optional): knowledge/corrections.json maps an image base to a
{was, true_label, note} record, stored as an auditable feedback trail.

Idempotent: an image already present as an exemplar for its part is skipped.
"""
from __future__ import annotations
import glob
import json
import os
import sys

from . import knowledge_base as kb
from . import image_features as F
from . import taxonomy as TAX
from . import settings

CORRECTIONS_PATH = settings.CORRECTIONS_PATH


def review_files():
    """Every reviews/<part>.json."""
    return sorted(glob.glob(os.path.join(settings.REVIEWS_DIR, "*.json")))


def resolve_image(base, entry):
    """entry['image'] if on disk, else <LEGACY_AES_DIR>/<base>.jpg, else None."""
    p = entry.get("image")
    if p and os.path.exists(p):
        return p
    alt = os.path.join(settings.LEGACY_AES_DIR, base + ".jpg")
    return alt if os.path.exists(alt) else None


def primary_label(entry):
    if entry.get("result") == "OK" or not entry.get("defects"):
        return "OK"
    dets = sorted(entry["defects"], key=lambda d: TAX.priority(d.get("category", "")), reverse=True)
    return TAX.canonical(dets[0]["category"])


def existing_names(part, _cache={}):
    if part not in _cache:
        con = kb.connect()
        rows = con.execute("SELECT name FROM exemplars WHERE part=?", (part,)).fetchall()
        con.close()
        _cache[part] = {r["name"] for r in rows}
    return _cache[part]


def apply_corrections():
    if not os.path.exists(CORRECTIONS_PATH):
        return 0
    corr = json.load(open(CORRECTIONS_PATH))
    con = kb.connect()
    for base, c in corr.items():
        con.execute("DELETE FROM feedback WHERE note LIKE ?", (f"%[{base}]%",))
        con.execute(
            "INSERT INTO feedback(inspection_id,true_label,note,created_at) VALUES(NULL,?,?,?)",
            (c["true_label"], f"[{base}] (was: {c.get('was', '')}) {c.get('note', '')}", kb._now()),
        )
    con.commit()
    con.close()
    return len(corr)


def main():
    kb.init_db()
    files = review_files()
    if not files:
        raise SystemExit(f"no *.json review files found in {settings.REVIEWS_DIR}")

    # Load every review file, then guard: all categories must be known defects.
    reviews = {f: json.load(open(f)) for f in files}
    all_cats = [d.get("category", "")
                for review in reviews.values()
                for e in review.values()
                for d in e.get("defects", [])]
    ok, unknown = TAX.validate(all_cats)
    if not ok:
        print("ERROR: categories not in knowledge/taxonomy.json:", sorted(set(unknown)))
        print("Add them to taxonomy.json (or fix the spelling) and re-run.")
        sys.exit(1)

    added = skipped = missing = 0
    have = {}
    for f, review in reviews.items():
        print(f"== {os.path.basename(f)} ==")
        source = os.path.basename(f).replace(".json", "")
        for base, entry in review.items():
            part = entry.get("part", "default")
            names = have.setdefault(part, set(existing_names(part)))
            if base in names:
                skipped += 1
                continue
            path = resolve_image(base, entry)
            if not path:
                print("  MISSING IMAGE:", base)
                missing += 1
                continue
            feat = F.extract(path)
            label = primary_label(entry)
            kb.add_exemplar(base, path, label, feat["vector"],
                            phash=feat["signals"].get("phash", ""),
                            source=source, confirmed=1, part=part)
            names.add(base)
            added += 1
            print(f"  + {part} {base} -> {label}")

    fb = apply_corrections()
    cache = kb.rebuild_cache()
    print(f"\nexemplars: +{added} added, {skipped} already present, {missing} missing")
    print(f"feedback:  {fb} corrections recorded")
    for p in sorted(cache.get("parts", {})):
        print(f"  {p}: {cache['parts'][p]}")
    print("lessons embedded:", bool(cache.get("lessons")))


if __name__ == "__main__":
    main()
