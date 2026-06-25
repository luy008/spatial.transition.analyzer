"""Movement Cost + Directional Transformation 분석."""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional
from shapely.geometry import LineString


@dataclass
class MovementCostResult:
    route_id: str
    plan_distance_m: float
    dist_3d_m: float
    rise_m: float
    slope_percent: float
    slope_ratio: float
    slope_angle_deg: float
    dist_per_rise_m: float
    est_time_s: float
    speed_mps: float


@dataclass
class DirectionalResult:
    route_id: str
    cumulative_rotation_deg: float
    curve_ratio: float
    straight_ratio: float
    n_direction_changes: int
    start_bearing_deg: float
    end_bearing_deg: float
    net_direction_change_deg: float
    tortuosity: float


def compute_movement_cost(
    route_id: str,
    centerline: LineString,
    rise_m: float,
    speed_mps: float = 0.8,
) -> MovementCostResult:
    plan = centerline.length
    dist3d = math.hypot(plan, rise_m)
    slope_dec = rise_m / plan if plan > 0 else 0
    return MovementCostResult(
        route_id=route_id,
        plan_distance_m=plan,
        dist_3d_m=dist3d,
        rise_m=rise_m,
        slope_percent=slope_dec * 100,
        slope_ratio=plan / rise_m if rise_m > 0 else 0,
        slope_angle_deg=math.degrees(math.atan(slope_dec)) if slope_dec > 0 else 0,
        dist_per_rise_m=plan / rise_m if rise_m > 0 else 0,
        est_time_s=dist3d / speed_mps if speed_mps > 0 else 0,
        speed_mps=speed_mps,
    )


def compute_directional_transformation(
    route_id: str,
    centerline: LineString,
    segment_threshold_deg: float = 15.0,
) -> DirectionalResult:
    coords = list(centerline.coords)
    if len(coords) < 2:
        return DirectionalResult(route_id, 0, 0, 1, 0, 0, 0, 0, 1.0)

    bearings = []
    for i in range(1, len(coords)):
        dx = coords[i][0] - coords[i-1][0]
        dy = coords[i][1] - coords[i-1][1]
        b = math.degrees(math.atan2(dy, dx)) % 360
        bearings.append(b)

    cumulative = 0.0
    n_changes = 0
    prev = bearings[0]
    for b in bearings[1:]:
        diff = b - prev
        # unwrap
        while diff > 180: diff -= 360
        while diff < -180: diff += 360
        cumulative += abs(diff)
        if abs(diff) > segment_threshold_deg:
            n_changes += 1
        prev = b

    # curve vs straight ratio: segments where angular change > threshold
    curve_segs = sum(1 for i in range(1, len(bearings))
                     if abs((bearings[i] - bearings[i-1] + 180) % 360 - 180) > 2.0)
    total_segs = max(len(bearings) - 1, 1)
    curve_ratio = curve_segs / total_segs

    start_b = bearings[0]
    end_b = bearings[-1]
    net = (end_b - start_b + 180) % 360 - 180

    plan_len = centerline.length
    straight_len = math.hypot(
        coords[-1][0] - coords[0][0],
        coords[-1][1] - coords[0][1],
    )
    # circular routes: start≈end → straight_len≈0; cap at plan_len/0.01
    min_straight = max(straight_len, plan_len * 0.01)
    tortuosity = plan_len / min_straight

    return DirectionalResult(
        route_id=route_id,
        cumulative_rotation_deg=cumulative,
        curve_ratio=curve_ratio,
        straight_ratio=1.0 - curve_ratio,
        n_direction_changes=n_changes,
        start_bearing_deg=start_b,
        end_bearing_deg=end_b,
        net_direction_change_deg=net,
        tortuosity=tortuosity,
    )
