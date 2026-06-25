"""건축 분석 다이어그램 렌더러 — CLI/Streamlit/테스트 공용.

A3 레이아웃: 제목(상단 12%) / 수직개요+시퀀스 패널(중단 52%) /
가시 띠(중하단 10%) / 수직 단면+CRITICAL READING(하단 26%).
"""
from __future__ import annotations
import math
import os
from pathlib import Path
from typing import List, Tuple, Optional, Dict

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Rectangle
import matplotlib.font_manager as fm
from shapely.geometry import LineString, Point, Polygon

from core.geometry_classifier import (classify_entity, auto_classify_all,
                                       remove_lines_inside_void)
from core.models import GeometryClass, IsovistResult
from core.dxf_loader import entity_to_linestring

# ── 팔레트 ──────────────────────────────────────────────────────────
C_OPAQUE   = "#2C3E50"
C_CURTAIN  = "#16A085"
C_OPEN     = "#AAB7B8"
C_COURT    = "#17BECF"
C_STAIR    = "#2980B9"
C_RAMP     = "#C0392B"
C_PREV     = "#7F8C8D"
C_NEXT     = "#E74C3C"
C_ISO      = "#5DADE2"
C_OBS      = "#E67E22"
C_VOID     = "#EAF7F0"

A3_W_MM, A3_H_MM = 420.0, 297.0
FORBIDDEN = [
    "Stair to Ramp: Does a Change in Circulation Produce a Change in Experience?",
    "계단에서 램프로의 전환은 최상부 전시공간으로의 경험 전환을 만드는가?",
    "TRANSITION MATRIX",
]


# ── 폰트 ──────────────────────────────────────────────────────────
def _setup_font() -> Optional[str]:
    available = {f.name for f in fm.fontManager.ttflist}
    for name in ["Noto Sans CJK KR", "Noto Sans KR", "Malgun Gothic",
                 "AppleGothic", "NanumGothic"]:
        if name in available:
            matplotlib.rcParams["font.family"] = name
            matplotlib.rcParams["axes.unicode_minus"] = False
            return name
    matplotlib.rcParams["axes.unicode_minus"] = False
    return None


# ── 금지문구 검사 ────────────────────────────────────────────────
def _check_forbidden(texts: List[str]) -> List[str]:
    hits = []
    for t in texts:
        for f in FORBIDDEN:
            if f and f in str(t):
                hits.append(f"금지문구 발견: {f!r}")
    return hits


# ── 기하 헬퍼 ───────────────────────────────────────────────────

def _dense_arc_pts(arc: dict, n: int = 200) -> List[Tuple[float, float]]:
    """routes.json arc 서브-객체 → 밀집 호 점열 (n 점).

    start_angle_deg == end_angle_deg → 완전한 원(360°)으로 처리.
    """
    if not arc:
        return []
    cx, cy = float(arc["center"][0]), float(arc["center"][1])
    r = float(arc["radius"])
    a0_deg = float(arc.get("start_angle_deg", 0))
    a1_deg = float(arc.get("end_angle_deg", 360))
    ccw = bool(arc.get("ccw", True))
    a0 = math.radians(a0_deg)
    a1 = math.radians(a1_deg)
    # start == end → full circle
    if abs(a1_deg - a0_deg) < 1e-6:
        a1 = a0 + 2 * math.pi
    elif ccw:
        if a1 < a0:
            a1 += 2 * math.pi
    else:
        if a0 < a1:
            a0 += 2 * math.pi
    angles = np.linspace(a0, a1, n)
    return [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in angles]


def _best_centerline_pts(route_data: dict) -> List[Tuple[float, float]]:
    """arc 또는 control_points에서 최적 밀집 점열 반환."""
    arc = route_data.get("arc")
    cp = route_data.get("control_points", [])
    cp_tuples = [tuple(p) for p in cp]
    # R1: 521+ 점 → 그대로 사용
    if len(cp_tuples) >= 50:
        return cp_tuples
    # S1/S2/S3: arc 정보로 밀집 보간
    if arc:
        return _dense_arc_pts(arc, n=200)
    return cp_tuples


def _extract_level_walls(dxf_entities: list, window: list,
                          court_center: Tuple[float, float],
                          court_radius: float,
                          scale: float = 0.001) -> Tuple[List[LineString], List[LineString]]:
    """level window 내 DXF 엔티티 → 불투명·커튼 LineString (중정 void 제거).

    dxf_entities: load_dxf() 반환 목록 (geom 미포함, _entity로 변환)
    window: [xmin, ymin, xmax, ymax] in metres
    """
    xmin, ymin, xmax, ymax = window
    walls: List[LineString] = []
    curtains: List[LineString] = []
    for ent in dxf_entities:
        cls = classify_entity(ent)
        if cls not in (GeometryClass.OPAQUE, GeometryClass.CURTAIN):
            continue
        g = entity_to_linestring(ent, scale=scale)
        if g is None or g.is_empty or g.length < 1e-6:
            continue
        bx0, by0, bx1, by1 = g.bounds
        if bx1 < xmin or bx0 > xmax or by1 < ymin or by0 > ymax:
            continue
        if cls == GeometryClass.OPAQUE:
            walls.append(g)
        else:
            curtains.append(g)
    center_pt = Point(court_center)
    walls, _ = remove_lines_inside_void(walls, center_pt, court_radius)
    curtains, _ = remove_lines_inside_void(curtains, center_pt, court_radius)
    return walls, curtains


def _shared_extent(all_pts_groups: List[List[Tuple[float, float]]],
                   court_radius: float, padding: float = 0.15) -> float:
    """중정 중심 정렬 후 모든 경로를 포괄하는 반-extent (동일 축척용)."""
    max_he = court_radius + 2.0
    for pts in all_pts_groups:
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        he = max(max(abs(x - cx) for x in xs), max(abs(y - cy) for y in ys), 1.0)
        max_he = max(max_he, he)
    return max_he * (1 + padding)


# ── 패널 그리기 ──────────────────────────────────────────────────

def _draw_route_panel(ax: plt.Axes, walls: List[LineString],
                       curtains: List[LineString],
                       centerline_pts: List[Tuple[float, float]],
                       court_center: Tuple[float, float],
                       court_radius: float,
                       route_col: str,
                       is_ramp: bool,
                       iso_polys: Optional[List[List[Tuple[float, float]]]] = None,
                       obs_pts: Optional[List[Tuple[float, float]]] = None,
                       extent: float = 8.0) -> None:
    """단일 패널 내에 평면 장면 그리기 (중정 중심 기준 좌표계)."""
    cx, cy = court_center

    def T(x, y):
        return x - cx, y - cy

    # 1. 벽 (OPAQUE)
    for ls in walls:
        pts = [T(x, y) for x, y in ls.coords]
        ax.plot([p[0] for p in pts], [p[1] for p in pts],
                "-", color=C_OPAQUE, lw=0.75, zorder=2)

    # 2. Isovist 면
    if iso_polys:
        for poly_coords in iso_polys:
            if len(poly_coords) < 3:
                continue
            pxs = [p[0] - cx for p in poly_coords]
            pys = [p[1] - cy for p in poly_coords]
            ax.fill(pxs, pys, color=C_ISO, alpha=0.18, zorder=3)

    # 3. 중정 void 마스킹 (불투명 면)
    th = np.linspace(0, 2 * math.pi, 128)
    ax.fill(court_radius * np.cos(th), court_radius * np.sin(th),
            color=C_VOID, alpha=1.0, zorder=5)

    # 4. 커튼월
    for ls in curtains:
        pts = [T(x, y) for x, y in ls.coords]
        ax.plot([p[0] for p in pts], [p[1] for p in pts],
                "-", color=C_CURTAIN, lw=1.1, zorder=6)
    ax.plot(court_radius * np.cos(th), court_radius * np.sin(th),
            "-", color=C_CURTAIN, lw=1.2, zorder=6)
    ax.plot(0, 0, "+", color=C_CURTAIN, ms=6, zorder=6)

    # 5. 경로 중심선
    if centerline_pts:
        pxs = [p[0] - cx for p in centerline_pts]
        pys = [p[1] - cy for p in centerline_pts]
        lw = 2.2 if is_ramp else 1.6
        ax.plot(pxs, pys, "-", color=route_col, lw=lw, zorder=7)
        ax.plot(pxs[0], pys[0], "o", color=route_col, ms=5, zorder=8)
        ax.plot(pxs[-1], pys[-1], "s", color=route_col, ms=5, zorder=8)

    # 6. 관찰자 점
    if obs_pts:
        for ox, oy in obs_pts:
            ax.plot(ox - cx, oy - cy, "o", color=C_OBS, ms=7, zorder=9)

    ax.set_xlim(-extent, extent)
    ax.set_ylim(-extent, extent)
    ax.set_aspect("equal")
    ax.axis("off")


# ── 가시 띠 ──────────────────────────────────────────────────────

def _draw_visibility_band(ax: plt.Axes, iso_results: List[IsovistResult]) -> None:
    """PREVIOUS/COURTYARD/NEXT 가시 띠 (채운 부분 = 가시)."""
    if not iso_results:
        ax.axis("off")
        return
    n = len(iso_results)
    seg = 1.0 / max(n - 1, 1)
    rows = [("PREV", C_PREV, "previous_visible"),
            ("COURT", C_COURT, "courtyard_visible"),
            ("NEXT", C_NEXT, "next_visible")]
    band_h, gap = 0.8, 0.5
    for r_idx, (label, col, key) in enumerate(rows):
        y_top = -(r_idx * (band_h + gap))
        ax.add_patch(Rectangle((0, y_top - band_h), 1, band_h,
                                fill=False, ec="#ccc", lw=0.5, zorder=2))
        for i, res in enumerate(iso_results):
            if getattr(res, key, False):
                x0 = max(0.0, i * seg - seg / 2)
                ax.add_patch(Rectangle((x0, y_top - band_h), seg, band_h,
                                        fc=col, ec="none", alpha=0.85, zorder=3))
        ax.text(-0.02, y_top - band_h / 2, label,
                ha="right", va="center", fontsize=4.5, color=col)
    ax.set_xlim(-0.08, 1.02)
    ax.set_ylim(-(len(rows) * (band_h + gap)), 0.5)
    ax.axis("off")


# ── 수직 개요 ────────────────────────────────────────────────────

def _draw_overview(ax: plt.Axes, routes_ordered: List[dict],
                   levels: dict, all_arc_pts: dict) -> None:
    """수직 적층 의사-axonometric 개요."""
    cum_h = 0.0
    last_px, last_py = None, None
    for rd in routes_ordered:
        rid = rd["route_id"]
        is_ramp = rd.get("is_ramp", False)
        col = C_RAMP if is_ramp else C_STAIR
        rise = rd.get("rise_m", 3.0)
        pts = all_arc_pts.get(rid, rd.get("centerline_pts", []))
        if not pts:
            cum_h += rise
            continue
        src_lv = rd.get("source_level", "L01")
        dst_lv = rd.get("destination_level", "L02")
        lv_key = dst_lv if is_ramp else src_lv
        lv = levels.get(lv_key, {})
        cm = tuple(lv.get("courtyard_center", [0, 0]))
        n = len(pts)
        zs = [cum_h + rise * (k / max(n - 1, 1)) for k in range(n)]
        xs = [p[0] - cm[0] for p in pts]
        ys = [p[1] - cm[1] for p in pts]
        px = [xs[k] + 0.45 * ys[k] for k in range(n)]
        py = [zs[k] + 0.38 * ys[k] for k in range(n)]
        ax.plot(px, py, "-", color=col, lw=2.5 if is_ramp else 1.5)
        mid = n // 2
        ax.annotate(rid, (px[mid], py[mid]), color=col, fontsize=7,
                    fontweight="bold", ha="center",
                    xytext=(0, 4), textcoords="offset points")
        if is_ramp:
            ax.plot(px[0], py[0], "D", color=C_RAMP, ms=6)
        last_px, last_py = px[-1], py[-1]
        cum_h += rise
    if last_px is not None:
        ax.annotate("최상부\n전시", (last_px, last_py), color="#333",
                    fontsize=6, ha="center",
                    xytext=(0, 6), textcoords="offset points")
    ax.set_aspect("equal")
    ax.axis("off")


# ── 수직 단면 ────────────────────────────────────────────────────

def _draw_section(ax: plt.Axes, routes_ordered: List[dict]) -> None:
    cum_x, cum_z = 0.0, 0.0
    for rd in routes_ordered:
        rid = rd["route_id"]
        plan = rd.get("plan_m", 5.0)
        rise = rd.get("rise_m", 3.0)
        is_ramp = rd.get("is_ramp", False)
        col = C_RAMP if is_ramp else C_STAIR
        if is_ramp:
            ax.plot([cum_x, cum_x + plan], [cum_z, cum_z + rise],
                    "-", color=col, lw=2.5)
        else:
            n_s = max(3, int(rise / 0.2))
            sw = plan / n_s; sh = rise / n_s
            xs2 = [cum_x]; zs2 = [cum_z]
            for _ in range(n_s):
                xs2.append(xs2[-1] + sw); zs2.append(zs2[-1])
                xs2.append(xs2[-1]); zs2.append(zs2[-1] + sh)
            ax.plot(xs2, zs2, "-", color=col, lw=1.5)
        ax.text(cum_x + plan / 2, cum_z + rise / 2 + 0.5, rid,
                ha="center", fontsize=8, fontweight="bold", color=col)
        cum_x += plan + 1.0
        cum_z += rise
    ax.text(cum_x + 0.3, cum_z, "TOP\nGALLERY",
            ha="left", va="center", fontsize=7, color="#333")
    ax.set_xlabel("누적 수평 이동거리 (m)", fontsize=7)
    ax.set_ylabel("누적 높이 (m)", fontsize=7)
    ax.tick_params(labelsize=6)
    ax.grid(True, alpha=0.25)


# ── 비판적 독해 ──────────────────────────────────────────────────

def _build_critical_reading(routes_ordered: List[dict]) -> List[str]:
    ramp = [r for r in routes_ordered if r.get("is_ramp")]
    stairs = [r for r in routes_ordered if not r.get("is_ramp")]
    if not ramp:
        return ["분석 완료 후 자동 생성됩니다."]
    rr = ramp[0]
    st_mean = sum(r.get("dist_3d_m", 0) for r in stairs) / max(len(stairs), 1)
    s1 = (f"하부 계단은 평균 {st_mean:.1f}m의 직접적 상승을 반복한다. "
          f"{rr.get('route_id', 'R1')}은 중정을 "
          f"{rr.get('rotation_deg', 360):.0f}° 순환하며 "
          f"약 {rr.get('dist_3d_m', 30.0):.1f}m의 이동을 형성한다.")
    ev = rr.get("visibility_events", {})
    court = ev.get("courtyard_visibility_duration_percent")
    nxt = ev.get("next_space_first_visible_percent")
    court_str = f"{court:.0f}%" if court is not None else "—"
    nxt_str = (f"진행률 {nxt:.0f}%에서 처음 인지된다" if nxt is not None
               else "이동이 끝날 때까지 인지되지 않는다")
    s2 = (f"R1에서 중정은 이동 구간의 {court_str} 동안 지속적으로 인지되지만, "
          f"최상부 전시공간은 {nxt_str}.")
    slope = rr.get("slope_percent", 0)
    s3 = (f"약 {slope:.1f}%의 경사와 {rr.get('dist_3d_m', 30.0):.0f}m의 긴 순환 동선이 "
          f"최상부 전시공간의 경험적 전환으로 충분히 이어지는지는 "
          f"별도의 비판적 판단이 필요하다.")
    return [s1, s2, s3]


METHOD_LIMITS = [
    "2차원 Isovist는 램프에서 관찰자의 눈높이가 3m 상승하는 실제 단면 경험과 신체적 피로를 평면적 가시관계로 환원한다.",
    "커튼월의 반사·빛·재료·난간·음향·전시물 배치가 만드는 실제 암시 효과는 이 분석으로 설명되지 않는다.",
]


def _wrap_text(s: str, width: int = 26) -> str:
    out, line = [], ""
    for ch in s:
        line += ch
        if len(line) >= width and ch in " ,·.":
            out.append(line.rstrip())
            line = ""
    if line:
        out.append(line)
    return "\n".join(out)


def _save_all(fig: plt.Figure, png: str, pdf: str,
               svg: Optional[str] = None) -> Tuple[bool, str]:
    ok = True
    for p in (png, pdf, svg):
        if p:
            os.makedirs(Path(p).parent, exist_ok=True)
    try:
        fig.savefig(png, dpi=200, facecolor="white", bbox_inches="tight")
    except Exception as e:
        ok = False; print(f"PNG 저장 실패: {e}")
    try:
        from matplotlib.backends.backend_pdf import PdfPages
        with PdfPages(pdf) as pp:
            pp.savefig(fig, facecolor="white", bbox_inches="tight")
    except Exception as e:
        ok = False; print(f"PDF 저장 실패: {e}")
    if svg:
        try:
            fig.savefig(svg, format="svg", facecolor="white", bbox_inches="tight")
        except Exception as e:
            print(f"SVG 저장 실패: {e}")
    plt.close(fig)
    return ok, "" if ok else "저장 실패"


# ── 메인 렌더링 함수 ─────────────────────────────────────────────

def render_architectural_diagram(
    project_data: dict,
    analysis_results: dict,
    output_png: str,
    output_pdf: str,
    output_svg: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    project_data  : {project_name, title_en, title_ko, design_question,
                     routes: {rid: {..., arc, rise_m, ...}},
                     levels: {lid: {courtyard_center, courtyard_radius_m, window}},
                     spaces: {}}
    analysis_results : {movement_cost, directional, iso_R1, obstacles_R1,
                         dxf_entities, findings, ramp_metrics, ...}
    """
    _setup_font()

    # ── 금지문구 검사 ───────────────────────────────────────
    title_en = project_data.get("title_en", "")
    title_ko = project_data.get("title_ko", "")
    design_q = project_data.get("design_question", "")
    all_texts = [title_en, title_ko, design_q]
    hits = _check_forbidden(all_texts)
    if hits:
        return False, " / ".join(hits)

    routes_json = project_data.get("routes", {})
    levels      = project_data.get("levels", {})
    spaces      = project_data.get("spaces", {})
    dxf_entities = analysis_results.get("dxf_entities", [])
    mc_map       = analysis_results.get("movement_cost", {})
    dr_map       = analysis_results.get("directional", {})
    iso_R1_data  = analysis_results.get("iso_R1", {})
    ramp_metrics = analysis_results.get("ramp_metrics")
    findings     = analysis_results.get("findings", [])

    route_order = ["S1", "S2", "S3", "R1"]

    # ── 경로별 데이터 구조 구성 ────────────────────────────
    all_arc_pts: Dict[str, List[Tuple[float, float]]] = {}
    routes_ordered: List[dict] = []

    for rid in route_order:
        rdata = routes_json.get(rid)
        if not rdata:
            continue
        is_ramp = rdata.get("circulation_type", "stair") == "ramp"
        rise = float(rdata.get("rise_m", 3.0))
        arc = rdata.get("arc")
        cp = rdata.get("control_points", [])

        # 밀집 호 점열 (R1=721점 그대로, S1/S2/S3=arc 보간)
        pts = _best_centerline_pts(rdata)
        all_arc_pts[rid] = pts

        src_lv = rdata.get("source_level", "L01")
        dst_lv = rdata.get("destination_level", "L02")
        vis_lv = dst_lv if is_ramp else src_lv
        lv_info = levels.get(vis_lv, {})
        court_center = tuple(lv_info.get("courtyard_center", [0, 0]))
        court_radius = float(lv_info.get("courtyard_radius_m", 4.0))

        mc = mc_map.get(rid)
        plan_m   = mc.plan_distance_m if mc else 0.0
        dist_3d  = mc.dist_3d_m       if mc else rise
        slope_pc = mc.slope_percent    if mc else 0.0

        dr = dr_map.get(rid, {})
        json_rot = float(rdata.get("ramp_total_rotation_deg", 270.0)) if is_ramp else 90.0
        if hasattr(dr, "cumulative_rotation_deg"):
            rot_deg = dr.cumulative_rotation_deg
        elif isinstance(dr, dict):
            rot_deg = dr.get("cumulative_rotation_deg", json_rot)
        else:
            rot_deg = json_rot

        iso_results = []
        vis_events  = {}
        if rid == "R1":
            iso_results = iso_R1_data.get("results", [])
            vis_events  = iso_R1_data.get("events", {})

        routes_ordered.append({
            "route_id":       rid,
            "is_ramp":        is_ramp,
            "source_level":   src_lv,
            "destination_level": dst_lv,
            "vis_level":      vis_lv,
            "court_center":   court_center,
            "court_radius":   court_radius,
            "centerline_pts": pts,
            "rise_m":         rise,
            "plan_m":         plan_m,
            "dist_3d_m":      dist_3d,
            "slope_percent":  slope_pc,
            "rotation_deg":   rot_deg,
            "iso_results":    iso_results,
            "visibility_events": vis_events,
        })

    n_routes = len(routes_ordered)
    if n_routes == 0:
        fig, ax = plt.subplots(figsize=(A3_W_MM / 25.4, A3_H_MM / 25.4))
        ax.text(0.5, 0.5, "분석 경로가 없습니다.", ha="center", va="center",
                transform=ax.transAxes, fontsize=14)
        ax.axis("off")
        return _save_all(fig, output_png, output_pdf, output_svg)

    # ── 공통 패널 extent ──────────────────────────────────
    max_court_r = max((rd["court_radius"] for rd in routes_ordered), default=4.0)
    pts_for_extent = [
        [(p[0] - rd["court_center"][0], p[1] - rd["court_center"][1])
         for p in rd["centerline_pts"]]
        for rd in routes_ordered
    ]
    extent = _shared_extent(pts_for_extent, max_court_r, padding=0.18)

    # ── per-level 벽 추출 ─────────────────────────────────
    level_walls: Dict[str, Tuple[List, List]] = {}
    for rd in routes_ordered:
        lv = rd["vis_level"]
        if lv in level_walls:
            continue
        lv_info = levels.get(lv, {})
        window = lv_info.get("window")
        if not window or not dxf_entities:
            level_walls[lv] = ([], [])
            continue
        cc = rd["court_center"]
        cr = rd["court_radius"]
        walls, curtains = _extract_level_walls(dxf_entities, window, cc, cr)
        level_walls[lv] = (walls, curtains)

    # ── 비판적 독해 ───────────────────────────────────────
    crit_lines = _build_critical_reading(routes_ordered)
    all_texts += crit_lines
    hits = _check_forbidden(all_texts)
    if hits:
        return False, " / ".join(hits)

    # ═══════════════════════════════════════════════════════
    # A3 Figure 조립
    # ═══════════════════════════════════════════════════════
    fig = plt.figure(figsize=(A3_W_MM / 25.4, A3_H_MM / 25.4))
    fig.patch.set_facecolor("white")

    # 레이아웃 상수 (figure 좌표 0~1)
    TOP = 0.97
    TITLE_BOT = 0.86        # 제목 영역 하단
    PANEL_TOP = 0.84        # 패널 상단
    BAND_TOP  = 0.38        # 가시 띠 상단
    BAND_BOT  = 0.28        # 가시 띠 하단
    SEC_TOP   = 0.26        # 단면 상단
    SEC_BOT   = 0.04        # 단면 하단
    LEFT_OVW  = 0.02        # 수직개요 left
    OVW_W     = 0.12        # 수직개요 width
    PANEL_L   = 0.15        # 패널 시작 left
    PANEL_AREA_W = 0.58     # 4개 패널 전체 width
    CR_L      = 0.75        # Critical Reading left
    CR_W      = 0.23        # Critical Reading width

    # ── 제목 ──────────────────────────────────────────────
    ax_t = fig.add_axes([0.05, TITLE_BOT, 0.68, TOP - TITLE_BOT])
    ax_t.axis("off")
    ax_t.text(0.0, 0.95, title_en or "Spatial Transition Analysis",
              fontsize=11, fontweight="bold", transform=ax_t.transAxes, va="top")
    ax_t.text(0.0, 0.60, title_ko or "",
              fontsize=9, color="#444", transform=ax_t.transAxes, va="top")
    q_wrapped = _wrap_text(design_q, 90) if design_q else ""
    ax_t.text(0.0, 0.30, q_wrapped,
              fontsize=6.5, color="#333", transform=ax_t.transAxes, va="top")

    # ── 수직 개요 ─────────────────────────────────────────
    ax_ovw = fig.add_axes([LEFT_OVW, BAND_BOT, OVW_W, PANEL_TOP - BAND_BOT])
    ax_ovw.axis("off")
    _draw_overview(ax_ovw, routes_ordered, levels, all_arc_pts)
    ax_ovw.text(0.5, 1.01, "수직동선 개요",
                transform=ax_ovw.transAxes, ha="center", va="bottom",
                fontsize=7, fontweight="bold")

    # ── 경로 패널 (4개 균등) ─────────────────────────────
    panel_w = PANEL_AREA_W / n_routes
    panel_h = PANEL_TOP - BAND_TOP
    band_h  = BAND_TOP - BAND_BOT

    for i, rd in enumerate(routes_ordered):
        rid = rd["route_id"]
        is_ramp = rd["is_ramp"]
        col = C_RAMP if is_ramp else C_STAIR
        lv = rd["vis_level"]
        walls, curtains = level_walls.get(lv, ([], []))

        left = PANEL_L + i * panel_w
        ax_p = fig.add_axes([left, BAND_TOP, panel_w * 0.95, panel_h])

        # R1 isovist polygons (절대 좌표)
        iso_polys = None
        obs_pts = None
        if rid == "R1":
            iso_res = rd.get("iso_results", [])
            if iso_res:
                iso_polys = [r.polygon_coords for r in iso_res
                             if r.polygon_coords and len(r.polygon_coords) >= 3]
                # 대표 관찰자: 0%/50%/100%
                targets = [0, len(iso_res) // 2, len(iso_res) - 1]
                pts_list = rd["centerline_pts"]
                obs_pts = []
                for ti in targets:
                    if ti < len(pts_list):
                        obs_pts.append(pts_list[ti])

        _draw_route_panel(
            ax_p, walls, curtains,
            centerline_pts=rd["centerline_pts"],
            court_center=rd["court_center"],
            court_radius=rd["court_radius"],
            route_col=col,
            is_ramp=is_ramp,
            iso_polys=iso_polys,
            obs_pts=obs_pts,
            extent=extent,
        )

        # 라벨
        ax_p.set_title(rid, fontsize=9, fontweight="bold",
                       pad=3, color=col)

        # 수치 주석
        ann_lines = []
        if is_ramp and ramp_metrics:
            ann_lines.append(ramp_metrics.annotation())
        else:
            ann_lines.append(f"이동 {rd['dist_3d_m']:.1f}m · 상승 {rd['rise_m']:.1f}m")
            if rd["slope_percent"] > 0:
                ratio = rd["plan_m"] / rd["rise_m"] if rd["rise_m"] > 0 else 0
                ann_lines.append(f"경사 {rd['slope_percent']:.1f}% (1:{ratio:.1f})")
        ax_p.text(0.5, -0.06, "\n".join(ann_lines),
                  transform=ax_p.transAxes,
                  ha="center", va="top", fontsize=5.5, color=col)

        # ── 가시 띠 ────────────────────────────────────────
        ax_b = fig.add_axes([left, BAND_BOT, panel_w * 0.95, band_h * 0.85])
        _draw_visibility_band(ax_b, rd.get("iso_results", []))

    # ── Critical Reading + Method Limit (우측) ────────────
    ax_cr = fig.add_axes([CR_L, SEC_BOT, CR_W, PANEL_TOP - SEC_BOT - 0.02])
    ax_cr.axis("off")
    ax_cr.set_xlim(0, 1); ax_cr.set_ylim(0, 1)

    ax_cr.text(0.0, 1.0, "CRITICAL READING",
               fontsize=9, fontweight="bold",
               transform=ax_cr.transAxes, va="top")
    yy = 0.92
    for i, sline in enumerate(crit_lines):
        wrapped = _wrap_text(sline, 26)
        n_nl = wrapped.count("\n") + 1
        ax_cr.text(0.0, yy, f"{i+1}. " + wrapped,
                   transform=ax_cr.transAxes, va="top",
                   fontsize=6.8, color="#222")
        yy -= n_nl * 0.042 + 0.028

    yy -= 0.02
    ax_cr.text(0.0, yy, "METHODOLOGICAL LIMIT",
               fontsize=8.5, fontweight="bold",
               transform=ax_cr.transAxes, va="top")
    yy -= 0.05
    for ml in METHOD_LIMITS:
        wrapped = _wrap_text(ml, 26)
        n_nl = wrapped.count("\n") + 1
        ax_cr.text(0.0, yy, "• " + wrapped,
                   transform=ax_cr.transAxes, va="top",
                   fontsize=6.2, color="#444")
        yy -= n_nl * 0.038 + 0.02

    # ── 수직 분석 단면 ─────────────────────────────────────
    ax_sec = fig.add_axes([LEFT_OVW + OVW_W + 0.01, SEC_BOT,
                            CR_L - LEFT_OVW - OVW_W - 0.03,
                            SEC_TOP - SEC_BOT])
    _draw_section(ax_sec, routes_ordered)
    ax_sec.set_title("분석 단면 — 반복 계단 → 전환 → 램프 곡선 상승",
                      fontsize=7.5, fontweight="bold", loc="left")

    return _save_all(fig, output_png, output_pdf, output_svg)
