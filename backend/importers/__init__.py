"""券商导入器包：支持富途 / IBKR / 通用 CSV 解析。"""

from importers.base import BaseImporter, ImportedTransactionDraft
from importers.futu import FutuImporter
from importers.ibkr import IBKRImporter
from importers.generic import GenericImporter

BROKER_IMPORTERS = {
    "futu": FutuImporter,
    "ibkr": IBKRImporter,
    "generic": GenericImporter,
}

__all__ = [
    "BaseImporter",
    "ImportedTransactionDraft",
    "FutuImporter",
    "IBKRImporter",
    "GenericImporter",
    "BROKER_IMPORTERS",
]
