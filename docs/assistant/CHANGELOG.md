# Rejestr zmian struktury i bazy wiedzy

Wpisy są w kolejności od najnowszego. Ten plik nie zastępuje historii Git ani
changelogu produktu. Zapisuje zmiany wpływające na mapę projektu, źródła prawdy,
publiczne wejścia, krytyczne testy i wspólny UX.

## 2026-10-14 — wdrożenie audytu architektury, testów i UX

Zakres:

- naprawiono podwójną jednostkę ceny i rozdzielono mixiny masy/ceny;
- usunięto nieużywany równoległy dashboard i symbole bez odwołań, zachowując
  publiczne aliasy zgodności oraz wszystkie funkcjonalności użytkowe;
- uproszczono sprzedaż do selectorów + actions, dodano jeden builder szczegółów
  zdarzeń oraz wspólne formatowanie liczb;
- dodano wspólny `FormsetController`, komponenty receptury/produkcji, dialog
  potwierdzenia i wspólną bazę mobilnych kart formularzy;
- uporządkowano sprzedaż, śrutowanie, centralę, ustawienia, podnawigację,
  powiadomienia, cele dotykowe, safe area, błędy formularzy i favicon;
- dodano transakcyjną ochronę double-submit opartą o
  `FormSubmissionModel` dla sprzedaży, kosztów, dostaw i masowych zdarzeń;
- destrukcyjne wejścia zostały ograniczone do POST i sprawdzone z CSRF;
- naprawiono 500 w „Zużyciu paszy” przez załadowanie `feed_format`;
- ręczna kontrola wykryła i naprawiła niepoprawne klonowanie `<tr>` przez
  tymczasowy `<div>`; formsety klonują teraz natywny `template.content`.

Dokumentacja zaktualizowana:

- `PROJECT_STRUCTURE.md`: nowe źródła prawdy, model idempotencji, selectory,
  builder zdarzeń i wspólne elementy frontendu;
- `TEST_COVERAGE.md`: 622 testy, uzupełniona macierz krytyczna i smoke 38 tras;
- `UX_AUDIT.md`: status wdrożenia i wynik ponownej kontroli responsywności;
- `DUPLICATION_AND_DEAD_CODE_AUDIT.md`: wszystkie decyzje i statusy wykonania.

Migracje:

- `farms/0016_formsubmissionmodel.py` — jednorazowe tokeny krytycznych
  formularzy z unikalnością per gospodarstwo, użytkownik, zakres i token.

Testy i ręczna weryfikacja:

- pełny `pytest`: 622 przypadki na PostgreSQL 17.6;
- `manage.py check` i `makemigrations --check --dry-run`: bez problemów;
- Python compile, `node --check` i `git diff --check`: bez problemów;
- 38 głównych tras z `DEBUG=False`: bez 500;
- 360/720/900/1024/1440 px: brak globalnego overflow na ekranach kluczowych;
- light/dark/system, compact/comfortable, cele dotykowe, focus formsetów,
  klawiatura zakładek ustawień i konsola: sprawdzone bez błędów.

Ryzyka lub zgodność wsteczna:

- stare wejścia `SaleFormService`, `SaleRepository` i legacy `price_unit`
  pozostają adapterami zgodności, ale kod produkcyjny używa nowych źródeł;
- repozytorium nadal nie ma automatycznego runnera Playwright/axe; zoom 200%,
  kontrast i realne urządzenia pozostają ręczną bramką wydania;
- idempotencja nowych formularzy wymaga migracji `farms.0016`; stare klienty
  bez tokenu zachowują dotychczasowe zachowanie.

## 2026-10-08 — audyt duplikacji, martwego kodu i wspólnego UX

Zakres:

- dodano `DUPLICATION_AND_DEAD_CODE_AUDIT.md` z priorytetami, dowodami,
  proponowanymi wzorcami, testami akceptacyjnymi i etapami wdrożenia;
- wykryto nakładające się mechanizmy jednostki ceny, które na ekranie dostawy
  gotowej paszy renderują dwa pola i mogą wykonać podwójne przeliczenie;
- opisano kandydatów do usunięcia, nadmiarowe warstwy sprzedaży, równoległy
  stary dashboard oraz powtórzenia w formsetach, template'ach i CSS;
- uzupełniono `TEST_COVERAGE.md` o potwierdzoną lukę regresyjną jednostki ceny;
- dodano raport do indeksu w `README.md`, `docs/assistant/README.md` i
  `AGENTS.md`.

Zachowanie aplikacji: bez zmian; rekomendacje oczekują na akceptację.

Migracje: brak.

Testy i ręczna weryfikacja:

- bazą pozostaje pełny wynik 585 przechodzących testów na PostgreSQL 17.6;
- lokalnie odtworzono podwójne pole jednostki ceny i podwójne przeliczenie;
- kod aplikacji nie został zmieniony, dlatego pełnego zestawu nie uruchamiano
  ponownie dla samej dokumentacji.

Ryzyka lub zgodność wsteczna:

- znaleziony przypadek DRY-01/P0 pozostaje aktywny do czasu zaakceptowania i
  wdrożenia osobnej poprawki;
- lista martwego kodu wymaga ponownego sprawdzenia dynamicznych odwołań przed
  każdym usunięciem.

## 2026-10-07 — utworzenie trwałej bazy wiedzy

Zakres:

- dodano `docs/assistant/README.md` z kolejnością czytania i obowiązkiem
  aktualizacji dokumentacji;
- dodano `PROJECT_STRUCTURE.md` z mapą modułów, modeli, URL-i, zależności i
  krytycznych przepływów;
- dodano `TEST_COVERAGE.md` z wynikiem 585 testów, macierzą krytycznego pokrycia
  i priorytetami uzupełnień;
- dodano `UX_AUDIT.md` z ręcznym audytem aplikacji i listą rekomendacji;
- zaktualizowano `AGENTS.md` i `README.md`, aby kolejne zadania zaczynały od tej
  bazy zamiast od ponownej analizy całego repozytorium;
- skorygowano nieaktualne fragmenty `docs/architecture.md`: automatyczne podanie
  po produkcji, brak publicznego wymuszania braków, modele `sows` i format
  backupu v6.

Zachowanie aplikacji: bez zmian.

Weryfikacja:

- 585 testów przeszło na PostgreSQL 17.6;
- Django system check bez błędów;
- brak nowych migracji;
- ręczny audyt UI dla reprezentatywnych ekranów desktop/mobile;
- brak błędów i ostrzeżeń konsoli na sprawdzonych ekranach.

## Szablon następnego wpisu

```text
## RRRR-MM-DD — krótka nazwa

Zakres:
- dodano/usunięto/przeniesiono ...
- zmieniono źródło prawdy/przepływ/URL/model/komponent ...

Dokumentacja zaktualizowana:
- PROJECT_STRUCTURE.md: ...
- TEST_COVERAGE.md: ...
- UX_AUDIT.md: ...

Migracje:
- brak / lista

Testy i ręczna weryfikacja:
- ...

Ryzyka lub zgodność wsteczna:
- ...
```
