"""TAB 3 — GEOMETRY CLASSIFICATION: 벽·커튼월·중정 분류."""
import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import io
import streamlit as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from core.dxf_loader import (get_layer_names, entity_to_linestring,
                              filter_by_x_range, get_all_linestrings)
from core.geometry_classifier import (classify_entity, auto_classify_all,
                                       GeometryClass, remove_lines_inside_void,
                                       validate_courtyard_void)
from shapely.geometry import Point

st.set_page_config(page_title="Geometry — STA", layout="wide")
st.title("🗂 03. GEOMETRY CLASSIFICATION")

if not st.session_state.get("project"):
    st.warning("01 PROJECT에서 프로젝트를 여세요.")
    st.stop()
if not st.session_state.get("dxf_entities"):
    st.warning("02 IMPORT에서 DXF를 로드하세요.")
    st.stop()

proj = st.session_state.project
entities = st.session_state.dxf_entities
scale = proj.dxf_unit_scale

# ── 레이어 분류 규칙 설정 ─────────────────────────────────────
st.subheader("레이어 분류 규칙")
st.caption("레이어를 분류 유형에 드래그하거나 직접 입력하세요. 자동 분류 후 수정할 수 있습니다.")

layers = get_layer_names(entities)
cls_names = {
    GeometryClass.OPAQUE: "🧱 불투명 벽",
    GeometryClass.CURTAIN: "🪟 투명 커튼월",
    GeometryClass.OPENING: "🚪 개구부",
    GeometryClass.COURTYARD: "⭕ 중정 void",
    GeometryClass.EXCLUDE: "🚫 제외",
    GeometryClass.UNCLASSIFIED: "❓ 미분류",
}

# 기존 분류 규칙 로드
layer_cls = proj.layer_classification
if not layer_cls:
    layer_cls = {"opaque": [], "curtain": [], "opening": [], "courtyard": [], "exclude": []}

col1, col2 = st.columns([1, 1])
with col1:
    st.write("**레이어 목록**")
    with st.expander("전체 레이어 표시", expanded=True):
        for lyr in layers:
            # 이 레이어가 어디 분류됐는지 확인
            cur_cls = "미분류"
            for k, v in layer_cls.items():
                if lyr in (v or []):
                    cur_cls = k
                    break
            st.write(f"`{lyr}` → {cur_cls}")

with col2:
    st.write("**분류 설정**")
    cls_key = st.selectbox("분류", ["opaque", "curtain", "opening", "courtyard", "exclude"])
    lyr_sel = st.multiselect(f"'{cls_key}'에 포함할 레이어", layers,
                              default=layer_cls.get(cls_key, []))
    if st.button("분류 적용"):
        layer_cls[cls_key] = lyr_sel
        proj.layer_classification = layer_cls
        st.success(f"'{cls_key}' 분류 업데이트: {len(lyr_sel)}개 레이어")

# ── 자동 분류 미리보기 ────────────────────────────────────────
st.markdown("---")
st.subheader("자동 분류 미리보기")

if proj.floors:
    sel = st.selectbox("층 선택", [f.label for f in proj.floors])
    floor = next((f for f in proj.floors if f.label == sel), proj.floors[0])
else:
    floor = None
    st.info("02 IMPORT에서 층을 지정하세요.")

if floor and st.button("분류 미리보기 생성"):
    with st.spinner("분류 렌더링 중..."):
        floor_ents = filter_by_x_range(entities, floor.xmin, floor.xmax, scale)
        color_map = {
            GeometryClass.OPAQUE: "#333",
            GeometryClass.CURTAIN: "#17BECF",
            GeometryClass.OPENING: "#27AE60",
            GeometryClass.COURTYARD: "#9B59B6",
            GeometryClass.EXCLUDE: "#EEE",
            GeometryClass.UNCLASSIFIED: "#AAA",
        }
        fig, ax = plt.subplots(figsize=(9, 9))
        layer_rules = {l: k for k, v in layer_cls.items() for l in (v or [])}
        for e, cls in auto_classify_all(floor_ents, layer_rules):
            ls = entity_to_linestring(e, scale)
            if ls and not ls.is_empty and cls != GeometryClass.EXCLUDE:
                try:
                    xs, ys = ls.xy
                    ax.plot(xs, ys, "-", color=color_map.get(cls, "#AAA"),
                            lw=0.8 if cls == GeometryClass.OPAQUE else 0.5)
                except Exception:
                    pass
        # 중정 표시
        if floor.courtyard_center:
            cx, cy = floor.courtyard_center
            theta = np.linspace(0, 2 * 3.14159, 64)
            r = floor.courtyard_radius_m
            ax.fill(cx + r*np.cos(theta), cy + r*np.sin(theta),
                    color="#EAF7F0", alpha=0.8, zorder=5)
            ax.plot(cx + r*np.cos(theta), cy + r*np.sin(theta),
                    "-", color="#17BECF", lw=1.5, zorder=6, label="중정 커튼월")
        # 범례
        for cls, col in color_map.items():
            if cls == GeometryClass.EXCLUDE:
                continue
            ax.plot([], [], "-", color=col, label=cls_names.get(cls, cls.value), lw=2)
        ax.legend(loc="upper right", fontsize=7)
        ax.set_aspect("equal")
        ax.set_title(f"{floor.label} — 형상 분류", fontsize=11)
        ax.grid(True, alpha=0.15)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, dpi=130, facecolor="white")
        plt.close(fig)
        st.image(buf.getvalue(), use_container_width=True)

# ── 중정 void 검증 ────────────────────────────────────────────
st.markdown("---")
st.subheader("중정 내부 벽 검증")
st.caption("중정 void 내부에 불투명 벽이 남아 있으면 자동으로 제거합니다.")

if floor and floor.courtyard_center:
    if st.button("중정 void 검증 실행"):
        with st.spinner("검증 중..."):
            floor_ents = filter_by_x_range(entities, floor.xmin, floor.xmax, scale)
            layer_rules = {l: k for k, v in layer_cls.items() for l in (v or [])}
            opaque_lines = []
            for e, cls in auto_classify_all(floor_ents, layer_rules):
                if cls == GeometryClass.OPAQUE:
                    ls = entity_to_linestring(e, scale)
                    if ls and not ls.is_empty:
                        opaque_lines.append(ls)
            cx, cy = floor.courtyard_center
            center = Point(cx, cy)
            ok, n = validate_courtyard_void(opaque_lines, center, floor.courtyard_radius_m)
            if ok:
                st.success(f"✅ 중정 내부 불투명 벽 0개 — 정상")
            else:
                st.warning(f"⚠ 중정 내부 불투명 벽 {n}개 — 분석 시 자동 제거됩니다")
else:
    st.info("층 및 중정 중심이 지정된 후 검증할 수 있습니다.")

# ── 분류 저장 ────────────────────────────────────────────────
if st.button("✅ 분류 설정 저장", type="primary"):
    proj.layer_classification = layer_cls
    st.success("분류 설정 저장 완료. 04 ROUTES & SPACES로 이동하세요.")
