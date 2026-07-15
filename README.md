
# Manager Gospodarstwa

Aplikacja webowa do zarządzania gospodarstwem trzody chlewnej.

Projekt wspiera najważniejsze procesy związane z:

- maciorami i rozrodem,
- szczepieniami,
- oproszeniami i odsadzeniami,
- upadkami,
- sprzedażą,
- kosztami,
- magazynem,
- paszami i recepturami,
- śrutowaniem,
- zadaniami i powiadomieniami,
- statystykami oraz opłacalnością produkcji.

Aplikacja jest rozwijana jako praktyczny system odwzorowujący rzeczywiste procesy gospodarstwa.

## Produkcja

Aplikacja produkcyjna jest dostępna pod adresem:

```text
https://managergospodarstwa.duckdns.org
```

Aktualna architektura:

```text
Internet
→ Nginx
→ Gunicorn
→ Django
→ PostgreSQL w Supabase
```

Serwer produkcyjny działa na:

```text
Oracle Cloud
Ubuntu 24.04
```

---

## Technologie

Projekt wykorzystuje:

- Python
- Django
- Django Templates
- PostgreSQL
- SQLite w środowisku lokalnym
- Gunicorn
- Nginx
- systemd
- pytest
- GitHub Actions
- Supabase
- Cloudflare R2
- Let's Encrypt
- Certbot

---

## Główne moduły

### Maciory

Moduł obsługuje:

- rejestr macior,
- historię zdarzeń,
- krycia,
- badania USG,
- oproszenia,
- odsadzenia,
- szczepienia,
- planowane terminy,
- powiadomienia,
- historię produkcyjną.

### Upadki

Rejestr upadków uwzględnia:

- maciory,
- prosięta przed odsadzeniem,
- Prosiaki po odsadzeniu,
- warchlaki,
- tuczniki.

### Pasze i magazyn

Moduł obejmuje:

- składniki pasz,
- dostawy,
- stany magazynowe,
- receptury,
- śrutowanie,
- produkcję pasz,
- gotowe pasze,
- zużycie magazynowe,
- FIFO,
- korekty stanu.

### Sprzedaż

Moduł sprzedaży obsługuje:

- sprzedaż tuczników,
- import dokumentów,
- daty uboju,
- rozliczenia,
- przychody.

### Koszty i opłacalność

Moduł umożliwia:

- rejestr kosztów,
- kategorie kosztów,
- status płatności,
- analizę kosztów pasz,
- analizę sprzedaży,
- obliczanie opłacalności produkcji.

### Centrum zadań

Centrum zadań zbiera między innymi:

- badania USG,
- planowane oproszenia,
- szczepienia,
- niskie stany magazynowe,
- kolejkę śrutowań,
- sprzedaże bez rozliczenia.

---

## Uruchomienie lokalne

### 1. Pobranie projektu

```bash
git clone <adres-repozytorium>
cd managerGospodarstwa
```

### 2. Utworzenie środowiska wirtualnego

```bash
python -m venv .venv
```

Aktywacja na macOS i Linux:

```bash
source .venv/bin/activate
```

Aktywacja na Windows:

```bash
.venv\Scripts\activate
```

### 3. Instalacja zależności

```bash
pip install -r requirements.txt
```

### 4. Konfiguracja `.env`

W katalogu głównym utwórz plik `.env`.

Przykład lokalny:

```env
DEBUG=True
SECRET_KEY=local-development-secret-key
DATABASE_URL=
```

Przy `DEBUG=True` aplikacja korzysta z lokalnej bazy:

```text
db.sqlite3
```

### 5. Migracje

```bash
python manage.py migrate
```

### 6. Konto administratora

```bash
python manage.py createsuperuser
```

### 7. Uruchomienie aplikacji

```bash
python manage.py runserver
```

Aplikacja będzie dostępna pod adresem:

```text
http://127.0.0.1:8000
```

Panel administratora:

```text
http://127.0.0.1:8000/admin
```

---

## Dane demonstracyjne

W środowisku lokalnym można utworzyć dane demonstracyjne:

```bash
python manage.py seed_demo_data
```

Pełny reset lokalnych danych demonstracyjnych:

```bash
python manage.py seed_demo_data --reset
```

Polecenie `--reset` działa wyłącznie przy:

```env
DEBUG=True
```

---

## Testy

Uruchomienie wszystkich testów:

```bash
pytest
```

Sprawdzenie konfiguracji Django:

```bash
python manage.py check
```

Sprawdzenie, czy nie brakuje migracji:

```bash
python manage.py makemigrations --check --dry-run
```

---

## GitHub Actions

Projekt korzysta z trzech głównych workflow.

### Testy

Plik:

```text
.github/workflows/main-tests.yml
```

Workflow uruchamia się przy:

- pull requeście do `main`,
- pushu na `main`,
- uruchomieniu ręcznym.

Wykonuje:

- uruchomienie PostgreSQL 17,
- instalację zależności,
- `python manage.py check`,
- kontrolę brakujących migracji,
- wszystkie testy `pytest`.

### Deployment

Plik:

```text
.github/workflows/deploy-oracle.yml
```

Po poprawnym zakończeniu testów dla gałęzi `main` workflow:

- łączy się przez SSH z Oracle,
- pobiera najnowszy kod,
- instaluje zależności,
- wykonuje migracje,
- wykonuje `collectstatic`,
- restartuje Gunicorna,
- sprawdza dostępność strony produkcyjnej.

Skrypt wdrożeniowy na serwerze:

```text
/usr/local/bin/deploy-manager-gospodarstwa
```

### Backup bazy

Plik:

```text
.github/workflows/database-backup.yml
```

Workflow uruchamia się codziennie oraz ręcznie.

Wykonuje:

- backup PostgreSQL 17 przez `pg_dump`,
- sprawdzenie pliku przez `pg_restore`,
- utworzenie sumy SHA-256,
- zapis w GitHub Artifacts,
- wysłanie kopii do Cloudflare R2,
- usuwanie starych kopii,
- kontrolę liczby plików i rozmiaru bucketa.

Retencja:

```text
GitHub Artifacts:
14 dni

Cloudflare R2:
14 kopii dziennych
4 kopie tygodniowe
6 kopii miesięcznych
```

Każdy backup składa się z:

```text
backup.dump
backup.dump.sha256
```

---

## Produkcyjny `.env`

Przykładowa konfiguracja produkcyjna:

```env
DEBUG=False
SECRET_KEY=wartosc-tajna
DATABASE_URL=wartosc-tajna

ALLOWED_HOSTS=managergospodarstwa.duckdns.org,127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=https://managergospodarstwa.duckdns.org

SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

Nie należy dodawać do repozytorium:

```text
.env
DATABASE_URL
SECRET_KEY
prywatnych kluczy SSH
tokenów Cloudflare
haseł
```

---

## Najważniejsze polecenia produkcyjne

Status aplikacji:

```bash
sudo systemctl status manager-gospodarstwa --no-pager
```

Restart aplikacji:

```bash
sudo systemctl restart manager-gospodarstwa
```

Logi aplikacji:

```bash
sudo journalctl -u manager-gospodarstwa -n 200 --no-pager
```

Status Nginx:

```bash
sudo systemctl status nginx --no-pager
```

Test konfiguracji Nginx:

```bash
sudo nginx -t
```

Test strony:

```bash
curl -I https://managergospodarstwa.duckdns.org
```

Test odnowienia certyfikatu:

```bash
sudo certbot renew --dry-run
```

---

## Ręczne wdrożenie

W razie potrzeby deployment można uruchomić ręcznie na serwerze:

```bash
sudo /usr/local/bin/deploy-manager-gospodarstwa
```

Rollback kodu nie cofa automatycznie migracji bazy danych.

Przed ryzykowną migracją należy ręcznie uruchomić workflow backupu.

---

## Dokumentacja produkcyjna

Krótki opis produkcji, workflow i backupów:

```text
docs/PRODUCTION.md
```

---

## Najważniejsze zasady

- produkcja jest wdrażana wyłącznie z `main`,
- zmiany powinny trafiać do `main` przez pull request,
- testy muszą przejść przed wdrożeniem,
- sekrety nie mogą znajdować się w repozytorium,
- przed ryzykowną migracją należy wykonać backup,
- backupy powinny być okresowo testowane przez odtworzenie,
- rollback kodu nie oznacza rollbacku bazy danych.

---

## Status projektu

Projekt jest aktywnie rozwijany.

Nowe funkcje, zmiany modeli i migracje powinny zachowywać zgodność z istniejącymi danymi produkcyjnymi i nie mogą powodować ich utraty.
