# QMSInspector

QMSInspector is an offline inspection system for manufactured parts. It learns from
human-reviewed sample images, stores them in a local inspection memory database, and
then checks new images entirely on the machine - **no cloud, no LLM, no API keys**.

Unlike generic object detectors, it is trained on your actual part-specific defects,
part types, and pass/fail decisions. If an image does not match a known pattern with
confidence, it is marked **Needs Review** and sent back for human review.

This is built for repeat part inspection: fast review of known defects, safe handling
of unfamiliar cases, and full local control of the quality process.

### Terminology

- `Part` - a specific component type being inspected, such as a Bearing Cup or Bracket.
- `Taxonomy` - the list of allowed defect labels or categories for a part.
- `Review` - a human-validated marking that defines what is good or defective on a sample image.
- `Train` - the process of adding reviewed sample images into the local memory so the system can recognize them later.
- `Needs Review` - the safe fallback state when the image does not match any known sample confidently.
- `Inspection Memory DB` - the local SQLite database that stores learned sample data and prior inspection history.
- `Model` - the packaged local model built from the learned data for offline inference.

### Workflow diagram

```mermaid
flowchart TD
    A[Add Part] --> B[Upload images]
    B --> C[Train samples]

    K[Taxonomy] --> C
    M[Inspection Memory DB] --> C

    C --> D[Build model]
    D --> E[Inspect image]
    E --> F{Known match?}

    F -- Yes --> G[Resolved verdict]
    G --> G2[Defect box overlay]

    F -- No --> H[Needs Review]
    H --> I[Train again]
    I --> C
```

---

## How it works

```
 reviews/<part>.json --train--> data/inspection_memory.db --build--> models/best.pt
                                                                     |
                                            inspect (0 tokens) <-----+
                                                  |
                                RESOLVED (annotated verdict)  or  Needs Review
                                                                      |
                                             copied to  uncertain/  for retraining
```

* **train** - reads every `reviews/<part>.json` file, validates each human marking
 against the active taxonomy, extracts per-image feature vectors and perceptual hashes,
 and stores the approved training records in `data/inspection_memory.db`.
* **build** - loads the trained records from the database, rebuilds the normalized
 feature matrix and taxonomy metadata, and writes the packed inference artifact to
 `models/best.pt`.
* **inspect** - loads `best.pt`, extracts the feature vector and perceptual hash from
 an input image, performs local recall against stored reference entries, and returns
 either a resolved verdict with defect overlays or a `Needs Review` result. Images that
 fail recall are copied into `uncertain/` for later retraining.

Inspection never calls any external service.

---

## Install

```powershell
pip install -r requirements.txt
```

## Usage

```powershell
# 1. train from the review files (idempotent - skips already-learned images)
python qms.py train

# 2. build the packed model
python qms.py build

# 3. inspect an image or a folder (annotated outputs in inspect_out/)
python qms.py inspect "C:\path\to\image.jpg"
python qms.py inspect "C:\path\to\folder"

#    Needs Review images are copied to ./uncertain by default:
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
| POST   | `/learn`   | train a label at runtime (image + label)            |
| GET    | `/parts`   | learned parts + their defect categories             |
| GET    | `/stats`   | counts + recent inspections                         |

---

## Reviewing new images

For every image dropped in `uncertain/`, add an entry to the matching
`reviews/<part>.json` (mark OK, or the defect + its box/polygon), then re-run:

```powershell
python qms.py train
python qms.py build
```

The next inspection of that image (or a near-duplicate) resolves instantly with
zero tokens.

To add a **new part**, create `reviews/<new_part>.json` (same schema) and register
the part + its defects in `knowledge_base/taxonomy.json`. No code changes needed.

---

## Layout

```
qms.py                     single CLI (train | build | inspect | serve | stats)
inspector/
  settings.py              paths + tunables (env-overridable)
  taxonomy.py              central parts/defects/severity/colors loader
  image_features.py        OpenCV feature extraction + perceptual hash
  knowledge_base.py        SQLite inspection memory + knowledge cache
  renderer.py              draws defect masks / labels / banners
  recognizer.py            offline packed-model recall (the inspect engine)
  model_builder.py         packs everything into models/best.pt
  trainer.py               trains all parts from reviews/
  live_classifier.py       kNN + rule engine used by the REST API
  live_trainer.py          runtime add/correct used by the REST API
  web_api.py               Flask REST server (offline)
knowledge_base/            taxonomy.json, lessons.json, corrections.json
reviews/                   bearing_cup.json, bracket.json (human markings)
models/best.pt             the packed model
data/inspection_memory.db durable learned memory
```

### Folder purpose summary

- `data/` - local runtime data, including the main SQLite database
- `data/inspection_memory.db` - durable learning memory and prior inspection history
- `reviews/` - human-reviewed sample annotations for each part
- `knowledge_base/` - taxonomy, defect definitions, and training guidance
- `models/` - built inspection model package used for offline inference
- `inspect_out/` - generated annotated inspection outputs
- `uncertain/` - images that did not match confidently and need human review

All inspection is local and free. The only durable state you need to keep is
`data/inspection_memory.db`, `models/best.pt`, `reviews/`, and `knowledge_base/`.
