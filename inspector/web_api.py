"""REST API for the self-learning defect inspector (Flask). 100% offline, no LLM.

Endpoints
---------
GET  /health              -> service status + cache counts
POST /inspect             -> multipart 'image' file; returns the JSON verdict
                             plus status RESOLVED | NEEDS_REVIEW and a retrieval hint
POST /learn               -> train at runtime; multipart 'image' + form 'label',
                             or JSON {"path": "...", "label": "..."}; updates cache+DB
GET  /parts               -> parts + learned categories
GET  /stats               -> exemplar counts + recent inspections

Run:
    python qms.py serve --port 8000        # http://127.0.0.1:8000
"""
from __future__ import annotations
import os
import time
import uuid
import glob
import shutil
import zipfile
import threading

from flask import Flask, request, jsonify, send_from_directory, Response

from . import knowledge_base as kb
from . import live_trainer as LEARN
from . import live_classifier as INS
from . import recognizer as REC
from . import inspector_page
from . import settings

ROOT = settings.ROOT
UPLOAD_DIR = os.path.join(ROOT, "uploads")
RUNS_DIR = os.path.join(ROOT, "inspection_runs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RUNS_DIR, exist_ok=True)

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024  # 512 MB bulk uploads
_lock = threading.Lock()

# in-memory state, reloaded after each learn
_state = {"cache": None, "exemplars": None, "model": None}


def _reload():
    _state["cache"] = kb.load_cache()
    _state["exemplars"] = INS._load_exemplar_matrix()


def _model():
    if _state["model"] is None:
        _state["model"] = REC.load_model(settings.MODEL_PATH)
    return _state["model"]


def _ensure_loaded():
    if _state["cache"] is None:
        _reload()


def _save_upload(file_storage):
    ts = int(time.time() * 1000)
    safe = os.path.basename(file_storage.filename or "upload.jpg").replace(" ", "_")
    path = os.path.join(UPLOAD_DIR, f"{ts}_{safe}")
    file_storage.save(path)
    return path


@app.get("/health")
def health():
    _ensure_loaded()
    return jsonify({"status": "ok", "categories": kb.CATEGORIES,
                    "counts": _state["cache"].get("counts", {})})


@app.post("/inspect")
def inspect_ep():
    _ensure_loaded()
    part = (request.form.get("part") or request.args.get("part")
            or (request.get_json(silent=True) or {}).get("part") or "default")
    # Accept the image three ways for client convenience:
    #   1. multipart form field named 'image'
    #   2. raw binary request body (Postman "binary", or --data-binary)
    #   3. JSON {"path": "C:\\...jpg"} pointing at a server-side file
    path = None
    if "image" in request.files:
        path = _save_upload(request.files["image"])
    elif request.files:  # any uploaded file, whatever the field name
        path = _save_upload(next(iter(request.files.values())))
    else:
        j = request.get_json(silent=True)
        if j and j.get("path") and os.path.exists(j["path"]):
            path = j["path"]                       # server-side file path
        elif request.data and len(request.data) > 100 and not request.is_json:
            ts = int(time.time() * 1000)           # raw binary body (e.g. --data-binary)
            path = os.path.join(UPLOAD_DIR, f"{ts}_raw_upload.jpg")
            with open(path, "wb") as fh:
                fh.write(request.data)
    if not path:
        return jsonify({"error": "send an image as multipart field 'image', "
                                 "or a raw binary body, or JSON {\"path\": \"...\"}"}), 400
    try:
        with _lock:
            exemplars = INS._load_exemplar_matrix(part=part)   # scope to this part only
            res = INS.inspect_image(path, _state["cache"], exemplars, log=True)
    except Exception as e:  # noqa
        return jsonify({"error": str(e)}), 500

    status = "NEEDS_REVIEW" if res["needs_review"] else "RESOLVED"

    return jsonify({
        **res["verdict"],                      # result + defects (required schema)
        "part": part,
        "status": status,                       # RESOLVED | NEEDS_REVIEW
        "confidence": res["confidence"],
        "predicted": res["top"],
        "recall": res["recall"],
        "hint": res["hint"],                    # nearest known examples (for review)
        "image_path": path,                     # reuse this in /learn to train
    })


@app.post("/learn")
def learn_ep():
    _ensure_loaded()
    # accept either an uploaded file or a server-side path (from /inspect)
    if "image" in request.files:
        path = _save_upload(request.files["image"])
        label = request.form.get("label", "")
        part = request.form.get("part", "default") or "default"
    else:
        data = request.get_json(silent=True) or {}
        path = data.get("path", "")
        label = data.get("label", "")
        part = data.get("part", "default") or "default"
    if not label or not str(label).strip():
        return jsonify({"error": "label must be a non-empty defect category "
                                 "(or 'OK' for no defect). New parts may use new categories."}), 400
    if not path or not os.path.exists(path):
        return jsonify({"error": "image not found; upload 'image' or pass a valid 'path'"}), 400
    is_new_cat = label not in kb.categories_for_part(part)
    try:
        with _lock:
            LEARN.add(path, label, source="api", part=part)
            _reload()
    except Exception as e:  # noqa
        return jsonify({"error": str(e)}), 500
    return jsonify({"status": "LEARNED", "label": label, "part": part,
                    "new_category": is_new_cat,
                    "categories": kb.categories_for_part(part),
                    "part_counts": _state["cache"].get("parts", {}).get(part, {})})


@app.get("/parts")
def parts_ep():
    _ensure_loaded()
    parts = kb.list_parts()
    detail = {p: {"exemplars": n, "categories": kb.categories_for_part(p)}
              for p, n in parts.items()}
    return jsonify({"parts": detail})


@app.get("/stats")
def stats_ep():
    _ensure_loaded()
    con = kb.connect()
    recent = [dict(r) for r in con.execute(
        "SELECT name,pred,result,confidence,created_at FROM inspections "
        "ORDER BY id DESC LIMIT 10").fetchall()]
    con.close()
    return jsonify({"counts": _state["cache"].get("counts", {}), "recent_inspections": recent})


def _iter_uploaded_images(run_in_dir):
    """Save every uploaded image (and every image inside uploaded .zip) into
    run_in_dir. Returns a sorted list of saved image paths."""
    saved = []
    all_files = []
    for key in request.files:
        all_files.extend(request.files.getlist(key))
    for fs in all_files:
        fname = os.path.basename(fs.filename or "")
        if not fname:
            continue
        ext = os.path.splitext(fname)[1].lower()
        if ext == ".zip":
            zpath = os.path.join(run_in_dir, fname)
            fs.save(zpath)
            try:
                with zipfile.ZipFile(zpath) as zf:
                    for member in zf.namelist():
                        mext = os.path.splitext(member)[1].lower()
                        if mext in IMAGE_EXTS and not member.endswith("/"):
                            target = os.path.join(run_in_dir, os.path.basename(member))
                            with zf.open(member) as src, open(target, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                            saved.append(target)
            except zipfile.BadZipFile:
                pass
            finally:
                os.remove(zpath)
        elif ext in IMAGE_EXTS:
            target = os.path.join(run_in_dir, fname)
            fs.save(target)
            saved.append(target)
    # de-dup while keeping order
    seen, out = set(), []
    for p in sorted(saved):
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


@app.get("/")
def home_page():
    return Response(inspector_page.HTML, mimetype="text/html")


@app.post("/ui/inspect")
def ui_inspect():
    """Bulk inspection UI endpoint: accepts many images and/or .zip files.
    Runs the offline packed model (0 tokens) and returns per-image verdicts plus
    URLs to the annotated + original images."""
    run_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    run_dir = os.path.join(RUNS_DIR, run_id)
    in_dir = os.path.join(run_dir, "in")
    out_dir = os.path.join(run_dir, "out")
    os.makedirs(in_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)

    images = _iter_uploaded_images(in_dir)
    if not images:
        return jsonify({"error": "no images found; upload image files or a .zip of images"}), 400

    model = _model()
    results = []
    counts = {"RESOLVED": 0, "NEEDS_REVIEW": 0, "OK": 0, "DEFECT": 0}
    with _lock:
        for p in images:
            base = os.path.splitext(os.path.basename(p))[0]
            try:
                verdict, status, out_img = REC.inspect(p, model, out_dir, needs_review_dir=None)
            except Exception as e:  # noqa
                results.append({"name": os.path.basename(p), "error": str(e)})
                continue
            resolved = status.startswith("RESOLVED")
            result = verdict.get("result", "NEEDS_REVIEW")
            normalized_result = "NEEDS_REVIEW" if result == "NEEDS_REVIEW" else result
            counts["RESOLVED" if resolved else "NEEDS_REVIEW"] += 1
            if normalized_result in ("OK", "DEFECT"):
                counts[normalized_result] += 1
            defects = [{"type": d.get("type"), "severity": d.get("severity_priority"),
                        "location": d.get("location"), "primary": d.get("primary", False)}
                       for d in verdict.get("defects", [])]
            results.append({
                "name": os.path.basename(p),
                "part": verdict.get("part", "default"),
                "part_confident": verdict.get("part_confident", False),
                "status": "RESOLVED" if resolved else "NEEDS_REVIEW",
                "result": normalized_result,
                "defects": defects,
                "primary_defect": (defects[0]["type"] if defects else None),
                "annotated_url": f"/ui/file/{run_id}/out/{os.path.basename(out_img)}",
                "original_url": f"/ui/file/{run_id}/in/{os.path.basename(p)}",
            })
    # DEFECT first, then NEEDS_REVIEW, then OK, for an at-a-glance review order
    order = {"DEFECT": 0, "NEEDS_REVIEW": 1, "OK": 2}
    results.sort(key=lambda r: (r.get("part", ""), order.get(r.get("result"), 3)))
    by_part = {}
    for r in results:
        by_part.setdefault(r.get("part", "default"), {"total": 0, "DEFECT": 0, "OK": 0, "NEEDS_REVIEW": 0})
        by_part[r["part"]]["total"] += 1
        by_part[r["part"]][r["result"]] = by_part[r["part"]].get(r["result"], 0) + 1
    return jsonify({"run_id": run_id, "total": len(images),
                    "counts": counts, "by_part": by_part, "results": results})


@app.get("/ui/file/<run_id>/<kind>/<path:fname>")
def ui_file(run_id, kind, fname):
    if kind not in ("in", "out"):
        return jsonify({"error": "bad path"}), 404
    folder = os.path.join(RUNS_DIR, os.path.basename(run_id), kind)
    return send_from_directory(folder, fname)

def main():
    kb.init_db()
    _reload()
    port = int(os.environ.get("INSPECTOR_PORT", "8000"))
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()
