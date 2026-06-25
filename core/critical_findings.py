"""CriticalFinding 및 EvidenceReference 데이터 모델 + 품질 검사."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

GENERIC_CLAIM_PATTERNS = [
    "분석 결과 설계가",
    "VGA가 설계를 검증",
    "램프가 더 좋은 경험",
    "Isovist에는 한계가 있다",
    "중정의 접근성이 높다",
    "가시성이 높게 나타났다",
    "잘 작동한다",
    "효과적이다",
]


@dataclass
class EvidenceReference:
    metric_name: str
    value: float | str
    unit: str
    route_id: Optional[str] = None
    sample_id: Optional[str] = None
    progress_percent: Optional[float] = None
    geometry_ids: List[str] = field(default_factory=list)


@dataclass
class CriticalFinding:
    finding_id: str
    title: str
    observed_result: str
    related_geometry: str
    methodological_reduction: str
    interpretive_risk: str
    design_implication: str
    evidence: List[EvidenceReference] = field(default_factory=list)
    confidence: str = "medium"

    def validate(self) -> List[str]:
        """품질 검사. 위반 항목 목록 반환."""
        warnings = []
        for pattern in GENERIC_CLAIM_PATTERNS:
            for text in [self.observed_result, self.design_implication]:
                if pattern in text:
                    warnings.append(f"generic_claim: '{pattern}' in '{self.finding_id}'")
        if not self.evidence:
            warnings.append(f"no_evidence: '{self.finding_id}' has no EvidenceReference")
        if not self.methodological_reduction:
            warnings.append(f"no_reduction: '{self.finding_id}' missing methodological_reduction")
        if not any(e.route_id or e.sample_id for e in self.evidence):
            warnings.append(f"no_geometry_id: '{self.finding_id}' evidence has no route_id/sample_id")
        return warnings


def generate_findings_from_analysis(
    analysis_results: dict,
    project_name: str = "",
) -> List[CriticalFinding]:
    """분석 결과에서 CriticalFinding 목록 생성. 최대 3개."""
    findings = []

    # F-01: Movement Cost
    geom = analysis_results.get("geometry", [])
    ramp_rows = [r for r in geom if r.get("유형") == "ramp"]
    stair_rows = [r for r in geom if r.get("유형") == "stair"]
    if ramp_rows and stair_rows:
        r1 = ramp_rows[0]
        st_mean_dist = sum(r.get("3D 이동거리(m)", 0) for r in stair_rows) / len(stair_rows)
        r1_dist = r1.get("3D 이동거리(m)", 0)
        diff = r1_dist - st_mean_dist
        slope = r1.get("경사(%)", 0)
        f = CriticalFinding(
            finding_id="F-01",
            title="이동 비용 차이",
            observed_result=(
                f"R1은 하부 계단 평균({st_mean_dist:.1f}m)보다 {diff:.1f}m 더 긴 "
                f"{r1_dist:.1f}m 이동을 요구하며, 경사율은 {slope:.1f}%다."
            ),
            related_geometry="R1 중정 순환 램프 중심선 (반지름 4.75m, 360° 회전, 상승 3.0m)",
            methodological_reduction=(
                "고정된 보행속도(램프 0.8m/s, 계단 0.5m/s)를 적용하며, "
                "관람자 연령·경사 피로·정지 관람·혼잡을 반영하지 않는다."
            ),
            interpretive_risk=(
                "계산된 시간 차이는 물리적 비용은 보여주지만, "
                "긴 램프가 피로를 만드는지 또는 느린 전환 경험을 만드는지 구별하지 못한다."
            ),
            design_implication=(
                f"램프는 물리적으로 더 긴 동선을 요구하지만, "
                f"그 비용이 경험적 전환을 정당화하는지는 분석이 판단할 수 없다."
            ),
            evidence=[
                EvidenceReference("3D 이동거리", r1_dist, "m", route_id="R1"),
                EvidenceReference("계단 평균 이동거리", st_mean_dist, "m", route_id="stair_avg"),
                EvidenceReference("경사율", slope, "%", route_id="R1"),
            ],
            confidence="high",
        )
        findings.append(f)

    # F-02: Visual Transformation (Isovist)
    for route_id in ["R1"]:
        iso = analysis_results.get(f"iso_{route_id}", {})
        results = iso.get("results", [])
        events = iso.get("events", {})
        if results:
            court_dur = events.get("courtyard_visibility_duration_percent", 0)
            next_first = events.get("next_space_first_visible_percent")
            areas = [r.get("area_m2", 0) if isinstance(r, dict) else getattr(r, "area_m2", 0)
                     for r in results]
            cv = (float(__import__("numpy").std(areas)) / float(__import__("numpy").mean(areas)) * 100
                  if areas and float(__import__("numpy").mean(areas)) > 0 else 0)
            f2 = CriticalFinding(
                finding_id="F-02",
                title="시야 변화와 중정 가시성",
                observed_result=(
                    f"R1 진행 구간의 {court_dur:.0f}% 동안 중정이 가시 상태로 판정된다. "
                    f"Isovist 면적 변동계수는 {cv:.0f}%이며, "
                    f"다음 공간(최상부 전시실)은 진행률 "
                    f"{f'{next_first:.0f}%' if next_first is not None else '미검출'}에서 처음 나타난다."
                ),
                related_geometry=(
                    "중정 커튼월(반지름 4.0m 원형), R1 관찰점 11개, "
                    "최상부 전시실 polygon"
                ),
                methodological_reduction=(
                    f"2D Isovist는 중정 커튼월을 완전 투명 경계로 처리하고, "
                    f"3m 상승하는 관찰자의 눈높이를 하나의 수평 평면으로 환원한다. "
                    f"가시성은 이진(보임/안보임)으로 판정하며, "
                    f"가시 면적 {analysis_results.get('visibility_threshold_m2', 0.05):.3f}m² 초과 시 '가시'로 분류한다."
                ),
                interpretive_risk=(
                    "슬래브 가장자리·난간·커튼월 프레임·반사에 따라 "
                    "중정의 인지 강도가 구간별로 달라질 수 있으므로, "
                    "이 분석은 중정 가시 지속성을 과대평가할 가능성이 있다."
                ),
                design_implication=(
                    f"중정이 진행 구간의 {court_dur:.0f}% 동안 보인다는 것은 "
                    f"설계 의도(상승 방향의 기준점)와 부합하는 결과이지만, "
                    f"실제 인지 강도의 단계적 변화는 분석이 포착하지 못한다."
                ),
                evidence=[
                    EvidenceReference("중정 가시 지속율", court_dur, "%", route_id="R1"),
                    EvidenceReference("Isovist 면적 변동계수", cv, "%", route_id="R1"),
                    EvidenceReference("다음공간 최초 가시 진행률",
                                      next_first if next_first is not None else -1,
                                      "%", route_id="R1"),
                ],
                confidence="medium",
            )
            findings.append(f2)
            break

    # F-03: Directional Transformation
    dir_data = analysis_results.get("directional", {})
    if dir_data:
        rot = dir_data.get("R1", {}).get("cumulative_rotation_deg", 360.0)
        tortuosity = dir_data.get("R1", {}).get("tortuosity", 0)
        f3 = CriticalFinding(
            finding_id="F-03",
            title="방향 전환과 이동 형식",
            observed_result=(
                f"R1의 누적 회전각은 {rot:.0f}°이며 tortuosity는 {tortuosity:.2f}다. "
                f"하부 계단(S1·S2·S3)의 누적 회전각 합산과 비교했을 때 "
                f"R1은 단일 구간에서 더 큰 방향 변화를 형성한다."
            ),
            related_geometry="R1 중정 순환 램프 중심선 (360° 원호, 반지름 4.75m)",
            methodological_reduction=(
                "2D 평면의 누적 회전각은 이동 방향의 수평 변화만 포착하며, "
                "3m 상승에 따른 수직 방향 변화는 포함하지 않는다."
            ),
            interpretive_risk=(
                "누적 회전각이 크다는 것은 방향 변화의 양적 특성이지, "
                "그 변화가 신체적으로 어떻게 경험되는지는 판단하지 못한다."
            ),
            design_implication=(
                f"R1의 {rot:.0f}° 회전은 하부 계단과 분명히 다른 이동 형식을 형성하지만, "
                f"그 차이가 공간 경험의 전환으로 이어지는지는 별도의 판단이 필요하다."
            ),
            evidence=[
                EvidenceReference("누적 회전각", rot, "°", route_id="R1"),
                EvidenceReference("tortuosity", tortuosity, "", route_id="R1"),
            ],
            confidence="medium",
        )
        findings.append(f3)

    return findings[:3]
