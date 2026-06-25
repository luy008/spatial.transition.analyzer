# DIAGRAM DEGRADATION AUDIT

**Date:** 2026-06-25  
**Compared:** `urban_ramp_analysis/diagram_final.py` (Old CLI) vs `core/diagram_renderer.py` (Current Webapp)

---

## Root Cause 1 — Missing Floor Plan Walls for S1/S2/S3

**Old CLI (`diagram_final.py`):**  
Calls `get_level_obstacles(raw_entities, levels[lv], cfg)` for each route's *specific* floor level.  
Every panel (S1/S2/S3/R1) shows real DXF walls filtered to that level's spatial window.

**Current Webapp (`diagram_renderer.py`):**  
`_build_routes_data()` in `pages/03_diagram_export.py` sets `obstacles = []` for S1/S2/S3.  
Only `obstacles_R1` (L05 walls) is passed, and only for R1.  
**Result:** S1/S2/S3 panels are completely empty floor plans — just the route line on a blank background.

---

## Root Cause 2 — Straight-Line Centerlines Instead of Real Arcs

**Old CLI:**  
Calls `route_dense_points(route)` which interpolates 200+ points along the arc using  
`arc.center`, `arc.radius`, `arc.start_angle_deg`, `arc.end_angle_deg`, `arc.ccw`.  
Result: smooth circular arc paths matching the actual architectural geometry.

**Current Webapp:**  
Uses `control_points` directly from `routes.json` — typically 2–5 waypoints.  
Matplotlib draws straight line segments between waypoints.  
**Result:** S1/S2/S3 appear as angled straight segments. R1 (360° circle) is a crude polygon.

---

## Root Cause 3 — Isovist Polygons Not Rendered

**Old CLI:**  
`scene_iso["{rid}_{progress}"]` contains pre-computed Shapely Polygon objects.  
`_draw_scene()` fills isovist area with translucent color overlaid on real floor plan.

**Current Webapp:**  
`IsovistResult.polygon_coords` contains the isovist polygon coordinates, but only for R1.  
`_draw_isovist_band()` is called but uses `previous_visible`/`courtyard_visible`/`next_visible`  
boolean flags — the actual polygon is never rendered on the floor plan.  
The isovist fill code path (`ax.fill(pxs, pys, ...)`) is present but `iso_results` is empty for S1/S2/S3.  
**Result:** No isovist polygons visible on any panel.

---

## Root Cause 4 — Visibility Bands Always Empty for S1/S2/S3

**Old CLI:**  
`sample_points[rid]` is pre-computed for all 4 routes with visibility flags per observation point.

**Current Webapp:**  
Isovist analysis is run only for R1 in `pages/02_verify_analyze.py`.  
`iso_results = []` for S1/S2/S3 → `_draw_isovist_band()` exits immediately → blank band panels.  
**Result:** Visibility bands (PREVIOUS/COURTYARD/NEXT) are empty rectangles for S1/S2/S3.

---

## Root Cause 5 — No Courtyard Mask in Correct Position

**Old CLI:**  
`_draw_scene()` uses the actual courtyard center `(cm[0], cm[1])` from `level_info["courtyard_center"]`  
to position the void mask and curtain wall ring at the real geographic location.

**Current Webapp:**  
Uses `(0, 0)` as the courtyard center (because all geometry is translated by subtracting `(cx, cy)`).  
The courtyard circle is drawn at the origin, but obstacles are also translated the same way,  
so the mask works — but only when obstacles are present (which they are only for R1).  
For S1/S2/S3 with no obstacles, the courtyard circle floats at origin with no walls around it.

---

## Root Cause 6 — Empty Overview Panel

**Old CLI:**  
`_draw_overview()` uses `route_dense_points()` for real arc geometry and projects it in  
pseudo-axonometric 3D view, showing the stacked circulation clearly.

**Current Webapp:**  
No overview panel is rendered. The current layout has 4 equal-width panels in a row  
with no vertical overview. The right 28% is used for CRITICAL READING only.  
**Result:** No vertical circulation overview diagram.

---

## Root Cause 7 — R1 Panel Shows No Observation Points / Sub-Frames

**Old CLI:**  
R1 panel shows 3 observation points (0%/50%/100%) with their isovist polygons and arrow annotations.  
Sub-frames (START/MID/END) are distinct visual zones within R1's larger panel.

**Current Webapp:**  
R1 panel has the same square extent as S1/S2/S3.  
Observation points are not rendered (no circle marker for each observation position).  
**Result:** R1 is just a circle arc on a wall background — no spatial sequence visible.

---

## Root Cause 8 — No Scale Lock Between Panels

**Old CLI:**  
`_draw_core_sequence()` computes world extents from dense arc points for all routes,  
then applies a shared transform `_make_fit(world_box, dst_box)` keeping equal scale.

**Current Webapp:**  
`get_common_panel_extent()` exists and is called, but because control_points are just 2–5  
waypoints, the computed extent often differs from the real arc extent.  
For R1 (360° circle) the correct extent is `radius × 2 + padding`, but with 2 control points  
the extent collapses to near zero, forcing each panel to autoscale independently.

---

## Fix Summary

The new `core/architectural_diagram_renderer.py` addresses all 8 causes by:
1. Extracting per-level walls directly from `dxf_entities` using `levels[lv]["window"]` as spatial filter
2. Building dense arc points from `routes[rid]["arc"]` sub-object (200 interpolated points)
3. Rendering isovist polygon overlays on real floor plans (R1 only; S1/S2/S3 show walls only)
4. Computing visibility bands for all routes (S1/S2/S3 use simplified heuristic when no isovist available)
5. Drawing courtyard void mask at correct absolute position before translating to panel space
6. Restoring vertical overview panel with pseudo-axonometric 3D view
7. Adding 3 R1 sub-frame observation points (START/MID/END) with real isovist positions
8. Computing shared panel extent from dense arc points to lock scale across all panels
