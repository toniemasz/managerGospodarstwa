# Baza wiedzy projektu dla kolejnych prac

Ten katalog jest skróconym, utrzymywanym indeksem repozytorium. Jego celem jest
uniknięcie ponownego czytania całego projektu przy każdym zadaniu. Nie zastępuje
on kodu ani testów: przed zmianą nadal trzeba otworzyć wszystkie pliki należące
do konkretnego przepływu.

Stan dokumentacji: 2026-10-14, branch `develop`.

## Kolejność czytania przed zadaniem

1. `AGENTS.md` — zasady bezpieczeństwa, architektury, domeny i Definition of Done.
2. Ten plik — szybki wybór dalszej dokumentacji.
3. `PROJECT_STRUCTURE.md` — właściciel funkcji, modele, warstwy, URL-e i przepływy.
4. `TEST_COVERAGE.md` — istniejące zabezpieczenia i znane luki testowe.
5. `UX_AUDIT.md` — tylko dla zadań dotyczących interfejsu.
6. `DUPLICATION_AND_DEAD_CODE_AUDIT.md` — dla refaktoru, porządkowania warstw,
   wspólnych komponentów i usuwania martwego kodu.
7. `CHANGELOG.md` — ostatnie zmiany strukturalne i dokumentacyjne.
8. Dopiero potem kod oraz testy bezpośrednio związane z zadaniem.

Nie czytaj całego repozytorium bez potrzeby. Zacznij od modułu-właściciela,
publicznych wejść opisanych w mapie i wyszukania wszystkich użyć zmienianego
kontraktu przez `rg`.

## Szybki wybór modułu

| Potrzeba | Właściciel | Pierwsze pliki |
| --- | --- | --- |
| gospodarstwo, ustawienia, nawigacja, audyt, backup, raport przekrojowy | `farms` | `farms/views.py`, `farms/services/`, `farms/module_registry.py` |
| maciory, zdarzenia, status, szczepienia, upadki, prosięta | `sows` | `sows/domain/`, `sows/actions/`, `sows/services/`, `sows/selectors/` |
| składniki, dostawy, FIFO, receptury, produkcja, gotowa pasza | `feed` | `feed/actions/`, `feed/services/`, `feed/selectors/`, `feed/domain/` |
| sprzedaż i import rozliczeń PDF | `sales` | `sales/actions.py`, `sales/services/`, `sales/forms.py` |
| koszty ręczne i projekcja kosztu produkcji | `costs` | `costs/actions.py`, `costs/services.py` |
| jednostki, pieniądze, daty, cache, wspólne formularze | `common` | właściwy mały moduł w `common/` |

## Nienegocjowalne źródła prawdy

- Każdy odczyt i zapis danych użytkownika jest ograniczony do bieżącego
  gospodarstwa.
- Stan surowców wynika z `InventoryMovementModel`, a koszt zużycia z alokacji
  FIFO `ProductionIngredientUsageModel`.
- Zakończenie produkcji przechodzi przez `ProductionCompletionWorkflow`.
- Status maciory wynika z historii zdarzeń i `SowStateMachine`.
- Koszt paszy w finansach jest projekcją zakończonej produkcji; `costs` nie
  implementuje FIFO.
- Importy, przebudowy, cofnięcia i procesy wielomodelowe są atomowe.
- Backend pozostaje źródłem prawdy; JavaScript jest tylko ulepszeniem UI.

## Bezpieczne polecenia

Projekt wymaga PostgreSQL. Preferowane pełne uruchomienie:

```bash
bash test.sh
```

`test.sh` rezerwuje port `5432`. Gdy port jest zajęty, uruchom osobny kontener
na innym porcie i ustaw `TEST_DATABASE_URL` wyłącznie na tę bazę. Nie używaj
wartości `DATABASE_URL` z `.env` do testów.

Ważne: konfiguracja wybiera `TEST_DATABASE_URL` automatycznie tylko podczas
uruchomienia przez pytest/test. Zwykłe polecenia `manage.py check` oraz
`manage.py makemigrations --check --dry-run` korzystają z `DATABASE_URL`, więc
dla lokalnej weryfikacji ustaw jawnie oba adresy na bezpieczną bazę lokalną.

Przykład:

```bash
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5433/manager_ci \
TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5433/manager_ci \
.venv/bin/python manage.py makemigrations --check --dry-run
```

## Obowiązek aktualizacji tej bazy wiedzy

Po każdej zmianie strukturalnej zaktualizuj dokumentację w tym samym zadaniu.
Za zmianę strukturalną uznajemy w szczególności:

- dodanie, przeniesienie lub usunięcie modułu, warstwy albo publicznego punktu
  wejścia;
- zmianę modelu, relacji, migracji lub źródła prawdy;
- zmianę URL-a, widoku, wspólnego komponentu, pliku CSS/JS lub nawigacji;
- zmianę krytycznego procesu, transakcji, blokady, FIFO, audytu, importu lub
  backupu;
- dodanie albo usunięcie grupy testów lub zmianę zakresu krytycznego pokrycia.

Minimalna aktualizacja obejmuje:

1. poprawienie `PROJECT_STRUCTURE.md`;
2. poprawienie macierzy w `TEST_COVERAGE.md`, jeśli zmieniły się testy lub ryzyko;
3. poprawienie `UX_AUDIT.md`, jeśli zmienił się wspólny UI lub rekomendacja
   została wdrożona;
4. dopisanie wpisu na początku `CHANGELOG.md`;
5. poprawienie linków w `README.md` albo `docs/architecture.md`, jeśli stały się
   nieaktualne.

Nie zapisuj sekretów, danych użytkowników, pełnych payloadów backupu ani
lokalnych adresów produkcyjnych.

## Jak rozstrzygać rozbieżności

Priorytet mają kolejno:

1. aktualny kod i migracje;
2. testy przechodzące na PostgreSQL;
3. `AGENTS.md`;
4. ta baza wiedzy;
5. starsze opisy i komentarze.

Jeżeli dokumentacja nie zgadza się z kodem, popraw dokumentację w ramach zadania
i zapisz rozbieżność w `CHANGELOG.md`.
