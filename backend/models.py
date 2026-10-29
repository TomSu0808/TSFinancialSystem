"""数据模型（SQLModel 表）+ API 输入/输出 schema。

表：platform / holding / fxrate / snapshot
"""
import re
from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlmodel import Field, SQLModel
from sqlalchemy import UniqueConstraint

# 固定安全问题列表（key → 展示文本）
SECURITY_QUESTIONS: dict[str, str] = {
    "primary_school": "你的小学在哪？",
    "su_yanzu_handsome": "苏彦祖帅吗？",
    "favorite_car": "你最喜欢的车",
    "first_phone": "你的第一个手机是什么？",
    "favorite_game": "你最喜欢的游戏是什么？",
}


# ----------------------------- 枚举 -----------------------------
class Currency(str, Enum):
    CNY = "CNY"
    USD = "USD"
    HKD = "HKD"  # 预留


class AssetType(str, Enum):
    stock = "stock"
    etf = "etf"
    fund = "fund"
    bond = "bond"
    crypto = "crypto"
    cash = "cash"


class Market(str, Enum):
    A = "A"          # 沪深 A 股
    HK = "HK"        # 港股
    US = "US"        # 美股
    FUND = "FUND"    # 场外基金
    CRYPTO = "CRYPTO"
    NONE = "NONE"    # 不抓价（现金/债券等手填金额）


class HoldingSource(str, Enum):
    manual = "manual"      # 手填型：数量/成本用户直接维护
    derived = "derived"    # 交易驱动型：数量/成本由交易流水派生


class HoldingStatus(str, Enum):
    open = "open"
    closed = "closed"      # 清仓（数量归零），主列表默认隐藏


# ----------------------------- 表 -----------------------------
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    email: Optional[str] = Field(default=None, index=True)
    email_normalized: Optional[str] = Field(default=None, index=True)
    email_verified: bool = Field(default=False)
    email_verified_at: Optional[datetime] = Field(default=None)
    password_hash: str = ""
    password_changed_at: Optional[datetime] = Field(default=None)
    last_login_at: Optional[datetime] = Field(default=None)
    status: str = Field(default="active")  # active / disabled
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # 安全问题（用于找回密码）
    security_question_key: Optional[str] = Field(default=None)
    security_answer_hash: Optional[str] = Field(default=None)
    security_question_updated_at: Optional[datetime] = Field(default=None)


class AuthToken(SQLModel, table=True):
    """邮箱验证和密码重置 token（存 sha256 hash，不存明文）。"""
    __tablename__ = "authtoken"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    token_hash: str = Field(index=True)
    purpose: str  # "email_verification" | "password_reset"
    expires_at: datetime
    used_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_ip: Optional[str] = Field(default=None)


class Platform(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    name: str = Field(index=True)
    note: Optional[str] = None


class Holding(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    platform_id: int = Field(foreign_key="platform.id", index=True)
    currency: Currency = Currency.CNY
    asset_type: AssetType = AssetType.stock
    market: Market = Market.A
    symbol: str = ""
    name: str = ""
    quantity: Optional[float] = None       # 数量/股数/份额
    manual_value: Optional[float] = None   # 直接填的市值（无法抓价时用）
    cost_price: Optional[float] = None     # 成本价（单价，可选，用于盈亏）
    cost_value: Optional[float] = None     # 投入总成本/本金（本币，可选；基金等不知道单价时用）
    current_price: Optional[float] = None  # 当前价（刷新写入）
    prev_close: Optional[float] = None     # 昨收（刷新写入，算今日涨跌）
    price_updated_at: Optional[datetime] = None
    source: HoldingSource = HoldingSource.manual
    status: HoldingStatus = HoldingStatus.open
    realized_pnl: float = 0.0       # 累计已实现盈亏（derived）
    realized_pnl_incomplete: bool = False  # 存在成本未知的卖出，realized_pnl 仅含可计算部分
    realized_income: float = 0.0    # 累计分红/利息（derived）


class FxRate(SQLModel, table=True):
    pair: str = Field(default="USDCNY", primary_key=True)  # 1 USD = ? CNY
    rate: float = 7.2
    updated_at: Optional[datetime] = None


class Snapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    ts: datetime = Field(default_factory=datetime.utcnow)
    day: Optional[str] = Field(default=None, index=True)  # YYYY-MM-DD，每人每天一条
    total_cny: float = 0.0
    total_usd: float = 0.0


class DailyPnl(SQLModel, table=True):
    """UTC 日累计收益检查点；不从资产总额差伪造投资收益。"""
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_daily_pnl_user_day"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    day: str = Field(index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    returns_json: str = "{}"
    basis_json: str = "{}"
    details_json: str = "[]"  # 逐仓位累计收益快照（含名称/平台/币种/汇率），供按日查看明细
    pnl_cny: Optional[float] = None
    pnl_usd: Optional[float] = None
    status: str = "baseline"
    note: str = ""
    coverage_complete: bool = False


class TxnAction(str, Enum):
    adjust = "adjust"    # 持仓校准：quantity 为绝对数量，price 为平均成本；无现金流
    buy = "buy"          # 买入
    sell = "sell"        # 卖出
    dividend = "dividend"  # 分红/利息
    deposit = "deposit"  # 入金
    withdraw = "withdraw"  # 出金
    cash_adjust = "cash_adjust"  # 现金校准/初始化：amount 为该时点绝对余额；无现金流
    other = "other"      # 其它


class Transaction(SQLModel, table=True):
    """交易及持仓校准记录，买卖与校准驱动持仓重算。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    platform_id: Optional[int] = Field(default=None, foreign_key="platform.id", index=True)
    holding_id: Optional[int] = Field(default=None, foreign_key="holding.id", index=True)
    date: str = ""                       # YYYY-MM-DD
    action: TxnAction = TxnAction.buy
    name: str = ""
    symbol: str = ""
    currency: Currency = Currency.CNY      # 计价/持仓币种（港股为 HKD）
    cash_currency: Optional[Currency] = None  # 结算币种；空表示与 currency 相同（港股通用 CNY）
    fx_rate: Optional[float] = None       # 1 currency = ? cash_currency；跨币种买卖/分红用
    quantity: Optional[float] = None
    price: Optional[float] = None
    fee: Optional[float] = None
    amount: Optional[float] = None        # 现金流总额（结算币种；可手填，否则按 量×价±费×汇率 估算）
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Note(SQLModel, table=True):
    """投资心得 / 决策日志：自由记录的笔记，也可关联标的和持仓。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    title: Optional[str] = None
    content: str = ""
    # 关联字段
    related_holding_id: Optional[int] = Field(default=None, foreign_key="holding.id", index=True)
    source_report_id: Optional[int] = Field(default=None, foreign_key="researchreport.id", index=True)
    symbol: Optional[str] = Field(default=None, index=True)
    # 分类字段
    note_type: str = Field(default="general")  # thesis/risk/review/action/observation/general
    status: str = Field(default="active")       # active/resolved/invalidated/archived
    tags: Optional[str] = Field(default=None)   # 逗号分隔
    # 跟踪事项（复用决策日志，不新建第二套跟踪表）
    metric: Optional[str] = None                # 观察指标
    review_date: Optional[str] = None           # YYYY-MM-DD，或为空
    trigger_condition: Optional[str] = None     # 事件/指标触发条件
    report_version: Optional[int] = None        # 产生该事项的研究版本
    last_reviewed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ----------------------------- API schema -----------------------------
class PlatformCreate(SQLModel):
    name: str
    note: Optional[str] = None


class PlatformUpdate(SQLModel):
    name: Optional[str] = None
    note: Optional[str] = None


class HoldingCreate(SQLModel):
    platform_id: int
    currency: Currency = Currency.CNY
    asset_type: AssetType = AssetType.stock
    market: Market = Market.A
    symbol: str = ""
    name: str = ""
    quantity: Optional[float] = None
    manual_value: Optional[float] = None
    cost_price: Optional[float] = None
    cost_value: Optional[float] = None
    source: HoldingSource = HoldingSource.manual


class HoldingUpdate(SQLModel):
    platform_id: Optional[int] = None
    currency: Optional[Currency] = None
    asset_type: Optional[AssetType] = None
    market: Optional[Market] = None
    symbol: Optional[str] = None
    name: Optional[str] = None
    quantity: Optional[float] = None
    manual_value: Optional[float] = None
    cost_price: Optional[float] = None
    cost_value: Optional[float] = None


_USERNAME_RE = re.compile(r'^[a-zA-Z0-9_-]{3,32}$')
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class UserCreate(SQLModel):
    username: str
    email: Optional[str] = None  # 可选；填写后自动发送验证邮件
    password: str
    security_question_key: str  # 必须是 SECURITY_QUESTIONS 中的 key
    security_answer: str        # 明文，后端 hash 后存储


class UserLogin(SQLModel):
    username: str
    password: str


class UserRead(SQLModel):
    id: int
    username: str
    email: Optional[str] = None
    email_verified: bool = False
    status: str = "active"
    has_email: bool = False
    has_security_question: bool = False
    security_question_key: Optional[str] = None
    security_question_text: Optional[str] = None


class PasswordChange(SQLModel):
    old_password: str
    new_password: str


class ForgotPassword(SQLModel):
    email: str


class ResetPassword(SQLModel):
    token: str
    new_password: str


class VerifyEmailInput(SQLModel):
    token: str


class ChangeEmailInput(SQLModel):
    new_email: str


class SetSecurityQuestionInput(SQLModel):
    current_password: str
    security_question_key: str
    security_answer: str


class RecoveryQuestionInput(SQLModel):
    username: str


class ResetBySecurityQuestionInput(SQLModel):
    username: str
    security_question_key: str
    security_answer: str
    new_password: str


class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
    dev_verification_url: Optional[str] = None


class TransactionCreate(SQLModel):
    platform_id: Optional[int] = None
    holding_id: Optional[int] = None
    date: str = ""
    action: TxnAction = TxnAction.buy
    name: str = ""
    symbol: str = ""
    currency: Currency = Currency.CNY
    cash_currency: Optional[Currency] = None
    fx_rate: Optional[float] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    fee: Optional[float] = None
    amount: Optional[float] = None
    note: Optional[str] = None


class TransactionUpdate(SQLModel):
    platform_id: Optional[int] = None
    holding_id: Optional[int] = None
    date: Optional[str] = None
    action: Optional[TxnAction] = None
    name: Optional[str] = None
    symbol: Optional[str] = None
    currency: Optional[Currency] = None
    cash_currency: Optional[Currency] = None
    fx_rate: Optional[float] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    fee: Optional[float] = None
    amount: Optional[float] = None
    note: Optional[str] = None


class NoteCreate(SQLModel):
    title: Optional[str] = None
    content: str = ""
    related_holding_id: Optional[int] = None
    source_report_id: Optional[int] = None
    symbol: Optional[str] = None
    note_type: str = "general"
    status: str = "active"
    tags: Optional[str] = None
    metric: Optional[str] = None
    review_date: Optional[str] = None
    trigger_condition: Optional[str] = None
    report_version: Optional[int] = None


class NoteUpdate(SQLModel):
    title: Optional[str] = None
    content: Optional[str] = None
    related_holding_id: Optional[int] = None
    source_report_id: Optional[int] = None
    symbol: Optional[str] = None
    note_type: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[str] = None
    metric: Optional[str] = None
    review_date: Optional[str] = None
    trigger_condition: Optional[str] = None
    report_version: Optional[int] = None
    last_reviewed_at: Optional[datetime] = None


class ResearchStatus(str, Enum):
    draft = "draft"
    prompt_ready = "prompt_ready"  # legacy
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ReportLanguage(str, Enum):
    zh = "zh"
    en = "en"


class ResearchReport(SQLModel, table=True):
    """投研报告：AI 投研工作台生成的结构化研究记录。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    template_key: str = ""
    title: str = ""
    target_name: str = ""
    symbol: Optional[str] = None
    market: Optional[str] = None
    report_language: str = "zh"           # ReportLanguage values
    related_holding_id: Optional[int] = Field(default=None, foreign_key="holding.id")
    status: str = "draft"                 # ResearchStatus values
    input_context_md: Optional[str] = None
    skill_md: Optional[str] = None        # snapshot of the AI Berkshire skill used
    prompt_md: Optional[str] = None
    report_md: Optional[str] = None
    sources_json: Optional[str] = None
    error_message: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None        # BYOK 自定义 base URL
    user_ai_key_id: Optional[int] = Field(default=None, index=True)  # FK → UserAIKey.id
    provider_response_id: Optional[str] = None
    # 研究连续性与执行引擎。旧报告这些字段为空，可继续按原 Markdown 展示。
    parent_report_id: Optional[int] = Field(default=None, foreign_key="researchreport.id", index=True)
    version: int = Field(default=1)
    execution_mode: str = Field(default="standard")   # standard | multi_agent
    engine: Optional[str] = None                      # ai_provider | TradingAgents
    engine_version: Optional[str] = None
    engine_commit: Optional[str] = None
    report_json: Optional[str] = None                 # 本次生成的结构化摘要（缺失时降级正文）
    multi_agent_json: Optional[str] = None            # 各角色观点与分歧
    input_snapshot_json: Optional[str] = None         # 提交 AI 前的数据快照与覆盖说明
    usage_json: Optional[str] = None                  # 原始 usage 汇总
    budget_json: Optional[str] = None                 # 限额与停止原因
    source_status_json: Optional[str] = None          # 实际检索状态，不伪造“已核验”
    data_cutoff: Optional[str] = None
    idempotency_key: Optional[str] = Field(default=None, index=True)
    progress_stage: Optional[str] = None              # 最近真实阶段（事件表为完整记录）
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ResearchRunEvent(SQLModel, table=True):
    """研究任务的真实后台事件；前端进度只读这里，不生成虚假百分比。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    report_id: int = Field(foreign_key="researchreport.id", index=True)
    seq: int = Field(default=0)
    stage: str = ""
    status: str = ""                 # started/completed/failed/cancelled/info
    message: str = ""
    payload_json: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ResearchMessage(SQLModel, table=True):
    """报告内追问。每条消息独立保存，不覆盖原报告；一个报告一条连续对话。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    report_id: int = Field(foreign_key="researchreport.id", index=True)
    role: str = ""                   # user | assistant
    content: str = ""
    status: str = Field(default="completed")  # queued/running/completed/failed/cancelled
    request_id: Optional[str] = Field(default=None, index=True)
    provider_response_id: Optional[str] = None
    sources_json: Optional[str] = None
    new_sources_json: Optional[str] = None
    data_as_of: Optional[str] = None
    used_web_search: bool = Field(default=False)
    search_status: Optional[str] = None
    context_compressed: bool = Field(default=False)
    error_message: Optional[str] = None
    usage_json: Optional[str] = None
    budget_json: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ResearchPreference(SQLModel, table=True):
    """用户可编辑的研究偏好；不从资产规模推断。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, unique=True)
    investment_goal: Optional[str] = None
    holding_period: Optional[str] = None
    risk_preference: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ResearchRunCreate(SQLModel):
    template_key: str
    target_name: Optional[str] = None
    symbol: Optional[str] = None
    market: Optional[str] = None
    related_holding_id: Optional[int] = None
    report_language: ReportLanguage = ReportLanguage.zh
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    extra_instruction: Optional[str] = None
    use_web_search: bool = True
    display_currency: Currency = Currency.CNY
    execution_mode: str = "standard"       # standard | multi_agent
    include_holding_context: bool = True
    idempotency_key: Optional[str] = None


class ResearchPreviewRequest(SQLModel):
    template_key: str
    target_name: Optional[str] = None
    symbol: Optional[str] = None
    market: Optional[str] = None
    related_holding_id: Optional[int] = None
    report_language: ReportLanguage = ReportLanguage.zh
    display_currency: Currency = Currency.CNY
    execution_mode: str = "standard"
    include_holding_context: bool = True
    use_web_search: bool = True
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None


class ResearchUpdateRequest(SQLModel):
    extra_instruction: Optional[str] = None
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    use_web_search: bool = True
    idempotency_key: Optional[str] = None


class ResearchMessageCreate(SQLModel):
    question: str
    use_web_search: bool = False
    request_id: Optional[str] = None


class ResearchPreferenceUpdate(SQLModel):
    investment_goal: Optional[str] = None
    holding_period: Optional[str] = None
    risk_preference: Optional[str] = None


class TrackingItem(SQLModel):
    text: str
    metric: Optional[str] = None
    review_date: Optional[str] = None
    trigger_condition: Optional[str] = None
    symbol: Optional[str] = None
    status: str = "active"


class TrackingSaveRequest(SQLModel):
    items: List[TrackingItem]


class ResearchReportCreate(SQLModel):
    template_key: str
    title: str
    target_name: str
    symbol: Optional[str] = None
    market: Optional[str] = None
    related_holding_id: Optional[int] = None
    report_language: ReportLanguage = ReportLanguage.zh


class ResearchReportUpdate(SQLModel):
    title: Optional[str] = None
    target_name: Optional[str] = None
    symbol: Optional[str] = None
    market: Optional[str] = None
    status: Optional[str] = None
    report_language: Optional[str] = None
    prompt_md: Optional[str] = None
    report_md: Optional[str] = None


class UserAIKey(SQLModel, table=True):
    """用户自带 AI Provider API Key（BYOK）。同一用户同一 provider 只存一条。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    provider: str = Field(index=True)          # gpt / deepseek / glm / claude
    encrypted_api_key: str                      # Fernet 加密，绝不明文存储
    key_last4: str = Field(default="")          # 明文后 4 位，用于前端展示
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    is_default: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: Optional[datetime] = None


# ---- UserAIKey schemas ----

class UserAIKeyCreate(SQLModel):
    provider: str
    api_key: str
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    is_default: bool = False


class UserAIKeyUpdate(SQLModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    is_default: Optional[bool] = None


class UserAIKeyRead(SQLModel):
    id: int
    provider: str
    key_last4: str
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    is_default: bool
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None


class UserAIKeyTestInput(SQLModel):
    provider: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


# ── 自动化任务记录 ─────────────────────────────────────────────────────────────
class AutomationRun(SQLModel, table=True):
    """每次自动/手动全局刷新任务的执行记录。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    job_name: str = Field(default="daily_refresh")  # daily_refresh / manual
    triggered_by: str = Field(default="scheduler")  # scheduler / manual
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    status: str = Field(default="running")  # running / success / partial_failed / failed
    users_total: int = 0
    users_succeeded: int = 0
    holdings_total: int = 0
    holdings_updated: int = 0
    fx_updated: bool = False
    snapshots_saved: int = 0
    error_message: Optional[str] = None


# ── 导入会话 ───────────────────────────────────────────────────────────────────
class ImportSession(SQLModel, table=True):
    """一次导入会话（preview → commit 流程）。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    platform_id: Optional[int] = Field(default=None, index=True)
    broker_type: str = ""                    # futu / ibkr / generic
    file_name: Optional[str] = None
    detected_fields: Optional[str] = None    # JSON: 自动识别的列映射
    user_mapping: Optional[str] = None       # JSON: 用户修正后的映射
    rows_json: Optional[str] = None          # JSON: 解析后的所有行
    summary_json: Optional[str] = None       # JSON: {valid, error, warning, duplicate}
    status: str = "previewed"                # previewed / committed / failed
    created_transaction_count: int = 0
    skipped_duplicate_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── 对账快照 ───────────────────────────────────────────────────────────────────
class ReconSnapshot(SQLModel, table=True):
    """导入后对账结果：一行一条标的对比。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    import_session_id: Optional[int] = Field(default=None, index=True)
    platform_id: Optional[int] = Field(default=None, index=True)
    symbol: str = ""
    name: str = ""
    currency: Optional[str] = None
    broker_quantity: Optional[float] = None
    system_quantity: Optional[float] = None
    quantity_diff: Optional[float] = None
    broker_cost: Optional[float] = None
    system_cost: Optional[float] = None
    cost_diff: Optional[float] = None
    status: str = "matched"                 # matched / warning / error
    detail_json: Optional[str] = None       # JSON: 额外详情
    created_at: datetime = Field(default_factory=datetime.utcnow)


def market_value(h: Holding) -> float:
    """统一市值口径：手填金额优先，否则数量×现价（Decimal 精度）。"""
    if h.status == HoldingStatus.closed:
        return 0.0
    if h.manual_value is not None:
        return float(h.manual_value)
    if h.quantity is not None and h.current_price is not None:
        from decimal_utils import d_mul, to_float
        return to_float(d_mul(h.quantity, h.current_price))
    return 0.0


def _trade_value_in_holding_currency(t: "Transaction"):
    """交易的持仓币种金额：买入为付出的成本，卖出为到手的金额（含费用）。

    数量×价格本身就是持仓币种；手填 amount 是结算币种的实际净额，
    跨币种时按 fx_rate 折回持仓币种。
    """
    from decimal_utils import to_d

    qty, price, fee = to_d(t.quantity), to_d(t.price), to_d(t.fee)
    if t.amount is not None:
        cash = to_d(t.amount)
        if t.cash_currency is not None and t.cash_currency != t.currency:
            if not t.fx_rate:
                return qty * price  # 缺汇率时退回不含费用的成交额
            cash = cash / to_d(t.fx_rate)
        return cash
    if t.action == TxnAction.buy:
        return qty * price + fee
    return qty * price - fee


def day_change(h: Holding, today_trades=None) -> float:
    """今日涨跌额（本币）。

    按昨收→现价计市值变动；当日买入/卖出的份额按成交价起算，只算持有
    期间的涨跌，避免把成交前的行情算成当日盈亏：
        现市值 + 当日卖出净额 − 当日买入净额 − 昨日收盘时的持仓市值
    没有当日交易时退化为 数量 ×（现价 − 昨收）。
    """
    if h.status == HoldingStatus.closed or h.manual_value is not None:
        return 0.0
    trades = [
        t for t in (today_trades or [])
        if t.action in (TxnAction.buy, TxnAction.sell)
    ]
    if not trades:
        if h.quantity is not None and h.current_price is not None and h.prev_close is not None:
            from decimal_utils import d_mul, d_sub, to_float
            price_diff = d_sub(h.current_price, h.prev_close)
            return to_float(d_mul(h.quantity, price_diff))
        return 0.0
    if h.current_price is None:
        return 0.0

    from decimal_utils import to_d, to_float

    bought_qty = sum((to_d(t.quantity) for t in trades if t.action == TxnAction.buy), to_d(0))
    sold_qty = sum((to_d(t.quantity) for t in trades if t.action == TxnAction.sell), to_d(0))
    prev_qty = to_d(h.quantity) - bought_qty + sold_qty
    if prev_qty and h.prev_close is None:
        return 0.0

    baseline = prev_qty * to_d(h.prev_close)
    bought = sum(
        (_trade_value_in_holding_currency(t) for t in trades if t.action == TxnAction.buy),
        to_d(0),
    )
    sold = sum(
        (_trade_value_in_holding_currency(t) for t in trades if t.action == TxnAction.sell),
        to_d(0),
    )
    return to_float(to_d(market_value(h)) + sold - bought - baseline)


def cost_basis(h: Holding) -> Optional[float]:
    """成本（本币）：优先投入总成本 cost_value，否则数量×成本价（Decimal 精度）。缺两者则返回 None。"""
    if h.cost_value is not None:
        return float(h.cost_value)
    if h.quantity is not None and h.cost_price is not None:
        from decimal_utils import d_mul, to_float
        return to_float(d_mul(h.quantity, h.cost_price))
    return None


def profit(h: Holding) -> Optional[float]:
    """累计盈亏（本币）= 市值 − 成本（Decimal 精度）。成本未知则返回 None。"""
    if h.status == HoldingStatus.closed:
        return 0.0
    if not has_valuation(h):
        return None
    cb = cost_basis(h)
    if cb is None:
        return None
    from decimal_utils import d_sub, to_d, to_float
    return to_float(d_sub(to_d(market_value(h)), to_d(cb)))


def has_valuation(h: Holding) -> bool:
    return h.manual_value is not None or (h.quantity is not None and h.current_price is not None)
