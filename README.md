# QMSInspector

Offline, **zero-token** quality-inspection system for manufactured parts
(currently **Bearing Cup** and **Bracket**). It learns from human-marked example
images, packs everything into one portable model file, and then inspects new
images entirely on your machine - **no cloud, no LLM, no API keys**.

Uncertain images (ones the model has never seen) are set aside so a human can
teach them later, closing the loop.

---

## How it works

```
 reviews/<part>.json  --teach-->  data/learning.db  --build-->  models/best.pt
                                                                     |
                                            inspect (0 tokens) <-----+
                                                  |
                                RESOLVED (annotated verdict)  or  UNCERTAIN
                                                                      |
                                             copied to  uncertain/  for teaching
```

* **teach** - reads every `reviews/<part>.json` (each entry = a human marking:
  part, OK/DEFECT, defect boxes/polygons) and stores it as a confirmed example
  (feature vector + perceptual hash) in `data/learning.db`.
* **build** - packs all examples + geometry + taxonomy + lessons into a single
  `models/best.pt`.
* **inspect** - loads `best.pt` and matches each image by perceptual hash. A match
  replays the confirmed verdict and draws the exact defect masks. No match =>
  `UNCERTAIN`, and the image is copied to `uncertain/` for later teaching.

Inspection never calls any external service.

---

## Install

```powershell
pip install -r requirements.txt
```

## Usage

```powershell
# 1. teach from the review files (idempotent - skips already-learned images)
python qms.py teach

# 2. build the packed model
python qms.py build

# 3. inspect an image or a folder (annotated outputs in inspect_out/)
python qms.py inspect "C:\path\to\image.jpg"
python qms.py inspect "C:\path\to\folder"

#    UNCERTAIN images are copied to ./uncertain by default:
python qms.py inspect "C:\path\to\folder" --uncertain-dir "C:\to_review"
python qms.py inspect "C:\path\to\folder" --no-collect      # don't copy

# summary of what has been learned
python qms.py stats
```

### REST API (also offline)

```powershell
python qms.py serve --port 8000
```

### Startup helper

If you want a one-command reset, use:

```bash
./start.sh
```

That deletes previous `inspection_runs/*` output and starts the server on port `8000`.
To install dependencies first, opt in explicitly:

```bash
./start.sh --install
```

On Windows, use:

```powershell
.\start.bat
```

Or with optional dependency install:

```powershell
.\start.bat --install
```

| Method | Path       | Purpose                                             |
|--------|------------|-----------------------------------------------------|
| GET    | `/health`  | service status + counts                             |
| POST   | `/inspect` | inspect an uploaded image; returns the JSON verdict |
| POST   | `/learn`   | teach a label at runtime (image + label)            |
| GET    | `/parts`   | learned parts + their defect categories             |
| GET    | `/stats`   | counts + recent inspections                         |

---

## Teaching new images

For every image dropped in `uncertain/`, add an entry to the matching
`reviews/<part>.json` (mark OK, or the defect + its box/polygon), then re-run:

```powershell
python qms.py teach
python qms.py build
```

The next inspection of that image (or a near-duplicate) resolves instantly with
zero tokens.

To add a **new part**, create `reviews/<new_part>.json` (same schema) and register
the part + its defects in `knowledge/taxonomy.json`. No code changes needed.

---

## Layout

```
qms.py                     single CLI (teach | build | inspect | serve | stats)
inspector/
  settings.py              paths + tunables (env-overridable)
  taxonomy.py              central parts/defects/severity/colors loader
  image_features.py        OpenCV feature extraction + perceptual hash
  knowledge_base.py        SQLite learning DB + knowledge cache
  renderer.py              draws defect masks / labels / banners
  recognizer.py            offline packed-model recall (the inspect engine)
  model_builder.py         packs everything into models/best.pt
  teacher.py               learns all parts from reviews/
  live_classifier.py       kNN + rule engine used by the REST API
  live_trainer.py          runtime add/correct used by the REST API
  web_api.py               Flask REST server (offline)
knowledge/                 taxonomy.json, lessons.json, corrections.json
reviews/                   bearing_cup.json, bracket.json (human markings)
models/best.pt             the packed model
data/learning.db           durable learned memory
```

All inspection is local and free. The only durable state you need to keep is
`data/learning.db`, `models/best.pt`, `reviews/`, and `knowledge/`.
