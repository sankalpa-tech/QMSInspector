"""QMSInspector - unified command-line interface. 100% offline, ZERO LLM tokens.
 
Production loop:
 
   train   reviews/<part>.json + images  -> inspection_memory.db
   build   inspection_memory.db          -> models/best.pt
    inspect image|dir  --(best.pt)-->  RESOLVED (0 tokens) | Needs Review
                                       Needs Review images are collected for later
                                       manual review (see --needs-review-dir).
 
Commands:
   python qms.py train                       # learn every reviews/<part>.json
   python qms.py build                       # repack models/best.pt from the DB
    python qms.py inspect <image|dir> [--out DIR] [--needs-review-dir DIR|--no-collect]
   python qms.py serve [--port 8000]         # REST API (offline)
   python qms.py stats                       # DB + model summary
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import sys

from inspector import settings

log = settings.get_logger("qms")


def _images(target):
    if os.path.isdir(target):
        out = []
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.PNG"):
            out += glob.glob(os.path.join(target, ext))
        return sorted(set(out))
    return [target]


def cmd_train(args):
    from inspector import trainer
    trainer.main()
    return 0


def cmd_build(args):
    from inspector import model_builder
    model_builder.build()
    return 0


def cmd_inspect(args):
    from inspector import recognizer
    if not os.path.exists(settings.MODEL_PATH):
        log.error("model missing: %s  (run: python qms.py build)", settings.MODEL_PATH)
        return 2
    model = recognizer.load_model(settings.MODEL_PATH)
    out_dir = args.out or settings.OUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    needs_review_dir = None if args.no_collect else (args.needs_review_dir or settings.NEEDS_REVIEW_DIR)

    n_resolved = n_needs_review = 0
    for p in _images(args.target):
        if not os.path.exists(p):
            log.warning("skip missing: %s", p)
            continue
        verdict, status, out_img = recognizer.inspect(p, model, out_dir, needs_review_dir=needs_review_dir)
        if status.startswith("RESOLVED"):
            n_resolved += 1
        else:
            n_needs_review += 1
        print(f"\n=== {os.path.basename(p)} ===")
        print(json.dumps({k: v for k, v in verdict.items() if k != "hint"}, indent=2))
        print("STATUS:", status)
        print("annotated:", out_img)

    total = n_resolved + n_needs_review
    if total > 1:
        print(f"\n{n_resolved} resolved (0 tokens), {n_needs_review} needs review "
              f"/ {total} total.")
        if n_needs_review and needs_review_dir:
            print(f"Needs Review images collected in: {needs_review_dir}")
    return 0


def cmd_serve(args):
    os.environ["INSPECTOR_PORT"] = str(args.port)
    from inspector import web_api
    web_api.main()
    return 0


def cmd_stats(args):
    from inspector import knowledge_base as kb
    kb.init_db()
    con = kb.connect()
    parts = dict((r[0], r[1]) for r in con.execute(
        "SELECT part, COUNT(*) FROM exemplars GROUP BY part"))
    fb = con.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
    insp = con.execute("SELECT COUNT(*) FROM inspections").fetchone()[0]
    con.close()
    print("model     :", settings.MODEL_PATH,
          "(exists)" if os.path.exists(settings.MODEL_PATH) else "(MISSING)")
    print("exemplars :", parts)
    print("feedback  :", fb, "| inspections:", insp)
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="qms", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    pt = sub.add_parser("train", help="learn every reviews/<part>.json into inspection_memory.db")
    pt.set_defaults(func=cmd_train)

    pb = sub.add_parser("build", help="repack models/best.pt from the inspection memory DB")
    pb.set_defaults(func=cmd_build)

    pi = sub.add_parser("inspect", help="inspect image(s) locally (0 tokens)")
    pi.add_argument("target")
    pi.add_argument("--out", help="output folder for annotated images")
    pi.add_argument("--needs-review-dir", dest="needs_review_dir",
                    help="folder to copy Needs Review images into (default: ./needs_review)")
    pi.add_argument("--no-collect", action="store_true",
                    help="do not copy Needs Review images anywhere")
    pi.set_defaults(func=cmd_inspect)

    ps = sub.add_parser("serve", help="run the offline REST API")
    ps.add_argument("--port", type=int, default=8000)
    ps.set_defaults(func=cmd_serve)

    pst = sub.add_parser("stats", help="show DB + model summary")
    pst.set_defaults(func=cmd_stats)
    return p


def main(argv):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
