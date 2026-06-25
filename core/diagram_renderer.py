"""A3 건축 다이어그램 렌더러 — 동일 축척 패널 + SVG/PDF/PNG 출력."""
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

from core.models import (ProjectData, RouteSpec, RouteMetrics,
                          IsovistResult, DiagramSettings)
from core.ramp_analysis import CircularRampMetrics


def setup_korean_font() -> Optional[str]:
    available = {f.name for f in fm.fontManager.ttflist}
    for name in ["Noto Sans CJK KR", "Noto Sans KR", "Malgun Gothic",
                 "AppleGothic", "NanumGothic"]:
        if name in available:
            matplotlib.rcParams["font.family"] = name
            matplotlib.rcParams["axes.unicode_minus"] = False
            return name
    matplotlib.rcParams["axes.unicode_minus"] = False
    return None


def get_common_panel_extent(geom_groups: List[List[Tuple[float, float]]],
                             padding: float = 0.12) -> float:
    """모든 경로를 중정 중심 정렬 후 공통 half-extent 계산 (동일 축척 보장)."""
    max_he = 0.0
    for pts in geom_groups:
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        he = max(abs(x - cx) for x in xs + [cx]) if xs else 1.0
        he = max(he, max(abs(y - cy) for y in ys + [cy]) if ys else 1.0)
        max_he = max(max_he, he)
    return max(max_he * (1 + padding), 3.0)


def _apply_equal_panel(ax: plt.Axes, extent: float) -> None:
    ax.set_xlim(-extent, extent)
    ax.set_ylim(-extent, extent)
    ax.set_aspect("equal")
    try:
        ax.set_box_aspect(1)
    except AttributeError:
        pass
    ax.axis("off")


def _draw_scalebar(ax: plt.Axes, extent: float, bar_len: float = 5.0) -> None:
    x0 = -extent * 0.85
    y0 = -extent * 0.88
    ax.plot([x0, x0 + bar_len], [y0, y0], "k-", lw=1.5, solid_capstyle="butt")
    ax.text(x0 + bar_len / 2, y0 - extent * 0.04, f"{bar_len:.0f} m",
            ha="center", va="top", fontsize=5.5)


def _draw_courtyard(ax: plt.Axes, center: Tuple[float, float],
                    radius_m: float, court_color: str) -> None:
    cx, cy = center
    theta = np.linspace(0, 2 * math.pi, 128)
    ring_x = cx + radius_m * np.cos(theta)
    ring_y = cy + radius_m * np.sin(theta)
    ax.fill(ring_x, ring_y, color="#EAF7F0", alpha=1.0, zorder=3)
    ax.plot(ring_x, ring_y, "-", color=court_color, lw=1.3, zorder=4)
    ax.plot(cx, cy, "+", color=court_color, ms=7, zorder=5)


def _draw_obstacles(ax: plt.Axes, obstacles: list, center: Tuple[float, float],
                    courtyard_radius: float, opaque_color: str = "#555") -> None:
    cx, cy = center
    for obs in obstacles:
        try:
            xs, ys = obs.xy
            ax.plot([x - cx for x in xs], [y - cy for y in ys],
                    "-", color=opaque_color, lw=0.7, zorder=2)
        except Exception:
            pass
    # 중정 내부 void 마스킹
    theta = np.linspace(0, 2 * math.pi, 128)
    ax.fill(courtyard_radius * np.cos(theta), courtyard_radius * np.sin(theta),
            color="#EAF7F0", alpha=1.0, zorder=5)


def _draw_isovist_band(ax_band: plt.Axes, results: List[IsovistResult],
                        colors: Tuple[str, str, str]) -> None:
    n = len(results)
    if n == 0:
        return
    keys = ["previous_visible", "courtyard_visible", "next_visible"]
    labels = ["PREVIOUS", "COURTYARD", "NEXT"]
    band_h, gap = 0.9, 0.6
    for r_idx, (key, label, col) in enumerate(zip(keys, labels, colors)):
        y_top = -(r_idx * (band_h + gap))
        ax_band.add_patch(Rectangle((0, y_top - band_h), 1, band_h,
                                     fill=False, ec="#ccc", lw=0.5))
        seg = 1.0 / (n - 1) if n > 1 else 1.0
        for i, res in enumerate(results):
            if getattr(res, key):
                ax_band.add_patch(Rectangle((i * seg - seg/2, y_top - band_h),
                                             seg, band_h, fc=col, ec="none", alpha=0.85))
        ax_band.text(-0.02, y_top - band_h / 2, label, ha="right", va="center",
                     fontsize=5, color=col)
    ax_band.set_xlim(-0.05, 1.05)
    ax_band.set_ylim(-(len(keys) * (band_h + gap)), 0.5)
    ax_band.axis("off")


def _draw_vertical_section(ax: plt.Axes, route_data: List[dict],
                            ramp_color: str, stair_color: str) -> None:
    ax.clear()
    cum_x = 0.0
    cum_z = 0.0
    for rd in route_data:
        plan = rd.get("plan_m", 5.0)
        rise = rd.get("rise_m", 3.0)
        is_ramp = rd.get("is_ramp", False)
        rid = rd.get("id", "")
        col = ramp_color if is_ramp else stair_color
        if is_ramp:
            ax.plot([cum_x, cum_x + plan], [cum_z, cum_z + rise], "-", color=col, lw=2.5)
        else:
            # 계단: 톱니 모양
            n_steps = max(1, int(rise / 0.15))
            step_w = plan / n_steps
            step_h = rise / n_steps
            xs2 = [cum_x]
            zs2 = [cum_z]
            for s in range(n_steps):
                xs2.append(xs2[-1] + step_w); zs2.append(zs2[-1])
                xs2.append(xs2[-1]); zs2.append(zs2[-1] + step_h)
            ax.plot(xs2, zs2, "-", color=col, lw=1.5)
        mid_x = cum_x + plan / 2
        ax.text(mid_x, cum_z + rise / 2 + 0.4, rid, ha="center",
                fontsize=8, fontweight="bold", color=col)
        cum_x += plan; cum_z += rise
    ax.text(cum_x + 0.5, cum_z, "TOP\nGALLERY", ha="left", va="center",
            fontsize=7, color="#333")
    ax.set_xlabel("누적 수평 이동거리 (m)", fontsize=8)
    ax.set_ylabel("누적 높이 (m)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.grid(True, alpha=0.25)
    ax.set_aspect("auto")


def render_diagram(
    routes_data: List[dict],
    project: ProjectData,
    output_png: str,
    output_pdf: str,
    output_svg: Optional[str] = None,
) -> Tuple[bool, str]:
    """범용 A3 다이어그램 렌더링. routes_data 는 각 경로의 분석 결과 포함."""
    setup_korean_font()
    ds = project.diagram_settings

    fig = plt.figure(figsize=(420 / 25.4, 297 / 25.4))
    fig.patch.set_facecolor(ds.bg_color)

    n_routes = len(routes_data)
    if n_routes == 0:
        fig.text(0.5, 0.5, "분석 경로가 없습니다.", ha="center", fontsize=14)
        _save(fig, output_png, output_pdf)
        return True, "경로 없음"

    # 레이아웃 — 상단: 제목, 중단: 패널×n_routes, 하단: 단면
    title_h = 0.13
    bottom_h = 0.22
    mid_h = 1.0 - title_h - bottom_h

    # 제목 영역
    ax_title = fig.add_axes([0.03, 1.0 - title_h, 0.70, title_h])
    ax_title.axis("off")
    ax_title.text(0.0, 0.90, ds.title_en or "Spatial Transition Analysis",
                  fontsize=11, fontweight="bold", transform=ax_title.transAxes, va="top")
    if ds.title_ko:
        ax_title.text(0.0, 0.62, ds.title_ko, fontsize=9,
                      transform=ax_title.transAxes, va="top")
    if ds.design_question:
        ax_title.text(0.0, 0.40, ds.design_question, fontsize=6.5,
                      transform=ax_title.transAxes, va="top",
                      wrap=True, color="#333")

    # 공통 패널 extent 계산
    all_pts = []
    for rd in routes_data:
        pts = rd.get("centerline_pts", [])
        cx, cy = rd.get("court_center", (0, 0))
        all_pts.append([(x - cx, y - cy) for x, y in pts])
    extent = get_common_panel_extent(all_pts, padding=0.15)

    stair_col = ds.stair_color
    ramp_col = ds.ramp_color
    court_col = ds.court_color

    panel_w = 0.68 / max(n_routes, 1)
    panel_h = mid_h * 0.82

    for i, rd in enumerate(routes_data):
        left = 0.03 + i * panel_w
        bottom = bottom_h + mid_h * 0.18
        ax = fig.add_axes([left, bottom, panel_w * 0.92, panel_h])
        cx, cy = rd.get("court_center", (0, 0))
        crad = rd.get("court_radius", 4.0)
        is_ramp = rd.get("is_ramp", False)
        col = ramp_col if is_ramp else stair_col

        # 장애물 (중정 중심 정렬)
        for obs in rd.get("obstacles", []):
            try:
                xs, ys = obs.xy
                ax.plot([x - cx for x in xs], [y - cy for y in ys],
                        "-", color="#999", lw=0.6, zorder=2)
            except Exception:
                pass
        # Isovist
        for res in rd.get("iso_results", []):
            if res.polygon_coords:
                pxs = [p[0] - cx for p in res.polygon_coords]
                pys = [p[1] - cy for p in res.polygon_coords]
                ax.fill(pxs, pys, color=col, alpha=0.12, zorder=3)
        # 중정 마스킹·커튼월
        theta = np.linspace(0, 2 * math.pi, 128)
        ax.fill(crad * np.cos(theta), crad * np.sin(theta), color="#EAF7F0", alpha=1.0, zorder=5)
        ax.plot(crad * np.cos(theta), crad * np.sin(theta), "-", color=court_col, lw=1.2, zorder=6)
        ax.plot(0, 0, "+", color=court_col, ms=6, zorder=6)
        # 경로선
        pts = rd.get("centerline_pts", [])
        if pts:
            px = [p[0] - cx for p in pts]
            py = [p[1] - cy for p in pts]
            ax.plot(px, py, "-", color=col, lw=2.0 if is_ramp else 1.5, zorder=7)
            ax.plot(px[0], py[0], "o", color=col, ms=5, zorder=8)
            ax.plot(px[-1], py[-1], "s", color=col, ms=5, zorder=8)

        _apply_equal_panel(ax, extent)
        _draw_scalebar(ax, extent, bar_len=max(2.0, round(extent * 0.3)))

        ax.set_title(rd.get("route_id", f"Route {i+1}"), fontsize=9, fontweight="bold",
                     pad=3, color=col)

        # 수치 주석
        if ds.show_annotations:
            ann = rd.get("annotation", "")
            ax.text(0.5, -0.08, ann, transform=ax.transAxes,
                    ha="center", va="top", fontsize=6, color=col)

        # 가시 띠
        band_ax = fig.add_axes([left, bottom_h + 0.005, panel_w * 0.92, mid_h * 0.14])
        iso_res = rd.get("iso_results", [])
        _draw_isovist_band(band_ax, iso_res, (ds.stair_color, court_col, ramp_col))

    # CRITICAL READING
    if ds.show_critical_reading:
        ax_cr = fig.add_axes([0.72, bottom_h + 0.04, 0.26, mid_h + title_h - 0.08])
        ax_cr.axis("off")
        ax_cr.text(0.0, 1.0, "CRITICAL READING", fontsize=8, fontweight="bold",
                   transform=ax_cr.transAxes, va="top")
        cr_texts = _build_critical_reading(routes_data, project)
        for idx, txt in enumerate(cr_texts):
            ax_cr.text(0.0, 0.82 - idx * 0.28, f"{idx+1}. {txt}",
                       transform=ax_cr.transAxes, va="top",
                       fontsize=6.5, wrap=True, color="#222")

    # 수직 분석 단면
    if ds.show_section:
        ax_sec = fig.add_axes([0.03, 0.01, 0.65, bottom_h - 0.015])
        section_data = [{"id": rd.get("route_id", "?"),
                         "plan_m": rd.get("plan_m", 5.0),
                         "rise_m": rd.get("rise_m", 3.0),
                         "is_ramp": rd.get("is_ramp", False)}
                        for rd in routes_data]
        _draw_vertical_section(ax_sec, section_data, ramp_col, stair_col)
        ax_sec.set_title("분석 단면 — 계단 → 램프 → 최상부",
                          fontsize=8, fontweight="bold", loc="left")

    # 방법론 한계
    if ds.show_method_limit:
        ax_ml = fig.add_axes([0.72, 0.01, 0.26, bottom_h - 0.01])
        ax_ml.axis("off")
        ax_ml.text(0.0, 1.0, "METHODOLOGICAL LIMIT", fontsize=7, fontweight="bold",
                   transform=ax_ml.transAxes, va="top")
        limits = [
            "2차원 Isovist는 램프에서의 실제 단면 경험과 신체적 피로를 평면적 가시관계로 환원한다.",
            "관찰점의 눈높이 상승과 3차원 공간 전환을 2D 분석으로 완전히 재현할 수 없다.",
        ]
        for ii, lt in enumerate(limits):
            ax_ml.text(0.0, 0.75 - ii * 0.35, f"• {lt}", transform=ax_ml.transAxes,
                       va="top", fontsize=5.5, wrap=True, color="#444")

    ok_png, ok_pdf = _save(fig, output_png, output_pdf)
    if output_svg:
        try:
            fig.savefig(output_svg, format="svg", facecolor=ds.bg_color)
        except Exception:
            pass
    return ok_png and ok_pdf, ""


def _build_critical_reading(routes_data: List[dict], project: ProjectData) -> List[str]:
    ramp_routes = [r for r in routes_data if r.get("is_ramp")]
    stair_routes = [r for r in routes_data if not r.get("is_ramp")]
    if not ramp_routes:
        return ["분석 완료 후 자동 생성됩니다."]
    rr = ramp_routes[0]
    st_mean = (sum(r.get("dist_3d_m", 0) for r in stair_routes) /
               max(len(stair_routes), 1))
    s1 = (f"하부 계단은 평균 {st_mean:.1f}m의 직접적인 상승을 반복한다. "
          f"반면 {rr.get('route_id', 'R1')}은 중정을 {rr.get('rotation_deg', 360):.0f}° "
          f"순환하며 약 {rr.get('dist_3d_m', 30.0):.1f}m의 이동을 형성한다.")
    ev = rr.get("visibility_events", {})
    court = ev.get("courtyard_visibility_duration_percent")
    nxt = ev.get("next_space_first_visible_percent")
    court_str = f"{court:.0f}%" if court is not None else "—"
    nxt_str = f"{nxt:.0f}%" if nxt is not None else "알 수 없음"
    s2 = (f"중정은 이동 과정의 {court_str} 동안 지속적으로 인지되지만, "
          f"다음 공간은 진행률 {nxt_str}에서 처음 나타난다.")
    slope = rr.get("slope_percent", 0)
    s3 = (f"약 {slope:.1f}%의 경사와 {rr.get('dist_3d_m', 30.0):.0f}m의 긴 순환 동선이 "
          f"최상부 전시공간의 경험적 전환으로 충분히 이어지는지는 별도의 비판적 판단이 필요하다.")
    return [s1, s2, s3]


def _save(fig: plt.Figure, png: str, pdf: str) -> Tuple[bool, bool]:
    os.makedirs(Path(png).parent, exist_ok=True)
    os.makedirs(Path(pdf).parent, exist_ok=True)
    ok_png = ok_pdf = False
    try:
        fig.savefig(png, dpi=200, facecolor="white", bbox_inches="tight")
        ok_png = True
    except Exception as e:
        print(f"PNG 저장 실패: {e}")
    try:
        from matplotlib.backends.backend_pdf import PdfPages
        with PdfPages(pdf) as pp:
            pp.savefig(fig, facecolor="white", bbox_inches="tight")
        ok_pdf = True
    except Exception as e:
        print(f"PDF 저장 실패: {e}")
    plt.close(fig)
    return ok_png, ok_pdf
