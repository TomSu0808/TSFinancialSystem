"""投研工作台模板元数据（来源：ai-berkshire 精简适配版，MIT 许可证）。

v1 主推 5 个与平台最贴合的核心流程；其余 11 个作为扩展备用，全部在前端按类别展示。
prompt 组装时关键规则：多源验证、估值禁止心算、免责声明收尾。
"""
from typing import Any, Dict, List

CATEGORIES = ["深度研究", "财报分析", "行业筛选", "持仓管理"]

TEMPLATES: List[Dict[str, Any]] = [
    # ── 深度研究 ────────────────────────────────────────────────
    {
        "key": "investment-research",
        "name": "单公司深度研究",
        "category": "深度研究",
        "description": "对单一标的进行商业模式、护城河、管理层、财务质量和估值的全面研究。",
        "priority": True,
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
            {"name": "related_holding_id", "label": "关联持仓（可选）", "required": False},
        ],
    },
    {
        "key": "competitive-moat",
        "name": "护城河深度分析",
        "category": "深度研究",
        "description": "系统评估公司护城河来源、宽度及可持续性，判断竞争优势的质量。",
        "priority": False,
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
        ],
    },
    {
        "key": "red-flag-scan",
        "name": "风险红旗扫描",
        "category": "深度研究",
        "description": "从财务、治理、业务三个维度识别潜在风险信号，适合买入前做快速尽调。",
        "priority": False,
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
        ],
    },
    {
        "key": "management-assessment",
        "name": "管理层评估",
        "category": "深度研究",
        "description": "评估管理层资本分配能力、激励机制设计和历史执行记录。",
        "priority": False,
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
        ],
    },
    # ── 财报分析 ────────────────────────────────────────────────
    {
        "key": "earnings-analysis",
        "name": "财报深度解读",
        "category": "财报分析",
        "description": "解读最新季报/年报，重点关注核收质量、现金流健康度和指引可信度。",
        "priority": False,
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
            {"name": "related_holding_id", "label": "关联持仓（可选）", "required": False},
        ],
    },
    {
        "key": "dcf-valuation",
        "name": "DCF 估值模型",
        "category": "财报分析",
        "description": "基于自由现金流折现的估值框架，要求多情景假设并注明来源，禁止心算。",
        "priority": False,
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
        ],
    },
    {
        "key": "balance-sheet-review",
        "name": "资产负债表健康检查",
        "category": "财报分析",
        "description": "评估资产质量、债务结构和流动性风险，识别隐性负债。",
        "priority": False,
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
        ],
    },
    {
        "key": "quality-score",
        "name": "企业质量评分",
        "category": "财报分析",
        "description": "基于盈利质量、财务稳健性、业务可预测性对企业质量打分。",
        "priority": False,
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
        ],
    },
    # ── 行业筛选 ────────────────────────────────────────────────
    {
        "key": "sector-analysis",
        "name": "行业格局分析",
        "category": "行业筛选",
        "description": "分析行业竞争格局、供需结构和驱动因素，识别高质量赛道的特征。",
        "priority": False,
        "input_fields": [
            {"name": "target_name", "label": "行业名称", "required": True},
        ],
    },
    {
        "key": "peer-comparison",
        "name": "同业对比分析",
        "category": "行业筛选",
        "description": "对目标公司与主要竞争对手进行多维度横向对比，找出相对优势。",
        "priority": False,
        "input_fields": [
            {"name": "target_name", "label": "目标公司", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
        ],
    },
    {
        "key": "sector-screener",
        "name": "行业机会筛选",
        "category": "行业筛选",
        "description": "系统梳理某行业内的投资机会，按质量和估值双维度排序。",
        "priority": False,
        "input_fields": [
            {"name": "target_name", "label": "行业名称", "required": True},
        ],
    },
    {
        "key": "esg-assessment",
        "name": "ESG 风险评估",
        "category": "行业筛选",
        "description": "评估企业在环境、社会、治理三个维度的风险敞口。",
        "priority": False,
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
        ],
    },
    # ── 持仓管理 ────────────────────────────────────────────────
    {
        "key": "investment-checklist",
        "name": "买入前检查清单",
        "category": "持仓管理",
        "description": "在买入前系统过一遍核心问题清单，避免冲动决策和遗漏关键风险。",
        "priority": True,
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
            {"name": "related_holding_id", "label": "关联持仓（可选）", "required": False},
        ],
    },
    {
        "key": "portfolio-review",
        "name": "组合整体复盘",
        "category": "持仓管理",
        "description": "基于当前全仓位数据做组合结构分析、论文回顾和行动优先级排序。",
        "priority": True,
        "input_fields": [],  # 自动读取全仓，无需手填
    },
    {
        "key": "thesis-tracker",
        "name": "投资论文追踪",
        "category": "持仓管理",
        "description": "回顾当初买入论文，检验哪些假设已被验证、哪些已经失效。",
        "priority": True,
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "related_holding_id", "label": "关联持仓（必选）", "required": True},
        ],
    },
    {
        "key": "news-pulse",
        "name": "持仓异动归因",
        "category": "持仓管理",
        "description": "针对近期股价或基本面异动，分析原因并判断是否影响投资论文。",
        "priority": True,
        "input_fields": [
            {"name": "target_name", "label": "公司名称", "required": True},
            {"name": "symbol", "label": "代码", "required": False},
            {"name": "market", "label": "市场", "required": False},
            {"name": "related_holding_id", "label": "关联持仓（可选）", "required": False},
        ],
    },
]

_TEMPLATE_MAP = {t["key"]: t for t in TEMPLATES}

_EN_TEMPLATE_TITLES: Dict[str, str] = {
    "investment-research": "Deep Company Research",
    "competitive-moat": "Competitive Moat Analysis",
    "red-flag-scan": "Red Flag Scan",
    "management-assessment": "Management Assessment",
    "earnings-analysis": "Earnings Review",
    "dcf-valuation": "DCF Valuation",
    "balance-sheet-review": "Balance Sheet Review",
    "quality-score": "Quality Score",
    "sector-analysis": "Sector Analysis",
    "peer-comparison": "Peer Comparison",
    "sector-screener": "Sector Screener",
    "esg-assessment": "ESG Assessment",
    "investment-checklist": "Pre-Buy Checklist",
    "portfolio-review": "Portfolio Review",
    "thesis-tracker": "Thesis Tracker",
    "news-pulse": "News Pulse",
}

DISCLAIMER = "\n\n---\n> **免责声明**：AI 生成内容仅供研究记录，不构成投资建议。关键数据请多源验证，估值假设须注明来源。"


def _lang_instruction(lang: str) -> str:
    if lang == "en":
        return (
            "\n\n## Output Language\n\n"
            "Please write the full report in English.\n"
            "Use clear institutional investment research style.\n"
            "Keep company names, financial terms, and source citations precise."
        )
    return (
        "\n\n## 输出语言\n\n"
        "请使用简体中文输出完整报告。\n"
        "术语可以保留必要英文缩写，例如 DCF、FCF、ROE、PE。"
    )


def _disclaimer(lang: str) -> str:
    if lang == "en":
        return (
            "\n\n---\n> **Disclaimer**: AI-generated content is for research logging only "
            "and does not constitute investment advice. Verify key data from multiple sources; "
            "all valuation assumptions must be cited."
        )
    return DISCLAIMER


def get_template(key: str) -> Dict[str, Any]:
    t = _TEMPLATE_MAP.get(key)
    if not t:
        raise ValueError(f"未知模板 key: {key}")
    return t


def build_research_prompt(
    key: str,
    target_name: str,
    symbol: str = "",
    market: str = "",
    holding_ctx: str = "",
    portfolio_ctx: str = "",
    report_language: str = "zh",
    extra_instruction: str = "",
) -> str:
    """根据模板 key 和上下文数据组装 Markdown prompt（支持多语言输出）。"""
    t = get_template(key)
    label = t["name"]
    sym_part = f"（{symbol}，{market} 市场）" if symbol else ""

    if key == "investment-research":
        body = f"""你是一位严谨的价值投资分析师，请对 **{target_name}**{sym_part} 进行深度基本面研究。
{holding_ctx}
## 研究框架

### 1. 商业模式
- 核心产品/服务及收入来源
- 客户群体与市场规模
- 商业模式可持续性

### 2. 护城河分析（Moat）
- 品牌、成本优势、网络效应、转换成本、规模优势各项评分
- 护城河宽度（宽 / 窄 / 无）及可持续年限判断

### 3. 管理层评估
- 历史资本分配记录（ROE/ROIC 趋势）
- 薪酬结构与股东利益对齐程度
- 关键人风险

### 4. 财务质量
- 近 3-5 年自由现金流生成能力
- 负债水平与偿债能力
- 盈利质量（应收款/收入比、折旧政策）

### 5. 估值框架
- 采用不少于 2 种估值方法（DCF / PE / PB / EV/EBITDA）
- 列出各方法的关键假设及来源（**禁止心算，所有数字需标明出处**）
- 合理价值区间 & 当前安全边际

### 6. 风险清单
- 行业级风险（监管、技术替代、周期性）
- 公司级风险（竞争加剧、执行失误、财务杠杆）
- 近期催化剂（正面 / 负面）"""

    elif key == "investment-checklist":
        body = f"""在买入 **{target_name}**{sym_part} 之前，请逐项回答以下清单，所有"否"或"不确定"均需补充说明。
{holding_ctx}
## 买入检查清单

### A. 商业理解
- [ ] 我能用 2 句话清晰解释这家公司怎么赚钱吗？
- [ ] 我理解其主要客户群体和定价逻辑吗？
- [ ] 这个行业未来 5 年的结构性趋势是什么？

### B. 竞争优势
- [ ] 公司有可识别的护城河吗？护城河来源是什么？
- [ ] 竞争对手进入这个市场的主要壁垒是什么？
- [ ] 过去 5 年市场份额是扩大还是缩小？

### C. 管理层质量
- [ ] 管理层的历史资本分配决策记录如何？
- [ ] 管理层持股比例合理吗？有没有大量减持信号？
- [ ] 公司是否有过重大业绩承诺失信的记录？

### D. 财务健康
- [ ] 自由现金流近 3 年是否持续为正？
- [ ] 净债务/EBITDA 是否在可接受范围（<3x 为宜）？
- [ ] 有没有表外负债或重大或有负债？

### E. 估值合理性
- [ ] 当前估值相对历史均值和同业处于什么位置？
- [ ] 内在价值的悲观情景下是否仍有安全边际？
- [ ] 我的目标价和止损逻辑是什么？

### F. 风险认知
- [ ] 最大的 3 个下行风险是什么？我能接受吗？
- [ ] 哪些事件会让我重新评估持仓？
- [ ] 仓位大小与风险级别匹配吗？"""

    elif key == "portfolio-review":
        body = f"""你是一位组合管理顾问，请对以下投资组合进行系统复盘。
{portfolio_ctx}
## 复盘框架

### 1. 组合结构分析
- 集中度风险（最大单仓占比是否超过 30%？）
- 行业 / 地域 / 货币分散度评估
- 当前现金比例是否合理？

### 2. 各持仓论文回顾
对每个持仓逐一回答：
- 当初买入的核心逻辑是什么？
- 该逻辑现在是否仍然成立？
- 有哪些新事实改变了我的判断？

### 3. 仓位优化建议
- 是否存在明显高估（可减仓）的持仓？
- 是否存在低估且逻辑更强的持仓（可加仓）？
- 哪些持仓的相关性过高，带来重叠风险？

### 4. 行动优先级
按优先级列出：
1. 需要立即深入研究的标的
2. 考虑加减仓的标的（及理由）
3. 保持观察不动的标的"""

    elif key == "thesis-tracker":
        body = f"""请对 **{target_name}**{sym_part} 的投资论文进行追踪复盘。
{holding_ctx}
## 论文追踪框架

### 1. 原始买入论文
（请在此填写当初的核心买入逻辑：）

### 2. 关键假设清单
列出买入时的 3-5 个核心假设，逐项检验：
| 假设 | 当时预期 | 当前实际 | 状态（✅验证 / ⚠️存疑 / ❌失效） |
|------|---------|---------|-------------------------------|
| 假设 1 | | | |
| 假设 2 | | | |
| 假设 3 | | | |

### 3. 新增事实更新
- 自买入以来，有哪些新事实支持论文？
- 有哪些新事实质疑论文？
- 是否触及了原始的止损逻辑？

### 4. 结论与行动
- 论文整体状态：🟢 仍然成立 / 🟡 部分存疑 / 🔴 已失效
- 建议行动：持有 / 加仓 / 减仓 / 清仓
- 下一个检查节点（日期或触发事件）："""

    elif key == "news-pulse":
        body = f"""针对 **{target_name}**{sym_part} 的近期异动，请进行归因分析。
{holding_ctx}
## 异动归因框架

### 1. 异动描述
- 具体异动（股价涨跌幅 / 基本面事件）：
- 发生时间：
- 市场整体背景（同期大盘/行业表现）：

### 2. 可能原因分析
按可能性排序，逐一分析：
1. **宏观/市场因素**：是否受到利率、汇率、风险偏好等宏观因素驱动？
2. **行业因素**：同行业是否有类似异动？是否有监管 / 政策变化？
3. **公司基本面因素**：是否有业绩、管理层、产品等方面的实质性变化？
4. **市场情绪因素**：是否存在过度反应？

### 3. 对投资论文的影响
- 本次异动是否改变了核心投资逻辑？（是 / 否，请说明）
- 需要关注的后续跟踪指标：
- 是否需要重新评估仓位？

### 4. 行动建议
- 操作：维持 / 加仓 / 减仓 / 清仓
- 理由：
- 设置的观察节点："""

    elif key == "competitive-moat":
        body = f"""请对 **{target_name}**{sym_part} 进行护城河深度分析。

### 护城河来源识别
对以下 5 种来源逐项评估（强 / 弱 / 无，并说明理由）：
1. **无形资产**（品牌、专利、牌照）
2. **成本优势**（规模经济、专有技术、地理优势）
3. **网络效应**（用户越多价值越大）
4. **转换成本**（客户切换到竞争对手的成本）
5. **高效规模**（小市场中的主导者）

### 护城河宽度评估
- 综合宽度：宽 / 窄 / 无
- 预计可持续年限：
- 最大威胁来源：

### 历史护城河验证
- 过去 10 年 ROIC 是否持续高于资本成本（WACC）？
- 市场份额趋势如何？"""

    elif key == "red-flag-scan":
        body = f"""请对 **{target_name}**{sym_part} 进行风险红旗扫描，逐项打分（🔴高风险 / 🟡注意 / 🟢正常）。

### A. 财务红旗
- [ ] 应收账款增速是否持续超过收入增速？
- [ ] 经营现金流是否长期低于净利润？
- [ ] 频繁的一次性项目或会计政策变更？
- [ ] 审计意见是否保留意见或无法表示意见？
- [ ] 管理层薪酬与股东回报是否脱钩？

### B. 治理红旗
- [ ] 大股东是否存在持续大规模减持？
- [ ] 是否有关联交易且定价不透明？
- [ ] 独立董事是否真正独立？
- [ ] CFO/审计委员会是否频繁更换？

### C. 业务红旗
- [ ] 客户集中度是否过高（前 5 客户占收入 >50%）？
- [ ] 核心技术或人才是否高度依赖单一个体？
- [ ] 市场份额是否持续流失？
- [ ] 资本开支 / 研发投入是否异常下滑？

### 综合判断
- 发现红旗数量：____
- 最高优先级风险：
- 是否影响买入决策："""

    elif key == "earnings-analysis":
        body = f"""请对 **{target_name}**{sym_part} 的最新财报进行深度解读。
{holding_ctx}
### 1. 收入质量
- 收入结构（按业务线/地区拆分）是否健康？
- 增长来源：有机增长 vs 并购贡献？
- 递延收入 / 预收款趋势？

### 2. 利润质量
- 毛利率 / 运营利润率趋势，排除一次性项目后的调整利润？
- EBITDA 与实际 FCF 的差距（资本化率）？

### 3. 现金流健康度
- 经营现金流转化率（OCF / 净利润）是否 >80%？
- 资本开支趋势，是否处于投资周期？

### 4. 管理层指引可信度
- 本季度指引达成率（vs 上季度指引）？
- 对下季度 / 全年的指引是否保守 / 激进？

### 5. 关注问题与跟踪指标
- 本期最需要跟踪的 2-3 个指标："""

    elif key == "dcf-valuation":
        body = f"""请对 **{target_name}**{sym_part} 进行 DCF 估值分析。
**注意：所有数字必须标明来源，禁止凭空估算。**

### 假设输入（需填入真实数据后执行）
| 参数 | 悲观情景 | 基准情景 | 乐观情景 | 数据来源 |
|------|---------|---------|---------|---------|
| 近 3 年平均 FCF | | | | 财报 |
| 未来 5 年 FCF 增速 | | | | 行业报告/公司指引 |
| 永续增长率 | | | | 宏观数据 |
| WACC | | | | 计算过程见下 |

### WACC 计算
- 无风险利率（10Y 国债）：
- 股权风险溢价：
- Beta：
- 债务成本（税后）：
- 资本结构（E/E+D）：
- WACC =

### 估值结果
| 情景 | 内在价值/股 | 当前价 | 安全边际 |
|------|-----------|-------|---------|
| 悲观 | | | |
| 基准 | | | |
| 乐观 | | | |

### 敏感性分析
增速和 WACC 变动对估值的影响矩阵："""

    elif key == "balance-sheet-review":
        body = f"""请对 **{target_name}**{sym_part} 的资产负债表进行健康检查。

### 1. 资产质量
- 流动资产中应收账款 / 存货占比是否异常？
- 商誉金额及历史减值记录？
- 无形资产 / 递延税资产的合理性？

### 2. 负债结构
- 短期债务 / 长期债务比例？
- 净债务 / EBITDA（理想 <3x）？
- 未来 12 个月债务到期偿还压力？

### 3. 隐性负债识别
- 经营性租赁（IFRS 16 前的表外项）？
- 或有负债（诉讼、担保）？
- 养老金缺口（制造业重点关注）？

### 4. 流动性评估
- 流动比率（>1.5 为健康）：
- 速动比率（>1 为健康）：
- 现金覆盖近 12 个月利息支出的倍数：

### 综合判断
- 资产负债表整体健康度：🟢优 / 🟡良 / 🔴差
- 最需关注的风险点："""

    elif key == "quality-score":
        body = f"""请对 **{target_name}**{sym_part} 进行企业质量综合评分（满分 100）。

### 评分维度

| 维度 | 权重 | 评分（0-10） | 说明 |
|------|------|------------|------|
| 盈利质量（FCF 转化率）| 20% | | |
| 财务稳健（杠杆 & 流动性）| 20% | | |
| 增长可持续性 | 20% | | |
| 竞争优势（护城河）| 20% | | |
| 管理层质量 | 10% | | |
| 估值合理性 | 10% | | |

### 加权总分
计算过程：

### 结论
- 总分：/ 100
- 优势：
- 弱项：
- 相对同业排名："""

    elif key == "sector-analysis":
        body = f"""请对 **{target_name}** 行业进行结构性分析。

### 1. 行业格局
- 集中度（CR4/CR8）及变化趋势？
- 主要竞争者及各自竞争策略？
- 是否存在隐性区域性或细分垄断？

### 2. 供需结构与定价权
- 供给弹性如何（新产能进入壁垒）？
- 需求端是否具有粘性？
- 历史价格周期规律？

### 3. 行业驱动因素
- 增量驱动（渗透率提升、需求扩容）？
- 结构性驱动（市场整合、技术升级）？
- 宏观敏感度（利率、汇率、政策）？

### 4. 赛道质量评估
- 行业平均 ROIC（过去 10 年）：
- 长期增长天花板：
- 主要风险（颠覆性技术、监管风险）："""

    elif key == "peer-comparison":
        body = f"""请对 **{target_name}**{sym_part} 与主要竞争对手进行横向对比分析。

### 对比维度（填入真实数据）

| 指标 | {target_name} | 竞争对手 A | 竞争对手 B | 行业均值 |
|------|-------------|----------|----------|---------|
| 市值 | | | | |
| 收入增速（3Y CAGR）| | | | |
| 毛利率 | | | | |
| EBITDA 利润率 | | | | |
| ROIC | | | | |
| 净债务/EBITDA | | | | |
| PE（TTM）| | | | |
| EV/EBITDA | | | | |

### 差异化分析
- 目标公司相对于竞争对手的核心优势：
- 明显劣势：
- 估值溢价/折价的合理性：

### 结论"""

    elif key == "sector-screener":
        body = f"""请对 **{target_name}** 行业内的投资机会进行系统筛选。

### 筛选标准（参考门槛）
- ROIC > 12%（过去 3 年平均）
- 净债务/EBITDA < 3x
- 自由现金流近 3 年持续为正
- 近 5 年营收 CAGR > GDP 增速

### 候选公司清单
| 公司 | 代码 | 市场 | ROIC | 净利润率 | PE | 初步评级 |
|------|------|------|------|---------|-----|--------|
| | | | | | | |

### 重点关注标的
按吸引力排序，列出 3-5 个值得深研的标的及理由："""

    elif key == "esg-assessment":
        body = f"""请对 **{target_name}**{sym_part} 进行 ESG 风险评估。

### E（环境）
- 主要环境风险敞口（碳排放、污染、资源消耗）？
- 公司碳中和承诺及实施路径可信度？
- 监管收紧对运营成本的潜在影响？

### S（社会）
- 供应链劳工风险（尤其是新兴市场供应商）？
- 数据隐私与消费者保护合规状况？
- 社区关系与许可经营稳定性？

### G（治理）
- 股权结构是否有控制权失衡风险？
- 独立董事占比及审计委员会有效性？
- 股东回报历史（分红、回购一致性）？

### ESG 综合评分
| 维度 | 风险等级（低/中/高） | 主要关注点 |
|------|-------------------|---------|
| 环境 | | |
| 社会 | | |
| 治理 | | |"""

    else:
        # 通用兜底模板
        body = f"""请对 **{target_name}**{sym_part} 进行【{label}】分析。
{holding_ctx}
请按照严谨的投资研究标准，系统覆盖以下方面：
1. 基本情况概述
2. 核心分析框架
3. 关键风险因素
4. 结论与行动建议

**注意：关键数据需多源验证，定量判断须注明假设来源。**"""

    lang_block = _lang_instruction(report_language)
    extra_block = f"\n\n## 附加说明\n\n{extra_instruction}" if extra_instruction else ""
    disclaimer = _disclaimer(report_language)

    if report_language == "en":
        title_name = _EN_TEMPLATE_TITLES.get(key, label)
        return f"# {title_name}: {target_name}\n\n{body}{lang_block}{extra_block}{disclaimer}"
    return f"# {label}：{target_name}\n\n{body}{lang_block}{extra_block}{disclaimer}"


def build_prompt(
    key: str,
    target_name: str,
    symbol: str = "",
    market: str = "",
    holding_ctx: str = "",
    portfolio_ctx: str = "",
) -> str:
    """向后兼容：不含语言参数的旧版接口。"""
    return build_research_prompt(
        key=key,
        target_name=target_name,
        symbol=symbol,
        market=market,
        holding_ctx=holding_ctx,
        portfolio_ctx=portfolio_ctx,
    )
