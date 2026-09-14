"""Central defect taxonomy loader.

Every module gets part names, defect names, severity and colors from here, so
defect registration stays centralized. The source of truth is one rule file per
part (knowledge/rules/<part>.json, loaded via part_rules); if no rule files are
present it falls back to the legacy knowledge/taxonomy.json.

Public API:
    PARTS, DEFAULT_PART, DEFECT_NAMES
    priority(name)        -> int severity (5=critical .. 1=minor, 0=OK)
    color_for(name)       -> BGR tuple
    canonical(name)       -> map a raw/legacy string to a canonical defect name
    description(name)     -> str
    colors_map()          -> {canonical name: BGR}
    severity_rules()      -> [(severity, (kw, ...)), ...]  (checkpoint-compatible)
    validate(names)       -> (ok_bool, unknown_list)
"""
from __future__ import annotations
import json

from . import settings
from . import part_rules

if part_rules.available():
    _TAX = part_rules.build_taxonomy()
else:
    with open(settings.TAXONOMY_PATH, encoding="utf-8") as _fh:
        _TAX = json.load(_fh)

DEFECTS = _TAX["defects"]
PARTS = _TAX.get("parts", [])
DEFAULT_PART = _TAX.get("default_part", "Bearing Cup")
DEFAULT_SEVERITY = int(_TAX.get("default_severity", 2))
DEFECT_NAMES = list(DEFECTS.keys())
FALLBACK_COLOR = (0, 0, 255)

# name (lowercased) -> canonical, built from canonical names + aliases
_LOOKUP = {}
for _name, _spec in DEFECTS.items():
    _LOOKUP[_name.lower()] = _name
    for _a in _spec.get("aliases", []):
        _LOOKUP.setdefault(_a.lower(), _name)


def canonical(name):
    """Map any raw/legacy defect string to its canonical name (best effort)."""
    if not name:
        return name
    key = name.strip().lower()
    if key in _LOOKUP:
        return _LOOKUP[key]
    for alias, canon in _LOOKUP.items():
        if alias in key:
            return canon
    return name


def priority(name):
    """Severity for a defect name. Exact canonical first, then alias/keyword match."""
    if not name:
        return DEFAULT_SEVERITY
    spec = DEFECTS.get(canonical(name))
    if spec is not None:
        return int(spec.get("severity", DEFAULT_SEVERITY))
    return DEFAULT_SEVERITY


def color_for(name):
    spec = DEFECTS.get(canonical(name))
    if spec and spec.get("color"):
        return tuple(spec["color"])
    return FALLBACK_COLOR


def description(name):
    spec = DEFECTS.get(canonical(name))
    return spec.get("description", "") if spec else ""


def colors_map():
    """BGR color per canonical defect name (for renderers)."""
    return {n: tuple(s["color"]) for n, s in DEFECTS.items() if s.get("color")}


def severity_rules():
    """Checkpoint-compatible [(severity, (keyword, ...)), ...], highest first.

    Groups each defect's canonical name + aliases under its severity so legacy
    keyword-substring matching keeps working from the packed model.
    """
    by_sev = {}
    for name, spec in DEFECTS.items():
        sev = int(spec.get("severity", DEFAULT_SEVERITY))
        if sev <= 0:
            continue
        kws = by_sev.setdefault(sev, [])
        kws.append(name.lower())
        kws.extend(a.lower() for a in spec.get("aliases", []))
    return [(sev, tuple(dict.fromkeys(by_sev[sev]))) for sev in sorted(by_sev, reverse=True)]


def validate(names):
    """Return (all_known, [unknown names]) for a list of raw defect strings."""
    unknown = [n for n in names if canonical(n) not in DEFECTS]
    return (not unknown), unknown
