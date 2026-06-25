"""형상 분류 — 레이어·색상 기반 자동 분류 + 중정 void 처리."""
from __future__ import annotations
import math
from typing import List, Tuple, Dict, Optional

from shapely.geometry import LineString, Point, Polygon, MultiLineString
from shapely.ops import unary_union

from core.models import GeometryClass

# 기본 색상 분류 규칙 (ezdxf ACI 색상 인덱스)
DEFAULT_COLOR_RULES: Dict[int, GeometryClass] = {
    4: GeometryClass.CURTAIN,
    2: GeometryClass.OPAQUE,
    3: GeometryClass.OPAQUE,
    1: GeometryClass.EXCLUDE,
    5: GeometryClass.EXCLUDE,
    6: GeometryClass.EXCLUDE,
    7: GeometryClass.OPAQUE,
    8: GeometryClass.EXCLUDE,
    9: GeometryClass.EXCLUDE,
    40: GeometryClass.EXCLUDE,
}

DEFAULT_LAYER_RULES: Dict[str, GeometryClass] = {
    "A-02-WALL": GeometryClass.OPAQUE,
    "A-03-WALL": GeometryClass.OPAQUE,
    "SectionCutEdges": GeometryClass.OPAQUE,
    "AA-DWXM-WIND": GeometryClass.CURTAIN,
    "Dor": GeometryClass.CURTAIN,
    "A-01-OPEN": GeometryClass.OPENING,
    "WA2(가벽)_TED.A": GeometryClass.OPAQUE,
    "0": GeometryClass.OPAQUE,
}

EXCLUDE_LAYER_KEYWORDS = ["DIM", "TEXT", "TXT", "NOTE", "ELEV", "HIDD",
                           "FURL", "SYM", "HRAL", "DDOT", "shadow", "ETC",
                           "SYMB", "FRAME", "HACH", "HAT", "form", "DEFPOINT",
                           "TITLE", "WID", "STRS"]


def classify_entity(entity: dict, layer_rules: Optional[Dict[str, str]] = None,
                    color_rules: Optional[Dict[int, str]] = None) -> GeometryClass:
    layer = entity.get("layer", "")
    color = entity.get("color", 7)
    etype = entity.get("type", "")

    # 텍스트·치수는 제외
    if etype in ("TEXT", "MTEXT", "DIMENSION", "HATCH", "INSERT"):
        return GeometryClass.EXCLUDE

    # 제외 레이어 키워드
    for kw in EXCLUDE_LAYER_KEYWORDS:
        if kw in layer:
            return GeometryClass.EXCLUDE

    # 사용자 레이어 규칙
    if layer_rules:
        for lname, cls_str in layer_rules.items():
            if lname in layer:
                try:
                    return GeometryClass(cls_str)
                except ValueError:
                    pass

    # 기본 레이어 규칙
    for lname, cls in DEFAULT_LAYER_RULES.items():
        if lname == layer:
            return cls

    # 사용자 색상 규칙
    if color_rules:
        for c_str, cls_str in color_rules.items():
            try:
                if int(c_str) == color:
                    return GeometryClass(cls_str)
            except (ValueError, TypeError):
                pass

    # 기본 색상 규칙
    c = DEFAULT_COLOR_RULES.get(color)
    if c:
        return c

    return GeometryClass.UNCLASSIFIED


def auto_classify_all(entities: List[dict],
                      layer_rules: Optional[Dict[str, str]] = None,
                      color_rules: Optional[Dict[int, str]] = None) -> List[Tuple[dict, GeometryClass]]:
    return [(e, classify_entity(e, layer_rules, color_rules)) for e in entities]


def remove_lines_inside_void(lines: List[LineString], center: Point,
                              radius_m: float, tolerance_m: float = 0.03) -> Tuple[List[LineString], int]:
    """중정 void 내부 선 제거 (정확한 클리핑으로 바깥 부분은 보존)."""
    try:
        void = center.buffer(radius_m - tolerance_m, quad_segs=128)
    except TypeError:
        void = center.buffer(radius_m - tolerance_m, resolution=128)
    cleaned = []
    removed = 0
    for ls in lines:
        if ls is None or ls.is_empty:
            continue
        try:
            remaining = ls.difference(void)
        except Exception:
            cleaned.append(ls)
            continue
        if remaining.is_empty:
            removed += 1
            continue
        if remaining.geom_type == "LineString":
            if remaining.length > tolerance_m:
                cleaned.append(remaining)
            else:
                removed += 1
        elif remaining.geom_type == "MultiLineString":
            kept = [g for g in remaining.geoms if g.length > tolerance_m]
            cleaned.extend(kept)
            if not kept:
                removed += 1
        else:
            removed += 1
    return cleaned, removed


def validate_courtyard_void(lines: List[LineString], center: Point,
                             radius_m: float, tolerance_m: float = 0.03) -> Tuple[bool, int]:
    try:
        interior = center.buffer(radius_m - tolerance_m, quad_segs=128)
    except TypeError:
        interior = center.buffer(radius_m - tolerance_m, resolution=128)
    violations = 0
    for ls in lines:
        if ls is None or ls.is_empty:
            continue
        try:
            overlap = ls.intersection(interior)
            if not overlap.is_empty and overlap.length > tolerance_m:
                violations += 1
        except Exception:
            pass
    return violations == 0, violations
