"""统一导入中间模型和基类。

所有券商解析器都继承 BaseImporter，输出 ImportedTransactionDraft 列表。
导入服务层只对接 BaseImporter 接口，不关心具体券商格式。
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ImportedTransactionDraft:
    """解析后的标准化交易草稿（中间模型，不直接写库）。"""

    source: str = ""  # futu / ibkr / generic
    source_file_name: str = ""
    row_number: int = 0
    external_id: Optional[str] = None  # 券商侧 ID（若可提取）

    # 标准化交易字段
    date: str = ""  # YYYY-MM-DD
    action: str = ""  # buy / sell / dividend / deposit / withdraw / other
    symbol: str = ""
    name: str = ""
    market: str = ""  # A / HK / US / FUND / CRYPTO / NONE
    currency: str = ""  # CNY / USD / HKD
    quantity: Optional[float] = None
    price: Optional[float] = None
    fee: Optional[float] = None
    amount: Optional[float] = None

    # 解析元数据
    raw_payload: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    status: str = "valid"  # valid / warning / error / duplicate

    def normalized_hash(self) -> str:
        """生成归一化哈希，用于去重检测。

        基于 (source, symbol, currency, date, action, quantity, price, amount)
        的稳定字符串，忽略格式差异。
        """
        parts = [
            self.source,
            (self.symbol or "").strip().upper(),
            (self.currency or "").strip().upper(),
            (self.date or "").strip(),
            (self.action or "").strip().lower(),
        ]
        for v in (self.quantity, self.price, self.amount):
            if v is not None:
                parts.append(f"{v:.6f}")
            else:
                parts.append("")
        raw = "|".join(parts).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def row_hash(self) -> str:
        """基于原始 payload 的行级哈希（用于逐行去重）。"""
        raw = (self.source + "|" + str(self.row_number) + "|" +
               str(sorted(self.raw_payload.items()))).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


class BaseImporter:
    """券商导入器基类。

    子类只需实现:
      - _parse_csv_rows(data: bytes) -> List[dict]
      - _map_row(row_num: int, row: dict) -> ImportedTransactionDraft

    parse() 返回 drafts 列表（含 errors 标记），由 import_service 做统一校验。
    """

    broker_type: str = "generic"

    SUPPORTED_ACTIONS = {"buy", "sell", "dividend", "deposit", "withdraw", "other"}
    SUPPORTED_CURRENCIES = {"CNY", "USD", "HKD"}

    def parse(self, data: bytes, file_name: str = "") -> List[ImportedTransactionDraft]:
        """解析文件字节流，返回标准化 draft 列表。"""
        try:
            rows = self._parse_csv_rows(data)
        except Exception as e:
            return [
                ImportedTransactionDraft(
                    source=self.broker_type,
                    source_file_name=file_name,
                    status="error",
                    errors=[f"文件解析失败: {e}"],
                )
            ]

        drafts = []
        for row_num, row in enumerate(rows, 1):
            try:
                d = self._map_row(row_num, row)
            except Exception as e:
                d = ImportedTransactionDraft(
                    source=self.broker_type,
                    source_file_name=file_name,
                    row_number=row_num,
                    status="error",
                    errors=[f"行 {row_num} 映射失败: {e}"],
                    raw_payload=row,
                )
            d.source_file_name = file_name
            drafts.append(d)
        return drafts

    def detect_fields(self, headers: List[str]) -> Dict[str, Optional[str]]:
        """从 CSV 列名列表自动识别字段映射。返回 {field_name: column_name or None}。"""
        raise NotImplementedError

    def _parse_csv_rows(self, data: bytes) -> List[dict]:
        """子类实现：将字节流解析为 dict 行列表。"""
        raise NotImplementedError

    def _map_row(self, row_num: int, row: dict) -> ImportedTransactionDraft:
        """子类实现：将一行 dict 映射为 ImportedTransactionDraft。"""
        raise NotImplementedError

    def _validate_and_normalize(self, d: ImportedTransactionDraft) -> None:
        """统一基础校验和标准化（由 import_service 调用，也可子类预调用）。"""
        # date 校验
        if not d.date:
            d.errors.append("日期不能为空")
        else:
            try:
                datetime.strptime(d.date, "%Y-%m-%d")
            except ValueError:
                try:
                    # Try common Futu format: 2024/01/15
                    parsed = datetime.strptime(d.date, "%Y/%m/%d")
                    d.date = parsed.strftime("%Y-%m-%d")
                except ValueError:
                    d.errors.append(f"日期格式无效（需为 YYYY-MM-DD 或 YYYY/MM/DD）：{d.date}")

        # action 校验
        if d.action not in self.SUPPORTED_ACTIONS:
            d.errors.append(f"不支持的交易类型: {d.action}，支持: {', '.join(sorted(self.SUPPORTED_ACTIONS))}")
        else:
            d.action = d.action.lower()

        # currency 校验
        if d.currency:
            d.currency = d.currency.strip().upper()
            if d.currency not in self.SUPPORTED_CURRENCIES:
                d.errors.append(f"不支持的币种: {d.currency}，支持: {', '.join(sorted(self.SUPPORTED_CURRENCIES))}")

        # price/quantity/fee/amount 数字校验
        for field in ("price", "fee", "amount", "quantity"):
            v = getattr(d, field, None)
            if v is not None:
                try:
                    setattr(d, field, float(v))
                except (TypeError, ValueError):
                    d.errors.append(f"{field} 不是有效数字: {v}")
                    setattr(d, field, None)

        # 最终状态
        if d.errors:
            d.status = "error"
        elif d.warnings:
            d.status = "warning"
