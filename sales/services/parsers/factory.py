from sales.services.parsers.default_pdf_parser import DefaultSaleSettlementPdfParser


class SaleSettlementParserFactory:
    @staticmethod
    def create(file_type: str = 'pdf'):
        if file_type != 'pdf':
            raise ValueError(f"Nieobsługiwany typ parsera: {file_type}")
        return DefaultSaleSettlementPdfParser()
