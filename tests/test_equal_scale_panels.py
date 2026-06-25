"""동일 축척 패널 단위 테스트."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.diagram_renderer import get_common_panel_extent
from shapely.geometry import Point
import math


def _make_pts(radius, n=16):
    return [(radius * math.cos(2*math.pi*i/n), radius * math.sin(2*math.pi*i/n))
            for i in range(n)]


def test_equal_extent_single():
    pts = _make_pts(5.0)
    e = get_common_panel_extent([pts])
    # 12% padding이 추가되므로 5.0 이상, 7.0 미만이면 정상
    assert 5.0 <= e < 7.0


def test_equal_extent_multiple():
    pts_small = _make_pts(3.0)
    pts_large = _make_pts(7.0)
    e = get_common_panel_extent([pts_small, pts_large])
    # 더 큰 radius를 cover해야 함
    assert e >= 7.0


def test_equal_extent_minimum():
    pts = [(0.1, 0.1), (0.2, 0.2)]
    e = get_common_panel_extent([pts])
    assert e >= 1.0


def test_empty_returns_default():
    e = get_common_panel_extent([])
    assert e > 0
