# Color Palette & Brand Style — Okabe-Ito

**This is the single source of truth for all colors and brand-specific styles.** To customize diagrams for your own
brand, edit this file — everything else in the skill is universal.

This palette is built on the **Okabe-Ito colorblind-safe palette** (Okabe & Ito, 2008). The eight base hues are
distinguishable under the most common forms of color vision deficiency. Every color in a diagram must be an Okabe-Ito
base hue or a tint/shade derived from one (rules below).

---

## Base Palette (Okabe-Ito)

| Name | Hex |
|------|-----|
| Black | `#000000` |
| Orange | `#E69F00` |
| Sky Blue | `#56B4E9` |
| Bluish Green | `#009E73` |
| Yellow | `#F0E442` |
| Blue | `#0072B2` |
| Vermillion | `#D55E00` |
| Reddish Purple | `#CC79A7` |
| Gray (extended) | `#999999` |

**Derivation rules** (when a lighter fill or darker stroke is needed):

- **Fill tint** = base hue mixed 80% toward white (keeps the hue identity, gives a light fill)
- **Stroke shade** = base hue darkened ~40% (only when the base hue is too light to work as a stroke, e.g. Yellow)

---

## Shape Colors (Semantic)

Colors encode meaning, not decoration. Each semantic purpose has a fill/stroke pair. The hue carries the meaning; fills
are light tints of the stroke's hue.

| Semantic Purpose | Fill | Stroke | Okabe-Ito Hue |
|------------------|------|--------|---------------|
| Primary/Neutral | `#CCE3F0` | `#0072B2` | Blue |
| Secondary | `#DDF0FB` | `#56B4E9` | Sky Blue |
| Tertiary | `#EEF8FD` | `#56B4E9` | Sky Blue (lighter fill) |
| Start/Trigger | `#FAECCC` | `#E69F00` | Orange |
| End/Success | `#CCECE3` | `#009E73` | Bluish Green |
| Decision | `#FCFAD9` | `#968E29` | Yellow (stroke darkened — pure yellow is too light for a stroke) |
| Warning/Reset | `#F7DFCC` | `#D55E00` | Vermillion |
| Error | `#F2C7A3` | `#A34800` | Vermillion (darkened — stronger than Warning) |
| AI/LLM | `#F5E4ED` | `#CC79A7` | Reddish Purple |
| Inactive/Disabled | `#E6E6E6` | `#999999` (use dashed stroke) | Gray |

**Rule**: Always pair a darker stroke with a lighter fill for contrast.

**Note**: Warning and Error intentionally share the vermillion hue family (Okabe-Ito has one red); Error uses the
darker, more saturated pair.

---

## Text Colors (Hierarchy)

Use color on free-floating text to create visual hierarchy without containers.

| Level | Color | Use For |
|-------|-------|---------|
| Title | `#00476F` (dark Blue shade) | Section headings, major labels |
| Subtitle | `#0072B2` (Blue) | Subheadings, secondary labels |
| Body/Detail | `#595959` (dark Gray shade) | Descriptions, annotations, metadata |
| On light fills | `#000000` (Black) | Text inside light-colored shapes |
| On dark fills | `#FFFFFF` | Text inside dark-colored shapes |

---

## Evidence Artifact Colors

Used for code snippets, data examples, and other concrete evidence inside technical diagrams.

| Artifact | Background | Text Color |
|----------|-----------|------------|
| Code snippet | `#262626` (near-black) | Syntax-colored, drawn from Okabe-Ito hues (Sky Blue, Orange, Bluish Green, Yellow) |
| JSON/data example | `#262626` | `#56B4E9` (Sky Blue — readable on dark) |

---

## Default Stroke & Line Colors

| Element | Color |
|---------|-------|
| Arrows | Use the stroke color of the source element's semantic purpose |
| Structural lines (dividers, trees, timelines) | Black (`#000000`) or Gray (`#999999`) |
| Marker dots (fill + stroke) | Blue (`#0072B2`) |

---

## Background

| Property | Value |
|----------|-------|
| Canvas background | `#ffffff` |
