"""Lint Excalidraw JSON for structural integrity, skill-policy compliance, and likely visual defects.

Stdlib only — safe to run with plain python3, no venv needed.

Usage:
    python3 lint_excalidraw.py <file.excalidraw> [<file2> ...]
    python3 lint_excalidraw.py --errors-only <file.excalidraw>   # policy/geometry warnings don't affect exit code
    python3 lint_excalidraw.py --hook                            # Claude Code PostToolUse hook mode (reads JSON from stdin)

Exit codes:
    0  clean (or, with --errors-only, warnings only)
    2  findings reported (printed to stderr)

Severities:
    ERROR — file is structurally broken (dangling bindings, duplicate IDs, bad JSON).
            The renderer refuses to render these.
    WARN  — violates skill policy (palette, opacity, fontFamily) or likely visual
            defect (text overflow, overlaps, stray arrow endpoints). Heuristic;
            judge against the rendered PNG.

Color palette: allowed colors are parsed from color-palette.md (all hex codes
mentioned there, plus "transparent"). Edit the palette file and the linter
follows automatically.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

KNOWN_ELEMENT_TYPES = {
    "rectangle", "ellipse", "diamond", "text", "arrow", "line",
    "freedraw", "image", "frame", "embeddable", "magicframe",
}
LINEAR_TYPES = {"arrow", "line", "freedraw"}
# Types that can host bound text via a text element's containerId
CONTAINER_TYPES = {"rectangle", "ellipse", "diamond", "arrow", "image", "embeddable"}
# Types with a meaningful axis-aligned bounding box for overlap checks
BOXY_TYPES = {"rectangle", "ellipse", "diamond", "text", "image"}

KNOWN_FILL_STYLES = {"solid", "hachure", "cross-hatch", "zigzag"}
KNOWN_STROKE_STYLES = {"solid", "dashed", "dotted"}

# Monospace (fontFamily 3, the skill default) is ~0.6em per character.
CHAR_WIDTH_FACTOR = 0.6
DEFAULT_LINE_HEIGHT = 1.25
BOUND_TEXT_PADDING = 5  # excalidraw's padding inside containers

CONTAINER_RATIO_LIMIT = 0.30  # skill rule: <30% of text elements in containers
CONTAINER_RATIO_MIN_TEXTS = 6  # ratio rule is meaningless on tiny diagrams
ARROW_BINDING_MAX_GAP = 40    # px an arrow endpoint may sit from its bound element
OVERLAP_TOLERANCE = 4         # px of intersection ignored as touching, not overlapping
ORTHOGONAL_TOLERANCE = 2      # px of drift still counted as horizontal/vertical
ARROWHEAD_MIN_FINAL_SEGMENT = 40  # px; skill targets >=60, warn when clearly undersized


@dataclass
class Finding:
    severity: str  # "ERROR" | "WARN"
    element_id: str | None
    message: str

    def format(self) -> str:
        loc = f"[{self.element_id}] " if self.element_id else ""
        return f"{self.severity} {loc}{self.message}"


def load_palette() -> set[str] | None:
    """Parse allowed colors from color-palette.md (same dir as this script).

    Returns None if the palette file is missing (color checks are skipped).
    """
    palette_path = Path(__file__).parent / "color-palette.md"
    if not palette_path.exists():
        return None
    text = palette_path.read_text(encoding="utf-8")
    colors = {c.lower() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", text)}
    colors.add("transparent")
    return colors


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def bbox(el: dict) -> tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) for an element."""
    x, y = el.get("x", 0), el.get("y", 0)
    if el.get("type") in LINEAR_TYPES and el.get("points"):
        xs = [x + p[0] for p in el["points"]]
        ys = [y + p[1] for p in el["points"]]
        return (min(xs), min(ys), max(xs), max(ys))
    w, h = abs(el.get("width", 0)), abs(el.get("height", 0))
    return (x, y, x + w, y + h)


def boxes_intersect(a: tuple, b: tuple, tolerance: float) -> bool:
    return (
        a[0] + tolerance < b[2] and b[0] + tolerance < a[2]
        and a[1] + tolerance < b[3] and b[1] + tolerance < a[3]
    )


def box_contains(outer: tuple, inner: tuple, slack: float = 2.0) -> bool:
    return (
        outer[0] - slack <= inner[0] and outer[1] - slack <= inner[1]
        and outer[2] + slack >= inner[2] and outer[3] + slack >= inner[3]
    )


def point_to_box_distance(px: float, py: float, box: tuple) -> float:
    dx = max(box[0] - px, 0, px - box[2])
    dy = max(box[1] - py, 0, py - box[3])
    return math.hypot(dx, dy)


def estimated_text_size(text: str, font_size: float, max_width: float | None,
                        line_height: float) -> tuple[float, float]:
    """Estimate rendered (width, height) of text, wrapping at max_width if given."""
    char_w = font_size * CHAR_WIDTH_FACTOR
    lines = text.split("\n")
    if max_width and max_width > char_w:
        chars_per_line = max(1, int(max_width / char_w))
        wrapped = 0
        for line in lines:
            wrapped += max(1, math.ceil(len(line) / chars_per_line)) if line else 1
        n_lines = wrapped
        width = min(max((len(l) for l in lines), default=0) * char_w, max_width)
    else:
        n_lines = len(lines)
        width = max((len(l) for l in lines), default=0) * char_w
    return (width, n_lines * font_size * line_height)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def lint_data(data: dict, palette: set[str] | None) -> list[Finding]:
    findings: list[Finding] = []
    err = lambda eid, msg: findings.append(Finding("ERROR", eid, msg))
    warn = lambda eid, msg: findings.append(Finding("WARN", eid, msg))

    # --- wrapper ---
    if data.get("type") != "excalidraw":
        err(None, f"top-level 'type' must be 'excalidraw', got {data.get('type')!r}")
    raw_elements = data.get("elements")
    if not isinstance(raw_elements, list):
        err(None, "'elements' is missing or not an array")
        return findings
    if not raw_elements:
        err(None, "'elements' array is empty — nothing to render")
        return findings

    bg = data.get("appState", {}).get("viewBackgroundColor", "#ffffff")
    if isinstance(bg, str) and bg.lower() not in ("#ffffff", "transparent"):
        warn(None, f"appState.viewBackgroundColor is {bg}; palette specifies #ffffff")

    elements = [e for e in raw_elements if isinstance(e, dict) and not e.get("isDeleted")]

    # --- ids & required fields ---
    by_id: dict[str, dict] = {}
    for i, el in enumerate(elements):
        eid = el.get("id")
        if not eid or not isinstance(eid, str):
            err(None, f"element at index {i} (type={el.get('type')!r}) has no string 'id'")
            continue
        if eid in by_id:
            err(eid, "duplicate element id")
            continue
        by_id[eid] = el

    for eid, el in by_id.items():
        etype = el.get("type")
        if etype not in KNOWN_ELEMENT_TYPES:
            err(eid, f"unknown element type {etype!r}")
            continue
        for field in ("x", "y", "width", "height"):
            if not isinstance(el.get(field), (int, float)):
                err(eid, f"'{field}' is missing or not a number")
        if etype in LINEAR_TYPES:
            pts = el.get("points")
            if not isinstance(pts, list) or len(pts) < 2:
                err(eid, f"{etype} needs a 'points' array with at least 2 points")
        if etype == "text":
            if not isinstance(el.get("text"), str):
                err(eid, "text element missing 'text' string")
            elif el.get("originalText") is not None and el["text"] != el["originalText"]:
                warn(eid, "'text' and 'originalText' differ — they should match in hand-written JSON")

    # --- reference integrity & reciprocity ---
    for eid, el in by_id.items():
        # containerId → container exists, is containable, and points back
        cid = el.get("containerId")
        if cid is not None:
            container = by_id.get(cid)
            if container is None:
                err(eid, f"containerId '{cid}' references a nonexistent element")
            else:
                if container.get("type") not in CONTAINER_TYPES:
                    err(eid, f"containerId '{cid}' points at a {container.get('type')!r}, which cannot contain text")
                back = container.get("boundElements") or []
                if not any(isinstance(b, dict) and b.get("id") == eid for b in back):
                    err(eid, f"container '{cid}' does not list this text in its boundElements (binding must be reciprocal)")

        # boundElements → targets exist and point back
        for b in el.get("boundElements") or []:
            if not isinstance(b, dict):
                err(eid, f"boundElements entry is not an object: {b!r}")
                continue
            bid = b.get("id")
            target = by_id.get(bid)
            if target is None:
                err(eid, f"boundElements references nonexistent element '{bid}'")
                continue
            ttype = target.get("type")
            if b.get("type") != ttype:
                warn(eid, f"boundElements entry for '{bid}' declares type {b.get('type')!r} but element is {ttype!r}")
            if ttype == "text" and target.get("containerId") != eid:
                err(eid, f"boundElements lists text '{bid}' but that text's containerId is {target.get('containerId')!r} (binding must be reciprocal)")
            if ttype == "arrow":
                sb, ebind = target.get("startBinding"), target.get("endBinding")
                bound_ids = {x.get("elementId") for x in (sb, ebind) if isinstance(x, dict)}
                if eid not in bound_ids:
                    err(eid, f"boundElements lists arrow '{bid}' but that arrow's start/endBinding does not reference this element")

        # arrow bindings → targets exist and point back
        if el.get("type") == "arrow":
            for key in ("startBinding", "endBinding"):
                binding = el.get(key)
                if binding is None:
                    continue
                if not isinstance(binding, dict) or not binding.get("elementId"):
                    err(eid, f"{key} is malformed: {binding!r}")
                    continue
                tid = binding["elementId"]
                target = by_id.get(tid)
                if target is None:
                    err(eid, f"{key} references nonexistent element '{tid}'")
                    continue
                back = target.get("boundElements") or []
                if not any(isinstance(b, dict) and b.get("id") == eid for b in back):
                    err(eid, f"{key} targets '{tid}' but '{tid}' does not list this arrow in its boundElements (binding must be reciprocal)")

        fid = el.get("frameId")
        if fid is not None and fid not in by_id:
            err(eid, f"frameId '{fid}' references a nonexistent element")

    # --- skill policy ---
    for eid, el in by_id.items():
        etype = el.get("type")
        if el.get("opacity", 100) != 100:
            warn(eid, f"opacity is {el.get('opacity')}; skill requires 100 (use color/size for hierarchy)")
        if etype == "text" and el.get("fontFamily") != 3:
            warn(eid, f"fontFamily is {el.get('fontFamily')}; skill requires 3")
        if el.get("roughness", 0) != 0:
            warn(eid, f"roughness is {el.get('roughness')}; skill default is 0 (hand-drawn style only if requested)")
        fs = el.get("fillStyle")
        if fs is not None and fs not in KNOWN_FILL_STYLES:
            warn(eid, f"unknown fillStyle {fs!r}")
        ss = el.get("strokeStyle")
        if ss is not None and ss not in KNOWN_STROKE_STYLES:
            warn(eid, f"unknown strokeStyle {ss!r}")

        if palette is not None:
            for key in ("strokeColor", "backgroundColor"):
                color = el.get(key)
                if isinstance(color, str) and color.lower() not in palette:
                    warn(eid, f"{key} {color} is not in color-palette.md — do not invent new colors")

    # container ratio
    texts = [el for el in by_id.values() if el.get("type") == "text"]
    contained = [el for el in texts if el.get("containerId")]
    if len(texts) >= CONTAINER_RATIO_MIN_TEXTS and len(contained) / len(texts) > CONTAINER_RATIO_LIMIT:
        warn(None, f"{len(contained)}/{len(texts)} text elements are inside containers "
                   f"(>{CONTAINER_RATIO_LIMIT:.0%}) — skill prefers free-floating text; remove containers that carry no meaning")

    # --- geometry heuristics ---
    # text overflow inside containers (bound text wraps to width, overflows vertically)
    for el in texts:
        cid = el.get("containerId")
        container = by_id.get(cid) if cid else None
        font_size = el.get("fontSize", 16)
        line_height = el.get("lineHeight", DEFAULT_LINE_HEIGHT)
        text = el.get("text") or ""
        if container and isinstance(container.get("width"), (int, float)):
            inner_w = abs(container["width"]) - 2 * BOUND_TEXT_PADDING
            inner_h = abs(container.get("height", 0)) - 2 * BOUND_TEXT_PADDING
            est_w, est_h = estimated_text_size(text, font_size, inner_w, line_height)
            if est_h > inner_h + 2:
                warn(el["id"], f"text likely overflows container '{cid}': needs ~{est_h:.0f}px height, "
                               f"container offers {inner_h:.0f}px — widen or heighten the container, or shorten the text")
            longest_word = max((len(w) for w in re.split(r"\s+", text)), default=0)
            if longest_word * font_size * CHAR_WIDTH_FACTOR > inner_w + 2:
                warn(el["id"], f"a word in this text is wider (~{longest_word * font_size * CHAR_WIDTH_FACTOR:.0f}px) "
                               f"than container '{cid}' ({inner_w:.0f}px inner width)")
        elif not container and isinstance(el.get("width"), (int, float)):
            est_w, _ = estimated_text_size(text, font_size, None, line_height)
            declared = abs(el["width"])
            if est_w > 0 and declared > 0:
                deviation = abs(est_w - declared) / max(est_w, declared)
                if deviation > 0.30 and abs(est_w - declared) > 40:
                    warn(el["id"], f"declared width {declared:.0f}px vs ~{est_w:.0f}px estimated for the text — "
                                   f"misdeclared sizes break alignment and overlap checks")

    # partial overlaps between boxy elements (full containment = section pattern, allowed)
    boxy = [el for el in by_id.values()
            if el.get("type") in BOXY_TYPES
            and not el.get("angle")
            and all(isinstance(el.get(f), (int, float)) for f in ("x", "y", "width", "height"))]
    for i in range(len(boxy)):
        for j in range(i + 1, len(boxy)):
            a, b = boxy[i], boxy[j]
            if set(a.get("groupIds") or []) & set(b.get("groupIds") or []):
                continue
            if a.get("containerId") == b["id"] or b.get("containerId") == a["id"]:
                continue
            ba, bb = bbox(a), bbox(b)
            if not boxes_intersect(ba, bb, OVERLAP_TOLERANCE):
                continue
            if box_contains(ba, bb) or box_contains(bb, ba):
                continue  # nesting is a legitimate section/grouping pattern
            warn(a["id"], f"partially overlaps '{b['id']}' ({a.get('type')} vs {b.get('type')}) — "
                          f"reposition so they either separate or nest cleanly")

    # orthogonal routing: arrows must run horizontal/vertical with 90-degree bends,
    # and the final segment must be long enough for a full-size arrowhead
    for eid, el in by_id.items():
        if el.get("type") != "arrow":
            continue
        pts = el.get("points")
        if not isinstance(pts, list) or len(pts) < 2:
            continue
        for i in range(len(pts) - 1):
            dx = abs(pts[i + 1][0] - pts[i][0])
            dy = abs(pts[i + 1][1] - pts[i][1])
            if dx > ORTHOGONAL_TOLERANCE and dy > ORTHOGONAL_TOLERANCE:
                warn(eid, f"segment {i + 1} is diagonal ({dx:.0f}x{dy:.0f}px) — skill requires "
                          f"orthogonal routing: horizontal/vertical segments with 90-degree bends")
        fdx = pts[-1][0] - pts[-2][0]
        fdy = pts[-1][1] - pts[-2][1]
        final_len = math.hypot(fdx, fdy)
        if final_len < ARROWHEAD_MIN_FINAL_SEGMENT:
            warn(eid, f"final segment is only {final_len:.0f}px — the arrowhead will render "
                      f"undersized; aim for >=60px on the final approach")

    # arrow endpoints far from their bound elements
    for eid, el in by_id.items():
        if el.get("type") != "arrow" or not el.get("points"):
            continue
        x, y = el.get("x", 0), el.get("y", 0)
        for key, point in (("startBinding", el["points"][0]), ("endBinding", el["points"][-1])):
            binding = el.get(key)
            if not isinstance(binding, dict):
                continue
            target = by_id.get(binding.get("elementId"))
            if target is None:
                continue  # already an ERROR above
            dist = point_to_box_distance(x + point[0], y + point[1], bbox(target))
            if dist > ARROW_BINDING_MAX_GAP:
                warn(eid, f"{key} targets '{binding['elementId']}' but the arrow endpoint is ~{dist:.0f}px away "
                          f"from it — adjust the arrow's x/y/points to land on the element")

    return findings


def lint_file(path: Path, palette: set[str] | None) -> list[Finding]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        return [Finding("ERROR", None, f"cannot read file: {e}")]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return [Finding("ERROR", None, f"invalid JSON: {e}")]
    if not isinstance(data, dict):
        return [Finding("ERROR", None, "top level must be a JSON object")]
    return lint_data(data, palette)


def report(path: Path, findings: list[Finding], stream) -> None:
    errors = sum(1 for f in findings if f.severity == "ERROR")
    warns = len(findings) - errors
    print(f"{path}: {errors} error(s), {warns} warning(s)", file=stream)
    for f in findings:
        print(f"  {f.format()}", file=stream)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lint Excalidraw JSON files")
    parser.add_argument("files", nargs="*", type=Path, help=".excalidraw files to lint")
    parser.add_argument("--errors-only", action="store_true",
                        help="only structural ERRORs affect the exit code (warnings still printed)")
    parser.add_argument("--hook", action="store_true",
                        help="Claude Code PostToolUse hook mode: read tool payload JSON from stdin")
    args = parser.parse_args()

    if args.hook:
        try:
            payload = json.load(sys.stdin)
            file_path = payload.get("tool_input", {}).get("file_path", "")
        except (json.JSONDecodeError, AttributeError):
            sys.exit(0)  # not a payload we understand; stay silent
        if not file_path.endswith(".excalidraw"):
            sys.exit(0)
        path = Path(file_path)
        if not path.exists():
            sys.exit(0)
        findings = lint_file(path, load_palette())
        if findings:
            report(path, findings, sys.stderr)
            print("Fix ERRORs before rendering; treat WARNs as likely defects and "
                  "verify against the rendered PNG.", file=sys.stderr)
            sys.exit(2)
        sys.exit(0)

    if not args.files:
        parser.error("no input files (or use --hook)")

    palette = load_palette()
    if palette is None:
        print("note: color-palette.md not found — color checks skipped", file=sys.stderr)

    exit_code = 0
    for path in args.files:
        if not path.exists():
            print(f"{path}: file not found", file=sys.stderr)
            exit_code = 2
            continue
        findings = lint_file(path, palette)
        if not findings:
            print(f"{path}: clean")
            continue
        report(path, findings, sys.stderr)
        if any(f.severity == "ERROR" for f in findings) or not args.errors_only:
            exit_code = 2
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
