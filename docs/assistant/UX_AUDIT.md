# Audyt UX aplikacji

Data audytu: 2026-10-07, wdrożenie i ponowna weryfikacja: 2026-10-14.
Rekomendacje interfejsowe zostały wdrożone; opis pierwotnych problemów
pozostaje dokumentacją powodów zmian.

## 1. Zakres i metoda

Sprawdzono kod wspólnego shellu, komponenty, CSS, JavaScript i reprezentatywne
template'y. Aplikację uruchomiono lokalnie na danych demonstracyjnych i
obejrzano w przeglądarce.

Ekrany desktopowe (1280 px):

- centrala, katalog modułów i lista macior;
- magazyn/ruchy, nowe śrutowanie;
- nowa sprzedaż, koszty, statystyki i ustawienia.

Ekrany mobilne (360 px):

- centrala, lista macior, magazyn i formularz sprzedaży.

Po wdrożeniu sprawdzono centralę, zużycie paszy, nowe śrutowanie, sprzedaż i
ustawienia przy 360, 720, 900, 1024 i 1440 px. Nie wykryto globalnego poziomego
scrolla ani błędów konsoli. Podgląd light/dark/system i
compact/standard/comfortable działa bez zapisu, a powrót do wartości
początkowych wyłącza ostrzeżenie o niezapisanych zmianach. Sprawdzono cele
dotykowe na 360 px, focus po dodaniu wierszy oraz zakładki ustawień obsługiwane
strzałkami. Zoom 200%, kontrast automatyczny i realne urządzenia pozostają
manualną bramką przed wydaniem, ponieważ repozytorium nadal nie zawiera runnera
Playwright/axe.

## Status rekomendacji

- usunięto podwójną jednostkę ceny i podwójne przeliczenie;
- mobilne główne akcje, zakładki i ikony mają docelowy obszar około 44 px;
- formset sprzedaży ma nazwy dostępności, jeden pusty wiersz, karty mobilne,
  focus i komunikat `aria-live`;
- śrutowanie korzysta z jednego wyboru receptury i przyklejonej stopki;
- sprzedaż progresywnie ujawnia dane dodatkowe oraz właściwy tryb rozliczenia;
- formatowanie liczb przechodzi przez wspólny moduł;
- centrala mobilna pokazuje najpierw maksymalnie pięć zadań pilnych/na dziś;
- podnawigacja przewija aktywną zakładkę i sygnalizuje dalsze pozycje;
- dashboard respektuje wybrane, niepowtarzające się KPI;
- ustawienia mają pięć rzeczywistych paneli, live preview i poprawny dirty state;
- podsumowanie błędów linkuje do pól;
- licznik powiadomień pokazuje pilne/na dziś i stosuje `99+`;
- dodano safe area dolnej nawigacji i favicon;
- wspólny dialog potwierdzeń zastępuje rozproszone `window.confirm` dla prostego CRUD.

Punkty odniesienia:

- [WCAG 2.2 — target size minimum](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum);
- [GOV.UK — error summary](https://design-system.service.gov.uk/components/error-summary/)
  i [error message](https://design-system.service.gov.uk/components/error-message/);
- [SAP Fiori — responsive table](https://experience.sap.com/fiori-design-web/responsive-table/)
  oraz [table overview](https://experience.sap.com/fiori-design-web/table-overview/).

Wnioski dla pracy w gospodarstwie idą celowo dalej niż minimum WCAG: interfejs
może być używany jedną ręką, w ruchu i w gorszych warunkach, dlatego dla
głównych akcji mobilnych docelowy obszar około 44 × 44 px jest rozsądniejszy niż
formalny próg 24 × 24 px.

## 2. Co działa dobrze

- Spójny shell przypomina panel operacyjny/ERP, a nie stronę marketingową.
- Nawigacja desktopowa, topbar i dolna nawigacja mobilna są przewidywalne.
- Strony mają jasny tytuł, krótki opis i zwykle jedną wyróżnioną akcję.
- Kolory, odstępy i gęstości opierają się na tokenach.
- Filtry są domyślnie zwinięte i nie dominują nad treścią.
- Tabele odczytowe przechodzą na telefonie do kart label/value; sprawdzone
  komórki miały `data-label`.
- Formularze standardowe mają etykiety, błędy inline i ogólne podsumowanie.
- Dostępne są skip link, globalny `:focus-visible`, `aria-live`, semantyczne
  dialogi i opisy ikon.
- `prefers-reduced-motion` jest respektowane dla spinnera i powiadomień.
- Ustawienia pozwalają zmienić gęstość, motyw i rozmiar tekstu.
- Centrala dobrze eksponuje pracę „do wykonania”, a nie tylko statyczne KPI.
- Jednostki kg/t i zł/kg/zł/t są jawne w formularzach paszowych.

## 3. Wdrożone rekomendacje — pierwotne uzasadnienie

### P0. Usunąć drugą kontrolkę jednostki ceny z dostawy gotowej paszy

Rozszerzony audyt wykazał, że `ReadyFeedDeliveryForm` otrzymuje z dwóch mixinów
dwa pola opisane „Jednostka ceny”. Template renderuje oba. Nie jest to wyłącznie
problem wizualny: payload z obiema jednostkami ustawionymi na `t` może wykonać
konwersję ceny dwa razy.

Zastosować:

- jedno widoczne pole jednostki ceny i jedno przeliczenie po stronie serwera;
- ten sam kontrakt pola w pojedynczej dostawie gotowej paszy oraz formsecie
  dostaw składników;
- test HTML liczby kontrolek i test regresyjny podwójnego payloadu;
- nie naprawiać problemu przez samo ukrycie jednego selecta w template.

Szczegółowy plan techniczny: `DUPLICATION_AND_DEAD_CODE_AUDIT.md`, DRY-01/P0.

### P1. Zwiększyć cele dotykowe na telefonie

Pomiar na 360 px wykazał wiele przycisków, zakładek i paginacji o wysokości
33–38 px. Formalne minimum WCAG 2.2 może być spełnione dzięki rozmiarowi lub
odstępom, ale w kontekście gospodarstwa te elementy są zbyt mało wybaczające.

Zastosować:

- minimalną wysokość 44 px dla głównych przycisków, zakładek, paginacji i akcji
  wiersza na `max-width: 720px`;
- minimum 44 × 44 px dla ikon w topbarze i przycisków bez tekstu;
- większy odstęp między akcją główną i destrukcyjną;
- test automatyczny mierzący najważniejsze cele na 360 px.

Nie należy zwiększać wszystkich desktopowych kontrolek, bo tryb compact ma
świadomie wysoką gęstość. Zmiana powinna być mobilna i kontekstowa.

### P1. Naprawić etykiety dostępności w tabeli klas sprzedaży

W formularzu sprzedaży widoczne inputy formsetu (`rows-*-line_no`, klasa,
ilość, waga, cena, wartości) nie mają powiązanych elementów `label` ani
`aria-label`. Nagłówki tabeli pomagają wzrokowo, ale nie tworzą pewnej nazwy
dostępności dla każdego pola. Na telefonie tabela i tak staje się formularzem
kartowym.

Zastosować:

- na desktopie dodać unikalne `aria-label`, np. „Waga, pozycja 2”, albo
  semantyczne powiązanie nagłówka kolumny i wiersza przez `headers`/`id`;
- na mobile renderować każdy wiersz jako `fieldset`/kartę z widocznymi etykietami;
- po dodaniu wiersza przenosić focus do pierwszego pola nowej pozycji;
- ogłaszać dodanie/usunięcie wiersza w `aria-live`;
- ograniczyć początkowo widoczne puste wiersze do jednego.

SAP Fiori odradza używanie responsywnej tabeli jako formularza. Dla tego ekranu
najlepszy będzie układ hybrydowy: tabela na desktopie, karta formularza na
telefonie.

### P1. Uprościć formularz nowego śrutowania

Na ekranie są dwa selektory receptury: osobny do podglądu składników i osobny w
formularzu zapisu. To zwiększa ryzyko, że użytkownik obejrzy jedną recepturę, a
zapisze inną. Główna akcja zapisu znajduje się poniżej pierwszego widoku przy
wysokości 720 px.

Zastosować:

- jeden selektor receptury jako źródło podglądu i zapisu;
- po wyborze pokazać pod nim skład oraz przewidywane zużycie;
- pozostawić datę, czas, ilość i jednostkę w jednym zwartym wierszu na desktopie;
- dodać przyklejony pasek „Anuluj / Zapisz” tylko dla dłuższych formularzy;
- wyraźniej oddzielić opcję natychmiastowego zakończenia, bo uruchamia FIFO,
  koszt i podanie paszy.

### P1. Uprościć pierwszą część formularza sprzedaży na mobile

Na 360 px pierwszy ekran zajmują także pola opcjonalne: tatuaż, mięsność, waga
żywa, jednostka i wybój. Wybór sposobu rozliczenia oraz tabela klas pojawiają się
znacznie niżej, choć to one decydują o dalszym przebiegu.

Zastosować:

- zostawić na początku datę i numer dokumentu;
- przenieść pola dodatkowe do zwijanej sekcji „Dane dodatkowe”;
- pokazać wybór: ręcznie / PDF / później zaraz po danych podstawowych;
- po wyborze pokazywać wyłącznie właściwy następny krok;
- dla trybu „później” nie renderować pustych wierszy klas;
- dodać przyklejony pasek zapisu na telefonie.

### P1. Ujednolicić polskie formatowanie liczb

Na dashboardzie część ostatnich zdarzeń prezentowała wartości typu
`3093.75 zł`, podczas gdy podsumowania używały polskiego przecinka i odstępów.
Wartości finansowe i ilości muszą wszędzie przechodzić przez wspólne filtry
`smart_number`/`smart_unit` albo odpowiedniki domenowe.

Zastosować testy template dla:

- przecinka dziesiętnego;
- spacji tysięcy;
- jawnej jednostki;
- stabilnej liczby miejsc po przecinku zależnie od typu wartości.

### P2. Ograniczyć długość centrali na telefonie

Każda kategoria zadań pokazuje osobną kartę z dwiema akcjami. Przy wielu
kategoriach użytkownik długo przewija, zanim dotrze do szybkich akcji i KPI.

Zastosować:

- jedną sekcję „Pilne i na dziś” z maksymalnie 3–5 pozycjami;
- pozostałe grupy jako zwarte wiersze z liczbą i linkiem;
- sortowanie według pilności i terminu, nie według modułu;
- zapamiętanie najczęściej wykonywanych szybkich akcji per gospodarstwo dopiero
  po potwierdzeniu realnej potrzeby — bez automatycznego, ukrytego uczenia.

### P2. Poprawić mobilną nawigację modułu

Zakładki modułów są przewijane poziomo. Działa to bez globalnego overflow, ale
na 360 px następne pozycje są częściowo ukryte, a widoczny scrollbar konkuruje z
treścią.

Zastosować:

- automatycznie przewijać aktywną zakładkę do widoku;
- dodać subtelny gradient/krawędź sugerującą dalsze pozycje;
- na bardzo wąskich ekranach pokazać 2–3 najważniejsze zakładki i „Więcej”;
- nie zawijać wszystkich zakładek w kilka wysokich rzędów.

### P2. Zmniejszyć redundancję statystyk

Podsumowanie ma dużą liczbę kafli, a część wskaźników (np. pasza/waga żywa)
powtarza się w górnym podsumowaniu i niższej sekcji. Przy takim zagęszczeniu
ważne odchylenia nie wyróżniają się wystarczająco.

Zastosować:

- 4–5 KPI decyzyjnych na górze;
- jeden wpis każdego wskaźnika;
- trend i porównanie z poprzednim okresem obok liczby, jeśli dane są dostępne;
- pozostałe mierniki w sekcjach domenowych;
- jednoznaczny stan „brak danych” zamiast zera, gdy zero sugerowałoby wynik.

### P2. Uporządkować ustawienia

Strona ma około 2787 px wysokości. Kotwice sekcji i przyklejony zapis pomagają,
ale na jednej stronie mieszczą się dane gospodarstwa, wygląd, moduły, dashboard,
reguły domenowe i backup.

Zastosować:

- zachować jeden formularz dla ustawień współzależnych, ale pokazywać rzeczywiste
  panele zakładek: Ogólne, Wygląd, Moduły, Reguły, Dane;
- umożliwić tymczasowy podgląd motywu/gęstości przed zapisem albo jasno napisać,
  że zmiana zadziała po zapisaniu;
- przeliczać stan „niezapisane” względem wartości początkowych — w audycie
  ostrzeżenie pozostało widoczne po ręcznym powrocie do pierwotnych opcji;
- rozdzielić backup/restore wizualnie od codziennych ustawień i mocniej opisać
  skutek trybu zastąpienia.

### P2. Ulepszyć obsługę błędów formularza

Istnieje ogólne podsumowanie, błędy inline i JS przenoszący focus do pierwszego
błędu. Podsumowanie nie zawiera jednak listy odnośników do błędnych pól.

Zgodnie ze wzorcem GOV.UK:

- lista w podsumowaniu powinna linkować do każdego błędnego pola/wiersza;
- treść w podsumowaniu powinna odpowiadać treści inline;
- tytuł strony po błędzie może zaczynać się od „Błąd:”;
- komunikat ma mówić, co poprawić, bez technicznych sformułowań;
- przy błędzie formsetu wskazać numer wiersza i nazwę pola.

### P3. Powiadomienia i licznik zadań

Licznik `71` jest widoczny, ale nie mówi, ile elementów jest pilnych. Duża liczba
może szybko stać się szumem.

Zastosować:

- badge tylko dla pilnych/na dziś albo podział „pilne / pozostałe” w menu;
- licznik `99+` dla bardzo dużej wartości;
- zachować maksymalnie kilka pozycji w topbarze i link do centrum zadań;
- nie używać czerwieni dla zwykłej informacji bez pilności.

### P3. Bezpieczny obszar dolnej nawigacji

Dolna nawigacja jest czytelna i ma stabilne pięć pozycji. Należy uzupełnić ją o
`env(safe-area-inset-bottom)` i analogiczny padding treści dla urządzeń z belką
gestów/notchem. Dodatkowo warto sprawdzić orientację poziomą i klawiaturę
ekranową przy formularzach.

### P3. Uzupełnić favicon

Podczas audytu serwer deweloperski zwracał `404` dla `/favicon.ico`. Nie wpływa
to na procesy biznesowe, ale powoduje zbędne żądanie i pustą ikonę karty. Należy
dodać mały, kontrastowy znak aplikacji oraz jawny `<link rel="icon">` w
`base.html`.

## 4. Zrealizowana kolejność wdrożenia

### Etap 1 — dostępność i ryzyko pomyłki

1. Jedno pole i jedno przeliczenie jednostki ceny.
2. Etykiety pól formsetu sprzedaży.
3. Cele dotykowe 44 px na mobile.
4. Jeden selektor receptury w nowym śrutowaniu.
5. Spójne polskie formatowanie pieniędzy i ilości.
6. Linkowane podsumowanie błędów.

### Etap 2 — skrócenie pracy

1. Progresywne ujawnianie pól sprzedaży.
2. Sticky actions w długich formularzach.
3. Krótsza centrala mobilna i lepsza priorytetyzacja zadań.
4. Uporządkowanie zakładek modułów i ustawień.

### Etap 3 — analityka i dopracowanie

1. Redukcja duplikatów KPI i porównania okresów.
2. Powiadomienia według pilności.
3. Safe area, orientacja pozioma, dark/system, trzy gęstości i zoom 200%.
4. Automatyczne E2E i axe jako bramka regresji UI.

## 5. Kryteria akceptacji dla przyszłej zmiany UX

- główny proces ma mniej kroków lub mniejsze ryzyko pomyłki, a nie tylko inny
  wygląd;
- na 360 px brak globalnego poziomego scrolla;
- podstawowe akcje mobilne mają około 44 px wysokości/obszaru;
- każde pole ma programową nazwę i błąd powiązany z polem;
- główna akcja jest dostępna bez szukania końca długiego formularza;
- użytkownik rozumie skutek operacji FIFO, kosztowej i destrukcyjnej;
- light/dark/system oraz compact/standard/comfortable są sprawdzone;
- klawiatura, focus, zoom 200%, długie polskie teksty i konsola są sprawdzone;
- do zmiany dołączono test HTML lub E2E adekwatny do ryzyka.

Wdrożenie jest zapisane w `CHANGELOG.md`. Każda przyszła zmiana wspólnego UI
powinna ponownie przejść tę samą macierz szerokości, motywów, focusu i konsoli.
