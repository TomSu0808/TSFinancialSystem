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

    extra_block = f"\n\n## Additional Instructions\n\n{extra_instruction}" if extra_instruction else ""

    return (
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
        "## Source Requirements\n\n"
        "- Every factual claim must cite its source (annual report, SEC/exchange filing, "
        "earnings call, industry report, news).\n"
        "- If a source cannot be verified, state this explicitly — do not fabricate data.\n"
        "- Distinguish between audited facts, management estimates, and analyst consensus.\n"
        f"{extra_block}"
        f"{_disclaimer(report_language)}\n\n"
        "---\n"
        "*Research framework adapted from [xbtlin/ai-berkshire](https://github.com/xbtlin/ai-berkshire), "
        "MIT License.*"
    )
