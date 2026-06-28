"""富途证券 CSV 交易记录解析器。

支持富途常见导出的 CSV 格式：
- 中文列名（交易日期/成交日期、操作/买卖方向、代码、名称、数量…）
- 英文列名（date, action, symbol, name, quantity…）
- 混合列名

自动识别 buy/sell/dividend/deposit/withdraw 操作。
"""

import csv
import io
import re
from typing import Dict, List, Optional

from importers.base import BaseImporter, ImportedTransactionDraft


# 富途中文列名 → 标准字段映射
FUTU_CN_FIELD_MAP = {
    # 日期
    "交易日期": "date", "成交日期": "date", "日期": "date",
    # 操作
    "操作": "action", "买卖方向": "action", "类型": "action", "交易类型": "action",
    # 标的
    "代码": "symbol", "证券代码": "symbol", "股票代码": "symbol",
    "名称": "name", "证券名称": "name", "股票名称": "name",
    # 数量
    "数量": "quantity", "成交数量": "quantity", "股数": "quantity",
    # 价格
    "成交价格": "price", "价格": "price", "成交价": "price", "均价": "price",
    # 费用
    "费用": "fee", "手续费": "fee", "佣金": "fee", "交易费": "fee",
    "交易费用": "fee",
    # 金额
    "成交金额": "amount", "金额": "amount", "发生金额": "amount", "交易金额": "amount",
    # 币种
    "币种": "currency", "货币": "currency", "结算币种": "currency",
    # 市场
    "市场": "market", "交易市场": "market",
}

# 富途操作文本 → 标准 action
FUTU_ACTION_MAP = {
    "买入": "buy", "买": "buy",
    "卖出": "sell", "卖": "sell",
    "分红": "dividend", "股息": "dividend", "派息": "dividend",
    "入金": "deposit", "存入": "deposit", "转入": "deposit",
    "出金": "withdraw", "取出": "withdraw", "转出": "withdraw",
    "买入开仓": "buy", "卖出平仓": "sell",
}

# 富途市场文本 → 标准市场
FUTU_MARKET_MAP = {
    "港股": "HK", "香港": "HK", "HK": "HK",
    "美股": "US", "美国": "US", "US": "US",
    "A股": "A", "沪深": "A", "上海": "A", "深圳": "A", "A": "A",
    "基金": "FUND", "FUND": "FUND",
}


class FutuImporter(BaseImporter):
    """富途 CSV 交易记录导入器。"""

    broker_type = "futu"

    def detect_fields(self, headers: List[str]) -> Dict[str, Optional[str]]:
        """从列名自动识别字段映射。"""
        mapping: Dict[str, Optional[str]] = {
            "date": None, "action": None, "symbol": None, "name": None,
            "currency": None, "market": None,
            "quantity": None, "price": None, "fee": None, "amount": None,
        }
        for h in headers:
            if h is None:
                continue
            h_clean = h.strip()
            # 先查中文映射
            if h_clean in FUTU_CN_FIELD_MAP:
                target = FUTU_CN_FIELD_MAP[h_clean]
                if target in mapping:
                    mapping[target] = h_clean
            # 再尝试英文直接匹配
            h_lower = h_clean.lower().replace(" ", "_")
            if h_lower in mapping and mapping[h_lower] is None:
                mapping[h_lower] = h_clean
        return mapping

    def _parse_csv_rows(self, data: bytes) -> List[dict]:
        """解析富途 CSV 字节流。"""
        # Maybe BOM
        text = data.decode("utf-8-sig")
        # 富途某些 CSV 可能带空行，skip
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            return []
        reader = csv.DictReader(io.StringIO("\n".join(lines)))
        return list(reader)

    def _map_row(self, row_num: int, row: dict) -> ImportedTransactionDraft:
        """将富途一行 CSV 映射为 draft。"""
        d = ImportedTransactionDraft(
            source="futu",
            row_number=row_num,
            raw_payload=dict(row),
        )

        # 1. 识别字段映射
        fm = self._futu_field_map(row)
        # 2. 提取字段
        d.date = self._get(row, fm, "date")
        d.action = self._map_action(self._get(row, fm, "action"))
        d.symbol = self._get(row, fm, "symbol")
        d.name = self._get(row, fm, "name")
        d.currency = self._get(row, fm, "currency")
        d.market = self._map_market(self._get(row, fm, "market"))
        d.quantity = self._get_float(row, fm, "quantity")
        d.price = self._get_float(row, fm, "price")
        d.fee = self._get_float(row, fm, "fee")
        d.amount = self._get_float(row, fm, "amount")

        # 标准化 date（富途常见格式：2024/01/15 → 2024-01-15）
        if d.date:
            d.date = d.date.strip().replace("/", "-")

        # 3. 校验
        self._validate_and_normalize(d)

        return d

    def _futu_field_map(self, row: dict) -> Dict[str, str]:
        """逐个检查 row 的 key，返回 {target: actual_key} 映射。"""
        mapping = {}
        for key in row.keys():
            if key is None:
                continue
            key_clean = key.strip()
            if key_clean in FUTU_CN_FIELD_MAP:
                target = FUTU_CN_FIELD_MAP[key_clean]
                if target not in mapping:
                    mapping[target] = key_clean
            else:
                key_norm = key_clean.lower().replace(" ", "_")
                if key_norm in ("date", "action", "symbol", "name", "currency",
                                "market", "quantity", "price", "fee", "amount"):
                    if key_norm not in mapping:
                        mapping[key_norm] = key_clean

        # 补充：如果没找到，尝试模糊匹配
        for target in ("date", "action", "symbol", "name", "currency",
                       "quantity", "price", "fee", "amount"):
            if target not in mapping:
                for key in row.keys():
                    if key is None:
                        continue
                    if target in key.lower():
                        mapping[target] = key
                        break

        return mapping

    def _map_action(self, raw: str) -> str:
        """将富途操作文本映射为标准 action。"""
        if not raw:
            return ""
        raw = raw.strip()
        if raw.lower() in ("buy", "sell", "dividend", "deposit", "withdraw", "other"):
            return raw.lower()
        if raw in FUTU_ACTION_MAP:
            return FUTU_ACTION_MAP[raw]
        # 模糊匹配
        for cn, en in FUTU_ACTION_MAP.items():
            if cn in raw:
                return en
        return raw  # 未识别，留给校验层报 error

    def _map_market(self, raw: str) -> str:
        """将富途市场文本映射为标准 market。"""
        if not raw:
            return ""
        raw = raw.strip()
        if raw in ("A", "HK", "US", "FUND", "CRYPTO", "NONE"):
            return raw
        if raw in FUTU_MARKET_MAP:
            return FUTU_MARKET_MAP[raw]
        return raw

    def _get(self, row: dict, fm: dict, target: str) -> str:
        """从 row 中获取字段值。"""
        key = fm.get(target)
        if key is None:
            return ""
        return (row.get(key) or "").strip()

    def _get_float(self, row: dict, fm: dict, target: str) -> Optional[float]:
        """从 row 中获取数字字段值。"""
        val = self._get(row, fm, target)
        if not val:
            return None
        # Remove common formatting: thousand separators, currency symbols
        val = val.replace(",", "").replace("¥", "").replace("$", "").replace("HK$", "")
        try:
            return float(val)
        except ValueError:
            return None
