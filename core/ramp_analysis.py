"""램프 기하 계산 — 범용. 특정 프로젝트 좌표 하드코딩 없음."""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Tuple, List

from shapely.geometry import LineString, Point


@dataclass(frozen=True)
class CircularRampMetrics:
    radius_m: float
    rotation_deg: float
    rise_m: float
    horizontal_length_m: float
    travel_length_3d_m: float
    slope_percent: float
    slope_ratio: float
    slope_angle_deg: float
    est_time_s: float = 0.0
    speed_mps: float = 0.8

    def annotation(self) -> str:
        return (f"이동 {self.travel_length_3d_m:.1f}m · 회전 {self.rotation_deg:.0f}° · "
                f"상승 {self.rise_m:.1f}m\n경사 {self.slope_percent:.1f}% "
                f"(1:{self.slope_ratio:.1f})")


def calculate_circular_ramp_metrics(radius_m: float, rotation_deg: float,
                                     rise_m: float, speed_mps: float = 0.8) -> CircularRampMetrics:
    if radius_m <= 0:
        raise ValueError("radius_m must be > 0")
    if rotation_deg <= 0:
        raise ValueError("rotation_deg must be > 0")
    if rise_m <= 0:
        raise ValueError("rise_m must be > 0")
    horiz = radius_m * math.radians(rotation_deg)
    travel = math.hypot(horiz, rise_m)
    slope_dec = rise_m / horiz
    return CircularRampMetrics(
        radius_m=radius_m, rotation_deg=rotation_deg, rise_m=rise_m,
        horizontal_length_m=horiz, travel_length_3d_m=travel,
        slope_percent=slope_dec * 100.0, slope_ratio=horiz / rise_m,
        slope_angle_deg=math.degrees(math.atan(slope_dec)),
        est_time_s=travel / speed_mps, speed_mps=speed_mps)


def build_circular_ramp_centerline(center: Point, radius_m: float,
                                    start_angle_deg: float, direction: str = "ccw",
                                    rotation_deg: float = 360.0, segments: int = 720) -> LineString:
    """중정 중심 기준 원형 램프 중심선 생성 (하드코딩 없음)."""
    sign = 1.0 if direction.lower() == "ccw" else -1.0
    pts = []
    for i in range(segments + 1):
        frac = i / segments
        angle_rad = math.radians(start_angle_deg + sign * rotation_deg * frac)
        pts.append((center.x + radius_m * math.cos(angle_rad),
                    center.y + radius_m * math.sin(angle_rad)))
    return LineString(pts)


def sample_elevation_on_ramp(centerline: LineString, rise_m: float,
                              n: int = 11) -> List[Tuple[float, float, float]]:
    """중심선 위의 n개 관찰점 (x, y, z) 반환."""
    total = centerline.length
    result = []
    for i in range(n):
        frac = i / (n - 1) if n > 1 else 0.0
        pt = centerline.interpolate(frac, normalized=True)
        z = rise_m * frac
        result.append((pt.x, pt.y, z))
    return result
