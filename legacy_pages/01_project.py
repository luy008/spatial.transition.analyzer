"""TAB 1 — PROJECT: 새 프로젝트 / 열기 / DXF 업로드 / 저장."""
import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
import shutil
import streamlit as st
from core.models import ProjectData, DiagramSettings
from core.project_store import save_project, load_project, list_projects, autosave

SAMPLE_DATA = ROOT / "sample_data"
TEMPLATES = ROOT / "templates"
PROJECTS = ROOT / "projects"
PROJECTS.mkdir(exist_ok=True)

st.set_page_config(page_title="Project — STA", layout="wide")
st.title("📋 01. PROJECT")

# ── 탭 ───────────────────────────────────────────────────────
t_new, t_open, t_recent = st.tabs(["새 프로젝트", "프로젝트 열기", "최근 프로젝트"])

# ── 새 프로젝트 ───────────────────────────────────────────────
with t_new:
    st.subheader("새 프로젝트 만들기")
    col1, col2 = st.columns(2)
    with col1:
        template_choice = st.radio(
            "시작 방식",
            ["빈 프로젝트", "Cultural Gallery 샘플 (현재 설계)"],
            horizontal=True)
        proj_name = st.text_input("프로젝트 이름", value="My Circulation Study")
        title_en = st.text_input(
            "영문 제목",
            value=("From Repeated Stairs to a Courtyard Ramp: "
                   "Experiential Transition or Formal Device?")
            if "Gallery" in template_choice else "")
        title_ko = st.text_input("한글 제목 (개념)", value="반복되는 계단에서 중정 순환 램프로"
                                 if "Gallery" in template_choice else "")
    with col2:
        question = st.text_area(
            "설계 질문 (자유 변경 가능)",
            height=120,
            value=("하부 층에서 반복되던 계단 동선이 4층에서 5층으로 진입할 때 "
                   "중정 순환 램프로 전환되는 결정은, 최상부 전시공간으로의 실질적인 경험 전환을 "
                   "만드는가, 아니면 형태적으로만 분리된 동선 장치에 머무르는가?")
            if "Gallery" in template_choice else "")
        units = st.selectbox("도면 단위", ["mm", "m", "inch"], index=0)
        scale = st.number_input("단위 스케일 (m/unit)", value=0.001
                                if units == "mm" else 1.0, format="%.4f")

    if st.button("✅ 프로젝트 생성", type="primary"):
        if "Gallery" in template_choice:
            tpl = TEMPLATES / "current_project_template.json"
            proj = load_project(tpl) if tpl.exists() else ProjectData()
        else:
            proj = ProjectData()
        proj.project_name = proj_name
        proj.title_en = title_en
        proj.title_ko = title_ko
        proj.design_question = question
        proj.units = units
        proj.dxf_unit_scale = scale
        if proj.diagram_settings:
            proj.diagram_settings.title_en = title_en
            proj.diagram_settings.title_ko = title_ko
            proj.diagram_settings.design_question = question
        st.session_state.project = proj
        st.session_state.project_path = None
        st.session_state.dxf_entities = None
        st.success(f"프로젝트 '{proj_name}' 생성 완료")
        # 샘플 DXF 연결
        sample_dxf = SAMPLE_DATA / "Drawing1.dxf"
        if "Gallery" in template_choice and sample_dxf.exists():
            st.info(f"샘플 도면: {sample_dxf}")
            st.session_state.project.source_file = str(sample_dxf)

# ── 프로젝트 열기 ─────────────────────────────────────────────
with t_open:
    st.subheader("프로젝트 JSON 열기")
    uploaded = st.file_uploader("프로젝트 JSON 파일 업로드", type=["json"])
    if uploaded:
        try:
            d = json.loads(uploaded.read())
            proj = ProjectData.from_dict(d)
            st.session_state.project = proj
            st.session_state.project_path = None
            st.success(f"'{proj.project_name}' 열기 완료 — 경로 {len(proj.routes)}개")
        except Exception as e:
            st.error(f"파일 파싱 오류: {e}")

    st.markdown("---")
    st.subheader("샘플 프로젝트 열기")
    tpl = TEMPLATES / "current_project_template.json"
    if tpl.exists():
        if st.button("Cultural Gallery 샘플 열기"):
            proj = load_project(tpl)
            proj.source_file = str(SAMPLE_DATA / "Drawing1.dxf")
            st.session_state.project = proj
            st.session_state.project_path = str(tpl)
            st.success(f"'{proj.project_name}' 열기 완료")

# ── 최근 프로젝트 ─────────────────────────────────────────────
with t_recent:
    st.subheader("최근 프로젝트")
    plist = list_projects()
    if not plist:
        st.info("저장된 프로젝트가 없습니다. 새 프로젝트를 만드세요.")
    for p in plist[:10]:
        col1, col2 = st.columns([4, 1])
        with col1:
            st.write(f"📂 **{p.stem}** — `{p}`")
        with col2:
            if st.button("열기", key=f"open_{p}"):
                try:
                    proj = load_project(p)
                    st.session_state.project = proj
                    st.session_state.project_path = str(p)
                    st.success(f"'{proj.project_name}' 열기 완료")
                except Exception as e:
                    st.error(str(e))

# ── 현재 프로젝트 정보 + 저장 ─────────────────────────────────
st.markdown("---")
if st.session_state.project:
    proj = st.session_state.project
    st.subheader(f"현재 프로젝트: {proj.project_name}")
    col1, col2, col3 = st.columns(3)
    with col1:
        new_name = st.text_input("프로젝트 이름 수정", value=proj.project_name, key="edit_name")
        if new_name != proj.project_name:
            proj.project_name = new_name
    with col2:
        new_q = st.text_area("설계 질문 수정", value=proj.design_question, height=80, key="edit_q")
        if new_q != proj.design_question:
            proj.design_question = new_q
            if proj.diagram_settings:
                proj.diagram_settings.design_question = new_q
    with col3:
        st.metric("층 수", len(proj.floors))
        st.metric("동선 수", len(proj.routes))
        st.metric("공간 수", len(proj.spaces))

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("💾 저장"):
            path = save_project(proj)
            st.session_state.project_path = str(path)
            st.success(f"저장: {path}")
    with c2:
        if st.button("📤 JSON 다운로드 준비"):
            import json as _json
            st.download_button("⬇ JSON 다운로드",
                               data=_json.dumps(proj.to_dict(), ensure_ascii=False, indent=2),
                               file_name=f"{proj.project_name}.json",
                               mime="application/json")
    with c3:
        if st.button("🔄 초기화"):
            st.session_state.project = None
            st.session_state.dxf_entities = None
            st.session_state.analysis_results = {}
            st.rerun()
else:
    st.info("프로젝트가 열려 있지 않습니다.")
