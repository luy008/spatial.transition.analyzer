"""공통 데이터 모델 — 프로젝트·형상·동선·분석 결과."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum
import math


class GeometryClass(str, Enum):
    OPAQUE = "opaque"
    CURTAIN = "curtain"
    OPENING = "opening"
    COURTYARD = "courtyard"
    WALKABLE = "walkable"
    EXCLUDE = "exclude"
    SLAB = "slab"
    RAILING = "railing"
    UNCLASSIFIED = "unclassified"


class RouteType(str, Enum):
    STAIR = "stair"
    RAMP = "ramp"
    CORRIDOR = "corridor"
    ELEVATOR = "elevator"
    ESCALATOR = "escalator"
    OTHER = "other"


@dataclass
class FloorBounds:
    level_id: str
    label: str
    xmin: float
    ymin: float
    xmax: float
    ymax: float
    courtyard_center: Optional[Tuple[float, float]] = None
    courtyard_radius_m: float = 4.0

    def to_dict(self) -> dict:
        return {
            "level_id": self.level_id, "label": self.label,
            "xmin": self.xmin, "ymin": self.ymin,
            "xmax": self.xmax, "ymax": self.ymax,
            "courtyard_center": list(self.courtyard_center) if self.courtyard_center else None,
            "courtyard_radius_m": self.courtyard_radius_m,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FloorBounds":
        cc = d.get("courtyard_center")
        return cls(
            level_id=d["level_id"], label=d.get("label", d["level_id"]),
            xmin=d["xmin"], ymin=d["ymin"], xmax=d["xmax"], ymax=d["ymax"],
            courtyard_center=tuple(cc) if cc else None,
            courtyard_radius_m=d.get("courtyard_radius_m", 4.0))


@dataclass
class RouteSpec:
    route_id: str
    route_type: RouteType
    source_level: str
    destination_level: str
    rise_m: float
    width_m: float
    control_points: List[Tuple[float, float]] = field(default_factory=list)
    direction: str = "ccw"
    is_circular: bool = False
    circular_center: Optional[Tuple[float, float]] = None
    circular_radius_m: float = 4.75
    circular_rotation_deg: float = 360.0
    circular_start_angle_deg: float = 0.0
    previous_space_id: Optional[str] = None
    next_space_id: Optional[str] = None
    courtyard_related: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "route_id": self.route_id, "route_type": self.route_type.value,
            "source_level": self.source_level, "destination_level": self.destination_level,
            "rise_m": self.rise_m, "width_m": self.width_m,
            "control_points": [list(p) for p in self.control_points],
            "direction": self.direction, "is_circular": self.is_circular,
            "circular_center": list(self.circular_center) if self.circular_center else None,
            "circular_radius_m": self.circular_radius_m,
            "circular_rotation_deg": self.circular_rotation_deg,
            "circular_start_angle_deg": self.circular_start_angle_deg,
            "previous_space_id": self.previous_space_id,
            "next_space_id": self.next_space_id,
            "courtyard_related": self.courtyard_related, "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RouteSpec":
        cc = d.get("circular_center")
        return cls(
            route_id=d["route_id"], route_type=RouteType(d.get("route_type", "other")),
            source_level=d["source_level"], destination_level=d["destination_level"],
            rise_m=float(d.get("rise_m", 3.0)), width_m=float(d.get("width_m", 1.5)),
            control_points=[tuple(p) for p in d.get("control_points", [])],
            direction=d.get("direction", "ccw"), is_circular=d.get("is_circular", False),
            circular_center=tuple(cc) if cc else None,
            circular_radius_m=float(d.get("circular_radius_m", 4.75)),
            circular_rotation_deg=float(d.get("circular_rotation_deg", 360.0)),
            circular_start_angle_deg=float(d.get("circular_start_angle_deg", 0.0)),
            previous_space_id=d.get("previous_space_id"),
            next_space_id=d.get("next_space_id"),
            courtyard_related=d.get("courtyard_related", False),
            notes=d.get("notes", ""))


@dataclass
class SpaceSpec:
    space_id: str
    label: str
    polygon_points: List[Tuple[float, float]] = field(default_factory=list)
    is_courtyard: bool = False
    level_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {"space_id": self.space_id, "label": self.label,
                "polygon_points": [list(p) for p in self.polygon_points],
                "is_courtyard": self.is_courtyard, "level_id": self.level_id}

    @classmethod
    def from_dict(cls, d: dict) -> "SpaceSpec":
        return cls(space_id=d["space_id"], label=d.get("label", d["space_id"]),
                   polygon_points=[tuple(p) for p in d.get("polygon_points", [])],
                   is_courtyard=d.get("is_courtyard", False), level_id=d.get("level_id"))


@dataclass
class AnalysisSettings:
    n_sample_points: int = 11
    isovist_rays: int = 720
    isovist_max_dist_m: float = 30.0
    min_valid_isovist_area_m2: float = 1.0
    courtyard_visible_threshold: float = 0.05
    ramp_speed_mps: float = 0.8
    stair_speed_mps: float = 0.5
    stair_riser_height_m: float = 0.15
    stair_tread_depth_m: float = 0.30
    analysis_domain_radius_m: float = 18.0

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "AnalysisSettings":
        s = cls()
        for k, v in d.items():
            if hasattr(s, k):
                setattr(s, k, v)
        return s


@dataclass
class DiagramSettings:
    template: str = "sequence_focus"
    panel_size_mode: str = "equal"
    panel_scale_mode: str = "equal"
    title_en: str = ""
    title_ko: str = ""
    design_question: str = ""
    font_size_pt: float = 8.0
    line_width_pt: float = 0.8
    bg_color: str = "#FFFFFF"
    stair_color: str = "#2980B9"
    ramp_color: str = "#C0392B"
    court_color: str = "#17BECF"
    show_annotations: bool = True
    show_section: bool = True
    show_critical_reading: bool = True
    show_method_limit: bool = True
    page_width_mm: float = 420.0
    page_height_mm: float = 297.0

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "DiagramSettings":
        s = cls()
        for k, v in d.items():
            if hasattr(s, k):
                setattr(s, k, v)
        return s


@dataclass
class RouteMetrics:
    route_id: str
    plan_distance_m: float = 0.0
    dist_3d_m: float = 0.0
    rise_m: float = 0.0
    slope_percent: float = 0.0
    slope_ratio: float = 0.0
    slope_angle_deg: float = 0.0
    rotation_deg: float = 0.0
    cumulative_turn_deg: float = 0.0
    curve_ratio: float = 0.0
    est_time_s: float = 0.0
    dist_per_rise_m: float = 0.0

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class IsovistResult:
    progress_percent: float
    area_m2: float = 0.0
    perimeter_m: float = 0.0
    mean_dist_m: float = 0.0
    max_dist_m: float = 0.0
    previous_visible: bool = False
    courtyard_visible: bool = False
    next_visible: bool = False
    polygon_coords: List[Tuple[float, float]] = field(default_factory=list)


@dataclass
class ProjectData:
    project_name: str = "New Project"
    source_file: str = ""
    units: str = "mm"
    dxf_unit_scale: float = 0.001
    title_en: str = ""
    title_ko: str = ""
    design_question: str = ""
    floors: List[FloorBounds] = field(default_factory=list)
    routes: List[RouteSpec] = field(default_factory=list)
    spaces: List[SpaceSpec] = field(default_factory=list)
    layer_classification: Dict[str, List[str]] = field(default_factory=dict)
    analysis_settings: AnalysisSettings = field(default_factory=AnalysisSettings)
    diagram_settings: DiagramSettings = field(default_factory=DiagramSettings)

    def to_dict(self) -> dict:
        return {
            "project_name": self.project_name,
            "source_file": self.source_file,
            "units": self.units,
            "dxf_unit_scale": self.dxf_unit_scale,
            "title_en": self.title_en,
            "title_ko": self.title_ko,
            "design_question": self.design_question,
            "floors": [f.to_dict() for f in self.floors],
            "routes": [r.to_dict() for r in self.routes],
            "spaces": [s.to_dict() for s in self.spaces],
            "layer_classification": self.layer_classification,
            "analysis_settings": self.analysis_settings.to_dict(),
            "diagram_settings": self.diagram_settings.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectData":
        p = cls(
            project_name=d.get("project_name", "Untitled"),
            source_file=d.get("source_file", ""),
            units=d.get("units", "mm"),
            dxf_unit_scale=float(d.get("dxf_unit_scale", 0.001)),
            title_en=d.get("title_en", ""),
            title_ko=d.get("title_ko", ""),
            design_question=d.get("design_question", ""),
            layer_classification=d.get("layer_classification", {}),
        )
        p.floors = [FloorBounds.from_dict(f) for f in d.get("floors", [])]
        p.routes = [RouteSpec.from_dict(r) for r in d.get("routes", [])]
        p.spaces = [SpaceSpec.from_dict(s) for s in d.get("spaces", [])]
        p.analysis_settings = AnalysisSettings.from_dict(d.get("analysis_settings", {}))
        p.diagram_settings = DiagramSettings.from_dict(d.get("diagram_settings", {}))
        return p
