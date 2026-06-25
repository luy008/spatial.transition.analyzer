"""01 입력 — 프로젝트 시작: 예제 / 새 DXF / 저장된 프로젝트."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
import streamlit as st


def _load_cultural_gallery() -> dict:
    proj_dir = ROOT / "projects" / "cultural_gallery"
    p = proj_dir / "project.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8-sig"))
    for fname in ("routes", "spaces", "levels", "analysis_settings"):
        fp = proj_dir / f"{fname}.json"
        if fp.exists():
            data[fname] = json.loads(fp.read_text(encoding="utf-8-sig"))
    return data


def _go_analyze():
    st.session_state.analysis_complete = False
    st.switch_page("pages/02_verify_analyze.py")


st.title("01 입력")
st.markdown("---")

# ── 프로젝트 시작 옵션 ────────────────────────────────────────
c1, c2, c3 = st.columns(3)

with c1:
    st.markdown("#### 예제 프로젝트")
    st.caption("Cultural Gallery — 하부계단 S1·S2·S3 vs 중정 순환 램프 R1")
    if st.button("예제 불러오기", type="primary", use_container_width=True, key="btn_example"):
        data = _load_cultural_gallery()
        if data:
            st.session_state.project_source  = "example"
            st.session_state.project_data    = data
            st.session_state.project_loaded  = True
            st.session_state.analysis_recipe = data.get("analysis_recipe", "circulation_transition")
            st.session_state.project_id      = "cultural_gallery"
            st.success("Cultural Gallery 프로젝트 로드 완료")
        else:
            st.error("예제 파일 없음 (projects/cultural_gallery/)")

with c2:
    st.markdown("#### 새 DXF 업로드")
    st.caption("새 DXF 도면으로 신규 프로젝트 시작")
    if st.button("새 프로젝트 시작", use_container_width=True, key="btn_new"):
        st.session_state.project_source  = "new_dxf"
        st.session_state.project_data    = None
        st.session_state.project_loaded  = False
        st.session_state.analysis_complete = False

with c3:
    st.markdown("#### 저장된 프로젝트")
    st.caption("이전에 저장한 project.json 불러오기")
    if st.button("프로젝트 열기", use_container_width=True, key="btn_open"):
        st.session_state.project_source = "saved_project"

project_source = st.session_state.get("project_source", "example")

st.markdown("---")

# ══════════════════════════════════════════════════════════════
# 예제 프로젝트
# ══════════════════════════════════════════════════════════════
if project_source == "example":
    if st.session_state.get("project_data") is None:
        data = _load_cultural_gallery()
        if data:
            st.session_state.project_data    = data
            st.session_state.project_loaded  = True
            st.session_state.project_id      = "cultural_gallery"
            st.session_state.analysis_recipe = data.get("analysis_recipe", "circulation_transition")

    pd = st.session_state.project_data or {}
    if not pd:
        st.warning("위 버튼으로 예제를 먼저 불러오세요.")
        st.stop()

    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.subheader("프로젝트 정보")
        st.text_input("프로젝트 명", value=pd.get("project_name", ""),
                      disabled=True, key="pi_name")
        st.text_input("제목 (영문)", value=pd.get("title_en", ""),
                      disabled=True, key="pi_title_en")
        st.text_input("제목 (한글)", value=pd.get("title_ko", ""),
                      disabled=True, key="pi_title_ko")
        new_q     = st.text_area("설계 질문",   value=pd.get("design_question", ""),
                                 height=100, key="pi_question")
        new_intent = st.text_area("설계 의도",  value=pd.get("design_intent", ""),
                                  height=100, key="pi_intent")
        new_crit  = st.text_area("지도교수 질문", value=pd.get("professor_critique", ""),
                                 height=70,  key="pi_critique")
        if st.button("변경 사항 적용", key="btn_apply"):
            st.session_state.project_data["design_question"]  = new_q
            st.session_state.project_data["design_intent"]    = new_intent
            st.session_state.project_data["professor_critique"] = new_crit
            st.success("변경 사항 적용됨")

    with col_right:
        st.subheader("DXF 파일")
        src = pd.get("source_file", "sample_data/Drawing1.dxf")
        dxf_path = ROOT / src
        if dxf_path.exists():
            st.success(f"확인됨: `{src}`")
            st.metric("파일 크기", f"{dxf_path.stat().st_size // 1024} KB")
        else:
            st.error(f"파일 없음: `{src}`")
            st.info("`sample_data/` 폴더에 Drawing1.dxf를 복사하세요.")

        st.subheader("경로 요약")
        routes = pd.get("routes", {})
        if routes:
            rows = [{"경로": rid, "유형": r.get("circulation_type", "-"),
                     "출발층": r.get("source_level", "-"),
                     "도착층": r.get("destination_level", "-"),
                     "상승(m)": r.get("rise_m", "-")}
                    for rid, r in routes.items()]
            st.dataframe(rows, use_container_width=True, hide_index=True)

        st.subheader("분석 레시피")
        st.code(pd.get("analysis_recipe", "circulation_transition"))

    st.markdown("---")
    if dxf_path.exists():
        if st.button("도면 검증 및 분석 시작", type="primary",
                     use_container_width=True, key="btn_go_example"):
            _go_analyze()
    else:
        st.button("도면 검증 및 분석 시작", disabled=True,
                  use_container_width=True, help="DXF 파일이 없습니다.")

# ══════════════════════════════════════════════════════════════
# 새 DXF 업로드
# ══════════════════════════════════════════════════════════════
elif project_source == "new_dxf":
    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.subheader("프로젝트 정보 입력")
        proj_name  = st.text_input("프로젝트 명",
                                   placeholder="예: 도시문화복합시설 동선 분석",
                                   key="np_name")
        title_en   = st.text_input("제목 (영문)", key="np_title_en")
        title_ko   = st.text_input("제목 (한글)", key="np_title_ko")
        design_q   = st.text_area("설계 질문", height=90, key="np_question")
        design_int = st.text_area("설계 의도", height=90, key="np_intent")
        prof_crit  = st.text_area("지도교수 질문", height=60, key="np_critique")

    with col_right:
        st.subheader("DXF 파일 업로드")
        uploaded = st.file_uploader("DXF 파일 선택", type=["dxf"], key="np_dxf_upload")
        if uploaded:
            tmp_path = ROOT / "exports" / "_tmp_upload.dxf"
            tmp_path.parent.mkdir(exist_ok=True)
            tmp_path.write_bytes(uploaded.read())
            st.success(f"업로드 완료: `{uploaded.name}` "
                       f"({tmp_path.stat().st_size // 1024} KB)")
            try:
                from core.dxf_loader import load_dxf
                doc, entities = load_dxf(str(tmp_path))
                st.metric("엔티티 수", len(entities))
                layers = sorted(set(e["layer"] for e in entities))
                with st.expander(f"레이어 목록 ({len(layers)}개)", expanded=False):
                    st.write(layers)
                st.session_state.dxf_entities = entities
                st.session_state.dxf_doc      = doc
            except Exception as ex:
                st.error(f"DXF 파싱 오류: {ex}")

    st.markdown("---")
    can_start = bool(proj_name and (uploaded or st.session_state.get("dxf_entities")))
    if st.button("도면 검증 및 분석 시작", type="primary",
                 disabled=not can_start, use_container_width=True, key="btn_go_new"):
        st.session_state.project_data = {
            "project_name":      proj_name,
            "title_en":          title_en,
            "title_ko":          title_ko,
            "design_question":   design_q,
            "design_intent":     design_int,
            "professor_critique": prof_crit,
            "source_file":       "exports/_tmp_upload.dxf",
            "routes":  {},
            "spaces":  {},
            "levels":  {},
            "analysis_settings": {},
        }
        st.session_state.project_loaded  = True
        st.session_state.project_id      = proj_name or "new_project"
        st.session_state.analysis_recipe = "custom"
        _go_analyze()
    if not can_start:
        st.caption("프로젝트 명과 DXF 파일이 필요합니다.")

# ══════════════════════════════════════════════════════════════
# 저장된 프로젝트 열기
# ══════════════════════════════════════════════════════════════
elif project_source == "saved_project":
    st.subheader("저장된 프로젝트 열기")
    uploaded_proj = st.file_uploader("project.json 선택", type=["json"],
                                     key="open_proj_json")
    if uploaded_proj:
        try:
            proj_data = json.loads(uploaded_proj.read().decode("utf-8-sig"))
            st.success(f"로드: {proj_data.get('project_name', '(무제)')}")

            for fname in ("routes", "spaces", "levels", "analysis_settings"):
                sub = st.file_uploader(f"{fname}.json (선택)", type=["json"],
                                       key=f"open_{fname}")
                if sub:
                    try:
                        proj_data[fname] = json.loads(sub.read().decode("utf-8-sig"))
                        st.success(f"{fname}.json 로드됨")
                    except Exception as e:
                        st.warning(f"{fname}.json 파싱 실패: {e}")

            dxf_file = st.file_uploader("DXF 파일 (선택)", type=["dxf"], key="open_dxf")
            if dxf_file:
                tmp = ROOT / "exports" / "_open_project.dxf"
                tmp.parent.mkdir(exist_ok=True)
                tmp.write_bytes(dxf_file.read())
                proj_data["source_file"] = "exports/_open_project.dxf"
                st.success(f"DXF 업로드: {dxf_file.name}")

            if st.button("이 프로젝트로 분석 시작", type="primary",
                         use_container_width=True, key="btn_go_open"):
                st.session_state.project_data    = proj_data
                st.session_state.project_loaded  = True
                st.session_state.project_id      = proj_data.get("project_name", "loaded")
                st.session_state.analysis_recipe = proj_data.get("analysis_recipe",
                                                                   "circulation_transition")
                _go_analyze()
        except Exception as e:
            st.error(f"파일 파싱 실패: {e}")
    else:
        st.info("project.json 파일을 업로드하면 기존 프로젝트를 불러올 수 있습니다.")
