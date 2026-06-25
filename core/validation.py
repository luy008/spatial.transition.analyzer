"""최종 출력 전 검증 게이트."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List

from shapely.geometry import LineString, Point


@dataclass
class ValidationResult:
    passed: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def fail(self, msg: str):
        self.passed = False
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)


def validate_geometry(routes_data: List[dict], project_data) -> ValidationResult:
    vr = ValidationResult()
    for rd in routes_data:
        rid = rd.get("route_id", "?")
        plan = rd.get("plan_m", 0)
        if plan <= 0:
            vr.fail(f"{rid}: 경로 길이가 0 이하입니다.")
        slope = rd.get("slope_percent", 0)
        if rd.get("is_ramp") and slope > 20:
            vr.warn(f"{rid}: 경사 {slope:.1f}%는 일반적인 보행 램프 범위(≤15%)를 초과합니다.")
    return vr


def validate_equal_panels(ax_list: list) -> ValidationResult:
    vr = ValidationResult()
    if len(ax_list) < 2:
        return vr
    xlims = [ax.get_xlim() for ax in ax_list]
    ylims = [ax.get_ylim() for ax in ax_list]
    ref_x = xlims[0]; ref_y = ylims[0]
    for i, (xl, yl) in enumerate(zip(xlims[1:], ylims[1:]), 1):
        if abs(xl[0] - ref_x[0]) > 0.1 or abs(xl[1] - ref_x[1]) > 0.1:
            vr.fail(f"패널 {i}의 x축 범위가 패널 0과 다릅니다.")
        if abs(yl[0] - ref_y[0]) > 0.1 or abs(yl[1] - ref_y[1]) > 0.1:
            vr.fail(f"패널 {i}의 y축 범위가 패널 0과 다릅니다.")
    return vr


def validate_courtyard_void(obstacles: List[LineString],
                              center: Point, radius_m: float = 4.0) -> ValidationResult:
    from core.geometry_classifier import validate_courtyard_void as _v
    vr = ValidationResult()
    ok, n = _v(obstacles, center, radius_m)
    if not ok:
        vr.fail(f"중정 내부에 불투명 벽선 {n}개가 남아 있습니다.")
    return vr
