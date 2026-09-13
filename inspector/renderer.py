"""Draw defect annotations onto inspection images.

Renders every defect from a verdict/review entry: filled overlay + locator box +
severity-tagged label, with the highest-severity defect marked PRIMARY. Handles
both polygon (`points`) and box (`bbox` [+ optional `seg` method]) geometry.
Defect names, colors and severity come centrally from knowledge/taxonomy.json.
"""
from __future__ import annotations
import os
import re
import cv2
import numpy as np

from . import taxonomy as TAX

COLORS = TAX.colors_map()
FALLBACK = TAX.FALLBACK_COLOR
# Severity is centrally controlled in knowledge/taxonomy.json (via taxonomy.py).
SEVERITY_RULES = TAX.severity_rules()


def base(fn):
    """Normalize a filename to its IMG<digits> key (Roboflow-safe), else the stem."""
    m = re.match(r"(IMG\d+)", os.path.basename(fn))
    return m.group(1) if m else os.path.splitext(os.path.basename(fn))[0]


def color_for(name):
    return TAX.color_for(name)


def defect_priority(category):
    return TAX.priority(category)


def sort_by_priority(dets):
    """Return dets sorted highest-severity first (stable)."""
    return sorted(dets, key=lambda d: defect_priority(d.get("category", "")), reverse=True)


def draw_label(img, x, y, text, color):
    font, scale, th = cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
    (tw, tht), bl = cv2.getTextSize(text, font, scale, th)
    y = max(y, tht + 6)
    cv2.rectangle(img, (x, y - tht - 6), (x + tw + 6, y + bl - 2), color, -1)
    cv2.putText(img, text, (x + 3, y - 3), font, scale, (255, 255, 255), th, cv2.LINE_AA)


def _bbox_px(bbox, w, h):
    bx, by, bw, bh = bbox
    x0, y0 = int(bx * w), int(by * h)
    x1, y1 = int((bx + bw) * w), int((by + bh) * h)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    return x0, y0, x1, y1


def _largest_contours(mask, min_area, top=3):
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = [c for c in cnts if cv2.contourArea(c) >= min_area]
    cnts.sort(key=cv2.contourArea, reverse=True)
    return cnts[:top]


def segment_defect(img, bbox, method):
    """Return a list of pixel contours (Nx1x2 int32) segmenting the defect inside bbox.
    Real OpenCV masks: color thresholding for paint/stain/rust, edge/GrabCut for geometry.
    Returns [] if segmentation fails (caller falls back to the box)."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = _bbox_px(bbox, w, h)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return []
    roi = img[y0:y1, x0:x1]
    area = roi.shape[0] * roi.shape[1]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = None

    if method == "red_paint":
        m1 = cv2.inRange(hsv, (0, 60, 60), (12, 255, 255))
        m2 = cv2.inRange(hsv, (160, 40, 60), (180, 255, 255))
        mask = cv2.bitwise_or(m1, m2)
    elif method == "rust":
        # brown/orange-red, lower saturation than fresh paint
        mask = cv2.inRange(hsv, (3, 40, 40), (25, 255, 230))
    elif method == "dark":
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        thr = max(40, int(np.mean(gray) - 1.0 * np.std(gray)))
        mask = cv2.inRange(gray, 0, thr)
    elif method in ("edge", "geometry"):
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(gray, 40, 120)
        edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=2)
        mask = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    elif method == "grabcut":
        m = np.zeros(roi.shape[:2], np.uint8)
        bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
        rect = (2, 2, roi.shape[1] - 4, roi.shape[0] - 4)
        try:
            cv2.grabCut(roi, m, rect, bgd, fgd, 4, cv2.GC_INIT_WITH_RECT)
            mask = np.where((m == 1) | (m == 3), 255, 0).astype(np.uint8)
        except Exception:
            return []
    if mask is None:
        return []
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    cnts = _largest_contours(mask, min_area=max(30, 0.01 * area))
    out = []
    for c in cnts:
        c = c + np.array([[x0, y0]])  # shift to full-image coords
        out.append(c.astype(np.int32))
    return out


def annotate(img, dets, uncertain=False):
    """dets: list of dict {category, points(norm) | bbox(norm) [+ seg method], reason}.
    Draws every defect. The highest-severity defect is marked PRIMARY (thicker border)."""
    h, w = img.shape[:2]
    overlay = img.copy()
    dets = sort_by_priority(dets)
    for i, d in enumerate(dets):
        name = d["category"]
        is_primary = (i == 0) and not uncertain and len(dets) >= 1
        color = (0, 140, 255) if uncertain else color_for(name)
        prefix = "? " if uncertain else ("* " if is_primary else "")
        label = prefix + name + (f"  [P{defect_priority(name)}]" if not uncertain else "")
        seg_contours = []
        if d.get("points"):
            pts = np.array([[int(x * w), int(y * h)] for x, y in d["points"]], np.int32)
            seg_contours = [pts]
            x0, y0 = int(pts[:, 0].min()), int(pts[:, 1].min())
            x1, y1 = int(pts[:, 0].max()), int(pts[:, 1].max())
        else:
            bx, by, bw, bh = d["bbox"]
            x0, y0 = int(bx * w), int(by * h)
            x1, y1 = int((bx + bw) * w), int((by + bh) * h)
            if d.get("seg"):
                seg_contours = segment_defect(img, d["bbox"], d["seg"])
        if seg_contours:
            cv2.fillPoly(overlay, seg_contours, color)
            cv2.polylines(img, seg_contours, True, color, 2, cv2.LINE_AA)
            allpts = np.vstack([c.reshape(-1, 2) for c in seg_contours])
            x0, y0 = int(allpts[:, 0].min()), int(allpts[:, 1].min())
            x1, y1 = int(allpts[:, 0].max()), int(allpts[:, 1].max())
        else:
            cv2.rectangle(overlay, (x0, y0), (x1, y1), color, -1)
        # Draw a locator rectangle + defect name label. Primary gets a thicker border.
        pad = 6
        rx0, ry0 = max(0, x0 - pad), max(0, y0 - pad)
        rx1, ry1 = min(w - 1, x1 + pad), min(h - 1, y1 + pad)
        cv2.rectangle(img, (rx0, ry0), (rx1, ry1), color, 4 if is_primary else 2, cv2.LINE_AA)
        draw_label(img, rx0, ry0, label, color)
    cv2.addWeighted(overlay, 0.30, img, 0.70, 0, img)
    return img


def draw_ok_banner(img):
    h, w = img.shape[:2]
    color = COLORS.get("OK", (0, 180, 0))
    cv2.rectangle(img, (0, 0), (w - 1, h - 1), color, 8)
    draw_label(img, 15, 40, "OK - no defect", color)
    return img
