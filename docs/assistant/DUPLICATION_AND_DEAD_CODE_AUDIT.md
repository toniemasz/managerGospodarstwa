# Audyt duplikacji, martwego kodu i spójności UX

Aktualizacja: 2026-10-14. Status: rekomendacje wdrożone i zweryfikowane;
historyczne dowody pozostawiono jako uzasadnienie decyzji.

## 1. Cel i sposób analizy

Audyt objął moduły Python, template'y Django, wspólny JavaScript i CSS. Użyto:

- wyszukiwania wszystkich odwołań przez `rg`;
- porównania struktur funkcji i klas w AST Pythona;
- porównania powtarzających się fragmentów template'ów i deklaracji CSS;
- prześledzenia publicznych wejść: URL → view → form → action/service → model;
- ręcznego sprawdzenia reprezentatywnych ekranów w lokalnej przeglądarce;
- istniejących 585 testów jako punktu odniesienia.

Wynik nie jest automatycznym poleceniem usunięcia każdego podobnego fragmentu.
W Django część wejść może być wykorzystywana dynamicznie. Przed usunięciem
każdego symbolu nadal trzeba ponownie znaleźć wszystkie użycia, uruchomić testy
modułu i sprawdzić publiczny przepływ. Jawne powtórzenia kontroli gospodarstwa,
transakcji i reguł domenowych nie powinny być centralizowane tylko po to, aby
zmniejszyć liczbę linii.

## Stan wdrożenia 2026-10-14

| Id | Stan | Zastosowane rozwiązanie |
| --- | --- | --- |
| DRY-01 | wykonane | jeden kontrakt `price_per_kg_unit`, rozdzielone mixiny i kontrolowana zgodność `price_unit` |
| DEAD-01 | wykonane | jedna fasada `TodayDashboardService`, helper ustawień przeniesiony, stary serwis i template usunięte |
| ARCH-01 | wykonane | farm-scoped selectory sprzedaży, zapis w actions, `SaleImportService`; dawne wejścia zachowane jako aliasy kompatybilności |
| DOMAIN-01 | wykonane | wspólny farm-scoped builder `sows.services.event_details` dla pojedynczych i masowych zdarzeń |
| UX-01 | wykonane | mały `FormsetController` z domenowymi hookami; natywne klonowanie `<template>`, focus i `aria-live` |
| UX-02 | wykonane | współdzielone części receptury i produkcji, aktywny `page_header`, usunięty martwy `task_item` |
| UX-03 | wykonane | wspólny dostępny dialog prostych potwierdzeń, spójne stopki; procesy wysokiego ryzyka pozostały dedykowane |
| UX-04 | wykonane | presety rozmiaru są główne, suwak jest ujawniany jako ustawienie własne |
| FORMAT-01 | wykonane | `common.number_formatting` i cienkie adaptery template |
| CSS-01 | wykonane | wspólna `.mobile-form-cards`, jedna definicja `.row-actions` |
| DRY-02 | wykonane | małe helpery formularzy i parserów bez łączenia różnych kontraktów domenowych |
| DEAD-02/03 | wykonane | usunięto symbole bez użyć i nieużywane importy; publiczne/testowe API zachowano jako zgodność |
| COMPAT-01 | zachowane świadomie | aliasy nadal istnieją, aby nie łamać funkcji i integracji; warstwa produkcyjna nie tworzy przez nie drugiego źródła prawdy |

Podczas ręcznego testu wykryto i naprawiono dodatkowy błąd wspólnego kontrolera:
`<tr>` nie może być parsowany w tymczasowym `<div>`. Klonowanie odbywa się teraz
przez `HTMLTemplateElement.content`, dzięki czemu management form, struktura
tabeli i przeniesienie focusu pozostają poprawne we wszystkich czterech formsetach.

## 2. Podsumowanie decyzji

Najważniejsze znaleziska:

1. **P0 — dwa mechanizmy jednostki ceny w jednym formularzu.** To nie jest
   wyłącznie duplikacja: formularz gotowej paszy pokazuje dwie listy „Jednostka
   ceny”, a POST zawierający obie wartości `t` dzieli cenę przez 1000 dwa razy.
2. **P1 — równoległa, nieużywana klasa starego dashboardu.** Aktywny ekran
   korzysta z `TodayDashboardService`, ale `FarmDashboardService` nadal powiela
   część pobierania danych. Funkcja ustawień z tego samego pliku jest aktywna,
   więc nie można usunąć całego pliku bez przeniesienia jej.
3. **P1 — nadmiarowa warstwa sprzedaży.** `SaleRepository` mapuje ORM 1:1 do
   `PigSaleEntity`, który powiela pola i obliczenie modelu. Nie daje to obecnie
   realnej wymienności źródła danych.
4. **P1 — powtórzony builder szczegółów zdarzenia maciory.** Formularz masowy i
   serwis zdarzeń wykonują tę samą logikę szczepienia.
5. **P1 — cztery podobne kontrolery formsetów w JS i powielone fragmenty
   template'ów.** Wspólny jest mechanizm techniczny, a różne pozostają reguły
   domenowe.
6. **P2 — martwe symbole i nieużywane komponenty.** Są kandydaci o wysokiej
   pewności oraz osobna grupa API używanych wyłącznie przez testy, której nie
   należy usuwać bez decyzji o kompatybilności.
7. **P2 — niespójna prezentacja liczb, pieniędzy i akcji formularza.** Istnieją
   co najmniej trzy lokalne formatery liczb oraz wiele ręcznych wariantów
   nagłówka, anulowania, usuwania i potwierdzeń.

Rekomendowany kierunek to kilka małych zmian, nie duży refaktor. Najpierw
integralność ceny, potem bezpieczne usunięcie kodu bez wejść, a dopiero później
wspólne komponenty UX i uproszczenie warstw.

## 3. Wdrożone rekomendacje i historyczne uzasadnienie

### DRY-01 / P0 — jedno źródło prawdy dla jednostki ceny

**Dowód**

- `common/forms.py` zawiera dwa nakładające się mixiny:
  `KilogramStorageFormMixin` obsługuje masę, ale dodatkowo dodaje `price_unit` i
  przelicza `price_per_kg`; `PricePerKilogramStorageFormMixin` dodaje
  `price_per_kg_unit` i wykonuje to samo przeliczenie.
- `DeliveryForm` oraz `ReadyFeedDeliveryForm` dziedziczą po obu mixinach.
- `delivery_form.html` ręcznie renderuje tylko `price_per_kg_unit`, ukrywając
  drugi element. `ready_feed_delivery_form.html` iteruje po wszystkich polach,
  dlatego pokazuje oba selecty.
- Ręczna próba formularza dała:
  `2100 zł/t → 2.10000 zł/kg` przy jednym polu oraz
  `2100 zł/t → 0.00210 zł/kg` przy obu polach ustawionych na `t`.

**Rekomendacja**

- zastosować zasadę Single Responsibility:
  `KilogramStorageFormMixin` obsługuje wyłącznie masę, a
  `PricePerKilogramStorageFormMixin` wyłącznie cenę;
- przyjąć jedno publiczne pole `price_per_kg_unit`;
- usunąć lokalne kopie `PRICE_UNIT_CHOICES`, `KILOGRAMS_PER_TONNE` i kwantu z
  `common/forms.py`, korzystając z `common.units`;
- jeśli stare formularze z przeglądarki wymagają zgodności, mapować dawny klucz
  `price_unit` tylko na granicy wejścia i przez ograniczony okres, bez dodawania
  drugiego pola do formularza;
- nie łączyć obsługi masy i ceny w jeden duży „uniwersalny” mixin.

**Testy akceptacyjne**

- dokładna lista pól obu formularzy zawiera jedną jednostkę ceny;
- HTML obu ekranów zawiera dokładnie jeden widoczny select „Jednostka ceny”;
- `2100 zł/t` zawsze zapisuje `2.10000 zł/kg`, także dla ewentualnego payloadu
  zgodności wstecznej;
- podanie obu nazw klucza nie może wykonać podwójnego przeliczenia;
- kg/t, wartości graniczne, formularz pojedynczy i formset dostaw;
- pełne testy `feed`, ponieważ wynik wpływa na FIFO i koszt.

### DEAD-01 / P1 — rozdzielenie aktywnych ustawień od starego dashboardu

**Dowód**

- aktywny `modules_home_view` renderuje `farms/today_dashboard.html` z
  `TodayDashboardService`;
- brak odwołań do klasy `FarmDashboardService`;
- `FarmDashboardService._inventory_summary()` i `_task_summary()` powtarzają
  mechanizm obecny w `TodayDashboardService`;
- `dashboard_stat_groups()` z tego samego pliku jest używane w ustawieniach i
  musi pozostać;
- `templates/sows/modules_home.html` nie jest renderowany ani include'owany.

**Rekomendacja**

- przenieść `dashboard_stat_groups()` do modułu ustawień/dashboard registry;
- usunąć dopiero wtedy nieużywaną klasę `FarmDashboardService` i stary template;
- zachować `TodayDashboardService` jako jedną fasadę odczytu dla ekranu dnia;
- po usunięciu sprawdzić selektory CSS specyficzne dla starego template'u, ale
  nie usuwać wspólnych klas dashboardu używanych w aktywnym ekranie.

**Testy akceptacyjne**

- URL `modules_home` nadal renderuje aktywny dashboard;
- ekran ustawień nadal grupuje statystyki;
- test braku referencji do usuniętego template'u/klasy;
- testy `farms` i reprezentatywne testy dashboardów innych domen.

### ARCH-01 / P1 — uproszczenie warstw odczytu sprzedaży

**Dowód**

- `SaleRepository` opakowuje Django ORM i mapuje każdy `PigSaleModel` 1:1 do
  `PigSaleEntity`;
- encja kopiuje pola modelu i powiela właściwość `total_price`;
- repozytorium jest potrzebne głównie `SaleDashboardService`, bez drugiego
  źródła danych lub wymiennej implementacji;
- `SaleFormService.save_sale()` i `replace_sale_rows()` są cienkimi delegacjami
  do istniejących actions.

**Rekomendacja**

- odczyty przenieść do nazwanych selectorów/QuerySetów ograniczonych przez
  `farm`, zwracających modele albo wąski, niemutowalny DTO tylko tam, gdzie
  raport faktycznie go potrzebuje;
- zapis pozostawić w `sales.actions` jako publiczny Command/Action;
- `SaleFormService` ograniczyć do orkiestracji importu i przygotowania formularza
  albo nazwać tę odpowiedzialność wprost `SaleImportService`;
- zachować parser PDF jako Adapter, ale usunąć pustą implementację Strategy i
  Factory, dopóki istnieje tylko jeden obsługiwany typ. Fabrykę przywrócić, gdy
  pojawi się drugi realny parser;
- nie tworzyć wspólnego generycznego repozytorium dla pozostałych modułów.

**Testy akceptacyjne**

- farm scope dla listy, szczegółu i dashboardu;
- identyczne wartości netto/brutto oraz fallback sumy;
- import PDF, ostrzeżenia i atomowy zapis bez zmian;
- pomiar liczby zapytań przed i po, szczególnie dla relacji `rows`.

### DOMAIN-01 / P1 — jeden builder szczegółów zdarzeń macior

**Dowód**

- `BulkSowEventRowForm.build_details()` i `SowEventService.build_details()`
  wywołują `build_event_details()`, a następnie identycznie wyszukują plan
  szczepień i dodają `vaccination_plan_id`;
- formularz przejmuje przez to fragment mapowania domenowego.

**Rekomendacja**

- formularz ma jedynie walidować i konwertować dane;
- rozszerzyć jedno wejście domenowe, np. funkcję
  `build_event_details(data, farm=...)`, albo mały `EventDetailsBuilder`, jeśli
  potrzebne będą kolejne strategie;
- pojedynczy i masowy zapis powinny korzystać z tego samego buildera;
- trzy publicznie brzmiące `create_event` w action/service/repository pozostawić
  rozdzielone odpowiedzialnościami, ale nazwać jeden publiczny Action/Command,
  a zapis repozytorium oznaczyć jako wąskie wejście wewnętrzne.

**Testy akceptacyjne**

- pojedyncze i masowe szczepienie zapisują taki sam `vaccination_plan_id`;
- brak planu, plan innego gospodarstwa i nazwa różniąca się wielkością liter;
- rollback całego zestawu po błędzie jednego wiersza.

### UX-01 / P1 — wspólny kontroler techniczny formsetów

**Dowód**

`static/js/core/app.js` zawiera osobne:

- `initBulkEventForm`,
- `initSaleFormset`,
- `initRecipeFormset`,
- `initDeliveryFormset`.

Każdy powtarza część obsługi `TOTAL_FORMS`, klonowania `<template>`, indeksów,
ukrywania/usuwania wiersza, pustego stanu oraz inicjalizacji pól. Obliczenia
sprzedaży, sumy receptury i pola zależne zdarzeń są natomiast różnymi regułami.

**Rekomendacja**

- wprowadzić mały, deklaratywny `FormsetController` jako kontroler zachowania:
  kontener, template, prefix, przycisk dodawania, selektor usuwania i callback po
  zmianie wiersza;
- pozostawić osobne hooki domenowe dla sum sprzedaży, receptury i zdarzeń;
- nie budować dużego frameworka formularzy ani nie przenosić walidacji biznesowej
  do JavaScriptu;
- każdy formset ma nadal działać po stronie serwera bez JS.

**Testy akceptacyjne**

- jeden/kilka/pusty wiersz, dodanie, usunięcie istniejącego i nowego wiersza;
- poprawne indeksy oraz management form po wielu operacjach;
- błąd jednego wiersza zachowuje dane i wskazuje dokładny rekord;
- 360 px, klawiatura, focus oraz brak podwójnego submitu.

### UX-02 / P1 — wspólne komponenty bez „page buildera”

**Dowód**

- `add_recipe.html` i `recipe_version_form.html` powtarzają blok składników
  formsetu;
- `stage1.html` i `stage2.html` powtarzają tabelę składników, podsumowania,
  przełącznik ceny i checklistę;
- 51 template'ów ręcznie buduje `<section class="page-header">`, podczas gdy
  `templates/components/page_header.html` nie ma użyć;
- `components/form_field.html` jest używany tylko w części formularzy, a wiele
  ekranów ręcznie odtwarza label, pole i błędy;
- `components/task_item.html` nie ma użyć.

**Rekomendacja**

- utworzyć komponent formsetu składników receptury z jawnymi parametrami;
- wydzielić wspólne podsumowanie etapu produkcji, zachowując oddzielne akcje i
  reguły obu etapów;
- zdecydować: przyjąć `page_header.html` jako standard i uzupełnić go o zwykły
  link/akcje, albo usunąć go; nie utrzymywać równolegle martwego standardu;
- analogicznie zastosować albo usunąć `task_item.html`;
- rozwijać `form_field.html` tylko dla pól o tym samym kontrakcie HTML. Pola
  niestandardowe i formsety mogą pozostać jawne;
- nie tworzyć jednego komponentu z dziesiątkami flag dla każdej strony.

### UX-03 / P1 — jedna polityka edycji, anulowania i potwierdzeń

**Dowód**

- formularze mieszają „Wróć”, „Powrót” i „Anuluj” w nagłówku lub stopce;
- proste usuwanie korzysta z `data-confirm`, produkcja masowa z własnego
  `<dialog>`, a cofnięcie produkcji z osobnej strony/formularza;
- implementacje różnią się także położeniem danger zone.

**Rekomendacja**

- wspólny nagłówek formularza: link „Wróć” jako nawigacja;
- wspólna stopka: „Anuluj” + jedna główna akcja „Zapisz” lub nazwa procesu;
- proste destrukcyjne CRUD: jeden dostępny dialog potwierdzenia sterowany przez
  istniejący atrybut danych;
- akcje masowe: wariant dialogu pokazujący liczbę i zakres rekordów;
- operacje nieodwracalne lub przekrojowe, np. restore/cofnięcie rozliczenia:
  dedykowana strona z opisem konsekwencji i ewentualnym powodem;
- nie sprowadzać wszystkich poziomów ryzyka do jednego `window.confirm`.

### UX-04 / P2 — uproszczenie ustawienia rozmiaru tekstu

**Dowód**

Ekran ustawień ma jednocześnie suwak, pole liczbowe i pięć przycisków presetów.
Mechanizm JS korzysta z jednego źródła wartości i jest zsynchronizowany, ale
interfejs daje zbyt wiele równorzędnych sposobów wykonania tej samej czynności.

**Rekomendacja**

- jako główny wybór pokazać 3–4 opisane presety;
- suwak/pole liczbowe ujawnić dopiero po wyborze „Własny rozmiar”;
- „Przywróć 100%” pozostawić jako akcję drugorzędną;
- zachować jeden stan w JS i istniejącą obsługę klawiatury.

### FORMAT-01 / P2 — wspólne formatowanie prezentacyjne

**Dowód**

Konwersje i formatowanie są rozproszone między `common/units.py`,
`feed/templatetags/feed_format.py`, `farms/templatetags/ui_format.py` oraz
ręczne f-stringi z `zł`/`PLN` i kropką/przecinkiem dziesiętnym.

**Rekomendacja**

- wydzielić czyste funkcje prezentacyjne `to_decimal`, `format_decimal`,
  `format_money` i `format_percent` do małego modułu `common`;
- filtry template'ów mają być cienkimi adapterami do tych funkcji;
- konwersje jednostek pozostawić w `common.units`;
- parsowanie PDF/CSV pozostawić w adapterach importu, bo ma inne zasady i
  poziom tolerancji niż formatowanie UI.

### CSS-01 / P2 — wspólna baza mobilnych kart formularza

**Dowód**

- `.settlement-form-cards` i `.bulk-event-form-cards` powtarzają blokowy układ
  tabeli mobilnej, siatkę label/wartość, obramowania i typografię;
- `.row-actions` ma identyczne deklaracje w `buttons.css` i `tables.css`.

**Rekomendacja**

- wprowadzić bazową klasę `.mobile-form-cards` i małe modyfikatory domenowe;
- wybrać jednego właściciela `.row-actions`, najlepiej komponent tabeli lub
  jawny utility layout;
- nie scalać wszystkich podobnych kolorów/statusów w abstrakcyjne klasy, jeśli
  oznaczają inne stany domenowe.

### DRY-02 / P2–P3 — mniejsze powtórzenia do porządkowania lokalnego

| Miejsce | Powtórzenie | Zalecenie |
| --- | --- | --- |
| `common/forms.py` | `_place_field_after()` i `_place_price_unit_after_field()` implementują to samo przestawianie pól | po DRY-01 pozostawić jeden mały helper; nie tworzyć osobnej klasy |
| `feed/forms.py` | trzy warianty `clean_name()` sprawdzają pustą lub nieunikalną nazwę w gospodarstwie | wspólna funkcja walidująca tylko filtr `farm + name__iexact`; zachować domenowe komunikaty i modele |
| `sales/forms.py` | `PolishDecimalField.to_python()` i `PolishIntegerField.to_python()` mają taki sam szkielet normalizacji | mały helper normalizacji z przekazaną funkcją parsera; klasy pól pozostają osobne |
| `sales/services/pdf_import_service.py` | `_parse_decimal_field()` i `_parse_int_field()` powtarzają obsługę pustej wartości, ostrzeżenia i błędu | prywatny helper parsera z jawnym typem wyniku; nie łączyć go z łagodniejszą obsługą inputów HTML |
| `feed/templatetags/feed_format.py` i `farms/templatetags/ui_format.py` | lokalne `_to_decimal()` i formatery liczb | zrealizować razem z FORMAT-01, pozostawiając cienkie filtry domenowe |
| `feed/actions/deliveries.py` | pojedyncze `create_delivery()` i aktywne `create_deliveries()` wykonują podobny zapis, ale pierwsze wejście jest używane tylko przez test integracyjny | zdecydować, czy pojedyncze API jest publiczne; jeśli nie, testować formset/action produkcyjny zamiast utrzymywać równoległe wejście |
| `farms/services/farm_dashboard.py` i `today_dashboard.py` | cache lokalny `_inventory_summary()` i `_task_summary()` | znika naturalnie z usunięciem starej klasy; nie budować abstrakcyjnej klasy bazowej dla dwóch dashboardów |

Te punkty mają niższy priorytet niż DRY-01. Należy je wykonywać tylko przy
zmianie danego przepływu albo jako małe, osobne zadanie z testami zachowania.

### DEAD-02 / P2 — martwe symbole o wysokiej pewności

Poniższe symbole mają wyłącznie definicję i brak odwołań w kodzie oraz testach:

| Obszar | Kandydaci |
| --- | --- |
| cache | `invalidate_inventory_cache`, `invalidate_dashboard_cache`, `invalidate_task_cache`, `invalidate_profitability_cache`, `invalidate_statistics_cache`, `safe_cache_delete_many` |
| feed | `production_creates_produced_feed`, `ProductionRollbackError`, `feed.selectors.recipes.recipe_exists` |
| sows | `record_bulk_pregnancy_checks`, `record_bulk_vaccinations`, `PigletCareService.validate_pre_weaning_mortality` |
| template | `templates/sows/modules_home.html`, po decyzji: `components/page_header.html`, `components/task_item.html` |

Rekomendacja: usuwać małymi paczkami per moduł. Przed każdym usunięciem wykonać
ponowne `rg`, test importu modułu i testy domeny. Dla template'ów sprawdzić także
`render()`, `{% include %}`, ustawienia oraz dynamiczne nazwy.

### DEAD-03 / P3 — nieużywane importy i API używane tylko w testach

Nieużywane importy do usunięcia przy najbliższej zmianie danego modułu:

- `costs/actions.py`: `Decimal`;
- `feed/views.py`: `inventory_dashboard`;
- `feed/actions/finished_feed.py`: `ProductionModel`;
- `feed/actions/productions.py`: `completion_datetime_for`;
- `feed/actions/inventory.py`: `F`;
- `feed/services/production_completion.py`: `FeedDomainError`;
- `feed/selectors/productions.py`: `inventory_dashboard`;
- `farms/management/commands/seed_realistic_test_data.py`: `Sum`;
- `sales/services/sale_form_service.py`: `SaleClassRowModel`.

Osobno sklasyfikować publiczne funkcje używane obecnie tylko w testach, m.in.
`create_delivery`, `get_first_user_farm`, `get_or_create_legacy_farm`,
`PriceConfigForm`, `validate_production_capacity` i wybrane pomocnicze metody
statystyk macior. Nie są automatycznie martwe: mogą być kontraktem zgodności lub
wygodnym wejściem testowym. Decyzja powinna brzmieć: przenieść do fabryk testów,
oznaczyć jako compatibility API albo dodać rzeczywiste użycie produkcyjne.

### COMPAT-01 / P3 — jawny plan zakończenia warstw zgodności

- `farms/services/cache.py` jest re-exportem `common.cache` i jest używany przez
  testy patchujące starą ścieżkę. Dodać datę/warunek usunięcia i przepiąć testy,
  zamiast utrzymywać alias bezterminowo.
- `static/css/app.css` jest świadomie utrzymywanym plikiem kompatybilności i ma
  test. Nie jest martwy; usuwać dopiero po potwierdzeniu, że żaden deployment go
  nie ładuje.
- puste katalogi `tests/e2e/` są markerami planowanego zakresu testów, a nie
  martwym kodem produkcyjnym.

## 4. Powtórzenia, których nie należy scalać automatycznie

- `get_current_farm(request)` i jawne filtry `farm` — powtórzenie chroni izolację
  danych i powinno pozostać widoczne;
- transakcje i blokady w krytycznych actions — łączyć tylko wspólny mechanizm,
  nie reguły różnych procesów;
- providery dashboardów domenowych — podobne metody `total_between` mają różnych
  właścicieli danych;
- parser liczb z PDF i formatowanie liczb dla UI — oba używają `Decimal`, ale
  mają różne kontrakty błędu;
- klasy wyjątków bez własnych metod — są wartościowymi typami semantycznymi, o
  ile są rzucane i obsługiwane;
- read-only przełącznik jednostki prezentacji ceny nie jest tym samym co select
  jednostki wejściowej formularza;
- istniejący wspólny mechanizm switchy ustawień działa jako jeden system; warto
  dodać include dla wiersza, ale nie drugi kontroler przełączników.

## 5. Zalecana kolejność wdrożenia

### Etap A — integralność danych

1. DRY-01: jedno pole i jedno przeliczenie jednostki ceny.
2. Testy regresyjne obu formularzy i formsetu.
3. Pełne testy `feed` oraz kontrola zapisanych kosztów/FIFO.

### Etap B — bezpieczne sprzątanie

1. DEAD-01: rozdzielić aktywny helper ustawień i usunąć starą klasę/template.
2. DEAD-02: usuwać symbole paczkami per moduł.
3. DEAD-03/COMPAT-01: posprzątać importy i udokumentować kompatybilność.

### Etap C — spójność domeny i prezentacji

1. DOMAIN-01: wspólny builder zdarzeń.
2. FORMAT-01: wspólne formatowanie liczb.
3. ARCH-01: uprościć sprzedaż dopiero po testach zachowania i zapytań.

### Etap D — wspólny UX

1. UX-01: techniczny kontroler formsetów z hookami domenowymi.
2. UX-02 i UX-03: komponenty nagłówka, pól, formsetów i potwierdzeń.
3. CSS-01 i UX-04: redukcja powtórzeń stylów oraz liczby kontrolek.
4. Sprawdzenie 360/720/900/1024/1440 px, light/dark/system, trzech gęstości,
   klawiatury, focusu, zoom 200% i długich polskich wartości.

Każdy etap powinien być osobnym, małym zadaniem i osobnym punktem akceptacji.
Nie należy wykonywać wszystkich zmian w jednym refaktorze.

## 6. Kryteria zakończenia całego planu

- formularz ceny ma dokładnie jedno pole jednostki i nie może wykonać
  podwójnego przeliczenia;
- nie ma dwóch aktywnych serwisów przygotowujących ten sam dashboard;
- sprzedaż ma jedno źródło obliczeń modelowych i prostą warstwę odczytu;
- pojedyncze i masowe zdarzenia korzystają z jednego buildera szczegółów;
- wspólne zachowanie formsetu jest zaimplementowane raz, a reguły domenowe są
  osobnymi hookami;
- wszystkie komponenty w `templates/components/` są używane albo świadomie
  usunięte;
- nie ma dwóch definicji `.row-actions` ani dwóch kopii mobilnej karty tabeli;
- usuwane symbole mają potwierdzony brak odwołań i przechodzące testy modułu;
- wspólny UX przechodzi ręczną macierz responsywności i dostępności;
- `PROJECT_STRUCTURE.md`, `TEST_COVERAGE.md`, `UX_AUDIT.md` i `CHANGELOG.md` są
  aktualizowane w każdym zaakceptowanym etapie.

## 7. Stan bieżący

Plan został wdrożony z zachowaniem funkcjonalności użytkowych i kontraktów
zgodności, których usunięcie mogłoby złamać integracje. Dodano testy jednostek
ceny, selectorów, wspólnego buildera, bezpieczeństwa HTTP, idempotencji i
krytycznej współbieżności. Pełny wynik oraz pozostałe ograniczenia automatyzacji
przeglądarkowej są utrzymywane w `TEST_COVERAGE.md`.
