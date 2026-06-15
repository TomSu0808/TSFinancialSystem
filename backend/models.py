"""数据模型（SQLModel 表）+ API 输入/输出 schema。

表：platform / holding / fxrate / snapshot
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


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


# ----------------------------- 表 -----------------------------
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    email: Optional[str] = Field(default=None, index=True)  # 阶段2 邮箱找回用
    password_hash: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


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


class UserCreate(SQLModel):
    username: str
    password: str
    email: Optional[str] = None


class UserLogin(SQLModel):
    username: str
    password: str


class UserRead(SQLModel):
    id: int
    username: str
    email: Optional[str] = None


class PasswordChange(SQLModel):
    old_password: str
    new_password: str


class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class TransactionCreate(SQLModel):
    platform_id: Optional[int] = None
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
