"""AI Berkshire Skill Loader

Reads vendored skill markdown files from backend/research_assets/ai_berkshire/skills/.
Provides metadata for the template list API and raw skill content for prompt building.

Attribution: Research framework adapted from xbtlin/ai-berkshire, MIT License.
https://github.com/xbtlin/ai-berkshire
"""
from pathlib import Path
from typing import Any, Dict, List

SKILLS_DIR = Path(__file__).parent / "research_assets" / "ai_berkshire" / "skills"

# Metadata for each skill. skill content is read from the corresponding .md file.
AI_BERKSHIRE_SKILLS: Dict[str, Dict[str, Any]] = {
    # ── 深度研究 ──────────────────────────────────────────────────
    "investment-research": {
        "file": "investment-research.md",
        "name": "单公司深度研究",
        "category": "深度研究",
        "description": "基于巴菲特、芒格、段永平、李录四大师框架对单一标的进行全面基本面研究。",
        "priority": True,
        "source": "AI Berkshire",
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
            {"name": "related_holding_id", "label": "关联持仓（可选）", "required": False},
        ],
    },
    "investment-team": {
        "file": "investment-team.md",
        "name": "投资委员会讨论",
        "category": "深度研究",
        "description": "模拟多角色投资委员会对单一标的进行辩证讨论，给出委员会投票结论。",
        "priority": False,
        "source": "AI Berkshire",
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
            {"name": "related_holding_id", "label": "关联持仓（可选）", "required": False},
        ],
    },
    "investment-checklist": {
        "file": "investment-checklist.md",
        "name": "买入前检查清单",
        "category": "深度研究",
        "description": "在买入前系统过一遍核心问题清单，避免冲动决策和遗漏关键风险。",
        "priority": True,
        "source": "AI Berkshire",
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
            {"name": "related_holding_id", "label": "关联持仓（可选）", "required": False},
        ],
    },
    "dyp-ask": {
        "file": "dyp-ask.md",
        "name": "段永平式追问",
        "category": "深度研究",
        "description": "用段永平的「不为清单」和「做对的事」框架，用最简单的问题穿透企业本质。",
        "priority": False,
        "source": "AI Berkshire",
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
        ],
    },
    # ── 财报分析 ──────────────────────────────────────────────────
    "earnings-review": {
        "file": "earnings-review.md",
        "name": "财报深度解读",
        "category": "财报分析",
        "description": "解读最新季报/年报，重点关注收入质量、现金流健康度和指引可信度。",
        "priority": True,
        "source": "AI Berkshire",
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
            {"name": "related_holding_id", "label": "关联持仓（可选）", "required": False},
        ],
    },
    "earnings-team": {
        "file": "earnings-team.md",
        "name": "财报委员会讨论",
        "category": "财报分析",
        "description": "模拟基本面分析师、会计质疑者、管理层观察者和组合经理对财报进行多角度评审。",
        "priority": False,
        "source": "AI Berkshire",
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
        ],
    },
    "financial-data": {
        "file": "financial-data.md",
        "name": "财务数据整理",
        "category": "财报分析",
        "description": "结构化采集近 5 年收入、现金流、资产负债表和估值倍数，形成可复用的数据基础。",
        "priority": False,
        "source": "AI Berkshire",
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
        ],
    },
    "management-deep-dive": {
        "file": "management-deep-dive.md",
        "name": "管理层深度评估",
        "category": "财报分析",
        "description": "评估管理层资本分配能力、激励机制设计、沟通诚信度和历史执行记录。",
        "priority": False,
        "source": "AI Berkshire",
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
        ],
    },
    "quality-screen": {
        "file": "quality-screen.md",
        "name": "企业质量评分",
        "category": "财报分析",
        "description": "从盈利质量、财务稳健、成长持续性、竞争优势和管理层五维对企业打分（满分100）。",
        "priority": False,
        "source": "AI Berkshire",
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
        ],
    },
    # ── 行业筛选 ──────────────────────────────────────────────────
    "industry-research": {
        "file": "industry-research.md",
        "name": "行业格局分析",
        "category": "行业筛选",
        "description": "用波特五力分析行业竞争结构、供需动态和长期吸引力，识别高质量赛道特征。",
        "priority": False,
        "source": "AI Berkshire",
        "input_fields": [
            {"name": "target_name", "label": "行业名称", "required": True},
        ],
    },
    "industry-funnel": {
        "file": "industry-funnel.md",
        "name": "行业机会筛选",
        "category": "行业筛选",
        "description": "系统梳理行业内投资机会，经质量过滤和估值排序后输出优先研究清单。",
        "priority": False,
        "source": "AI Berkshire",
        "input_fields": [
            {"name": "target_name", "label": "行业名称", "required": True},
        ],
    },
    # ── 持仓管理 ──────────────────────────────────────────────────
    "portfolio-review": {
        "file": "portfolio-review.md",
        "name": "组合整体复盘",
        "category": "持仓管理",
        "description": "基于当前全仓位数据做组合结构分析、论文回顾和行动优先级排序。",
        "priority": True,
        "source": "AI Berkshire",
        "input_fields": [],
    },
    "thesis-tracker": {
        "file": "thesis-tracker.md",
        "name": "投资论文追踪",
        "category": "持仓管理",
        "description": "回顾当初买入论文，检验哪些假设已被验证、哪些已经失效，判断是否继续持有。",
        "priority": True,
        "source": "AI Berkshire",
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "related_holding_id", "label": "关联持仓（必选）", "required": True},
        ],
    },
    "news-pulse": {
        "file": "news-pulse.md",
        "name": "持仓异动归因",
        "category": "持仓管理",
        "description": "针对近期股价或基本面异动，归因分析并判断是否影响投资论文。",
        "priority": True,
        "source": "AI Berkshire",
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
            {"name": "related_holding_id", "label": "关联持仓（可选）", "required": False},
        ],
    },
}

_SKILLS_LIST: list = [
    {"key": k, **{f: v for f, v in meta.items() if f != "file"}}
    for k, meta in AI_BERKSHIRE_SKILLS.items()
]


def list_skills() -> List[Dict[str, Any]]:
    """Return the skills metadata list for the templates API endpoint."""
    return _SKILLS_LIST


def load_skill(key: str) -> str:
    """Load and return the raw markdown content of the named skill.

    Raises:
        ValueError: if the key is not in AI_BERKSHIRE_SKILLS.
        FileNotFoundError: if the markdown file is missing from disk.
    """
    meta = AI_BERKSHIRE_SKILLS.get(key)
    if not meta:
        raise ValueError(
            f"Unknown AI Berkshire skill key: '{key}'. "
            f"Available keys: {list(AI_BERKSHIRE_SKILLS)}"
        )
    skill_path = SKILLS_DIR / meta["file"]
    if not skill_path.exists():
        raise FileNotFoundError(
            f"Skill file not found: {skill_path}. "
            f"Re-vendor the ai_berkshire assets or check the file name."
        )
    return skill_path.read_text(encoding="utf-8")


def get_skill_meta(key: str) -> Dict[str, Any]:
    """Return the metadata dict for a skill key (without 'file' entry)."""
    meta = AI_BERKSHIRE_SKILLS.get(key)
    if not meta:
        raise ValueError(f"Unknown AI Berkshire skill key: '{key}'")
    return {f: v for f, v in meta.items() if f != "file"}
