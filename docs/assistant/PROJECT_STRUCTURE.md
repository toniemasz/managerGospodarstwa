# Mapa projektu `managerGospodarstwa`

Aktualizacja: 2026-10-14. Ta mapa opisuje aktualny branch `develop` i służy do
szybkiego zawężenia obszaru pracy. Statyczne liczby plików celowo pominięto,
ponieważ szybko się dezaktualizują; aktualny zakres zawsze ustalaj przez `rg --files`.

## 1. Obraz całości

```text
managerGospodarstwa/
├── AGENTS.md                    zasady obowiązujące każdą zmianę
├── README.md                    uruchomienie, technologie i deployment
├── manage.py
├── managerGospodarstwa/         konfiguracja Django i główne URL-e
├── common/                      neutralne helpery współdzielone
├── farms/                       kontekst gospodarstwa i funkcje przekrojowe
├── sows/                        stado, rozród, szczepienia, upadki, prosięta
├── feed/                        magazyn, FIFO, receptury i produkcja paszy
├── sales/                       sprzedaż i import rozliczeń PDF
├── costs/                       koszty ręczne i koszt produkcji paszy
├── templates/                   wspólny shell, komponenty i widoki modułów
├── static/                      źródłowy CSS i JavaScript
├── staticfiles/                 wynik collectstatic; nie edytować
├── docs/                        dokumentacja produktu i operacji
├── .github/workflows/           testy, deployment i backup produkcyjny
├── start.sh                     lokalny PostgreSQL, migracje, demo i serwer
├── test.sh                      izolowany PostgreSQL 17.6 i pytest
└── docker-compose.yml           lokalny PostgreSQL
```

`core/` nie zawiera obecnie kodu aplikacyjnego. Nie należy umieszczać tam nowych
funkcji bez jawnej decyzji architektonicznej.

## 2. Konfiguracja i wejście HTTP

- `managerGospodarstwa/settings.py` — aplikacje, middleware, cache, baza,
  lokalizacja i statyczne zasoby. `CurrentFarmMiddleware` działa po
  `AuthenticationMiddleware`.
- `managerGospodarstwa/urls.py` — główny router i administracyjne operacje
  backup/restore.
- `managerGospodarstwa/admin_backup.py` — wysokiego ryzyka backup/restore całej
  bazy, dostępne administratorowi.
- `templates/base.html` — wspólny dokument HTML, skip link, topbar, wiadomości i
  bloki rozszerzeń.
- `farms/context_processors.py` — dane wspólne dla shellu: gospodarstwo,
  nawigacja, wygląd i powiadomienia.

Główne prefiksy URL:

| Prefiks | Moduł | Najważniejsze widoki |
| --- | --- | --- |
| `/` | `sows` + centrala `farms` | centrala, katalog modułów, maciory, logowanie |
| `/ustawienia/` | `farms` | ustawienia, zadania, audyt, eksport/import, opłacalność |
| `/statystyki/` | `farms` | raport przekrojowy i sekcje domenowe |
| `/sprzedaz/` | `sales` | lista, formularz, import PDF, edycja i usuwanie |
| `/pasza/` | `feed` | składniki, magazyn, receptury, produkcja, podania |
| `/koszty/` | `costs` | koszty i kategorie |
| `/admin/` | Django admin | administracja i backup/restore bazy |

## 3. Moduły i publiczne wejścia

### `common`

Nie jest domeną biznesową. Zawiera:

- `money.py` — wspólna kwantyzacja kg, kwot i cen;
- `units.py` — konwersje kg/t oraz zł/kg i zł/t;
- `date_range.py` — jawny `DateRange` i parser zakresów;
- `filter_ui.py` — wspólny stan filtrów i aktywne chipy;
- `cache.py` — wersjonowane klucze per gospodarstwo, bezpieczny dostęp i
  unieważnianie po `transaction.on_commit`;
- `forms.py` — współdzielone mixiny pól ilości i ceny; obecnie mixin masy i
  mixin ceny mają rozdzielone odpowiedzialności, a zgodność starego klucza
  `price_unit` jest obsługiwana wyłącznie na granicy wejścia;
- `number_formatting.py` — jedno źródło polskiego formatowania liczb, pieniędzy
  i procentów dla kodu Python oraz cienkich filtrów template.

Nie przenoś tu reguł należących do konkretnej domeny.

### `farms`

Właściciel kontekstu gospodarstwa i funkcji przekrojowych.

- modele: `FarmModel`, `FarmSettingsModel`, `AuditLogModel`,
  `BackupImportPreviewModel`, `FormSubmissionModel`;
- aktywne gospodarstwo: `middleware.py`, `services/current_farm.py`,
  `services/farm_service.py`;
- nawigacja: `module_registry.py`, `services/module_navigation.py`,
  `actions/module_navigation.py`;
- dashboard i zadania: `services/today_dashboard.py`, `task_center.py` oraz
  `dashboard_settings.py`; stary równoległy `farm_dashboard.py` został usunięty;
- jednokrotny zapis formularzy: `services/idempotency.py` i unikalny klucz
  `(farm, user, scope, token)` w `FormSubmissionModel`;
- raportowanie: `services/statistics.py`, `statistics_presenter.py`,
  `statistics_period.py`, `profitability.py` i `calculators/statistics.py`;
- transfer danych: `services/data_backup.py` (format bieżący v6),
  `services/csv_transfer.py`;
- audyt: `services/audit_log_service.py`;
- wyszukiwanie: `services/global_search.py`;
- wejścia HTTP: `farms/views.py`, `farms/urls.py`.

`farms` agreguje publiczne raporty innych modułów, ale nie powiela ich reguł.

### `sows`

Właściciel cyklu produkcyjnego macior i opieki nad prosiętami.

- modele: `VaccinationPlanModel`, `SowModel`, `SowEventModel`,
  `PigletTransferModel`, `VaccinationCycleModel`, `MortalityReportModel`;
- maszyna stanów: `domain/sow_state_machine.py`;
- pozostałe reguły: `domain/event_details.py`, `mortality.py`,
  `vaccinations.py`;
- zapisy: `actions/sows.py`, `events.py`, `vaccinations.py`, `mortality.py`,
  `piglet_transfers.py`;
- procesy: `services/sow_event_service.py`, `bulk_event_service.py`,
  `event_details.py`, `piglet_care.py`, `vaccination_schedule.py`;
- odczyty: `selectors/mortality.py`, `selectors/piglet_transfers.py` oraz
  serwisy dashboardu, raportowania, aktywności i wyszukiwania;
- wejścia HTTP: `sows/views.py`, `sows/urls.py`.

Status maciory jest odtwarzany z chronologicznej historii `SowEventModel`.
Szczepienie nie zmienia głównego statusu. Przeniesienia prosiąt blokują właściwe
cykle i nie mogą spowodować ujemnego bilansu.

### `feed`

Najbardziej krytyczny moduł danych.

- surowce: `IngredientModel`, `DeliveryModel`,
  `IngredientPriceConfigModel`;
- receptury: `RecipeModel`, `RecipeItemModel`, `RecipeVersionModel`,
  `RecipeVersionItemModel`;
- produkcja i FIFO surowców: `ProductionModel`,
  `ProductionIngredientUsageModel`, `InventoryMovementModel`;
- gotowa pasza: `FeedProductModel`, `ReadyFeedDeliveryModel`,
  `FinishedFeedBatchModel`, `FeedServingModel`,
  `FeedServingAllocationModel`;
- zapisy: moduły w `feed/actions/`;
- czyste obliczenia: `calculators/feed_cost.py`;
- reguły i wyjątki: `domain/`;
- odczyty: `selectors/`;
- krytyczne workflow: `services/production_completion.py`,
  `production_reversal.py`, `reconciliation.py`, `integrity.py`;
- raporty/wyszukiwanie/dashboard: pozostałe moduły w `services/`;
- wejścia HTTP: `views.py`, `production_views.py`,
  `finished_feed_views.py`, `urls.py`.

Zwykłe zakończenie produkcji nie pozwala wymusić braków. Tryb częściowy/forced
jest ograniczony do kontrolowanej rekonsyliacji historycznej.

### `sales`

Właściciel dokumentów sprzedaży i ich wierszy klas.

- modele: `PigSaleModel`, `SaleClassRowModel`;
- zapis atomowy: `actions.py`;
- formularz i formset: `forms.py`;
- proces importu/formularza: `services/sale_form_service.py` z wejściem
  `SaleImportService`; dawny `SaleFormService` pozostaje aliasem zgodności;
- parsery: `services/parsers/` oraz `services/pdf_import_service.py`;
- odczyty i raporty: `selectors.py`, `reporting.py`, dashboard i search;
  `SaleRepository` pozostaje cienkim adapterem zgodności do selectorów;
- wejścia HTTP: `views.py`, `urls.py`.

Średnia cena za kg jest ważona wagą. Import PDF tworzy podgląd i ostrzeżenia;
niepewne wartości nie powinny być zapisywane bez świadomej akceptacji.

### `costs`

Właściciel rejestru kosztów.

- modele: `CostCategoryModel`, `CostModel`;
- zapisy: `actions.py`;
- listy i raporty: `services.py`;
- wejścia HTTP: `views.py`, `urls.py`.

Koszt ręczny i koszt produkcji to rozróżnione źródła. Jeden zakończony proces
produkcji ma najwyżej jeden wpis `CostModel.production`.

## 4. Kluczowe przepływy

### Kontekst żądania

```text
logowanie
  -> CurrentFarmMiddleware
  -> request.farm / get_current_farm(request)
  -> queryset/form/action ograniczony do farm
  -> template
```

### Zdarzenie maciory

```text
view + formularz
  -> SowEventActions / SowEventService
  -> walidacja SowStateMachine
  -> zapis SowEventModel w transakcji
  -> przeliczenie historii/statusu i zależnych danych
  -> audyt + unieważnienie cache po commit
```

### Dostawa surowca

```text
DeliveryForm/formset + token jednokrotnego zapisu
  -> farms.services.idempotency.execute_once
  -> feed.actions.deliveries
  -> DeliveryModel
  -> InventoryActions synchronizuje InventoryMovementModel
  -> ewentualna rekonsyliacja zależnego FIFO
  -> audyt + cache on_commit
```

### Receptura i wersja

```text
RecipeModel (tożsamość)
  -> RecipeVersionModel (snapshot historyczny)
  -> RecipeVersionItemModel
  -> nowa ProductionModel zapisuje recipe_version
```

`custom_recipe_data` ma pierwszeństwo dla jednorazowej produkcji.

### Zakończenie produkcji

```text
ProductionCompletionWorkflow (transaction.atomic)
  -> blokada ProductionModel
  -> walidacja przejścia
  -> InventoryActions.book_production
  -> blokady DeliveryModel i alokacje FIFO
  -> snapshot kosztu ProductionModel
  -> idempotentny CostModel
  -> FinishedFeedBatchModel
  -> automatyczny FeedServingModel + alokacja tej partii
  -> audyt/cache po commit
```

Niezmiennik kosztowy:

```text
sum(ProductionIngredientUsageModel.cost)
= ProductionModel.feed_cost_total
= CostModel.amount
= FinishedFeedBatchModel.total_cost
```

### Cofnięcie i przebudowa produkcji

`ProductionSettlementReversalWorkflow` wycofuje automatyczne podanie, alokacje
FIFO, koszt i partię, a następnie zapisuje powód i audyt. Odbudowa historii jest
scentralizowana w `ProductionReconciliationWorkflow`.

### Sprzedaż i PDF

```text
PigSaleForm + SaleClassRowFormSet + token jednokrotnego zapisu
  -> opcjonalny parser PDF i podgląd ostrzeżeń
  -> SaleImportService
  -> sales.actions.save_sale / replace_sale_rows
  -> przeliczenie sum i średniej ważonej
  -> audyt
```

### Raport przekrojowy

```text
serwisy raportowe sales/costs/feed/sows
  -> FarmStatisticsService
  -> StatisticsPresenter
  -> osobne sekcje template
```

### Backup gospodarstwa

`farms/services/data_backup.py` eksportuje pełny graf danych gospodarstwa.
Bieżący format to v6, a import obsługuje v1–v6. Analiza i preview nie zapisują
danych. Zastosowanie importu jest atomowe i jawnie rozróżnia dodanie od
zastąpienia.

## 5. Zależności między modułami

| Konsument | Dozwolona zależność | Zakaz |
| --- | --- | --- |
| `farms` | publiczne raporty, dashboardy i providery domen | ponowna implementacja FIFO/statusów |
| `costs` | wynik zatwierdzonego kosztu z `feed` | własne wyliczanie FIFO |
| `feed` | `costs.actions` dla projekcji kosztowej | zapis kosztu z widoku/template |
| `sales` | neutralne jednostki i raporty przekrojowe | bezpośrednie księgowanie kosztów |
| `sows` | `common`, `farms` dla kontekstu/audytu | zależność od UI innych domen |
| `common` | Django i biblioteka standardowa | import modeli domenowych |

Bezpośrednie importy wielu modeli przez backup/CSV i generator danych są
świadomymi integracjami pełnego grafu, nie wzorcem dla zwykłych funkcji.

## 6. Frontend

- wspólne komponenty: `templates/components/`;
- szablony domen: `templates/{farms,sows,feed,sales,costs}/`;
- tokeny: `static/css/base/variables.css`;
- shell/nawigacja: `base.css`, `navigation.css`;
- komponenty: `buttons.css`, `cards.css`, `forms.css`, `messages.css`,
  `tables.css`;
- style stron i breakpointy: `pages/app-pages.css`, `pages/responsive.css`;
- wspólny JS: `static/js/core/app.js`, `table-manager.js`;
- `FormsetController` w `app.js` jest wspólnym mechanizmem klonowania,
  usuwania, focusu, management form i pustego stanu; hooki sprzedaży, receptur,
  dostaw i zdarzeń pozostają domenowe;
- proste potwierdzenia CRUD korzystają ze wspólnego
  `components/confirmation_dialog.html`; procesy wysokiego ryzyka zachowują
  dedykowane ekrany/dialogi;
- współdzielone fragmenty receptury i etapów produkcji są w
  `templates/feed/components/`, a `page_header.html` jest aktywnym komponentem;
- JS stron: `static/js/pages/settings.js`, `productions.js`.

Nie edytuj `staticfiles/`; jest wynikiem `collectstatic`.

## 7. Miejsca wymagające szczególnej ostrożności

- `.env` może zawierać adres bazy innej niż lokalna; nie używaj go bez jawnego
  sprawdzenia celu.
- `ProductionModel` blokuje zwykłą edycję i usuwanie zakończonej produkcji.
- Relacje rozliczeniowe produkcji używają `RESTRICT`/`PROTECT` i wymagają action.
- Cache testowy jest domyślnie dummy; test hit/miss musi jawnie użyć locmem.
- `sows/views.py`, `feed/views.py`, `forms.py` oraz wspólne pliki CSS/JS są duże;
  przed zmianą znajdź dokładny fragment i wszystkie testy jego przepływu.
- Katalogi `*/tests/e2e/` są obecnie puste; nie zakładaj testu przeglądarkowego
  tylko dlatego, że katalog istnieje.
- Dokumentacja jest mapą. Przy zmianie zawsze wyszukaj wszystkie użycia modelu,
  funkcji, URL-a, klasy CSS albo komponentu.

## 8. Aktualizacja mapy

Po zmianie strukturalnej zaktualizuj co najmniej drzewo, sekcję właściciela,
model map, przepływ i zależności. Następnie dopisz wpis do
`docs/assistant/CHANGELOG.md`.
