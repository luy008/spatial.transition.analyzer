"""DXF 로더 — 재사용 가능한 범용 버전 (특정 프로젝트 좌표 하드코딩 없음)."""
from __future__ import annotations
import math
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

import ezdxf
from ezdxf import recover
from shapely.geometry import LineString, Point, Polygon


def load_dxf(path: str | Path) -> Tuple[Any, List[dict]]:
    """DXF를 ezdxf로 읽어 원시 엔티티 목록 반환. (doc, entities)"""
    path = str(path)
    try:
        doc, _ = recover.readfile(path)
    except Exception:
        doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    entities = []
    for e in msp:
        try:
            layer = getattr(e.dxf, "layer", "0") or "0"
            try:
                layer = layer.encode("latin-1").decode("cp949")
            except Exception:
                pass
            color = getattr(e.dxf, "color", 7)
            entities.append({"type": e.dxftype(), "layer": layer,
                             "color": color, "_entity": e})
        except Exception:
            pass
    return doc, entities


def entity_to_linestring(e: Any, scale: float = 0.001) -> Optional[LineString]:
    """단일 DXF 엔티티를 Shapely LineString으로 변환 (mm→m)."""
    t = e["type"]
    raw = e["_entity"]
    try:
        if t == "LINE":
            s = raw.dxf.start; end = raw.dxf.end
            return LineString([(s.x * scale, s.y * scale), (end.x * scale, end.y * scale)])
        elif t == "LWPOLYLINE":
            pts = [(p[0] * scale, p[1] * scale) for p in raw.get_points()]
            if len(pts) < 2:
                return None
            if raw.closed and pts[0] != pts[-1]:
                pts.append(pts[0])
            return LineString(pts)
        elif t in ("POLYLINE", "MESH"):
            pts = [(v.dxf.location.x * scale, v.dxf.location.y * scale)
                   for v in raw.vertices]
            return LineString(pts) if len(pts) >= 2 else None
        elif t == "ARC":
            cx, cy = raw.dxf.center.x * scale, raw.dxf.center.y * scale
            r = raw.dxf.radius * scale
            sa, ea = math.radians(raw.dxf.start_angle), math.radians(raw.dxf.end_angle)
            if ea < sa:
                ea += 2 * math.pi
            n = max(32, int((ea - sa) / math.pi * 64))
            pts = [(cx + r * math.cos(sa + (ea - sa) * i / n),
                    cy + r * math.sin(sa + (ea - sa) * i / n)) for i in range(n + 1)]
            return LineString(pts)
        elif t == "CIRCLE":
            cx, cy = raw.dxf.center.x * scale, raw.dxf.center.y * scale
            r = raw.dxf.radius * scale
            pts = [(cx + r * math.cos(2 * math.pi * i / 128),
                    cy + r * math.sin(2 * math.pi * i / 128)) for i in range(129)]
            return LineString(pts)
        elif t == "SPLINE":
            pts_raw = list(raw.control_points)
            if len(pts_raw) < 2:
                pts_raw = list(raw.fit_points)
            pts = [(p.x * scale, p.y * scale) for p in pts_raw]
            return LineString(pts) if len(pts) >= 2 else None
    except Exception:
        pass
    return None


def get_all_linestrings(entities: List[dict], scale: float = 0.001) -> List[Tuple[LineString, dict]]:
    """모든 엔티티를 LineString으로 변환. (geometry, entity_dict) 쌍 반환."""
    result = []
    for e in entities:
        ls = entity_to_linestring(e, scale)
        if ls is not None and not ls.is_empty and ls.length > 0:
            result.append((ls, e))
    return result


def get_layer_names(entities: List[dict]) -> List[str]:
    return sorted(set(e["layer"] for e in entities))


def get_bounds(entities: List[dict], scale: float = 0.001) -> Tuple[float, float, float, float]:
    """전체 DXF 영역 (xmin, ymin, xmax, ymax) in m."""
    xs, ys = [], []
    for e in entities:
        ls = entity_to_linestring(e, scale)
        if ls:
            b = ls.bounds
            xs += [b[0], b[2]]; ys += [b[1], b[3]]
    if not xs:
        return 0, 0, 1, 1
    return min(xs), min(ys), max(xs), max(ys)


def filter_by_layers(entities: List[dict], layers: List[str]) -> List[dict]:
    s = set(layers)
    return [e for e in entities if e["layer"] in s]


def filter_by_x_range(entities: List[dict], xmin: float, xmax: float,
                       scale: float = 0.001) -> List[dict]:
    result = []
    for e in entities:
        ls = entity_to_linestring(e, scale)
        if ls:
            b = ls.bounds
            if b[2] >= xmin and b[0] <= xmax:
                result.append(e)
    return result


def auto_detect_floors(entities: List[dict], scale: float = 0.001,
                       n_floors: int = 6) -> List[Dict]:
    """TEXT 좌표 기반 층별 x 범위 자동 추정."""
    text_xs = []
    for e in entities:
        if e["type"] in ("TEXT", "MTEXT"):
            raw = e["_entity"]
            try:
                x = getattr(raw.dxf, "insert", None) or getattr(raw.dxf, "text_direction", None)
                if x:
                    text_xs.append(x.x * scale)
            except Exception:
                pass
    if not text_xs:
        bnd = get_bounds(entities, scale)
        w = (bnd[2] - bnd[0]) / max(n_floors, 1)
        return [{"level_id": f"L{i+1:02d}", "label": f"Level {i+1:02d}",
                 "xmin": bnd[0] + i*w, "xmax": bnd[0] + (i+1)*w,
                 "ymin": bnd[1], "ymax": bnd[3]} for i in range(n_floors)]
    text_xs.sort()
    # 클러스터링: 큰 간격을 층 경계로 판단
    gaps = [(text_xs[i+1] - text_xs[i], i) for i in range(len(text_xs)-1)]
    gaps.sort(reverse=True)
    dividers = sorted([text_xs[i+1] for _, i in gaps[:n_floors-1]])
    all_xs = [text_xs[0] - 5] + dividers + [text_xs[-1] + 5]
    bnd = get_bounds(entities, scale)
    floors = []
    for i in range(len(all_xs) - 1):
        floors.append({"level_id": f"L{i+1:02d}", "label": f"Level {i+1:02d}",
                       "xmin": all_xs[i], "xmax": all_xs[i+1],
                       "ymin": bnd[1], "ymax": bnd[3]})
    return floors
