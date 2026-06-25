"""램프 수치 단위 테스트."""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ramp_analysis import calculate_circular_ramp_metrics, build_circular_ramp_centerline
from shapely.geometry import Point


def test_confirmed_full_rotation_ramp():
    m = calculate_circular_ramp_metrics(radius_m=4.75, rotation_deg=360.0, rise_m=3.0)
    assert abs(m.horizontal_length_m - 29.845) < 0.02
    assert abs(m.travel_length_3d_m - 29.996) < 0.02
    assert abs(m.slope_percent - 10.052) < 0.02
    assert abs(m.slope_ratio - 9.948) < 0.02
    assert abs(m.slope_angle_deg - 5.741) < 0.02
    assert abs(m.rotation_deg - 360.0) < 0.01


def test_half_rotation():
    m = calculate_circular_ramp_metrics(radius_m=4.75, rotation_deg=180.0, rise_m=3.0)
    assert abs(m.horizontal_length_m - 14.923) < 0.05
    assert m.slope_percent > 10


def test_centerline_length():
    cl = build_circular_ramp_centerline(Point(0, 0), 4.75, 0.0, "ccw", 360.0, segments=720)
    assert abs(cl.length - 29.845) < 0.05
    # 시작점과 끝점이 거의 같아야 함 (360° 완전 루프)
    pts = list(cl.coords)
    d = math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1])
    assert d < 0.1


def test_raises_on_invalid():
    import pytest
    with pytest.raises(ValueError):
        calculate_circular_ramp_metrics(-1, 360, 3)
    with pytest.raises(ValueError):
        calculate_circular_ramp_metrics(4.75, 0, 3)
    with pytest.raises(ValueError):
        calculate_circular_ramp_metrics(4.75, 360, 0)
