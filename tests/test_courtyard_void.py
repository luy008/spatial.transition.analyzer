"""중정 void 마스킹 단위 테스트."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.geometry_classifier import remove_lines_inside_void, validate_courtyard_void
from shapely.geometry import LineString, Point


def test_remove_interior_line():
    center = Point(0.0, 0.0)
    # 반지름 4m 내부 선분
    inside = LineString([(-2, 0), (2, 0)])
    # 외부 선분
    outside = LineString([(5, -3), (5, 3)])
    cleaned, removed = remove_lines_inside_void([inside, outside], center, radius_m=4.0)
    assert removed >= 1
    assert len(cleaned) == 1


def test_validate_passes_empty():
    center = Point(0.0, 0.0)
    ok, violations = validate_courtyard_void([], center, radius_m=4.0)
    assert ok is True
    assert violations == 0


def test_validate_detects_violation():
    center = Point(0.0, 0.0)
    inside = LineString([(-2, 0), (2, 0)])
    ok, violations = validate_courtyard_void([inside], center, radius_m=4.0)
    assert ok is False
    assert violations > 0


def test_line_on_boundary_not_removed():
    """경계에 걸친 선분은 일부가 밖에 있으므로 제거되지 않을 수 있음."""
    center = Point(0.0, 0.0)
    boundary = LineString([(3.5, 0), (5.0, 0)])  # 내부→외부 걸침
    cleaned, removed = remove_lines_inside_void([boundary], center, radius_m=4.0)
    # 어떤 결과든 예외 없이 실행되어야 함
    assert isinstance(cleaned, list)
