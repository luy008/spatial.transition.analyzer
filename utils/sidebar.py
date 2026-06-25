"""공통 사이드바 + 세션 상태 유틸리티."""
import streamlit as st

SESSION_DEFAULTS: dict = {
    # 프로젝트 출처: "example" | "new_dxf" | "saved_project"
    "project_source": "example",
    "project_id": None,
    "project_data": None,
    "project_loaded": False,
    # 분석 설정
    "analysis_recipe": "circulation_transition",
    "analysis_results": {},
    "analysis_complete": False,
    # DXF
    "dxf_entities": None,
    "dxf_doc": None,
    # 출력
    "diagram_paths": {},
    "quality_warnings": [],
}


def init_session() -> None:
    """세션 상태 초기값 설정 (한 번만)."""
    for k, v in SESSION_DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v
    # 과거 세션의 레거시 모드 키 제거 (오류·잔여 UI 방지)
    for legacy in (
        "app_mode", "start_mode", "analysis_done",
        "analysis_mode", "assignment_mode", "new_design_mode",
        "is_assignment", "is_new_design", "task_mode",
    ):
        st.session_state.pop(legacy, None)


def render_sidebar() -> None:
    """사이드바 — 프로젝트·입력·분석 상태 표시 (내비게이션 제외)."""
    with st.sidebar:
        pd = st.session_state.get("project_data")

        # ── 입력 상태 ─────────────────────────────────────────
        st.markdown("**입력 상태**")
        loaded = st.session_state.get("project_loaded", False)
        dxf_path_ok = False
        if pd:
            from pathlib import Path
            src = pd.get("source_file", "")
            if src:
                try:
                    from pages import _ROOT_PLACEHOLDER  # noqa
                except Exception:
                    pass
                try:
                    root = Path(__file__).parent.parent
                    dxf_path_ok = (root / src).exists()
                except Exception:
                    pass
        _check("DXF 파일", dxf_path_ok)
        _check("프로젝트 로드", loaded)

        st.markdown("---")

        # ── 분석 상태 ─────────────────────────────────────────
        st.markdown("**분석 상태**")
        results = st.session_state.get("analysis_results", {})
        dxf_verified = bool(results) and not results.get("dxf_error")
        analysis_ok = st.session_state.get("analysis_complete", False)
        diagram_ok = bool(st.session_state.get("diagram_paths", {}).get("png"))
        _check("도면 검증", dxf_verified)
        _check("분석 완료", analysis_ok)
        _check("출력 준비", diagram_ok)

        st.markdown("---")
        st.caption("No AI API · Local only · v2.1")


def _check(label: str, ok: bool) -> None:
    icon = "✓" if ok else "—"
    color = "green" if ok else "#999"
    st.markdown(
        f"<span style='color:{color}'>{icon}</span> {label}",
        unsafe_allow_html=True,
    )
