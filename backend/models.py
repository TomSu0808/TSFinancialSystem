"""数据模型（SQLModel 表）+ API 输入/输出 schema。

表：platform / holding / fxrate / snapshot
"""
import re
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel

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
    cost_price: Optional[float] = None     # 成本价（可选，用于盈亏）
    current_price: Optional[float] = None  # 当前价（刷新写入）
    prev_close: Optional[float] = None     # 昨收（刷新写入，算今日涨跌）
    price_updated_at: Optional[datetime] = None
    source: HoldingSource = HoldingSource.manual
    status: HoldingStatus = HoldingStatus.open
    realized_pnl: float = 0.0       # 累计已实现盈亏（derived）
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


class TxnAction(str, Enum):
    buy = "buy"          # 买入
    sell = "sell"        # 卖出
    dividend = "dividend"  # 分红/利息
    deposit = "deposit"  # 入金
    withdraw = "withdraw"  # 出金
    other = "other"      # 其它


class Transaction(SQLModel, table=True):
    """交易流水（独立账本，不自动改持仓）。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    platform_id: Optional[int] = Field(default=None, foreign_key="platform.id", index=True)
    holding_id: Optional[int] = Field(default=None, foreign_key="holding.id", index=True)
    date: str = ""                       # YYYY-MM-DD
    action: TxnAction = TxnAction.buy
    name: str = ""
    symbol: str = ""
    currency: Currency = Currency.CNY
    quantity: Optional[float] = None
    price: Optional[float] = None
    fee: Optional[float] = None
    amount: Optional[float] = None        # 现金流总额（可手填，否则前端按 量×价±费 估算展示）
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Note(SQLModel, table=True):
    """投资心得：自由记录的语录 / 笔记备忘。"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    title: Optional[str] = None
    content: str = ""
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
    quantity: Optional[float] = None
    price: Optional[float] = None
    fee: Optional[float] = None
    amount: Optional[float] = None
    note: Optional[str] = None


class NoteCreate(SQLModel):
    title: Optional[str] = None
    content: str = ""


class NoteUpdate(SQLModel):
    title: Optional[str] = None
    content: Optional[str] = None


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
    provider_response_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
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


def market_value(h: Holding) -> float:
    """统一市值口径：手填金额优先，否则数量×现价。"""
    if h.manual_value is not None:
        return h.manual_value
    if h.quantity is not None and h.current_price is not None:
        return h.quantity * h.current_price
    return 0.0


def day_change(h: Holding) -> float:
    """今日涨跌额（本币）。手填金额或缺昨收时记 0。"""
    if h.manual_value is not None:
        return 0.0
    if h.quantity is not None and h.current_price is not None and h.prev_close is not None:
        return h.quantity * (h.current_price - h.prev_close)
    return 0.0


def cost_basis(h: Holding) -> Optional[float]:
    """成本（本币）：数量×成本价。缺数量或成本价则返回 None（无法计算盈亏）。"""
    if h.quantity is not None and h.cost_price is not None:
        return h.quantity * h.cost_price
    return None


def profit(h: Holding) -> Optional[float]:
    """累计盈亏（本币）= 市值 − 成本。成本未知则返回 None。"""
    cb = cost_basis(h)
    if cb is None:
        return None
    return market_value(h) - cb
