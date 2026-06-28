"""通用 CSV 导入器：允许用户自定义字段映射。

适用场景：券商不在预设列表内，用户手动匹配 CSV 列到标准字段。
"""

import csv
import io
from datetime import datetime
from typing import Dict, List, Optional

from importers.base import BaseImporter, ImportedTransactionDraft


class GenericImporter(BaseImporter):
    """通用 CSV 导入器。依赖用户提供的字段映射。"""

    broker_type = "generic"

    def __init__(self, mapping: Optional[Dict[str, str]] = None):
        """
        mapping: {standard_field: csv_column_name}
        例如: {"date": "交易日期", "action": "类型", "symbol": "代码"}
        """
        self.user_mapping = mapping or {}

    def detect_fields(self, headers: List[str]) -> Dict[str, Optional[str]]:
        """自动检测列名。先精确匹配，再模糊匹配。"""
        mapping: Dict[str, Optional[str]] = {
            "date": None, "action": None, "symbol": None, "name": None,
            "currency": None, "market": None,
            "quantity": None, "price": None, "fee": None, "amount": None,
        }

        for h in headers:
            if h is None:
                continue
            h_clean = h.strip()
            h_lower = h_clean.lower().replace(" ", "_").replace("-", "_")

            # 精确匹配标准字段名
            for target in mapping:
                if mapping[target] is not None:
                    continue
                # 精确匹配字段名
                if h_lower == target:
                    mapping[target] = h_clean
                    break

            # 模糊匹配：列名包含目标字段名
            for target in mapping:
                if mapping[target] is not None:
                    continue
                if target in h_lower:
                    mapping[target] = h_clean

            # 中文常见列名
            cn_patterns = {
                "date": ["日期", "时间", "date"],
                "action": ["操作", "类型", "方向", "买卖", "action"],
                "symbol": ["代码", "symbol", "code"],
                "name": ["名称", "name", "证券"],
                "currency": ["币种", "currency", "货币"],
                "quantity": ["数量", "quantity", "股数", "份额"],
                "price": ["价格", "price", "成交价"],
                "fee": ["费用", "fee", "佣金", "手续费"],
                "amount": ["金额", "amount", "成交额"],
            }
            for target, patterns in cn_patterns.items():
                if mapping[target] is not None:
                    continue
                for pat in patterns:
                    if pat.lower() in h_lower:
                        mapping[target] = h_clean
                        break

        return mapping

    def _parse_csv_rows(self, data: bytes) -> List[dict]:
        """解析通用 CSV 字节流。"""
        text = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        return list(reader)

    def _map_row(self, row_num: int, row: dict) -> ImportedTransactionDraft:
        """使用用户映射将一行 CSV 转为 draft。"""
        d = ImportedTransactionDraft(
            source="generic",
            row_number=row_num,
            raw_payload=dict(row),
        )

        # 优先使用用户映射，否则自动检测
        fm = self._resolve_mapping(row)

        d.date = self._get(row, fm, "date")
        d.action = self._get(row, fm, "action")
        d.symbol = self._get(row, fm, "symbol")
        d.name = self._get(row, fm, "name")
        d.currency = self._get(row, fm, "currency")
        d.market = self._get(row, fm, "market")
        d.quantity = self._get_float(row, fm, "quantity")
        d.price = self._get_float(row, fm, "price")
        d.fee = self._get_float(row, fm, "fee")
        d.amount = self._get_float(row, fm, "amount")

        # 标准化 date
        if d.date:
            d.date = d.date.strip().replace("/", "-")
            # 尝试多种日期格式
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y"):
                try:
                    parsed = datetime.strptime(d.date, fmt)
                    d.date = parsed.strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue

        # 标准化 action
        if d.action:
            d.action = d.action.strip().lower()
            action_map = {
                "买入": "buy", "买": "buy", "buy": "buy",
                "卖出": "sell", "卖": "sell", "sell": "sell",
                "分红": "dividend", "股息": "dividend", "dividend": "dividend",
                "入金": "deposit", "存入": "deposit", "deposit": "deposit",
                "出金": "withdraw", "取出": "withdraw", "withdraw": "withdraw",
            }
            if d.action in action_map:
                d.action = action_map[d.action]

        self._validate_and_normalize(d)
        return d

    def _resolve_mapping(self, row: dict) -> Dict[str, str]:
        """解析最终使用的字段映射。"""
        # 如果有用户映射，直接使用
        if self.user_mapping:
            return self.user_mapping

        # 否则自动检测
        auto = {}
        for key in row.keys():
            k = key.strip().lower().replace(" ", "_").replace("-", "_")
            if k in ("date", "action", "symbol", "name", "currency",
                     "market", "quantity", "price", "fee", "amount"):
                if k not in auto:
                    auto[k] = key
        return auto

    def _get(self, row: dict, fm: dict, target: str) -> str:
        key = fm.get(target)
        if key is None:
            return ""
        return (row.get(key) or "").strip()

    def _get_float(self, row: dict, fm: dict, target: str) -> Optional[float]:
        val = self._get(row, fm, target)
        if not val:
            return None
        val = val.replace(",", "").replace("¥", "").replace("$", "")
        try:
            return float(val)
        except ValueError:
            return None
