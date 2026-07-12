# AGENTS.md — managerGospodarstwa

## 1. Kontekst i priorytety

Repozytorium zawiera produkcyjną aplikację Django `managerGospodarstwa` do zarządzania gospodarstwem trzody chlewnej.

Główne obszary:

* `farms` — gospodarstwo, ustawienia, użytkownik, nawigacja, historia zmian, eksport/import, statystyki i raporty przekrojowe,
* `sows` — maciory, zdarzenia produkcyjne, statusy, szczepienia i zadania,
* `feed` — składniki, dostawy, magazyn, FIFO, receptury, produkcja i podawanie paszy,
* `sales` — sprzedaż tuczników, rozliczenia i import PDF,
* `costs` — koszty, kategorie, płatności i opłacalność,
* `common` — współdzielone elementy techniczne niezależne od konkretnej domeny.

To działający system z realnymi danymi. Kolejność priorytetów:

1. integralność i bezpieczeństwo danych,
2. poprawność logiki biznesowej,
3. izolacja danych gospodarstw,
4. stabilność istniejących funkcji,
5. prostota, czytelność i testowalność,
6. spójny, responsywny i dostępny interfejs,
7. wydajność oparta na pomiarach.

Buduj najmniejsze rozwiązanie, które jest poprawne, bezpieczne i zgodne z istniejącą architekturą. Nie wybieraj rozwiązania najbardziej skomplikowanego tylko dlatego, że jest „bardziej zaawansowane”.

---

## 2. Zasady pracy z repozytorium

* Pracuj wyłącznie na branchu `develop`, chyba że użytkownik wyraźnie poleci inaczej.
* Nigdy nie modyfikuj `main`.
* Nie wykonuj commitów, pushy, merge ani pull requestów bez wyraźnego polecenia.
* Nie usuwaj istniejących funkcji bez zgody użytkownika.
* Nie zmieniaj zachowania niezwiązanego z zadaniem.
* Nie wykonuj dużego refaktoru, jeśli wystarczy mała zmiana.
* Nie poprawiaj całych modułów „przy okazji”.
* Przed zmianą prześledź aktualny przepływ danych, wszystkie użycia i istniejące testy.
* Zachowuj obecne nazewnictwo, kontrakty, URL-e i wzorce projektu.
* Jeżeli zauważysz dodatkowy problem, opisz go w podsumowaniu, ale nie naprawiaj bez potrzeby.
* Zawsze rozróżnij, czy użytkownik prosi o analizę, prompt czy faktyczną implementację.

Przed rozpoczęciem ustal:

* który moduł jest właścicielem funkcji,
* gdzie znajduje się źródło prawdy,
* czy zmiana dotyczy odczytu, zapisu, procesu, obliczeń, domeny czy prezentacji,
* czy operacja wymaga transakcji lub blokady,
* czy wpływa na historię, FIFO, koszty albo inne moduły,
* jakie testy powinny chronić zmianę,
* czy zmiana UI działa również na telefonie.

---

## 3. Architektura

Projekt ma pozostać modułowym monolitem Django.

Nie wprowadzaj bez wyraźnej zgody:

* mikroserwisów,
* SPA,
* Reacta, Vue ani innego dużego frameworka frontendowego,
* dodatkowej warstwy repository opakowującej Django ORM bez realnej potrzeby,
* event sourcingu, CQRS ani rozbudowanego event busa,
* kontenera dependency injection,
* nowego systemu stylów obok istniejącego.

Nową funkcję dodawaj do modułu, do którego należy biznesowo. Moduł przekrojowy może pobierać dane z innych modułów, ale nie powinien duplikować ich reguł.

Przykład:

* `farms` może pobierać koszt paszy do raportu,
* `costs` może odpytać `feed` o koszt produkcji,
* ale ani `farms`, ani `costs` nie powinny ponownie implementować FIFO.

---

## 4. Warstwy i odpowiedzialności

### `models.py`

Modele zawierają:

* strukturę danych,
* relacje,
* constraints i indeksy,
* proste właściwości,
* małe inwarianty naturalnie należące do pojedynczego modelu.

Nie umieszczaj w modelach:

* logiki HTTP,
* rozbudowanych procesów obejmujących wiele modeli,
* parserów,
* raportów i dashboardów,
* ukrytego księgowania całego procesu.

Nie stosuj bezrefleksyjnie „fat models”. Cięższa logika biznesowa należy do `actions`, `services`, `domain` albo `calculators`.

### `forms.py`

Formularze odpowiadają za:

* walidację danych użytkownika,
* konwersję wartości,
* ograniczanie querysetów do bieżącego gospodarstwa,
* widgety i komunikaty walidacyjne.

Formularz nie powinien księgować magazynu, przeliczać FIFO, tworzyć raportu ani wykonywać wielu zapisów.

### `views.py`

Widok jest cienką warstwą HTTP:

1. pobiera gospodarstwo i sprawdza uprawnienia,
2. obsługuje GET/POST,
3. tworzy formularz,
4. wywołuje selector, action albo service,
5. dodaje komunikat,
6. wykonuje `render()` albo `redirect()`.

Nie umieszczaj w widoku ciężkiej logiki, rozbudowanych obliczeń, parserów, FIFO ani dużych agregacji.

### `actions/`

Operacje zmieniające dane:

* tworzenie,
* edycja,
* usuwanie i archiwizacja,
* księgowanie,
* zmiana statusu,
* przebudowa danych,
* operacje transakcyjne i skutki uboczne.

Action powinien:

* mieć jeden jasno nazwany cel,
* walidować reguły biznesowe,
* korzystać z `transaction.atomic()`, gdy zmienia kilka powiązanych rekordów,
* zwracać przewidywalny wynik,
* zgłaszać jawny wyjątek domenowy,
* nie zależeć od HTML ani komunikatów UI.

### `selectors/`

Wyłącznie odczyt:

* querysety,
* filtrowanie i listy,
* szczegóły obiektu,
* dane dashboardów,
* agregacje do prezentacji.

Selector nie zapisuje danych i zawsze respektuje gospodarstwo.

### `services/`

Większe procesy i orkiestracja:

* raporty,
* import/export,
* statystyki i opłacalność,
* backup/restore,
* procesy wieloetapowe i przekrojowe,
* integracje i parsery.

Nie twórz jednego „god service” dla całego modułu.

### `calculators/`

Czyste, deterministyczne obliczenia bez skutków ubocznych:

* koszty,
* ilości,
* receptury,
* wartości jednostkowe,
* obliczenia magazynowe niezapisujące danych.

### `domain/`

Reguły biznesowe niezależne od HTTP:

* maszyny stanów,
* reguły przejść,
* typy i stałe domenowe,
* walidatory,
* wyjątki domenowe.

### Template

Template wyłącznie prezentuje dane przygotowane przez view, selector albo service.

* Nie umieszczaj w nim logiki biznesowej.
* Nie wykonuj skomplikowanych obliczeń.
* Nie duplikuj dużych fragmentów HTML.
* Wspólne elementy umieszczaj w `templates/components/` albo include.

### JavaScript

JavaScript jest progresywnym ulepszeniem interfejsu.

* Backend pozostaje źródłem prawdy.
* Walidacja klienta nie zastępuje walidacji serwera.
* Blokada przycisku nie zastępuje ochrony przed podwójnym zapisem.
* Nie duplikuj reguł biznesowych w JS.
* Krytyczne operacje powinny działać poprawnie również bez JS.
* Nie dodawaj HTMX ani Alpine.js bez wyraźnej zgody, jeśli projekt ich jeszcze nie używa.
* Jeśli dany mechanizm już istnieje, rozwijaj go zamiast tworzyć drugi.

---

## 5. Czysty kod

Stosuj KISS, DRY, SOLID i YAGNI jako praktyczne zasady, nie jako pretekst do komplikowania kodu.

### KISS

* Preferuj jawny i prosty przepływ.
* Unikaj „sprytnego” kodu, metaprogramowania i ukrytych efektów.
* Nie twórz abstrakcji dla jednego prostego użycia.
* Nie dziel jednej prostej operacji na wiele plików bez korzyści.

### DRY

Duplikację przenoś do właściwej warstwy:

* wspólne zapytanie → selector albo QuerySet,
* wspólny zapis → action,
* wspólny proces → service,
* wspólne obliczenie → calculator,
* wspólna reguła → domain,
* wspólny HTML → component/include,
* wspólny styl → klasa albo token CSS.

Nie łącz na siłę dwóch podobnych przepływów, jeśli mają różne znaczenie domenowe.

### SOLID

* Funkcja lub klasa powinna mieć jeden powód do zmiany.
* Nie twórz wielkich funkcji, widoków i klas.
* Ograniczaj zagnieżdżenia i stosuj szybkie wyjścia.
* Nie przekazuj wielu niepowiązanych flag sterujących całym procesem.
* Izoluj integracje zewnętrzne w małych adapterach/klientach.
* Nie twórz interfejsów i bazowych klas bez realnych wariantów.

### Nazwy i dokumentacja

* Nazwy mają jasno opisywać intencję.
* Unikaj niejednoznacznych nazw typu `data`, `obj`, `item`, `process`.
* Komentarze wyjaśniają „dlaczego”, a nie przepisują kod.
* Dla publicznych actions, services i nietrywialnych reguł używaj krótkich docstringów.
* Nie pozostawiaj nieaktualnych komentarzy.

### Python

* Stosuj PEP 8.
* Nie używaj `from module import *`.
* Korzystaj z istniejącej konfiguracji Ruff, Black lub innych narzędzi.
* Nie formatuj całego repozytorium przy małej zmianie.
* Używaj type hints tam, gdzie zwiększają czytelność.
* Do pieniędzy i precyzyjnych ilości używaj `Decimal`, nie `float`.

---

## 6. Wzorce projektowe

Stosuj wzorzec tylko wtedy, gdy upraszcza konkretny problem.

Preferowane zastosowania:

* Action/Command — jawna operacja zapisu,
* Service Layer — proces wieloetapowy lub przekrojowy,
* Selector/Query Object — reużywalny odczyt,
* State — cykl statusów,
* Strategy — rzeczywiście wymienne algorytmy,
* Adapter — parser lub integracja,
* Facade — prosty punkt wejścia do złożonego raportu,
* Value Object — ważna, niezmienna wartość domenowa.

Ograniczenia:

* Nie twórz fabryki dla jednego obiektu.
* Nie twórz interfejsu bez realnych implementacji.
* Nie ukrywaj krytycznej logiki w sygnałach Django.
* FIFO, magazyn, koszty, historia i zmiany statusów powinny mieć jawny przepływ.
* Sygnały są dopuszczalne tylko dla małych, niekrytycznych i dobrze przetestowanych efektów ubocznych.

---

## 7. Izolacja gospodarstwa

Każdy odczyt i zapis danych musi być ograniczony do bieżącego gospodarstwa.

Używaj:

```python
farm = get_current_farm(request)
```

albo `request.farm`, jeśli middleware już je przygotowuje.

Dotyczy to:

* list i szczegółów,
* dashboardów i statystyk,
* formularzy i pól relacyjnych,
* wyszukiwania i endpointów JSON,
* importów, eksportów i backupów,
* edycji, usuwania i archiwizacji,
* `get_object_or_404()`,
* załączników i operacji asynchronicznych.

Preferuj:

```python
obj = get_object_or_404(Model.objects.filter(farm=farm), pk=pk)
```

zamiast pobierania globalnego i późniejszego sprawdzania właściciela.

Testy izolacji powinny potwierdzać, że użytkownik nie może:

* zobaczyć,
* edytować,
* usunąć,
* użyć w formularzu,
* wyeksportować,
* pobrać pliku

należącego do innego gospodarstwa.

---

## 8. Bezpieczeństwo i błędy

* Nie wyłączaj CSRF, walidacji formularzy ani escaping HTML.
* `safe` stosuj tylko dla kontrolowanej treści.
* Operacje zmieniające dane wykonuj przez POST lub właściwą metodę, nie przez GET.
* Ukrycie przycisku w UI nie jest kontrolą dostępu.
* Waliduj typ, rozmiar, rozszerzenie i zawartość pliku.
* Nie ufaj nazwie pliku użytkownika.
* Nie hardcoduj sekretów ani ścieżek lokalnych.
* Nie ujawniaj stack trace na produkcji.
* Nie loguj haseł, tokenów ani pełnych danych wrażliwych.
* Link `next` po logowaniu musi być bezpiecznie walidowany.
* Nie używaj szerokiego `except Exception` bez dobrego powodu.
* Łap tylko błędy, które potrafisz obsłużyć.
* Dla reguł biznesowych stosuj jawne wyjątki domenowe.
* Użytkownik otrzymuje krótki komunikat, a szczegóły techniczne trafiają do logów.
* Proces wieloetapowy nie może pozostać częściowo wykonany.
* Operacje powtarzalne zabezpiecz przed podwójnym wykonaniem po stronie serwera.
* Loguj istotny kontekst, np. moduł, operację, `farm_id` i ID obiektu.

---

## 9. Baza danych i ORM

### Zapytania

* Najpierw napisz poprawne i czytelne zapytanie.
* Następnie zmierz liczbę zapytań i czas.
* Używaj `select_related()` dla relacji pojedynczych.
* Używaj `prefetch_related()` dla relacji wielowartościowych.
* Nie wykonuj zapytań w pętli, jeśli można pobrać dane zbiorczo.
* Używaj paginacji dla rosnących list.
* Nie pobieraj całych tabel bez potrzeby.
* `only()` i `defer()` stosuj tylko po pomiarze i ze świadomością dodatkowych zapytań.
* Nie optymalizuj kosztem poprawności domenowej.

### QuerySet i Manager

Twórz własne metody, gdy ten sam filtr domenowy powtarza się w kilku miejscach i nazwana metoda poprawia czytelność.

Nie ukrywaj jednak gospodarstwa w sposób, który ułatwia przypadkowy odczyt globalny.

### Constraints i indeksy

* Ważne inwarianty zabezpieczaj constraintami, jeśli baza może je bezpiecznie wymusić.
* Indeksy dodawaj pod rzeczywiste filtry, sortowanie i relacje.
* Nie indeksuj każdego pola „na zapas”.
* Przy optymalizacji porównaj zapytanie przed i po zmianie.

### Transakcje i blokady

Używaj `transaction.atomic()`, gdy operacja:

* zapisuje kilka powiązanych modeli,
* zmienia magazyn i koszt,
* przebudowuje FIFO,
* importuje zestaw rekordów,
* usuwa dane z konsekwencjami.

`select_for_update()`:

* stosuj tylko w transakcji,
* blokuj najmniejszy potrzebny zestaw rekordów,
* nie blokuj nullable strony `OUTER JOIN`,
* w razie relacji opcjonalnej zablokuj najpierw bazowe rekordy, a relacje pobierz osobno,
* dodaj test integracyjny dla krytycznego przepływu.

### Operacje zbiorcze

`bulk_create()` i `bulk_update()` stosuj tylko wtedy, gdy:

* nie są potrzebne `save()`, sygnały ani indywidualne skutki uboczne,
* walidacja została wykonana,
* audyt i integralność pozostają poprawne.

---

## 10. Cache i wydajność

Cache nie jest rozwiązaniem domyślnym.

Kolejność optymalizacji:

1. usuń zbędne zapytania,
2. napraw N+1,
3. ogranicz pobierane dane,
4. dodaj paginację,
5. uprość obliczenia lub agregację,
6. zmierz wynik,
7. dopiero potem rozważ cache.

Cache można dodać, gdy:

* odczyt jest kosztowny i częsty,
* dane mogą być chwilowo nieaktualne,
* istnieje jasny mechanizm unieważniania,
* korzyść przewyższa dodatkową złożoność.

Każdy cache musi mieć:

* jednoznaczny klucz,
* `farm_id`,
* `user_id`, jeśli wynik zależy od uprawnień,
* parametry filtrów i okresu,
* wersję klucza,
* jawny TTL,
* strategię unieważniania,
* test cache hit, miss i invalidation.

Przykład:

```text
farm:{farm_id}:dashboard:{period}:{filters_hash}:v2
```

Nie cache’uj bez solidnego unieważniania:

* aktualnego magazynu,
* dostępności FIFO,
* danych potrzebnych do blokad,
* uprawnień,
* formularzy zależnych od bieżącego stanu,
* danych wrażliwych,
* lazy querysetów.

Po zapisie unieważnij wszystkie powiązane klucze. Nie polegaj wyłącznie na krótkim TTL dla danych krytycznych.

Nie dodawaj cache „na zapas”. W podsumowaniu podaj pomiar, powód, klucz, TTL i sposób unieważniania.

---

## 11. Migracje, produkcja i backup

* Nową zmianę modelu realizuj nową migracją.
* Nie edytuj starych migracji bez bardzo mocnego powodu.
* Sprawdź wygenerowaną migrację.
* Użyj `makemigrations --check`, jeśli pasuje do workflow projektu.
* W migracji danych korzystaj z `apps.get_model()`.
* Dodanie `NOT NULL` musi uwzględniać istniejące rekordy.
* Duża migracja nie powinna niepotrzebnie blokować produkcji.
* Nie uruchamiaj destrukcyjnych poleceń na produkcyjnej bazie.
* Nie zakładaj, że dane lokalne i produkcyjne są identyczne.
* Import powinien być atomowy.
* Import użytkownika musi zachować gospodarstwo.
* Tryb dodania i zastąpienia danych muszą być rozróżnione.
* Duplikaty wykrywaj przez stabilne identyfikatory i reguły domenowe.
* Restore całej bazy jest operacją administracyjną wysokiego ryzyka.
* Zastąpienie danych wymaga jasnego potwierdzenia.
* Backup powinien być możliwy do zweryfikowania.
* Nie loguj zawartości backupu.

---

## 12. System UI/UX

Frontend jest oparty o Django Templates, wspólne komponenty, modułowe pliki CSS i istniejący JavaScript.

Przed zmianą sprawdź:

* `templates/base.html`,
* `templates/components/`,
* podobny istniejący widok,
* `static/css/variables.css`,
* `base.css`,
* `navigation.css`,
* `buttons.css`,
* `cards.css`,
* `messages.css`,
* `tables.css`,
* `forms.css`,
* `pages.css`,
* `responsive.css`,
* istniejące pliki w `static/js/`.

Najpierw użyj istniejącego komponentu, klasy i tokenu. Nie twórz osobnego systemu dla jednej strony.

### Docelowy styl

Interfejs ma wyglądać jak profesjonalny panel administracyjny / ERP:

* jasne i spokojne tło,
* ciemna zieleń jako główny akcent,
* sidebar na desktopie,
* topbar z kontekstem strony,
* jedna wyraźna główna akcja,
* kompaktowe sekcje,
* cienkie separatory,
* minimalne cienie,
* małe promienie zaokrąglenia,
* wysoka czytelność i gęstość informacji.

Interfejs nie ma wyglądać jak landing page.

Zakazane bez wyraźnej potrzeby:

* duże ozdobne karty dla prostych ustawień,
* mocne cienie,
* glassmorphism,
* duże gradienty,
* przypadkowe kolory,
* dekoracyjne ilustracje,
* ogromne puste przestrzenie,
* osobny styl dla każdego modułu.

### Karty i sekcje

Karta jest uzasadniona, gdy grupuje spójny zestaw informacji.

Dla prostych ustawień preferuj:

* nagłówek sekcji,
* krótki opis,
* wiersze ustawień,
* switch lub checkbox po prawej,
* cienkie separatory.

Nie twórz osobnej karty dla pojedynczego pola, checkboxa lub linku.

### Tokeny i motywy

* Korzystaj z istniejących zmiennych CSS.
* Nie wpisuj losowych kolorów w template.
* Nowy token dodaj tylko, gdy ma znaczenie globalne.
* Każdy widok sprawdź w trybach light, dark i system.
* Sprawdź gęstości compact, standard i comfortable.
* Nie ustawiaj sztywnych wysokości, które psują większą czcionkę.

---

## 13. Responsywność

Każda zmiana frontendu musi działać na telefonie, tablecie i desktopie.

### Zasady

* Korzystaj z istniejących breakpointów i wzorców w `responsive.css`.
* Nie dodawaj przypadkowego breakpointu dla jednej strony, jeśli można użyć istniejącego.
* Stosuj Grid i Flexbox.
* Używaj `minmax(0, 1fr)` dla kolumn mogących się przepełnić.
* Pozwalaj elementom i tekstom się zawijać.
* Długie polskie nazwy, liczby i jednostki nie mogą psuć układu.
* Podstawowy widok mobilny nie może wymagać poziomego scrolla.
* Kontrolowany scroll jest dopuszczalny tylko w kontenerze tabeli, której nie da się czytelnie przekształcić.
* Nie opieraj obsługi wyłącznie na hover.
* Nie ukrywaj głównej akcji na wąskim ekranie.

Sprawdź co najmniej:

* około 360 px,
* około 720 px,
* około 900 px,
* około 1024 px,
* około 1440 px.

### Mobile

* Jedna kolumna.
* Pola formularza mogą mieć pełną szerokość.
* Główne przyciski i akcje muszą być łatwe do naciśnięcia.
* Cel dotykowy powinien mieć około 44 × 44 px.
* Menu, dropdown i modal nie mogą wychodzić poza viewport.
* Tekst nie może być zbyt mały.
* Tabela korzysta z istniejącego wariantu mobilnego albo kontrolowanego wrappera.

### Desktop

* Wykorzystuj dostępną szerokość.
* Nie rozciągaj krótkich pól na całą stronę.
* Grupuj logicznie powiązane pola.
* Unikaj dużych pustych obszarów.
* Najważniejsze dane powinny być widoczne bez zbędnego przewijania.

---

## 14. Formularze i masowe dodawanie

Każdy formularz powinien mieć:

* jednoznaczny tytuł,
* logiczną kolejność pól,
* label powiązany z polem,
* informację o jednostce,
* krótki tekst pomocniczy tylko tam, gdzie potrzebny,
* błąd inline przy konkretnym polu,
* widoczny błąd ogólny,
* główny przycisk,
* anulowanie/powrót,
* zachowanie danych po błędzie walidacji.

Zasady:

* label nad polem,
* krótkie pola nie muszą zajmować 100% szerokości na desktopie,
* na mobile pola mogą mieć pełną szerokość,
* nie dziel prostego formularza na wiele ozdobnych kart,
* sekcje oddzielaj nagłówkiem i linią,
* błąd ma mówić, jak naprawić problem,
* nie pokazuj technicznego wyjątku.

Przy wysyłaniu:

* można zablokować przycisk i pokazać „Zapisywanie…”,
* przycisk musi zostać odblokowany po błędzie,
* backend nadal chroni przed podwójnym zapisem,
* dla dłuższej operacji pokaż spinner lub status,
* nie dodawaj sztucznego opóźnienia.

### Formsety i masowe dodawanie

* Używaj tego samego wzorca co inne masowe formularze.
* Nowy wiersz ma wyglądać jak istniejące.
* Management form i numeracja muszą pozostać poprawne.
* Usunięcie wiersza jest czytelne i odwracalne do zapisu.
* Na mobile każdy wiersz pozostaje czytelny.
* Walidacja wskazuje konkretny błędny wiersz.
* Testuj: jeden wiersz, kilka wierszy, dodanie, usunięcie, pusty wiersz i błąd jednego wiersza.
* Nie twórz osobnej strony dla operacji, która powinna działać jak istniejące masowe dodawanie.

---

## 15. Tabele, listy i akcje

### Desktop

* Najważniejsze kolumny pokazuj pierwsze.
* Liczby wyrównuj konsekwentnie.
* Jednostkę umieszczaj w nagłówku albo wartości.
* Akcje trzymaj w przewidywalnej kolumnie.
* Nie pokazuj zbyt wielu mało ważnych kolumn.
* Stosuj paginację i spójny pasek filtrów.

### Mobile

Preferuj:

1. istniejący wariant tabeli-kart,
2. ograniczenie do najważniejszych pól,
3. szczegóły po wejściu w rekord,
4. kontrolowany scroll tylko w ostateczności.

Dla tabeli-kart:

* każde `td` ma poprawny `data-label`,
* kluczowa wartość jest łatwa do znalezienia,
* akcje są duże i dostępne,
* pusty stan nie wygląda jak uszkodzony rekord.

Każda lista obsługuje:

* dane,
* pusty stan,
* brak wyników po filtrze,
* błąd,
* loading, jeśli jest asynchroniczny,
* długie wartości,
* dużą liczbę rekordów.

### Akcje

* Jedna główna akcja na stronie, gdy to możliwe.
* Akcje drugorzędne są wizualnie słabsze.
* Akcja destrukcyjna ma styl zagrożenia i potwierdzenie.
* Nawigacja jest linkiem, operacja przyciskiem.
* Sama ikona wymaga etykiety albo `aria-label`.
* Użytkownik musi rozumieć skutek przed wykonaniem operacji.

---

## 16. Feedback, loading i dostępność

Po ważnej akcji pokaż jasny wynik przez Django Messages Framework albo istniejący mechanizm.

Obsłuż:

* sukces,
* ostrzeżenie,
* błąd,
* informację,
* loading,
* brak danych.

Zasady:

* komunikat jest krótki i konkretny,
* sukces może zniknąć po kilku sekundach,
* błąd wymagający działania nie znika zbyt szybko,
* komunikaty dynamiczne korzystają z `aria-live`,
* po zmianie asynchronicznej nie trać kontekstu użytkownika,
* dla operacji powyżej zauważalnego czasu pokaż status.

Dostępność:

* każde pole ma label,
* obrazy mają poprawny `alt`,
* elementy działają z klawiatury,
* focus jest widoczny,
* kolejność tabulacji jest logiczna,
* nie używaj dodatniego `tabindex`,
* nie przekazuj znaczenia wyłącznie kolorem,
* ikona bez tekstu ma opis,
* używaj semantycznego HTML,
* sprawdź powiększenie 200%,
* nie blokuj skalowania,
* nie opieraj działania wyłącznie na animacji lub hover,
* respektuj `prefers-reduced-motion`, jeśli dodajesz animacje.

---

## 17. Workflow zmiany frontendowej

Przed zmianą:

1. otwórz aktualny template,
2. znajdź podobny widok,
3. sprawdź komponenty,
4. sprawdź CSS i JS,
5. rozpisz stany: dane, pusty, błąd, loading, długie wartości, mobile,
6. ustal, czy zadanie jest wyłącznie wizualne.

Podczas implementacji:

1. zachowaj istniejący layout,
2. użyj istniejących tokenów i klas,
3. nie dodawaj inline CSS bez potrzeby,
4. nie duplikuj komponentów,
5. nie wprowadzaj nowego frameworka,
6. nie zmieniaj backendu przy czysto wizualnym zadaniu,
7. sprawdź wszystkie miejsca użycia zmienionego komponentu,
8. rozwijaj wersję mobilną równolegle.

Po implementacji sprawdź:

* 360, 720, 900, 1024 i 1440 px,
* light, dark i system,
* compact, standard i comfortable,
* klawiaturę i focus,
* 200% zoom,
* brak błędów w konsoli,
* brak niekontrolowanego poziomego scrolla,
* długie polskie teksty,
* jednostki i liczby,
* pusty stan,
* błędy formularza,
* podwójne kliknięcie zapisu.

Nie twierdź, że UI jest responsywne, jeśli nie zostało sprawdzone.

---

## 18. Reguły domenowe

### `feed`

Moduł krytyczny: magazyn, dostawy, FIFO, receptury, produkcja, gotowa pasza i koszty.

* Stan magazynu wynika z ruchów magazynowych.
* Dostawa tworzy właściwy ruch.
* Produkcja zużywa składniki przez istniejące FIFO.
* FIFO jest źródłem prawdy dla kosztu zużycia.
* Zakończenie procesu przechodzi przez istniejącą akcję.
* Nie twórz alternatywnego księgowania w widoku.
* Kupiona i wyprodukowana gotowa pasza zachowują właściwe pochodzenie.
* Historia nie może zmieniać się przypadkowo po edycji bieżących danych.
* Korekta/usunięcie musi obsłużyć konsekwencje magazynowe i kosztowe.
* Nie dopuszczaj ujemnego stanu, jeśli przepływ nie przewiduje tego jawnie.
* Nie dodawaj opcji wymuszania operacji mimo braków, jeżeli użytkownik polecił ją usunąć.
* Każda zmiana FIFO wymaga testu integracyjnego.
* Przy blokadach nie blokuj nullable strony outer join.

### Receptury

* `RecipeModel` jest główną recepturą.
* `RecipeVersionModel` jest konkretną historyczną wersją.
* Nowa produkcja używa właściwej aktualnej wersji.
* Historyczna produkcja nie zmienia składu po edycji bieżącej receptury.
* `custom_recipe_data` musi być respektowane.
* Nie twórz drugiego systemu wersjonowania.
* Przeliczanie historii używa istniejącego mechanizmu przebudowy.
* Zmiana zakończonej produkcji wymaga testów kosztu, FIFO i audytu.

### `sows`

* Status maciory wynika z historii zdarzeń i reguł domenowych.
* Reguły przejść trzymaj w `domain`.
* Dodawanie, edycja i usuwanie zdarzeń przechodzi przez action/service.
* Nie ustawiaj niezależnego statusu, jeśli jest wyliczany ze zdarzeń.
* Szczepienia mogą mieć osobny cykl.
* Dashboard i zadania korzystają z jednego źródła prawdy.
* Zdarzenia kończące muszą jednoznacznie wpływać na aktywność.
* Zmiana historii przelicza zależne dane w kontrolowany sposób.

### `sales`

* Parser PDF pozostaje w `sales/services/parsers/`.
* Widok nie parsuje dokumentu.
* Oddziel odczyt tekstu od mapowania domenowego.
* Średnia cena za kg jest ważona wagą.
* Obsługuj polskie liczby i jednostki.
* Niepewne dane generują ostrzeżenie i podgląd.
* Nie zapisuj automatycznie danych niepewnych.
* Wykrywaj duplikaty dokumentów.
* Import jest atomowy.
* Dodaj testy reprezentatywnych i błędnych dokumentów.

### `costs`

* Każdy koszt należy do gospodarstwa.
* Kategorie są per gospodarstwo.
* Kosztów ręcznych nie mieszaj z kosztem paszy z produkcji.
* Koszt paszy pochodzi z zakończonych produkcji i FIFO.
* `costs` może pobierać wynik z `feed`, ale nie implementuje FIFO.
* Listy i podsumowania używają selectorów/services.
* Zapisy przechodzą przez action.

### `farms`

* Jest modułem systemowym i przekrojowym.
* Może agregować dane innych modułów.
* Nie przejmuje ich szczegółowej logiki.
* Dashboard przekrojowy odpytuje właścicieli danych.
* Nawigacja, widoczność modułów i aktywne URL-e są utrzymywane centralnie.

---

## 19. Polskie dane, historia i audyt

Uwzględniaj:

* przecinek dziesiętny,

* spacje i twarde spacje,

* `kg`, `t`, `zł`, `zł/kg`, `zł/t`, `szt.`, `%`,

* netto/brutto,

* polski format daty.

* Przechowuj liczby jako liczby, formatowanie wykonuj w prezentacji.

* Nie używaj `float` do pieniędzy.

* Zaokrąglanie musi być jawne.

* Pokazuj jednostkę.

* Komunikaty walidacyjne mają być po polsku.

Najważniejsze operacje zapisują historię zmian, szczególnie:

* tworzenie,
* edycja,
* usuwanie i archiwizacja,
* import/export,
* backup/restore,
* zmiany ustawień,
* magazyn i FIFO,
* receptury i produkcja,
* zmiany historycznych zdarzeń.

Przed usunięciem zachowaj potrzebną reprezentację obiektu. Audyt nie może zawierać sekretów.

---

## 20. Testy

Podstawowe polecenie:

```bash
pytest
```

Najpierw uruchom testy modułu:

```bash
pytest feed
pytest sows
pytest sales
pytest costs
pytest farms
```

Dla zmiany krytycznej lub przekrojowej uruchom pełny zestaw.

Stosuj:

* testy jednostkowe dla calculators/domain,
* testy actions i transakcji,
* testy selectors,
* testy integracyjne procesów,
* testy widoków i uprawnień,
* testy izolacji gospodarstwa,
* testy regresyjne dla naprawionego błędu,
* testy parserów,
* istniejące testy UI/E2E, jeśli projekt je posiada.

Szczególnie wymagane testy dla:

* FIFO i ruchów magazynowych,
* dostaw i gotowej paszy,
* kosztów,
* receptur i wersji,
* zakończenia produkcji,
* podawania paszy,
* importu PDF,
* statusów macior,
* eksportu/importu,
* backup/restore,
* usuwania danych,
* współbieżności,
* podwójnego wysłania formularza.

Przy optymalizacji:

* zmierz liczbę zapytań przed i po,
* dodaj test liczby zapytań tylko wtedy, gdy będzie stabilny i wartościowy.

Nie usuwaj testu dlatego, że przeszkadza. Nie zmieniaj oczekiwań bez sprawdzenia reguły biznesowej.

Jeśli testy nie przechodzą, podaj dokładnie które i czy błąd wynika ze zmiany.

---

## 21. Definition of Done

### Backend

Zmiana jest zakończona, gdy:

* znajduje się we właściwej warstwie,
* respektuje gospodarstwo,
* zachowuje integralność i historię,
* używa właściwej transakcji,
* nie duplikuje logiki,
* nie wprowadza oczywistego N+1,
* obsługuje błędy,
* ma test regresyjny lub test nowej reguły,
* odpowiednie testy przechodzą,
* migracja jest sprawdzona, jeśli powstała.

### Frontend

Zmiana jest zakończona, gdy:

* używa istniejącego layoutu, komponentów i tokenów,
* pasuje do stylu panelu administracyjnego,
* nie wprowadza zbędnych kart i dekoracji,
* działa na telefonie, tablecie i desktopie,
* nie ma niekontrolowanego poziomego scrolla,
* działa w light/dark/system,
* działa w compact/standard/comfortable,
* ma widoczny focus i działa z klawiatury,
* formularz zachowuje dane po błędzie,
* błędy są inline,
* zapis jest zabezpieczony przed duplikacją,
* lista ma pusty stan,
* długie wartości nie psują układu,
* nie ma błędów w konsoli,
* nie dodano zbędnego inline CSS ani duplikacji HTML.

---

## 22. Kiedy refaktorować

Refaktor jest uzasadniony, gdy:

* usuwa realną duplikację,
* naprawia źródło błędu,
* upraszcza konkretną funkcję,
* zmniejsza ryzyko,
* poprawia testowalność,
* wydziela logikę z widoku/template,
* usuwa N+1,
* centralizuje ważną regułę.

Nie refaktoruj tylko dlatego, że:

* można użyć większej liczby wzorców,
* inna architektura jest modna,
* cały projekt nie jest idealny,
* małe zadanie daje okazję do przebudowy modułu.

Większy refaktor przedstaw jako osobny etap.

---

## 23. Workflow zadania

1. Przeczytaj polecenie.
2. Ustal, czy chodzi o analizę, prompt czy implementację.
3. Sprawdź branch `develop`.
4. Znajdź wszystkie pliki przepływu.
5. Ustal źródło prawdy.
6. Sprawdź powiązania modułów i historię.
7. Sprawdź istniejące testy.
8. Wybierz najmniejszą bezpieczną zmianę.
9. Umieść ją we właściwej warstwie.
10. Dla UI sprawdź komponenty, CSS, JS i mobile.
11. Wprowadź zmianę bez pobocznego refaktoru.
12. Dodaj lub zaktualizuj testy.
13. Uruchom testy modułu.
14. Dla krytycznej zmiany uruchom pełny zestaw.
15. Sprawdź główny przepływ ręcznie.
16. Dla UI sprawdź rozmiary, motywy i gęstości.
17. Podsumuj zmiany, testy i ryzyka.

---

## 24. Format odpowiedzi końcowej

Po pracy programistycznej odpowiedz po polsku:

```text
Zmieniono:
- ...

Pliki:
- ...

Testy:
- ...

Sprawdzenie UI:
- ...

Jak sprawdzić ręcznie:
- ...

Wydajność / zapytania / cache:
- ...

Ryzyka / uwagi:
- ...
```

Zasady:

* Jeśli sekcja nie dotyczy zadania, wpisz „Nie dotyczy”.
* Jeśli testów nie uruchomiono, napisz dlaczego.
* Jeśli testy nie przeszły, wymień je.
* Jeśli czegoś nie wykonano, napisz to wprost.
* Nie twierdź, że UI jest responsywne bez sprawdzenia.
* Nie twierdź, że nie ma N+1 bez sprawdzenia zapytań.
* Nie sugeruj cache bez pomiaru.
* Nie ukrywaj ryzyka migracji lub zmiany historii.
* Nie wykonuj commita bez polecenia.

---

## 25. Zasada końcowa

Najpierw zrozum obecny przepływ i źródło prawdy. Następnie wykonaj najmniejszą zmianę w odpowiedniej warstwie.

Każda zmiana ma:

* nie psuć istniejącej logiki,
* chronić dane produkcyjne,
* respektować izolację gospodarstwa,
* zachować historię,
* być prosta i czytelna,
* być możliwa do przetestowania,
* być responsywna, jeśli dotyczy UI,
* pasować do systemowego stylu aplikacji,
* nie dodawać cache, wzorców ani frameworków bez rzeczywistej potrzeby.
