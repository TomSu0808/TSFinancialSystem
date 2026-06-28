"""Research Prompt Builder

Assembles the final AI research prompt from:
  1. AI Berkshire skill markdown (raw, unmodified)
  2. Platform context (holdings, portfolio data)
  3. Execution requirements (language, source standards, disclaimer)

The original skill content is NEVER modified — only wrapped with platform data.
Attribution: Research framework adapted from xbtlin/ai-berkshire, MIT License.
"""

_DISCLAIMER_ZH = (
    "\n\n---\n"
    "> **免责声明**：AI 生成内容仅供研究记录，不构成投资建议。"
    "请自行核验关键数据和结论。"
)

_DISCLAIMER_EN = (
    "\n\n---\n"
    "> **Disclaimer**: AI-generated content is for research logging only "
    "and does not constitute investment advice. "
    "Please independently verify key data and conclusions."
)


def _lang_block(lang: str) -> str:
    if lang == "en":
        return (
            "## Output Language\n\n"
            "Please write the full report in English.\n"
            "Use a clear institutional investment research style.\n"
            "Preserve company names, ticker symbols, financial metrics, "
            "and source citations precisely.\n"
            "Retain necessary abbreviations: DCF, FCF, ROE, ROIC, PE, EV/EBITDA."
        )
    return (
        "## 输出语言\n\n"
        "请使用简体中文输出完整报告。\n"
        "保留必要英文金融缩写，例如 DCF、FCF、ROE、ROIC、PE、EV/EBITDA。"
    )


def _priority_language_block(lang: str) -> str:
    if lang == "en":
        return (
            "# Highest Priority Instruction\n\n"
            "The final answer MUST be a complete English Markdown report.\n"
            "If any skill definition, source material, or platform context below uses another language, "
            "treat it as input only and write the final report in English. "
            "Preserve company names, ticker symbols, financial metric abbreviations, exact quotations, "
            "and URLs when needed."
        )
    return (
        "# 最高优先级指令\n\n"
        "最终答案必须是一份完整的简体中文 Markdown 报告。无论下方 skill、模板、来源材料或平台上下文使用什么语言，"
        "都只能作为输入信息参考，最终报告正文必须使用简体中文。\n\n"
        "标题、小节、摘要、表格字段、投资结论、风险提示、来源说明都必须使用简体中文。"
        "仅公司名、股票代码、财务指标缩写、英文原文引用和 URL 可以保留英文。"
        "不得输出英文报告；如果你准备使用英文，请先翻译成简体中文再输出。"
    )


def _format_requirements(lang: str) -> str:
    if lang == "en":
        return (
            "## Output Format Requirements\n\n"
            "- Output standard Markdown only — NO HTML tags.\n"
            "- Use clear heading hierarchy: `#` for the report title, `##` for major sections, "
            "`###` for sub-sections.\n"
            "- Use GFM Markdown tables (pipe syntax) for all data comparisons, financials, "
            "and metric summaries — do NOT use plain text columns or ASCII art.\n"
            "- Do NOT wrap the entire report in a fenced code block (``` ... ```).\n"
            "- Place all cited source URLs under a `## Sources` section at the end of the report; "
            "use markdown link syntax `[title](url)`.\n"
            "- Use `**bold**` for key metrics and `> blockquote` for important caveats."
        )
    return (
        "## 输出格式要求\n\n"
        "- 只输出标准 Markdown，不要输出 HTML 标签。\n"
        "- 使用清晰的标题层级：`#` 用于报告标题，`##` 用于主要章节，`###` 用于子章节。\n"
        "- 所有数据对比、财务数据、指标摘要必须使用 GFM Markdown 表格（竖线表格语法），"
        "不要使用纯文本对齐列或 ASCII 图。\n"
        "- 不要把整份报告包在代码块中（``` ... ```）。\n"
        "- 所有引用来源链接统一放在报告末尾的 `## 来源与核验` 小节，使用 Markdown 链接格式 `[标题](URL)`。\n"
        "- 使用 `**加粗**` 标出关键指标，使用 `> 引用块` 标出重要假设、限制或风险提示。\n"
        "- 表格列名、图表说明、章节标题必须使用简体中文。"
    )


def _source_requirements(lang: str) -> str:
    if lang == "en":
        return (
            "## Source Requirements\n\n"
            "- Every factual claim must cite its source (annual report, SEC/exchange filing, "
            "earnings call, industry report, news).\n"
            "- If a source cannot be verified, state this explicitly — do not fabricate data.\n"
            "- Distinguish between audited facts, management estimates, and analyst consensus."
        )
    return (
        "## 来源要求\n\n"
        "- 每一个关键事实判断都必须注明来源，例如年报、SEC/交易所公告、财报电话会、行业报告或新闻。\n"
        "- 如果来源无法核验，必须明确说明“未能核验”，不要编造数据。\n"
        "- 区分经审计事实、管理层预期和分析师一致预期。\n"
        "- 来源说明本身也必须使用简体中文，来源标题或机构名称可保留原文。"
    )


def _research_loop_requirements(lang: str) -> str:
    if lang == "en":
        return (
            "## Research Loop Output Requirements\n\n"
            "The report **MUST** include the following sections as Level 2 headings (`##`):\n\n"
            "1. **## Summary** — A concise 3–5 sentence investment conclusion.\n"
            "2. **## Core Assumptions** — Key assumptions underlying the investment thesis. "
            "Unverified items must be explicitly flagged, e.g. *(unverified assumption)* or *(source not confirmed)*.\n"
            "3. **## Key Risks** — Major risks that could invalidate the thesis or cause losses.\n"
            "4. **## Questions to Verify** — Specific questions that need further verification before acting.\n"
            "5. **## Tracking Metrics** — Specific, measurable metrics to monitor going forward "
            "(e.g., quarterly revenue growth, FCF margin trend, key product milestones).\n"
            "6. **## Action Items** — Concrete, trackable next steps as a **bullet list**. "
            "Each item must be specific and actionable "
            "(e.g., `- Review Q4 2025 earnings release by 2026-03-01`).\n\n"
            "> The report must include a data snapshot date or data-as-of date. "
            "Do not present AI-generated content as definitive investment advice."
        )
    return (
        "## 研究闭环输出要求\n\n"
        "报告**必须**包含以下章节，使用二级 Markdown 标题（`##`）：\n\n"
        "1. **## 结论摘要** — 3–5 句话的投资核心结论。\n"
        "2. **## 核心假设** — 支撑投资逻辑的关键假设。不确定信息必须标注，例如「待验证假设」或「来源未能核实」。\n"
        "3. **## 主要风险** — 可能导致投资逻辑失效或造成损失的关键风险点。\n"
        "4. **## 待验证问题** — 在采取行动之前需要进一步核实的具体问题清单。\n"
        "5. **## 跟踪指标** — 需要持续跟踪的具体、可量化指标（如季度营收增速、FCF 利润率趋势、关键产品里程碑）。\n"
        "6. **## 行动项** — 具体、可跟踪的下一步操作，必须使用**清单列表**格式（每条以 `- ` 开头）。"
        "每条行动项应具体可执行（如：`- 财报发布后一周内更新估值模型`）。\n\n"
        "> 报告必须包含数据时点或数据截止日期说明。不要将 AI 输出包装成确定性投资建议。"
    )


def _disclaimer(lang: str) -> str:
    return _DISCLAIMER_EN if lang == "en" else _DISCLAIMER_ZH


def build_prompt(
    skill_md: str,
    target_name: str,
    symbol: str = "",
    market: str = "",
    holding_ctx: str = "",
    portfolio_ctx: str = "",
    report_language: str = "zh",
    extra_instruction: str = "",
) -> str:
    """Assemble the final prompt for the AI provider.

    Structure:
      # AI Berkshire Skill
      <original skill markdown — unmodified>

      ---

      # Platform Context
      <target info + holding/portfolio data from user's account>

      ---

      # Execution Requirements
      <language, source standards, extra instruction, disclaimer>
    """
    # Build target line
    sym_part = f" ({symbol}" + (f", {market}" if market else "") + ")" if symbol else ""
    target_line = f"**Research Target**: {target_name}{sym_part}"

    # Context section
    if portfolio_ctx:
        context_body = portfolio_ctx
    elif holding_ctx:
        context_body = holding_ctx
    else:
        context_body = "\n*(No holding data available — proceeding with public information only.)*\n"

    extra_title = "## Additional Instructions" if report_language == "en" else "## 额外要求"
    extra_block = f"\n\n{extra_title}\n\n{extra_instruction}" if extra_instruction else ""
    final_language_guard = (
        "\n\nFinal answer language reminder: write the final report in English."
        if report_language == "en"
        else "\n\n最终语言提醒：最终报告必须使用简体中文输出，不要输出英文报告。"
    )

    return (
        f"{_priority_language_block(report_language)}\n\n"
        "---\n\n"
        "# AI Berkshire Skill\n\n"
        "以下是来自 xbtlin/ai-berkshire 的原始 skill 定义，请严格遵守其研究框架和输出纪律。\n"
        "*(The following is the original skill definition from xbtlin/ai-berkshire.)*\n\n"
        f"{skill_md}\n\n"
        "---\n\n"
        "# Platform Context\n\n"
        "以下是本资产管理平台注入的用户数据上下文。\n\n"
        f"{target_line}\n\n"
        f"{context_body}\n\n"
        "---\n\n"
        "# Execution Requirements\n\n"
        "你现在不是在 Claude Code slash command 中执行，而是在 Web 投研系统中执行。\n"
        "请严格遵守上方 AI Berkshire skill 的研究框架和输出纪律。\n\n"
        f"{_lang_block(report_language)}\n\n"
        f"{_format_requirements(report_language)}\n\n"
        f"{_source_requirements(report_language)}\n\n"
        f"{_research_loop_requirements(report_language)}"
        f"{extra_block}"
        f"{_disclaimer(report_language)}\n\n"
        f"{final_language_guard}\n\n"
        "---\n"
        "*Research framework adapted from [xbtlin/ai-berkshire](https://github.com/xbtlin/ai-berkshire), "
        "MIT License.*"
    )
