"""QMSInspector - unified command-line interface. 100% offline, ZERO LLM tokens.

Production loop:

    teach   reviews/<part>.json + images  -> learning.db
    build   learning.db                    -> models/best.pt
    inspect image|dir  --(best.pt)-->  RESOLVED (0 tokens) | UNCERTAIN
                                       UNCERTAIN images are collected for later
                                       manual teaching (see --uncertain-dir).

Commands:
    python qms.py teach                        # learn every reviews/<part>.json
    python qms.py build                        # repack models/best.pt from the DB
    python qms.py inspect <image|dir> [--out DIR] [--uncertain-dir DIR|--no-collect]
    python qms.py serve [--port 8000]          # REST API (offline)
    python qms.py stats                        # DB + model summary
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


def cmd_teach(args):
    from inspector import teacher
    teacher.main()
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
    uncertain_dir = None if args.no_collect else (args.uncertain_dir or settings.UNCERTAIN_DIR)

    n_resolved = n_uncertain = 0
    for p in _images(args.target):
        if not os.path.exists(p):
            log.warning("skip missing: %s", p)
            continue
        verdict, status, out_img = recognizer.inspect(p, model, out_dir, uncertain_dir=uncertain_dir)
        if status.startswith("RESOLVED"):
            n_resolved += 1
        else:
            n_uncertain += 1
        print(f"\n=== {os.path.basename(p)} ===")
        print(json.dumps({k: v for k, v in verdict.items() if k != "hint"}, indent=2))
        print("STATUS:", status)
        print("annotated:", out_img)

    total = n_resolved + n_uncertain
    if total > 1:
        print(f"\n{n_resolved} resolved (0 tokens), {n_uncertain} uncertain "
              f"/ {total} total.")
        if n_uncertain and uncertain_dir:
            print(f"uncertain images collected in: {uncertain_dir}")
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

    pt = sub.add_parser("teach", help="learn every reviews/<part>.json into learning.db")
    pt.set_defaults(func=cmd_teach)

    pb = sub.add_parser("build", help="repack models/best.pt from the learning DB")
    pb.set_defaults(func=cmd_build)

    pi = sub.add_parser("inspect", help="inspect image(s) locally (0 tokens)")
    pi.add_argument("target")
    pi.add_argument("--out", help="output folder for annotated images")
    pi.add_argument("--uncertain-dir", dest="uncertain_dir",
                    help="folder to copy UNCERTAIN images into (default: ./uncertain)")
    pi.add_argument("--no-collect", action="store_true",
                    help="do not copy UNCERTAIN images anywhere")
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
