# Manager Gospodarstwa

## Opis projektu

Manager Gospodarstwa to aplikacja webowa napisana w Django, której celem jest wspomaganie zarządzania gospodarstwem trzody chlewnej. Projekt obejmuje kilka głównych obszarów pracy gospodarstwa: ewidencję macior, obsługę zdarzeń produkcyjnych, kontrolę szczepień, analizę wyników rozrodu, sprzedaż tuczników oraz moduł paszowy związany z magazynem, recepturami i śrutowaniem.

Projekt jest działający, ale pozostaje w ciągłym rozwoju przeze mnie. Jest rozwijany jako praktyczna aplikacja, która ma odwzorowywać realne procesy występujące w gospodarstwie.

W realnych warunkach gospodarstwa aplikacja posiada zewnętrzną bazę danych, która jest opublikowana na stronie:

```text
https://managergospodarstwa.onrender.com/
```

Dodatkowo projekt może działać lokalnie na własnej bazie danych po zmianie ustawienia `DEBUG=True` w pliku `.env`. W tym trybie aplikacja korzysta z lokalnej bazy SQLite.

---

## Technologie

Projekt wykorzystuje:

- Python
- Django
- Django Templates
- SQLite w trybie lokalnym
- PostgreSQL / zewnętrzną bazę danych w trybie produkcyjnym
- WhiteNoise do obsługi plików statycznych
- Gunicorn do uruchamiania aplikacji na serwerze
- pytest do testów

---

## Konfiguracja środowiska `.env`

W katalogu głównym projektu należy utworzyć plik `.env`.

Przykładowa konfiguracja lokalna:

```env
DEBUG=True
SECRET_KEY=local-dev-secret-key
DATABASE_URL=
```

Przykładowa konfiguracja produkcyjna:

```env
DEBUG=False
SECRET_KEY=twoj-produkcyjny-sekretny-klucz
DATABASE_URL=postgres://user:password@host:port/database
```

Znaczenie pól:

- `DEBUG=True`  
  Uruchamia projekt lokalnie i korzysta z lokalnej bazy SQLite `db.sqlite3`.

- `DEBUG=False`  
  Uruchamia projekt w trybie produkcyjnym i wymaga poprawnego ustawienia `DATABASE_URL`.

- `SECRET_KEY`  
  Klucz bezpieczeństwa Django. W środowisku produkcyjnym musi być ustawiony.

- `DATABASE_URL`  
  Adres zewnętrznej bazy danych używany w trybie produkcyjnym.

---

## Uruchomienie projektu lokalnie

Poniżej znajduje się instrukcja uruchomienia projektu na lokalnym komputerze w trybie deweloperskim.

### 1. Pobranie projektu

Najpierw należy sklonować repozytorium:

```bash
git clone <adres_repozytorium>
cd managerGospodarstwa
```

### 2. Utworzenie środowiska wirtualnego

```bash
python -m venv .venv
```

Aktywacja środowiska na macOS / Linux:

```bash
source .venv/bin/activate
```

Aktywacja środowiska na Windows:

```bash
.venv\Scripts\activate
```

### 3. Instalacja zależności

Po aktywowaniu środowiska należy zainstalować wymagane biblioteki:

```bash
pip install -r requirements.txt
```

### 4. Utworzenie pliku `.env`

W głównym katalogu projektu należy utworzyć plik `.env`.

Dla uruchomienia lokalnego plik powinien wyglądać przykładowo tak:

```env
DEBUG=True
SECRET_KEY=local-dev-secret-key
DATABASE_URL=
```

Przy ustawieniu:

```env
DEBUG=True
```

projekt korzysta z lokalnej bazy danych SQLite, czyli pliku:

```text
db.sqlite3
```

W trybie lokalnym nie trzeba podawać `DATABASE_URL`.

### 5. Wykonanie migracji bazy danych

Po skonfigurowaniu `.env` należy utworzyć strukturę lokalnej bazy danych:

```bash
python manage.py migrate
```

### 6. Utworzenie konta administratora

Aby mieć dostęp do panelu administratora Django, należy utworzyć superużytkownika:

```bash
python manage.py createsuperuser
```

Następnie należy podać login, e-mail oraz hasło.

### 7. Uruchomienie serwera lokalnego

Projekt uruchamia się komendą:

```bash
python manage.py runserver
```

Po uruchomieniu aplikacja będzie dostępna pod adresem:

```text
http://127.0.0.1:8000/
```

Panel administratora będzie dostępny pod adresem:

```text
http://127.0.0.1:8000/admin/
```

### 8. Logowanie do aplikacji

Po wejściu na stronę należy zalogować się na konto użytkownika.

Jeżeli aplikacja jest uruchamiana pierwszy raz lokalnie, można użyć konta utworzonego przez:

```bash
python manage.py createsuperuser
```

Po zalogowaniu aplikacja automatycznie przypisuje użytkownikowi gospodarstwo i pozwala korzystać z modułów:

- maciory,
- sprzedaż,
- pasza,
- magazyn,
- receptury,
- śrutowanie,
- statystyki.

### 9. Uruchomienie testów

Testy można uruchomić komendą:

```bash
pytest
```

### Lokalna baza demonstracyjna

Przy `DEBUG=True` można utworzyć kompletny zestaw demonstracyjny:

```bash
python manage.py seed_demo_data
```

Logowanie do danych demo: `testtest` / `testtest`. Polecenie jest idempotentne. Pełne wyczyszczenie lokalnej bazy i ponowne utworzenie danych wykonuje:

```bash
python manage.py seed_demo_data --reset
```

`--reset` działa wyłącznie lokalnie przy `DEBUG=True` i usuwa wszystkie dane z lokalnej bazy.

### Bezpieczeństwo danych i nowe narzędzia

- Centrum zadań zbiera badania USG, oproszenia, szczepienia, niskie stany, kolejkę śrutowań i sprzedaże bez rozliczenia.
- Historia zmian zapisuje najważniejsze operacje i jest izolowana per gospodarstwo.
- Stan magazynu wynika z ruchów magazynowych: dostaw, zużycia produkcyjnego i korekt plus/minus.
- Korekta stanu jest dostępna w module magazynu i blokuje zejście poniżej zera.
- Ustawienia gospodarstwa udostępniają eksport/import CSV w archiwum ZIP; import jest atomowy i domyślnie wymaga pustego gospodarstwa.
- Analityka opłacalności pokazuje sprzedaż, produkcję i szacowany koszt paszy w wybranym okresie.
- Backup/restore całej bazy w panelu administracyjnym jest dostępny wyłącznie dla superusera; restore wymaga żądania POST i potwierdzenia.
- Istniejący eksport/import danych użytkownika w formacie ZIP/JSON pozostaje dostępny.

### 10. Najczęstsze problemy lokalne

Jeżeli po zmianach w modelach baza danych nie jest aktualna, należy wykonać:

```bash
python manage.py makemigrations
python manage.py migrate
```

Jeżeli pliki statyczne nie wyświetlają się poprawnie w trybie lokalnym, można uruchomić:

```bash
python manage.py collectstatic
```

W trybie lokalnym najważniejsze jest, aby w pliku `.env` było ustawione:

```env
DEBUG=True
```

Dzięki temu projekt korzysta z lokalnej bazy SQLite i nie wymaga połączenia z produkcyjną bazą danych.

---

## Główne moduły projektu

Projekt składa się z kilku aplikacji Django:

```text
managerGospodarstwa/
farms/
sows/
sales/
feed/
templates/
static/
```

---

# Moduł `farms`

Moduł `farms` odpowiada za przypisanie danych do konkretnego gospodarstwa użytkownika.

Najważniejsze założenia:

- każdy użytkownik posiada własne gospodarstwo,
- dane w aplikacji są filtrowane względem aktualnego gospodarstwa,
- middleware przypisuje aktualne gospodarstwo do `request.farm`,
- dzięki temu dane jednego użytkownika są logicznie oddzielone od danych innego użytkownika.

Najważniejszy model:

```text
FarmModel
```

Przechowuje:

- właściciela gospodarstwa,
- nazwę gospodarstwa,
- datę utworzenia.

## Logika biznesowa modułu `farms`

Logika biznesowa tego modułu polega na automatycznym przypisaniu użytkownika do gospodarstwa.

Po zalogowaniu aplikacja:

1. sprawdza, czy użytkownik posiada już gospodarstwo,
2. jeżeli nie posiada, tworzy nowe gospodarstwo,
3. przypisuje gospodarstwo do aktualnego żądania jako `request.farm`,
4. przekazuje tę informację do pozostałych modułów.

Dzięki temu moduły `sows`, `sales` oraz `feed` mogą filtrować dane tylko do gospodarstwa aktualnego użytkownika.

---

# Moduł `sows`

Moduł `sows` odpowiada za zarządzanie maciorami i ich historią produkcyjną.

Obsługiwane elementy:

- dodawanie macior,
- przegląd aktywnych macior,
- archiwizacja macior,
- historia zdarzeń dla każdej maciory,
- inseminacje,
- badania prośności,
- oproszenia,
- odsadzanie,
- szczepienia,
- plany szczepień,
- statystyki i dashboard.

Najważniejsze modele:

```text
SowModel
SowEventModel
VaccinationPlanModel
```

## `SowModel`

Przechowuje podstawowe informacje o maciorze:

- numer kolczyka / oznaczenie,
- datę wejścia do stada,
- datę utworzenia,
- informację, czy maciora jest zarchiwizowana,
- przypisanie do gospodarstwa.

## `SowEventModel`

Przechowuje zdarzenia związane z maciorą.

Obsługiwane typy zdarzeń:

```text
INSEMINATION
PREGNANCY_CHECK
FARROWING
WEANING
VACCINATION
```

Dodatkowe dane zdarzenia są zapisywane w polu JSON, dzięki czemu różne typy zdarzeń mogą przechowywać różne informacje.

Przykładowe dane szczegółowe:

- wynik badania prośności,
- liczba żywo urodzonych,
- liczba martwo urodzonych,
- liczba odsadzonych,
- nazwa szczepionki,
- identyfikator cyklu szczepienia.

## `VaccinationPlanModel`

Model odpowiada za konfigurację planów szczepień.

Plan szczepienia może być zależny od:

- planowanego terminu oproszenia,
- liczby dni po wybranym zdarzeniu,
- cyklu powtarzanego co określoną liczbę miesięcy,
- liczby dni wcześniej, kiedy ma pojawić się przypomnienie.

---

## Logika biznesowa modułu macior

W projekcie została wydzielona logika cyklu życia maciory.

Na podstawie historii zdarzeń aplikacja wylicza aktualny status maciory.

Przykładowe statusy:

```text
IDLE
INSEMINATED
TO_CHECK
PREGNANT
TO_RECHECK
LACTATING
```

Znaczenie statusów:

- `IDLE` — maciora jałowa,
- `INSEMINATED` — maciora po inseminacji,
- `TO_CHECK` — maciora oczekuje na badanie USG,
- `PREGNANT` — maciora prośna,
- `TO_RECHECK` — maciora do ponownego badania,
- `LACTATING` — maciora karmiąca po oproszeniu.

Najważniejsze reguły:

- po inseminacji aplikacja wylicza planowany termin oproszenia po 114 dniach,
- po 30 dniach od inseminacji maciora może zostać oznaczona jako wymagająca badania,
- po pozytywnym badaniu maciora otrzymuje status prośnej,
- po negatywnym badaniu maciora wraca do statusu jałowej,
- po wyniku niejednoznacznym maciora otrzymuje status do ponownego badania,
- po oproszeniu maciora otrzymuje status karmiącej,
- po odsadzeniu maciora wraca do statusu jałowej,
- aplikacja zlicza statystyki produkcyjne, np. żywo urodzone, martwo urodzone i odsadzone prosięta.

Dashboard macior pokazuje m.in.:

- liczbę wszystkich aktywnych macior,
- liczbę macior po inseminacji,
- liczbę macior prośnych,
- liczbę macior karmiących,
- liczbę macior jałowych,
- maciory wymagające badania,
- przypomnienia o szczepieniach.

---

## Masowe dodawanie zdarzeń

Projekt posiada logikę masowego dodawania zdarzeń dla macior.

W tym miejscu aplikacja sprawdza, czy dodawane zdarzenie pasuje do aktualnego statusu maciory.

Przykładowe reguły:

- maciora jałowa powinna rozpocząć cykl od inseminacji,
- maciora po inseminacji może mieć dodane badanie lub ponowną inseminację,
- maciora do badania może mieć dodane badanie albo ponowną inseminację,
- maciora prośna może mieć dodane oproszenie,
- maciora karmiąca powinna mieć jako kolejne zdarzenie odsadzenie,
- szczepienia mogą być dodawane niezależnie od statusu produkcyjnego.

Dzięki temu aplikacja ogranicza przypadkowe wprowadzanie niespójnej historii produkcyjnej.

---

# Moduł `sales`

Moduł `sales` odpowiada za ewidencję sprzedaży tuczników.

Obsługiwane funkcje:

- dodawanie sprzedaży,
- edycja sprzedaży,
- lista sprzedaży,
- filtrowanie sprzedaży po okresie,
- podsumowanie sprzedaży,
- import danych z rozliczenia PDF,
- zapis klas sprzedażowych,
- przeliczenie wartości sprzedaży na podstawie wierszy rozliczenia.

Najważniejsze modele:

```text
PigSaleModel
SaleClassRowModel
```

## `PigSaleModel`

Przechowuje główne dane sprzedaży:

- datę sprzedaży,
- numer dokumentu,
- tatuaż,
- liczbę sprzedanych sztuk,
- wagę całkowitą,
- klasę mięsności,
- cenę za kg,
- średnią mięsność SEUROP,
- wagę żywą,
- wybój,
- wartość netto,
- VAT,
- wartość brutto.

## `SaleClassRowModel`

Przechowuje szczegółowe wiersze rozliczenia według klas.

Dane wiersza:

- numer linii,
- klasa,
- ilość,
- waga,
- średnia waga,
- średnia mięsność,
- cena za kg,
- wartość netto,
- VAT,
- wartość brutto.

---

## Logika biznesowa modułu sprzedaży

Moduł sprzedaży umożliwia pracę na danych ręcznych oraz na danych importowanych z dokumentów rozliczeniowych.

Najważniejsze reguły:

- sprzedaż może zostać dodana ręcznie,
- sprzedaż może posiadać szczegółowe wiersze klas,
- jeżeli istnieją wiersze klas, aplikacja może przeliczyć dane główne sprzedaży,
- ilość, waga, wartość netto, VAT i brutto są sumowane z wierszy,
- średnia cena za kg jest liczona jako cena ważona wagą,
- dashboard sprzedaży wylicza podsumowania z wybranego okresu.

Dashboard sprzedaży wylicza:

- liczbę dokumentów sprzedaży,
- łączną liczbę sprzedanych sztuk,
- łączną wagę,
- łączny przychód,
- średnią cenę za kg,
- średnią wagę jednej sztuki.

---

## Import rozliczeń PDF

Projekt posiada parser rozliczeń PDF.

Parser próbuje odczytać z dokumentu m.in.:

- datę uboju / sprzedaży,
- numer dokumentu,
- tatuaż,
- wiersze tabeli rozliczenia,
- klasy,
- ilości,
- wagi,
- ceny,
- wartości netto,
- VAT,
- wartości brutto,
- podsumowanie dokumentu.

Dzięki temu możliwe jest szybsze uzupełnianie sprzedaży na podstawie dokumentów otrzymanych z zakładu.

---

# Moduł `feed`

Moduł `feed` odpowiada za część paszową gospodarstwa.

Obsługiwane funkcje:

- składniki paszowe,
- dostawy składników,
- ceny składników,
- magazyn pasz,
- receptury,
- elementy receptur,
- kalkulator kosztów,
- produkcja / śrutowanie,
- etapowe księgowanie produkcji.

Najważniejsze modele:

```text
IngredientModel
DeliveryModel
IngredientPriceConfigModel
RecipeModel
RecipeItemModel
ProductionModel
```

## `IngredientModel`

Przechowuje składniki paszowe.

Dane:

- nazwa składnika,
- opis,
- informacja, czy składnik jest przechowywany w binie / silosie,
- przypisanie do gospodarstwa.

## `DeliveryModel`

Przechowuje dostawy składników.

Dane:

- data dostawy,
- składnik,
- ilość w kg,
- cena za kg.

## `IngredientPriceConfigModel`

Przechowuje domyślną cenę składnika.

## `RecipeModel`

Przechowuje receptury paszowe.

## `RecipeItemModel`

Przechowuje składniki receptury i ich procentowy udział.

Udział składnika jest walidowany w zakresie od `0.01%` do `100%`.

## `ProductionModel`

Przechowuje zaplanowane lub zakończone śrutowanie.

Statusy produkcji:

```text
QUEUED
STAGE_1_DONE
COMPLETED
```

Znaczenie statusów:

- `QUEUED` — produkcja zaplanowana i oczekuje,
- `STAGE_1_DONE` — zakończono etap pobrania składników z binów,
- `COMPLETED` — produkcja została zakończona i zaksięgowana.

---

## Logika biznesowa modułu paszowego

Moduł paszowy rozdziela logikę na repozytoria, kalkulatory i serwisy.

Najważniejsze zasady:

- stan magazynowy składnika jest liczony jako:

```text
stan = suma dostaw - suma zużycia w zakończonych produkcjach
```

- zużycie składników jest liczone na podstawie receptury i ilości produkowanej paszy,
- aplikacja sprawdza, czy suma procentów w recepturze wynosi `100%`,
- koszt receptury jest liczony na podstawie udziałów procentowych składników i ich cen,
- koszt może być pokazany jako koszt za kg oraz koszt za tonę,
- aplikacja wykrywa niskie stany magazynowe,
- przed zakończeniem produkcji aplikacja może sprawdzić, czy w magazynie jest wystarczająca ilość składników,
- produkcja może przechodzić przez etapy:
  - kolejka,
  - etap 1,
  - zakończenie produkcji.

Moduł obsługuje również jednorazową zmianę proporcji receptury dla konkretnej produkcji przez pole `custom_recipe_data`.

---

## Struktura adresów URL

Główne ścieżki aplikacji:

```text
/                 - strona wyboru modułów
/maciory/         - dashboard macior
/sprzedaz/        - moduł sprzedaży
/pasza/           - moduł paszowy
/admin/           - panel administratora Django
```

Przykładowe adresy modułu macior:

```text
/maciory/
/maciory/dodaj/
/maciory/<id>/
/maciory/archiwum/
/maciory/statystyki/
/maciory/szczepienie-grupowe/
/maciory/badania-grupowe/
/maciory/zdarzenia/masowo/
```

Przykładowe adresy modułu sprzedaży:

```text
/sprzedaz/
/sprzedaz/dodaj/
/sprzedaz/<id>/edytuj/
```

Przykładowe adresy modułu paszowego:

```text
/pasza/skladniki/
/pasza/magazyn/
/pasza/receptury/
/pasza/srutowanie/
/pasza/kalkulator/
```

---

## Panel administratora

Panel administratora Django jest dostępny pod adresem:

```text
/admin/
```

Aby się zalogować, należy wcześniej utworzyć superużytkownika:

```bash
python manage.py createsuperuser
```

---

## Testy

Projekt posiada testy jednostkowe i integracyjne dla najważniejszych modułów.

Uruchomienie testów:

```bash
pytest
```

Testowane są m.in.:

- modele,
- formularze,
- repozytoria,
- widoki,
- encje domenowe,
- serwisy biznesowe.

---

## Deployment

Projekt jest przygotowany do działania w środowisku produkcyjnym.

W trybie produkcyjnym należy ustawić:

```env
DEBUG=False
SECRET_KEY=...
DATABASE_URL=...
```

Dodatkowo aplikacja korzysta z:

- `gunicorn`,
- `whitenoise`,
- `collectstatic`,
- migracji Django.

Przykładowe kroki wykonywane przy budowaniu aplikacji:

```bash
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py collectstatic --noinput
```

---

## Status projektu

Projekt jest działający, ale nadal rozwijany.

Aktualnie aplikacja obejmuje podstawowe i zaawansowane funkcje zarządzania gospodarstwem:

- obsługę macior,
- historię zdarzeń produkcyjnych,
- statusy macior,
- szczepienia i przypomnienia,
- statystyki produkcyjne,
- sprzedaż tuczników,
- import rozliczeń PDF,
- magazyn pasz,
- receptury,
- kalkulator kosztów paszy,
- produkcję / śrutowanie,
- wielogospodarstwowość opartą o użytkownika.

W przyszłości projekt może być dalej rozwijany m.in. o dodatkowe raporty, lepsze wykresy, eksport danych, rozbudowany system uprawnień, powiadomienia oraz kolejne automatyzacje procesów gospodarstwa.

---

## Autor

Projekt rozwijany przez Tomasza jako aplikacja wspomagająca zarządzanie gospodarstwem trzody chlewnej.
