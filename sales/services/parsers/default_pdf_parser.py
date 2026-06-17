from sales.services.parsers.base import SaleSettlementParserStrategy
from sales.services.pdf_import_service import SaleSettlementPdfParser


class DefaultSaleSettlementPdfParser(SaleSettlementPdfParser, SaleSettlementParserStrategy):
    pass
