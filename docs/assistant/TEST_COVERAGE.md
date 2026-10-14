# Dokumentacja testów i audyt pokrycia krytycznego

Aktualizacja: 2026-10-14.

## 1. Zweryfikowany stan

Pełny zestaw został uruchomiony na lokalnym, odizolowanym PostgreSQL 17.6:

```text
622 passed — pełny przebieg końcowy na lokalnym PostgreSQL 17.6
Django 6.0.5
pytest 9.0.3
pytest-django 4.12.0
```

Lokalne środowisko `.venv` używało Python 3.13.0. Docelowy runtime projektu i
CI używają Python 3.12.7, dlatego CI pozostaje rozstrzygającą weryfikacją
zgodności wersji Pythona.

Ponadto:

- `python manage.py check` — bez błędów;
- `makemigrations --check --dry-run` — brak zmian modeli (polecenie należy
  wykonywać z jawnym, bezpiecznym `DATABASE_URL`; patrz `README.md` w tym
  katalogu);
- kolekcja pytest — 622 przypadki;
- błędy/warningi konsoli na ręcznie sprawdzonych ekranach — brak.

Nie wykonano pomiaru pokrycia linii ani gałęzi. `coverage.py` i `pytest-cov` nie
są obecnie zależnościami projektu, więc liczby testów nie wolno przedstawiać
jako procentu pokrycia kodu.

## 2. Liczba zebranych przypadków

| Moduł | Przypadki pytest | Główne poziomy |
| --- | ---: | --- |
| `common` | 28 | jednostki, formatowanie, HTTP/CSRF, kontrakty JS, smoke nawigacji |
| `costs` | 19 | actions, formularze, widoki, idempotencja, izolacja, raporty, migracja |
| `farms` | 116 | ustawienia, cache, raporty, dashboardy, idempotencja, import/backup, UI HTML |
| `feed` | 191 | calculators, models, actions, FIFO, współbieżność, workflow, widoki, migracje |
| `sales` | 44 | modele, formularze, selectory, idempotencja, widoki, parser PDF, migracja |
| `sows` | 224 | domena, builder zdarzeń, actions, formularze, widoki, współbieżność, migracje |
| **Razem** | **622** | |

Parametryzacja powoduje, że liczba zebranych przypadków jest większa od liczby
funkcji `test_*`.

## 3. Lokalizacja testów

```text
common/tests/
costs/tests/
farms/tests/
feed/tests/unit/
feed/tests/integration/
feed/tests/test_*.py
sales/tests/
sows/tests/unit/
sows/tests/integration/
sows/tests/test_*.py
```

Katalogi `feed/tests/e2e/`, `sales/tests/e2e/` i `sows/tests/e2e/` zawierają
tylko puste `__init__.py`. Projekt nie ma obecnie automatycznych testów E2E w
przeglądarce.

## 4. Macierz procesów krytycznych

Legenda:

- **mocne** — bezpośrednie testy domeny, integracji i istotnych błędów;
- **częściowe** — główny przepływ jest chroniony, ale pozostaje ważna luka;
- **brak automatyzacji** — sprawdzane ręcznie albo wyłącznie pośrednio.

| Obszar | Ocena | Co jest chronione | Pozostałe ryzyko |
| --- | --- | --- | --- |
| FIFO surowców i ruchy magazynowe | mocne | kolejność FIFO, wiele dostaw, rebuild, rollback, stany i izolacja | konflikt różnych produkcji nadal wymaga scenariusza zależnego od kolejności |
| Zakończenie produkcji | mocne | atomowość, koszt, batch, podanie, błędy skutków ubocznych, farm scope i dwa równoległe zakończenia | pełny równoległy double-submit HTTP nie jest osobnym E2E; action chroni blokada |
| Cofnięcie i usuwanie produkcji | mocne | odwrócenie artefaktów, audyt, ochrona relacji, historyczny rebuild | brak testu równoległego cofnięcia z inną operacją |
| Receptury i wersje | mocne | snapshot, `custom_recipe_data`, 100%, przebudowa kosztów, migracje | formset mobilny sprawdzono ręcznie, bez runnera E2E w repo |
| Gotowa pasza i FIFO partii | mocne | partie, podanie, przywracanie, braki, izolacja i dwa współbieżne podania | monitorować warianty obejmujące wiele partii |
| Jednostki ceny | mocne | jedno pole/HTML, zł/kg i zł/t, granice, legacy payload i brak podwójnej konwersji | stary klucz `price_unit` pozostaje kontrolowaną zgodnością wejścia |
| Koszty | mocne | CRUD, koszt produkcji, izolacja, N+1, cache i powtórzony POST | edycja nie tworzy drugiego rekordu i nie wymaga tokenu create |
| Sprzedaż | mocne dla logiki | sumy, formset, duplikaty, izolacja, PDF, typ/sygnatura/10 MB i powtórzony POST | pełny upload w realnej przeglądarce pozostaje manualny |
| Statusy i zdarzenia macior | mocne | maszyna stanów, wspólny builder, actions, rollback, double-submit | pełny keyboard flow pozostaje manualny |
| Szczepienia | mocne | harmonogramy, cykle, duplikaty, skip, historia, izolacja, query count | brak rzeczywistego równoległego zamknięcia cyklu |
| Przeniesienia prosiąt | mocne | bilans, anulowanie, farm scope, query count i współbieżność | konflikt w przeglądarce pozostaje manualny |
| Upadki | mocne | typy, constraints, bilans, formularze i widoki | długie wartości wymagają kontroli wizualnej |
| Backup/restore i CSV | mocne dla integralności | round-trip, preview, atomowość, replace/add, limit uploadu i rozpakowanego ZIP | restore produkcyjny pozostaje operacją wysokiego ryzyka |
| Izolacja gospodarstw | mocne | testy formularzy, querysetów, widoków, raportów, eksportów i actions we wszystkich domenach | utrzymywać test przy każdym nowym endpointcie/polu relacyjnym |
| Audyt | częściowe/mocne | kluczowe CRUD, import/eksport, PDF, receptury, produkcja i zadania | nie ma jednej macierzy wymuszającej audyt dla każdej nowej operacji |
| Cache | mocne w objętych miejscach | key farm/version, hit, awaria backendu, invalidation on commit | testowy dummy cache ukrywa pomyłki poza testami z locmem |
| Wydajność ORM | częściowe | wybrane stabilne query counts: koszty, dostawy, szczepienia, prosięta | brak budżetów dla głównych dashboardów/list przy dużych danych |
| CSRF i metody HTTP | mocne dla macierzy | `enforce_csrf_checks=True` i 405 dla 11 destrukcyjnych endpointów | rozszerzać macierz wraz z nowymi zapisami |
| Podwójne wysłanie | mocne dla wskazanych create flows | transakcyjny token DB dla sprzedaży, kosztu, dostaw i masowych zdarzeń | stare integracje bez tokenu zachowują zgodność i nie mają tej warstwy |
| Responsywność | ręczna + smoke | 38 tras bez 500; pięć szerokości bez overflow; focus i główne akcje | brak repozytoryjnego runnera screenshot/E2E i realnego urządzenia |
| Dostępność | częściowe/mocne | semantyka, aria, focus formsetu, klawiatura zakładek, cele 44 px | brak axe, kontrastu automatycznego i zoom 200% |

## 5. Wniosek

622 testy chronią wszystkie krytyczne luki wskazane w audycie: jednostkę ceny,
współbieżność produkcji i podań, double-submit, granice uploadów, metody HTTP i
CSRF. Smoke-test renderuje 38 głównych tras z `DEBUG=False`, w tym „Zużycie
paszy”, i zabezpiecza wykryty brak `{% load feed_format %}`.

Nie jest to obietnica stuprocentowego pokrycia wszystkich możliwych gałęzi.
Pozostają jawne bramki infrastruktury przeglądarkowej: axe, screenshoty, zoom
200%, realne urządzenia i pełne uploady E2E.

## 6. Dalsza mierzalność

1. Rozważyć `coverage.py`/`pytest-cov` i najpierw zapisać stan bazowy bez
   sztucznego progu.
2. Dodać runner Playwright/axe jako osobne zadanie infrastrukturalne, a potem
   scenariusze logowanie → zdarzenie, dostawa → produkcja → koszt/podanie,
   sprzedaż/PDF i backup preview bez zastosowania.
3. Dopiero po analizie luk ustalić próg dla kodu domenowego/actions, nie dla
   migracji i prostych template'ów.
4. Dodać stabilne budżety zapytań tylko dla ekranów, których koszt rzeczywiście
   zmierzono na większym zbiorze danych.

## 7. Uruchamianie testów

Pełny zestaw:

```bash
bash test.sh
```

Moduł:

```bash
bash test.sh feed
bash test.sh sows
bash test.sh sales
bash test.sh costs
bash test.sh farms
```

Jeżeli lokalny port `5432` jest zajęty, nie zatrzymuj obcej usługi. Uruchom
kontener testowy na wolnym porcie i wywołaj:

```bash
TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5433/manager_ci \
.venv/bin/pytest --tb=short -ra
```

Przed testami potwierdź, że URL wskazuje wyłącznie bazę przeznaczoną do testów.

## 8. Testy wymagane zależnie od zmiany

| Zmiana | Minimalny zakres |
| --- | --- |
| model/constraint | test modelu + migracji + `makemigrations --check` |
| action zapisu | sukces, błąd, rollback, farm scope, audyt, double-submit |
| FIFO/produkcja | kalkulator + integracja PostgreSQL + rollback + współbieżność |
| selector/lista | filtr, pusty stan, farm scope, N+1 jeśli ryzyko jest realne |
| formularz | poprawne dane, każdy błąd, zachowanie danych, obca relacja |
| endpoint zapisu | auth, farm scope, metoda HTTP, CSRF, komunikat i redirect |
| import/upload | typ, rozmiar, uszkodzenie, duplikat, preview, atomowość |
| wspólny UI | desktop/mobile, klawiatura, focus, dark/system, zoom 200% |
| cache | hit, miss, błąd backendu, farm key, invalidation po commit/rollback |

Po zmianie zaktualizuj tę macierz i wpis w `CHANGELOG.md`.
