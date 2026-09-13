# QMSInspector - project context and expectations

This file is for future work sessions. Read this before making UI or labeling changes.

## What this project is

- Offline quality inspection workflow for manufactured parts
- No cloud, no LLM, no API calls during inspection
- Current parts in use: `Bearing Cup` and `Bracket`
- Training source of truth: `reviews\*.json`
- Learned memory: `data\inspection_memory.db`
- Packed deployable model: `models\best.pt`

## Core pipeline

1. `python qms.py train`
2. `python qms.py build`
3. `python qms.py serve --port 8000`

Important behavior:

- `train` is idempotent and skips already learned exemplar names
- If a review label changes for an already learned image, updating the JSON alone is not enough
- For relabeling an already learned sample, update both:
  - `reviews\*.json`
  - `data\inspection_memory.db`
- Then run `python qms.py build`
- Restart the server after rebuilding because the Flask app caches the model in memory

## Startup

### Windows

```powershell
.\start.bat
```

Optional dependency install:

```powershell
.\start.bat --install
```

### Bash

```bash
./start.sh
./start.sh --install
```

Startup scripts should:

- clear `inspection_runs\*`
- not force dependency install by default
- start the server on port `8000` unless overridden

## Current UI expectations

The UI should feel professional and clean while keeping workflow simple.

Preferred flow:

1. Create Project
2. Open Project
3. Add Parts
4. Click Part
5. View images again

The user also wants:

- delete part
- delete project

Naming constraint:

- Do not use the word `demo` in UI text, endpoint naming, file names, or output folder names

## Current UX decisions

- Use **Needs Review** consistently in the UI and docs
- Top summary cards should be clickable
- Bottom chips and top summary cards must stay synced to the same filter state
- `Images` summary card should reset to `All`
- Users must be able to reopen images later
- Avoid fake inspection percentages; real upload percent is fine, real processed-count progress is preferred
- Lightbox/popup should close on overlay click and on Escape
- Zoom/pan behavior should feel standard and intuitive for vertical drag direction
- Prefer custom lightbox controls if third-party zoom library worsens UX
- Keep both UI themes available with a user switch, with light theme as a preferred option

## Annotation expectations

- Labels must remain readable on bright metallic surfaces
- Locator boxes must be highly visible even for low-contrast defect colors
- Display outline visibility is more important than strictly using a muted taxonomy color for the box

Implemented direction:

- auto-scaled label text
- dark label background
- white text with dark stroke
- strong multi-stroke locator outline
- brighter focus color for low-saturation / low-contrast classes

## Domain labeling decisions

### Corrosion labeling

Current user/domain preference:

- If the mark looks like rust/corrosion, classify it as `Corrosion`
- Keep one category: `Corrosion`
- Multiple images can belong to the same `Corrosion` category

Already updated:

- `IMG20260824162037` -> `Corrosion`
- `IMG20260824162142` -> `Corrosion`

### Legacy manual-mark category removal

Current user/domain preference:

- The old manual-mark category is not a real defect category for this project
- Remove that legacy category from taxonomy, lessons, training data, and model artifacts
- Do not show or train manual-mark / reject-paint categories in the UI

### Dent category simplification

Current user/domain preference:

- Do not keep separate small edge/rim damage categories for bearing cups
- Merge all small bearing-cup edge/rim damage into a single category: `Dent`
- Treat cut/stepped edge damage and small rim interruptions as `Dent`

## Files most relevant for future edits

- `inspector\inspector_page.py` - UI HTML/JS
- `inspector\web_api.py` - Flask endpoints and UI routes
- `inspector\renderer.py` - annotation labels and boxes
- `inspector\recognizer.py` - offline inspection behavior
- `inspector\trainer.py` - training review data
- `inspector\knowledge_base.py` - SQLite learned exemplars
- `reviews\bearing_cup.json`
- `knowledge\taxonomy.json`

## Working rules for future sessions

- Favor clear, professional UX over noisy styling or unnecessary complexity
- Keep terminology clear for non-technical users
- If changing labels, keep `reviews`, `inspection_memory.db`, and `best.pt` aligned
- After model or renderer changes, restart the server and regenerate run outputs
- When the UI still shows old results, first suspect:
  1. old running server
  2. old `inspection_runs` output
  3. stale learned exemplar rows in `data\inspection_memory.db`
