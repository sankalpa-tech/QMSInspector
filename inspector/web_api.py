"""REST API for the self-learning defect inspector (Flask). 100% offline, no LLM.

Endpoints
---------
GET  /health              -> service status + cache counts
POST /inspect             -> multipart 'image' file; returns the JSON verdict
                             plus status RESOLVED | TEACH_NEEDED and a retrieval hint
POST /learn               -> teach at runtime; multipart 'image' + form 'label',
                             or JSON {"path": "...", "label": "..."}; updates cache+DB
GET  /parts               -> parts + learned categories
GET  /stats               -> exemplar counts + recent inspections

Run:
    python qms.py serve --port 8000        # http://127.0.0.1:8000
"""
from __future__ import annotations
import os
import time
import threading

from flask import Flask, request, jsonify

from . import knowledge_base as kb
from . import live_trainer as LEARN
from . import live_classifier as INS
from . import settings

ROOT = settings.ROOT
UPLOAD_DIR = os.path.join(ROOT, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
_lock = threading.Lock()

# in-memory state, reloaded after each learn
_state = {"cache": None, "exemplars": None}


def _reload():
    _state["cache"] = kb.load_cache()
    _state["exemplars"] = INS._load_exemplar_matrix()


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

    status = "TEACH_NEEDED" if res["needs_review"] else "RESOLVED"

    return jsonify({
        **res["verdict"],                      # result + defects (required schema)
        "part": part,
        "status": status,                       # RESOLVED | TEACH_NEEDED
        "confidence": res["confidence"],
        "predicted": res["top"],
        "recall": res["recall"],
        "hint": res["hint"],                    # nearest known examples (for review)
        "image_path": path,                     # reuse this in /learn to teach
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


def main():
    kb.init_db()
    _reload()
    port = int(os.environ.get("INSPECTOR_PORT", "8000"))
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()
