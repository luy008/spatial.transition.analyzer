"""Isovist 분석 — 범용 (ray casting)."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

import numpy as np
from shapely.geometry import LineString, Point, Polygon, MultiPolygon
from shapely.ops import unary_union

from core.models import IsovistResult


@dataclass
class IsovistParams:
    n_rays: int = 720
    max_dist_m: float = 30.0
    min_area_m2: float = 1.0
    courtyard_visible_threshold: float = 0.05


def _cast_rays(observer: Point, obstacles: List[LineString],
               n_rays: int, max_dist: float) -> List[Point]:
    endpoints = []
    angles = np.linspace(0, 2 * math.pi, n_rays, endpoint=False)
    for angle in angles:
        dx, dy = math.cos(angle) * max_dist, math.sin(angle) * max_dist
        ray = LineString([observer, (observer.x + dx, observer.y + dy)])
        hit_dist = max_dist
        for obs in obstacles:
            try:
                inter = ray.intersection(obs)
                if inter.is_empty:
                    continue
                if inter.geom_type == "Point":
                    d = observer.distance(inter)
                    if d < hit_dist:
                        hit_dist = d
                elif inter.geom_type in ("MultiPoint", "GeometryCollection"):
                    for g in inter.geoms:
                        if g.geom_type == "Point":
                            d = observer.distance(g)
                            if d < hit_dist:
                                hit_dist = d
            except Exception:
                pass
        ang_hit = angle
        endpoints.append(Point(observer.x + math.cos(ang_hit) * hit_dist,
                               observer.y + math.sin(ang_hit) * hit_dist))
    return endpoints


def compute_isovist(observer: Point, obstacles: List[LineString],
                    params: IsovistParams,
                    prev_space: Optional[Polygon] = None,
                    court_circle: Optional[Polygon] = None,
                    next_space: Optional[Polygon] = None) -> IsovistResult:
    endpoints = _cast_rays(observer, obstacles, params.n_rays, params.max_dist_m)
    coords = [(observer.x, observer.y)] + [(p.x, p.y) for p in endpoints]
    try:
        poly = Polygon(coords).buffer(0)
    except Exception:
        poly = Polygon()

    area = poly.area if not poly.is_empty else 0.0
    perim = poly.length if not poly.is_empty else 0.0
    dists = [observer.distance(p) for p in endpoints]
    mean_d = float(np.mean(dists)) if dists else 0.0
    max_d = float(np.max(dists)) if dists else 0.0

    def space_visible(sp: Optional[Polygon]) -> bool:
        if sp is None or sp.is_empty or poly.is_empty:
            return False
        try:
            inter = poly.intersection(sp)
            return inter.area > params.courtyard_visible_threshold
        except Exception:
            return False

    return IsovistResult(
        progress_percent=0.0,
        area_m2=area, perimeter_m=perim,
        mean_dist_m=mean_d, max_dist_m=max_d,
        previous_visible=space_visible(prev_space),
        courtyard_visible=space_visible(court_circle),
        next_visible=space_visible(next_space),
        polygon_coords=list(poly.exterior.coords) if not poly.is_empty else [])


def compute_route_isovists(obs_points: List[Tuple[float, float, float]],
                            obstacles: List[LineString],
                            params: IsovistParams,
                            prev_space: Optional[Polygon] = None,
                            court_circle: Optional[Polygon] = None,
                            next_space: Optional[Polygon] = None) -> List[IsovistResult]:
    results = []
    n = len(obs_points)
    for i, (x, y, z) in enumerate(obs_points):
        r = compute_isovist(Point(x, y), obstacles, params, prev_space, court_circle, next_space)
        r.progress_percent = (i / (n - 1) * 100) if n > 1 else 0.0
        results.append(r)
    return results


def compute_visibility_events(results: List[IsovistResult]) -> dict:
    n = len(results)
    if n == 0:
        return {}
    court_dur = sum(1 for r in results if r.courtyard_visible) / n * 100
    next_first = None
    prev_last = None
    for r in results:
        if r.next_visible and next_first is None:
            next_first = r.progress_percent
        if r.previous_visible:
            prev_last = r.progress_percent
    return {
        "courtyard_visibility_duration_percent": court_dur,
        "next_space_first_visible_percent": next_first,
        "previous_space_last_visible_percent": prev_last,
        "courtyard_visible_count": sum(1 for r in results if r.courtyard_visible),
        "next_visible_count": sum(1 for r in results if r.next_visible),
    }
