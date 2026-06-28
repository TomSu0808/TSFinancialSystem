"""IBKR (Interactive Brokers) Activity Statement 导入器。

支持 IBKR Activity Statement CSV 导出格式。

第一版支持：
- Trades（交易）
- Dividends（分红）
- Deposits / Withdrawals（出入金）

IBKR 文件字段复杂，无法识别的资产类别会在 preview 中标注 warning/error。
"""

import csv
import io
from typing import Dict, List, Optional

from importers.base import BaseImporter, ImportedTransactionDraft


# IBKR 常见资产类别
IBKR_ASSET_CATEGORIES = {
    "STK": "stock",
    "OPT": "stock",     # Option — 第一版标为 warning
    "FUT": "stock",     # Future — 第一版标为 warning
    "CASH": "cash",
    "BOND": "bond",
    "FUND": "fund",
    "ETF": "etf",
    "WAR": "stock",     # Warrant
    "CFD": "stock",     # CFD — 第一版标为 warning
}

# 第一版明确不支持的资产类别
UNSUPPORTED_CATEGORIES = {"OPT", "FUT", "CFD", "WAR"}

# IBKR section markers in Activity Statement
SECTION_MARKERS = {
    "Trades": "trades",
    "Trade": "trades",
    "Dividends": "dividends",
    "Dividend": "dividends",
    "Withholding Tax": "tax",
    "Deposits & Withdrawals": "cash",
    "Deposits": "cash",
    "Withdrawals": "cash",
    "Fees": "fees",
}


class IBKRImporter(BaseImporter):
    """IBKR Activity Statement 导入器。"""

    broker_type = "ibkr"

    def detect_fields(self, headers: List[str]) -> Dict[str, Optional[str]]:
        """从列名自动识别 IBKR 字段映射。"""
        # IBKR 列名通常是大写带空格
        mapping: Dict[str, Optional[str]] = {
            "date": None, "action": None, "symbol": None, "name": None,
            "currency": None, "market": None,
            "quantity": None, "price": None, "fee": None, "amount": None,
        }

        ibkr_map = {
            "date": ["trade date", "date", "settle date", "datetime"],
            "symbol": ["symbol", "underlying symbol", "isin"],
            "name": ["description", "asset category"],
            "currency": ["currency", "currency primary"],
            "quantity": ["quantity", "shares", "amount"],
            "price": ["trade price", "price", "t. price"],
            "fee": ["commission", "comm", "fees", "ib commission"],
            "amount": ["proceeds", "net cash", "trade money", "amount", "value"],
            "action": ["buy/sell", "code"],
        }

        for h in headers:
            h_lower = h.strip().lower()
            for target, aliases in ibkr_map.items():
                if mapping[target] is not None:
                    continue
                for alias in aliases:
                    if alias in h_lower:
                        mapping[target] = h.strip()
                        break

        return mapping

    def _parse_csv_rows(self, data: bytes) -> List[dict]:
        """解析 IBKR Activity Statement CSV。"""
        text = data.decode("utf-8-sig")
        lines = text.splitlines()
        if not lines:
            return []

        # IBKR Activity Statement 可能有 section headers
        # 第一版简化处理：跳过头部非数据行，只解析表格部分
        data_lines = []
        header = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if "Trade Date" in line or "Symbol" in line or "Date" in line:
                header = line
                continue
            if header and line.startswith("Total") or line.startswith("SubTotal"):
                continue
            if header:
                data_lines.append(line)

        if not header:
            # Try parsing as regular CSV with a header row
            if not lines:
                return []
            # Find the first line that looks like a header
            for i, line in enumerate(lines):
                if any(kw in line.lower() for kw in ("date", "symbol", "trade")):
                    header = line
                    data_lines = [l for l in lines[i+1:] if l.strip()
                                  and not l.strip().startswith("Total")
                                  and not l.strip().startswith("SubTotal")]
                    break
            if not header:
                # Fallback: treat first line as header
                reader = csv.DictReader(io.StringIO(text))
                return list(reader)

        csv_text = "\n".join([header] + data_lines)
        reader = csv.DictReader(io.StringIO(csv_text))
        return list(reader)

    def _map_row(self, row_num: int, row: dict) -> ImportedTransactionDraft:
        """将 IBKR 一行映射为 draft。"""
        d = ImportedTransactionDraft(
            source="ibkr",
            row_number=row_num,
            raw_payload=dict(row),
        )

        fm = self._ibkr_field_map(row)

        # 提取字段
        d.date = self._get(row, fm, "date")
        d.symbol = self._get(row, fm, "symbol")
        d.name = self._get(row, fm, "name")
        d.currency = self._get(row, fm, "currency")
        d.quantity = self._get_float(row, fm, "quantity")
        d.price = self._get_float(row, fm, "price")
        d.fee = self._get_float(row, fm, "fee")
        d.amount = self._get_float(row, fm, "amount")

        # Action 推断
        d.action = self._infer_action(row, fm, d)

        # 市场推断
        d.market = self._infer_market(row, d)

        # 资产类别检查
        asset_cat = self._get(row, fm, "asset_category")
        if asset_cat and asset_cat.upper() in UNSUPPORTED_CATEGORIES:
            d.warnings.append(f"资产类别 {asset_cat} 目前部分支持，请核对导入结果")

        # 标准化日期（IBKR 常见格式: 2024-01-15, 20240115）
        if d.date:
            date_str = d.date.strip()
            if len(date_str) == 8 and date_str.isdigit():
                # 20240115 → 2024-01-15
                d.date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

        self._validate_and_normalize(d)
        return d

    def _ibkr_field_map(self, row: dict) -> Dict[str, str]:
        """从 IBKR 行数据建立字段映射。"""
        mapping = {}
        aliases = {
            "date": ["trade date", "date", "settle date", "datetime", "date/time"],
            "symbol": ["symbol", "underlying symbol", "underlying", "isin"],
            "name": ["description", "asset category"],
            "currency": ["currency", "currency primary"],
            "quantity": ["quantity", "shares", "amount"],
            "price": ["trade price", "price", "t. price"],
            "fee": ["commission", "comm", "fees", "ib commission", "comm/fee"],
            "amount": ["proceeds", "net cash", "trade money", "value"],
            "asset_category": ["asset category", "asset class", "type"],
            "buy_sell": ["buy/sell", "code", "b/s", "side", "action"],
        }

        for key in row.keys():
            key_lower = key.strip().lower()
            for target, alias_list in aliases.items():
                if target in mapping:
                    continue
                for alias in alias_list:
                    if alias in key_lower:
                        mapping[target] = key
                        break

        return mapping

    def _infer_action(self, row: dict, fm: dict, d: ImportedTransactionDraft) -> str:
        """从 IBKR 行数据推断交易类型。"""
        # 直接看 buy/sell 列
        bs = self._get(row, fm, "buy_sell").upper()
        if bs in ("BUY", "B"):
            return "buy"
        if bs in ("SELL", "S"):
            return "sell"

        # 从 description 推断
        desc = self._get(row, fm, "name").upper()
        if "DIVIDEND" in desc or "DIV" in desc:
            return "dividend"
        if "DEPOSIT" in desc or "CREDIT" in desc:
            return "deposit"
        if "WITHDRAW" in desc or "DEBIT" in desc:
            return "withdraw"
        if "FEE" in desc or "COMMISSION" in desc:
            return "other"

        # 从 amount 符号推断
        amt = d.amount
        if d.quantity is not None and d.quantity > 0:
            return "buy"
        elif d.quantity is not None and d.quantity < 0:
            d.quantity = abs(d.quantity)
            return "sell"

        return ""  # 无法推断，留给校验层

    def _infer_market(self, row: dict, d: ImportedTransactionDraft) -> str:
        """从 symbol 和 currency 推断市场。"""
        symbol = d.symbol.upper() if d.symbol else ""
        # IBKR symbol 常见模式
        if symbol and not any(c.isdigit() for c in symbol):
            # Pure alpha: likely US
            return "US"
        if re_match(r'^\d{5,6}$', symbol):
            return "HK"
        if re_match(r'^\d{6}$', symbol):
            if d.currency == "CNY":
                return "A"
            return "HK"
        return ""

    def _get(self, row: dict, fm: dict, target: str) -> str:
        key = fm.get(target)
        if key is None:
            return ""
        return (row.get(key) or "").strip()

    def _get_float(self, row: dict, fm: dict, target: str) -> Optional[float]:
        val = self._get(row, fm, target)
        if not val:
            return None
        val = val.replace(",", "").replace("(", "-").replace(")", "")
        try:
            return float(val)
        except ValueError:
            return None


def re_match(pattern: str, text: str) -> bool:
    import re
    return bool(re.match(pattern, text))
