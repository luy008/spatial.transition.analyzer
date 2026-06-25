"""단계적 가시성 상태 분류 (NOT_VISIBLE / GLIMPSE / PARTIAL / DOMINANT)."""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Optional
from shapely.geometry import Polygon, Point


VISIBILITY_STATES = ["NOT_VISIBLE", "GLIMPSE", "PARTIAL", "DOMINANT"]


@dataclass
class VisibilityDetail:
    state: str
    visible_ratio: float = 0.0
    angular_width_deg: float = 0.0
    nearest_dist_m: float = 0.0
    area_m2: float = 0.0


def classify_visibility_state(
    visible_ratio: float,
    angular_width_deg: float,
    glimpse_ratio: float = 0.05,
    partial_ratio: float = 0.30,
    glimpse_angular_deg: float = 5.0,
    partial_angular_deg: float = 25.0,
) -> str:
    if visible_ratio <= 0.0:
        return "NOT_VISIBLE"
    if visible_ratio < glimpse_ratio or angular_width_deg < glimpse_angular_deg:
        return "GLIMPSE"
    if visible_ratio < partial_ratio or angular_width_deg < partial_angular_deg:
        return "PARTIAL"
    return "DOMINANT"


def compute_visibility_detail(
    isovist_poly: Optional[Polygon],
    target_poly: Optional[Polygon],
    observer: Point,
    thresholds: Optional[dict] = None,
) -> VisibilityDetail:
    """Isovist polygon과 대상 polygon의 교차로 상세 가시성 계산."""
    th = thresholds or {}
    if isovist_poly is None or isovist_poly.is_empty:
        return VisibilityDetail("NOT_VISIBLE")
    if target_poly is None or target_poly.is_empty:
        return VisibilityDetail("NOT_VISIBLE")
    try:
        inter = isovist_poly.intersection(target_poly)
        if inter.is_empty:
            return VisibilityDetail("NOT_VISIBLE")
        visible_area = inter.area
        target_area = target_poly.area
        ratio = visible_area / target_area if target_area > 0 else 0.0
        # 각도폭 계산: 교차 polygon의 관찰자 기준 각도 범위
        angular_width = 0.0
        try:
            if inter.geom_type in ("Polygon", "MultiPolygon"):
                coords = list(inter.exterior.coords) if inter.geom_type == "Polygon" else []
                if coords:
                    angles = [math.degrees(math.atan2(y - observer.y, x - observer.x)) % 360
                              for x, y in coords]
                    angles.sort()
                    if angles:
                        span = max(angles) - min(angles)
                        angular_width = min(span, 360 - span)
        except Exception:
            pass
        # 최근거리
        nearest = observer.distance(inter)
        state = classify_visibility_state(
            ratio, angular_width,
            th.get("glimpse_ratio", 0.05), th.get("partial_ratio", 0.30),
            th.get("glimpse_angular_deg", 5.0), th.get("partial_angular_deg", 25.0),
        )
        return VisibilityDetail(
            state=state,
            visible_ratio=ratio,
            angular_width_deg=angular_width,
            nearest_dist_m=nearest,
            area_m2=visible_area,
        )
    except Exception:
        return VisibilityDetail("NOT_VISIBLE")
