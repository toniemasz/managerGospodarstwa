from abc import ABC, abstractmethod
from typing import BinaryIO

from sales.services.pdf_import_service import SaleSettlementImport


class SaleSettlementParserStrategy(ABC):
    @abstractmethod
    def parse(self, file_obj: BinaryIO) -> SaleSettlementImport:
        raise NotImplementedError
