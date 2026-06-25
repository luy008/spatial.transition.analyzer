"""계단 기하 계산 — 범용."""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List, Tuple

from shapely.geometry import LineString, Point


@dataclass(frozen=True)
class StairMetrics:
    route_id: str
    rise_m: float
    plan_distance_m: float
    dist_3d_m: float
    n_treads: int
    riser_height_m: float
    tread_depth_m: float
    stair_angle_deg: float
    slope_percent: float
    est_time_s: float = 0.0


def calculate_stair_metrics(route_id: str, centerline: LineString,
                             rise_m: float, width_m: float = 1.5,
                             riser_m: float = 0.15, tread_m: float = 0.30,
                             speed_mps: float = 0.5) -> StairMetrics:
    plan_dist = centerline.length
    n_treads = max(1, round(rise_m / riser_m))
    actual_riser = rise_m / n_treads
    dist_3d = math.hypot(plan_dist, rise_m)
    angle = math.degrees(math.atan(rise_m / plan_dist)) if plan_dist > 0 else 90.0
    slope = (rise_m / plan_dist * 100) if plan_dist > 0 else 0
    return StairMetrics(
        route_id=route_id, rise_m=rise_m, plan_distance_m=plan_dist,
        dist_3d_m=dist_3d, n_treads=n_treads, riser_height_m=actual_riser,
        tread_depth_m=tread_m, stair_angle_deg=angle,
        slope_percent=slope, est_time_s=dist_3d / speed_mps)


def sample_stair_points(centerline: LineString, rise_m: float,
                         n: int = 11) -> List[Tuple[float, float, float]]:
    result = []
    for i in range(n):
        frac = i / (n - 1) if n > 1 else 0.0
        pt = centerline.interpolate(frac, normalized=True)
        result.append((pt.x, pt.y, rise_m * frac))
    return result
