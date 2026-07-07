# AGENTS.md — managerGospodarstwa

## Kontekst projektu

To repozytorium zawiera aplikację Django `managerGospodarstwa` służącą do zarządzania gospodarstwem trzody chlewnej. Aplikacja obejmuje między innymi:

* maciory, zdarzenia produkcyjne, szczepienia i statusy stada,
* sprzedaż tuczników i import rozliczeń PDF,
* składniki paszowe, dostawy, magazyn, FIFO, receptury i śrutowanie,
* koszty, kategorie kosztów, statystyki i opłacalność,
* ustawienia gospodarstwa, widoczność modułów, eksport/import danych i historię zmian.

Projekt jest działającą aplikacją z realnymi danymi, dlatego priorytetem jest stabilność, czytelność, bezpieczeństwo danych i możliwość bezpiecznego dodawania nowych funkcji bez psucia istniejącej logiki.

---

## Zasady pracy z repozytorium

* Pracuj wyłącznie na branchu `develop`, chyba że użytkownik wyraźnie poleci inaczej.
* Nigdy nie modyfikuj brancha `main`.
* Nie wykonuj commitów, chyba że użytkownik wyraźnie o to poprosi.
* Nie usuwaj istniejących funkcji bez wyraźnej zgody użytkownika.
* Nie wykonuj dużych refaktorów, jeśli wystarczy mała, bezpieczna zmiana.
* Przed zmianą zawsze sprawdź aktualną strukturę plików i sposób działania danego modułu.
* Zachowuj istniejący styl projektu, nazewnictwo, wzorce formularzy, widoków, serwisów i testów.
* Jeżeli widzisz problem architektoniczny niezwiązany bezpośrednio z zadaniem, opisz go w podsumowaniu, ale nie poprawiaj go przy okazji bez potrzeby.

---

## Główna zasada architektoniczna

Projekt ma pozostać modułowym monolitem Django. Nie należy rozbijać go na mikroserwisy ani przebudowywać całej struktury bez wyraźnego polecenia.

Podstawowe aplikacje domenowe:

```text
farms/   - gospodarstwo, ustawienia, użytkownik, historia zmian, raporty przekrojowe
sows/    - maciory, zdarzenia, statusy, szczepienia, dashboard stada
feed/    - pasza, magazyn, dostawy, FIFO, receptury, śrutowanie
sales/   - sprzedaż tuczników, rozliczenia, import PDF
costs/   - koszty, kategorie, płatności
common/  - współdzielone helpery niezależne od domeny
```

Nowe funkcje dodawaj do modułu, do którego domenowo należą. Nie wrzucaj wszystkiego do `farms`, `views.py` albo przypadkowych helperów.

---

## Warstwy kodu

Stosuj konsekwentny podział odpowiedzialności.

### `models.py`

Modele powinny zawierać:

* strukturę danych,
* relacje,
* constraints,
* indeksy,
* proste właściwości modelu,
* proste metody naturalnie należące do modelu.

Modele nie powinny zawierać ciężkiej logiki procesów, rozbudowanych operacji biznesowych ani logiki widoków.

### `forms.py`

Formularze odpowiadają za:

* walidację danych wejściowych użytkownika,
* ograniczenie querysetów do bieżącego gospodarstwa,
* wymagane i opcjonalne pola,
* komunikaty walidacyjne,
* format pól formularza.

Formularze nie powinny księgować magazynu, przeliczać FIFO, tworzyć raportów ani wykonywać złożonych skutków ubocznych.

### `views.py`

Widoki powinny być możliwie cienkie. Ich rola to:

* pobranie `farm` przez `get_current_farm(request)`,
* obsługa GET/POST,
* utworzenie formularza,
* sprawdzenie `form.is_valid()`,
* wywołanie odpowiedniego `action`, `service` albo `selector`,
* dodanie komunikatu `messages`,
* wykonanie `redirect()` albo `render()`.

Nie umieszczaj w widokach ciężkiej logiki biznesowej, rozbudowanych obliczeń, księgowania, FIFO, parserów PDF ani skomplikowanych agregacji.

### `actions/`

Folder `actions/` służy do operacji zmieniających dane.

Umieszczaj tu:

* tworzenie rekordów,
* edycję rekordów,
* usuwanie rekordów,
* księgowanie,
* operacje transakcyjne,
* operacje mające skutki uboczne,
* przebudowę danych po zmianach.

Akcje powinny używać `transaction.atomic()` tam, gdzie zmiana dotyczy kilku modeli lub może częściowo się nie udać.

### `selectors/`

Folder `selectors/` służy do odczytu danych.

Umieszczaj tu:

* query sety,
* filtrowanie list,
* konteksty dla widoków,
* dane do dashboardów,
* dane do szczegółów obiektu,
* agregacje do wyświetlenia.

Selector nie powinien zapisywać danych.

### `services/`

Folder `services/` służy do większych procesów biznesowych.

Umieszczaj tu:

* dashboardy,
* raporty,
* import/export,
* statystyki,
* opłacalność,
* centrum zadań,
* parsery i obsługę procesów, które łączą kilka kroków.

Serwis może korzystać z modeli, selectorów, kalkulatorów i prostych helperów, ale powinien mieć czytelny zakres odpowiedzialności.

### `calculators/`

Folder `calculators/` służy do czystych obliczeń.

Umieszczaj tu:

* kalkulacje kosztów,
* przeliczenia ilości,
* obliczenia receptur,
* obliczenia magazynowe niezapisujące danych.

Kalkulatory powinny być możliwie niezależne od requesta, widoków i szablonów.

### `domain/`

Folder `domain/` służy do reguł domenowych.

Umieszczaj tu:

* maszyny stanów,
* stałe domenowe,
* reguły przejść,
* proste walidatory biznesowe,
* logikę niezależną od HTTP.

Przykład: statusy i przejścia macior powinny pozostać w domenie, a nie w widoku.

---

## Najważniejsza zasada: farm isolation

Każde dane użytkownika muszą być filtrowane po bieżącym gospodarstwie.

Zawsze upewnij się, że zapytania są ograniczone przez:

```python
farm = get_current_farm(request)
```

albo przez `request.farm`, jeśli jest już dostępne.

Dotyczy to szczególnie:

* list,
* dashboardów,
* formularzy,
* eksportów,
* importów,
* backupów użytkownika,
* raportów,
* statystyk,
* operacji edycji i usuwania,
* zapytań `get_object_or_404()`.

Nie wolno dopuścić do sytuacji, w której użytkownik może odczytać, edytować, usunąć lub wyeksportować dane innego gospodarstwa.

---

## Zasady czystego kodu

Stosuj proste, czytelne i przewidywalne rozwiązania.

* Używaj nazw, które jasno pokazują intencję.
* Funkcje powinny robić jedną rzecz.
* Unikaj wielkich funkcji i wielkich widoków.
* Unikaj duplikacji logiki.
* Jeżeli ten sam kod pojawia się kilka razy, rozważ helper, selector, service, action albo template include.
* Nie dodawaj niepotrzebnych abstrakcji.
* Nie twórz wielu małych modułów tylko po to, żeby kod wyglądał „bardziej architektonicznie”.
* Nie komplikuj prostego przepływu bez realnej potrzeby.
* Nie ukrywaj logiki biznesowej w template.
* Nie mieszaj zmian backendowych, frontendowych i refaktoru w jednym zadaniu, jeśli nie jest to konieczne.
* Zachowuj zgodność z istniejącymi testami i stylem projektu.

---

## Standard dodawania nowej funkcji

Przed implementacją określ typ funkcji:

```text
zapis danych             -> actions/
odczyt/lista/dashboard   -> selectors/
większy proces           -> services/
czyste obliczenia        -> calculators/
reguły domenowe          -> domain/
obsługa formularza       -> forms.py
obsługa HTTP             -> views.py
```

Typowy przepływ pracy:

1. Sprawdź istniejące modele, formularze, widoki, akcje, serwisy i testy.
2. Znajdź najmniejsze miejsce, w którym zmiana powinna powstać.
3. Dodaj logikę w odpowiedniej warstwie.
4. Utrzymaj widok jako cienką warstwę HTTP.
5. Dopilnuj filtrowania po `farm`.
6. Dodaj albo zaktualizuj testy.
7. Uruchom odpowiednie testy.
8. Opisz zmiany i ryzyka.

---

## Moduł `feed` — szczególna ostrożność

Moduł `feed` jest biznesowo krytyczny. Dotyczy magazynu, FIFO, kosztów paszy, receptur i opłacalności.

Przy zmianach w tym module zachowaj szczególną ostrożność.

Nie zmieniaj przypadkowo znaczenia:

* dostaw,
* pozostałej ilości dostawy,
* ruchów magazynowych,
* FIFO,
* kosztu produkcji,
* kosztu za kg,
* kosztu za tonę,
* statusów śrutowania,
* wersji receptur,
* historycznych śrutowań.

Stan magazynu powinien wynikać z ruchów magazynowych, a nie z ręcznie utrzymywanej liczby.

Produkcja paszy powinna być księgowana przez istniejące akcje i mechanizmy magazynowe. Nie dopisuj alternatywnego księgowania w widoku.

Zakończone śrutowania i ich koszty są podstawą opłacalności, dlatego każda zmiana w FIFO, recepturach, dostawach lub produkcjach wymaga testów.

---

## Receptury i wersje receptur

Receptury są historycznie wrażliwe.

Zasady:

* `RecipeModel` reprezentuje recepturę jako główny byt.
* `RecipeVersionModel` reprezentuje konkretną wersję składu.
* Nowe śrutowania powinny używać aktualnej wersji receptury.
* Historyczne śrutowania nie powinny zmieniać się automatycznie po edycji aktualnej receptury.
* Edycja istniejącej wersji receptury powinna być świadomą operacją.
* Jeżeli edycja wersji wpływa na zakończone śrutowania, użytkownik musi to potwierdzić.
* Przeliczanie zakończonych śrutowań powinno używać istniejącej logiki przebudowy FIFO.
* `custom_recipe_data` dla konkretnego śrutowania musi być respektowane i nie może zostać przypadkowo utracone.

Nie twórz nowego mechanizmu wersjonowania obok istniejącego. Korzystaj z obecnych modeli i akcji.

---

## Magazyn i FIFO

Dostawy, ruchy magazynowe i zużycie składników muszą pozostać spójne.

Zasady:

* dostawa tworzy ruch magazynowy,
* produkcja zużywa składniki przez FIFO,
* produkcja zakończona tworzy ruch zużycia,
* usunięcie albo edycja danych powiązanych z FIFO musi zachować spójność,
* nie pozwalaj na ujemne stany, chyba że istniejący przepływ świadomie obsługuje wymuszone zatwierdzenie,
* nie licz kosztu produkcji średnią ceną, jeśli istniejące FIFO ma być źródłem prawdy,
* nie usuwaj rozliczonych dostaw bez bezpiecznej obsługi konsekwencji.

Każda zmiana w FIFO powinna mieć test integracyjny.

---

## Moduł `sows`

Logika cyklu maciory powinna pozostać w domenie i serwisach, nie w widokach.

Zasady:

* statusy maciory wynikają z historii zdarzeń,
* reguły przejść powinny być trzymane w `domain/`,
* dodawanie, edycja i usuwanie zdarzeń powinno przechodzić przez `actions/` albo istniejące serwisy,
* szczepienia mogą mieć osobne reguły od statusu produkcyjnego,
* dashboardy i powiadomienia powinny korzystać z istniejących serwisów.

Nie dopisuj nowych reguł cyklu bez sprawdzenia aktualnej maszyny stanów i testów.

---

## Moduł `sales`

Sprzedaż może być ręczna albo importowana z PDF.

Zasady:

* logika importu PDF powinna pozostać w `sales/services/parsers/` i serwisach sprzedaży,
* widok nie powinien sam parsować PDF,
* dane główne sprzedaży mogą być przeliczane z wierszy klas,
* średnia cena za kg powinna być liczona jako średnia ważona wagą,
* parsery muszą obsługiwać polskie formaty liczb: przecinek dziesiętny, spacje, jednostki, zł, kg, %, szt.,
* brakujące albo niepewne dane powinny generować zrozumiałe ostrzeżenia, a nie psuć całego importu, jeśli da się bezpiecznie pokazać podgląd.

Przy zmianach importu PDF dodaj testy dla reprezentatywnego tekstu dokumentu.

---

## Moduł `costs`

Koszty są częścią opłacalności.

Zasady:

* każdy koszt musi być przypisany do gospodarstwa,
* kategorie kosztów są per gospodarstwo,
* nie mieszaj kosztów ręcznych z kosztem paszy liczonym z produkcji,
* koszt paszy powinien pochodzić z zakończonych śrutowań i FIFO,
* koszty ręczne powinny pozostać osobną kategorią danych,
* lista kosztów i podsumowania powinny korzystać z serwisu albo selectorów.

Jeżeli moduł kosztów będzie rozbudowywany, preferuj dodanie `costs/actions.py` dla operacji zapisu zamiast rozbudowywania widoków.

---

## Moduł `farms`

`farms` jest modułem systemowym i przekrojowym.

Odpowiada za:

* gospodarstwo użytkownika,
* ustawienia,
* widoczność modułów,
* nawigację,
* historię zmian,
* eksport/import,
* centrum zadań,
* statystyki,
* opłacalność.

`farms` może agregować dane z innych modułów, ale nie powinien przejmować ich szczegółowej logiki biznesowej.

Przykład:

* `farms` może pokazać koszt paszy w statystykach,
* ale nie powinien samodzielnie księgować produkcji paszy.

---

## Nawigacja i moduły

Lista modułów, ich widoczność, adresy i aktywne URL-e powinny być utrzymywane centralnie w rejestrze modułów.

Przy dodawaniu nowej sekcji aplikacji sprawdź:

* czy trzeba dodać wpis do rejestru modułów,
* czy moduł powinien być widoczny w ustawieniach,
* czy powinien być dostępny w nawigacji głównej,
* czy powinien mieć ikonę,
* czy powinien mieć opis,
* czy aktywne URL-e są poprawnie oznaczone.

Nie duplikuj logiki nawigacji w template.

---

## UI i template

Frontend jest oparty o Django Templates i CSS.

Zasady:

* używaj istniejących komponentów z `templates/components/`,
* nie duplikuj dużych fragmentów HTML,
* wspólne układy formularzy, tabel, filtrów i komunikatów powinny być komponentami albo include,
* nie dodawaj lokalnych styli inline bez potrzeby,
* zachowaj spójność desktop/tablet/mobile,
* tabele muszą być czytelne i responsywne,
* filtry powinny korzystać z istniejącego wzorca,
* komunikaty błędów powinny być krótkie i zrozumiałe.

Nie wprowadzaj nowego frameworka frontendowego bez wyraźnej zgody użytkownika.

---

## UX, HTML i template

Przy każdej zmianie widoku najpierw sprawdź istniejące template, komponenty, include, klasy CSS i układ aplikacji. Nie twórz nowego stylu od zera, jeśli projekt ma już gotowy wzorzec.

Widoki mają być czytelne, spokojne wizualnie, responsywne, spójne z resztą aplikacji i możliwe do obsługi na desktopie oraz telefonie. Nie przeładowuj ich informacjami.

Formularze powinny mieć jasny tytuł, krótki opis celu, logiczną kolejność pól, krótkie teksty pomocnicze tam, gdzie użytkownik może się pomylić, widoczne błędy walidacji, czytelne przyciski główne i drugorzędne oraz link powrotu albo anulowania.

Tabele i listy powinny pokazywać najważniejsze informacje jako pierwsze, mieć czytelne nagłówki, unikać zbyt szerokich kolumn, działać na mniejszych ekranach oraz korzystać z istniejących komponentów tabel, kart i filtrów, jeśli są dostępne.

Nie umieszczaj logiki biznesowej w template. Template ma tylko prezentować dane przygotowane przez view, selector albo service.

Nie duplikuj dużych fragmentów HTML. Jeśli podobny układ pojawia się kilka razy, użyj include albo istniejącego komponentu.

Nie dodawaj inline CSS bez potrzeby. Preferuj istniejące klasy i wspólne pliki stylów.

Przy dodawaniu nowej funkcji zadbaj, aby użytkownik rozumiał, co robi dana akcja, jakie będą jej skutki, czy zmiana jest odwracalna i czy wpływa na dane historyczne.

Dla operacji ryzykownych, takich jak usunięcie, archiwizacja, przeliczenie danych, import, restore albo zmiana historii, pokaż jasne ostrzeżenie albo wymagaj świadomego potwierdzenia, jeśli obecny UX projektu tak robi.

---

## Formatowanie liczb i polskie dane

Aplikacja jest używana po polsku i operuje na danych gospodarskich.

Uwzględniaj:

* przecinek dziesiętny,
* spacje i twarde spacje jako separatory tysięcy,
* jednostki: kg, t, zł, zł/kg, szt., %, netto, brutto,
* daty w polskim kontekście,
* czytelne komunikaty walidacyjne.

Nie psuj obsługi polskich formatów przez zbyt agresywne parsowanie.

---

## Historia zmian i audyt

Najważniejsze operacje powinny zapisywać historię zmian.

Dotyczy to szczególnie:

* tworzenia,
* edycji,
* usuwania,
* archiwizacji,
* importu,
* eksportu,
* backupu,
* restore,
* zmian ustawień,
* operacji magazynowych,
* przeliczania receptur i śrutowań.

Jeżeli operacja usuwa obiekt, zapisz jego reprezentację przed usunięciem, aby można było poprawnie utworzyć wpis audytu.

---

## Backup, eksport, import i produkcja

Projekt może działać z produkcyjną bazą danych.

Zasady:

* nie zakładaj, że aplikacja działa tylko lokalnie,
* nie hardcoduj ścieżek lokalnych,
* nie hardcoduj sekretów,
* nie loguj haseł, tokenów ani danych wrażliwych,
* nie usuwaj migracji,
* nie zmieniaj starych migracji bez bardzo mocnego powodu,
* importy powinny być atomowe,
* eksporty muszą być ograniczone do właściwego gospodarstwa/użytkownika,
* restore całej bazy musi pozostać operacją administracyjną i bezpieczną.

---

## Testy

Po zmianach backendowych uruchamiaj testy.

Preferowane polecenie:

```bash
pytest
```

Dla zmian lokalnych uruchamiaj najpierw testy danego modułu, np.:

```bash
pytest feed
pytest sows
pytest sales
pytest costs
pytest farms
```

Jeżeli zmiana dotyczy krytycznej logiki, dodaj albo zaktualizuj testy.

Szczególnie wymagane testy dla zmian w:

* FIFO,
* ruchach magazynowych,
* kosztach paszy,
* recepturach i wersjach receptur,
* śrutowaniach,
* sprzedaży i importach PDF,
* izolacji po gospodarstwie,
* eksportach/importach,
* usuwaniu danych,
* statusach macior.

Jeżeli testów nie da się uruchomić, napisz dlaczego.

Jeżeli testy nie przechodzą, nie ukrywaj tego. Podaj, które testy padły i czy wygląda to na skutek Twojej zmiany.

---

## Kiedy nie refaktorować

Nie refaktoruj tylko dlatego, że kod mógłby wyglądać lepiej.

Refaktor jest uzasadniony, gdy:

* usuwa realną duplikację,
* zmniejsza ryzyko błędów,
* upraszcza dodanie konkretnej funkcji,
* wydziela logikę z widoku do właściwej warstwy,
* poprawia testowalność,
* naprawia istniejący problem architektoniczny.

Nie rób dużych zmian struktury przy małym zadaniu. Jeśli widzisz większy problem, zaproponuj go użytkownikowi jako osobny etap.

---

## Bezpieczny workflow dla każdego zadania

Dla każdego zadania wykonaj kolejno:

1. Przeczytaj polecenie użytkownika.
2. Sprawdź branch i pracuj na `develop`.
3. Znajdź pliki związane z funkcją.
4. Zrozum obecny przepływ danych.
5. Określ najmniejszą bezpieczną zmianę.
6. Wybierz właściwą warstwę: model, form, action, selector, service, calculator, domain, view, template.
7. Wprowadź zmianę.
8. Dodaj lub zaktualizuj testy, jeżeli zmiana dotyczy logiki.
9. Uruchom odpowiednie testy.
10. Podsumuj zmiany, pliki, testy i ryzyka.

---

## Final response format

Na końcu każdej pracy programistycznej odpowiedz po polsku w takim formacie:

```text
Zmieniono:
- ...

Pliki:
- ...

Testy:
- ...

Jak sprawdzić ręcznie:
- ...

Ryzyka / uwagi:
- ...
```

Jeżeli czegoś nie udało się zrobić, napisz to wprost.

Jeżeli testy nie były uruchomione, napisz dlaczego.

Jeżeli znaleziono problem niezwiązany bezpośrednio z zadaniem, opisz go krótko w sekcji „Ryzyka / uwagi”, ale nie naprawiaj go bez potrzeby.

---

## Najważniejsza zasada końcowa

Dodawaj nowe funkcje tak, aby nie psuć istniejącej logiki.

Najpierw zrozum aktualny przepływ, potem wykonaj małą zmianę w odpowiedniej warstwie, dopilnuj izolacji po gospodarstwie i zabezpiecz zmianę testem.
