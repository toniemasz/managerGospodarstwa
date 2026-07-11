from django.core.exceptions import ValidationError


class FeedDomainError(ValidationError):
    """Bazowy, przewidywalny błąd domeny paszowej."""


class InvalidProductionTransitionError(FeedDomainError):
    pass


class InsufficientInventoryError(FeedDomainError):
    pass


class CrossFarmAccessError(FeedDomainError):
    pass


class FinishedFeedInsufficientStockError(FeedDomainError):
    pass


class ProductionRollbackError(FeedDomainError):
    pass
