"""프로젝트 저장/불러오기 단위 테스트."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import ProjectData, FloorBounds, RouteSpec, RouteType
from core.project_store import save_project, load_project


def _sample_project():
    proj = ProjectData(project_name="test_proj")
    proj.title_en = "Test Project"
    proj.title_ko = "테스트 프로젝트"
    proj.floors = [
        FloorBounds(level_id="4F", label="4층", xmin=140000, ymin=60000,
                    xmax=180000, ymax=90000,
                    courtyard_center=(160000.0, 74000.0), courtyard_radius_m=4.0)
    ]
    proj.routes = [
        RouteSpec(route_id="R1", route_type=RouteType.RAMP,
                  source_level="4F", destination_level="5F",
                  rise_m=3.0, width_m=1.5,
                  is_circular=True,
                  circular_center=(160000.0, 74000.0), circular_radius_m=4.75,
                  circular_rotation_deg=360.0)
    ]
    return proj


def test_roundtrip_json():
    proj = _sample_project()
    d = proj.to_dict()
    proj2 = ProjectData.from_dict(d)
    assert proj2.project_name == proj.project_name
    assert proj2.title_en == proj.title_en
    assert len(proj2.floors) == 1
    assert len(proj2.routes) == 1
    assert proj2.routes[0].circular_rotation_deg == 360.0
    assert proj2.routes[0].rise_m == 3.0


def test_save_load_file(tmp_path):
    proj = _sample_project()
    # save_project는 기본 경로에 저장하므로 tmp_path 기반 저장은 직접 json으로 테스트
    d = proj.to_dict()
    fpath = tmp_path / "test.json"
    fpath.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    loaded = json.loads(fpath.read_text(encoding="utf-8"))
    proj2 = ProjectData.from_dict(loaded)
    assert proj2.floors[0].courtyard_center == (160000.0, 74000.0)
    assert proj2.floors[0].courtyard_radius_m == 4.0
