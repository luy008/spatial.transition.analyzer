"""분석 레시피 로딩 및 추천 (규칙 기반, AI API 없음)."""
from __future__ import annotations
import json
from pathlib import Path
from typing import List, Dict

RECIPES_DIR = Path(__file__).parent.parent / "analysis_recipes"

RECIPE_KEYWORDS: Dict[str, List[str]] = {
    "circulation_transition": ["동선", "계단", "램프", "전환", "시퀀스", "도착", "경험"],
    "visibility_threshold": ["시야", "가시", "보이드", "중정", "개구부", "인지"],
    "accessibility": ["접근", "거리", "경사", "이동시간", "무장애"],
    "connectivity": ["연결", "네트워크", "중심성", "깊이", "선택"],
    "daylight": ["일조", "채광", "빛", "그림자"],
}


def load_recipe(recipe_id: str) -> dict:
    path = RECIPES_DIR / f"{recipe_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"id": recipe_id, "methods": []}


def list_recipes() -> List[dict]:
    recipes = []
    for p in sorted(RECIPES_DIR.glob("*.json")):
        try:
            recipes.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return recipes


def recommend_recipe(question: str) -> List[str]:
    """키워드 기반 레시피 추천. AI 없음."""
    scores: Dict[str, int] = {k: 0 for k in RECIPE_KEYWORDS}
    for recipe_id, keywords in RECIPE_KEYWORDS.items():
        for kw in keywords:
            if kw in question:
                scores[recipe_id] += 1
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [r for r, s in ranked if s > 0]
