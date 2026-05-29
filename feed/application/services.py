from feed.infrastructure.repositories import FeedRepository


class FeedManagementService:
    def __init__(self, repository: FeedRepository = None):
        self.repository = repository or FeedRepository()

    def get_inventory_dashboard(self):
        inventory = self.repository.get_inventory_state()

        # Ostrzeżenia o niskim stanie (< 500 kg)
        low_stock = [item for item in inventory if item.current_stock < 500]

        return {
            'inventory': inventory,
            'low_stock_alerts': low_stock
        }

    def get_calculator_data(self):
        return self.repository.get_recipe_costs()