# Wdrożenie produkcyjne, CI/CD, backupy i monitoring

Dokument opisuje aktualną konfigurację produkcyjną projektu **Manager Gospodarstwa** oraz procedury wdrażania, wykonywania kopii zapasowych, przywracania danych i diagnostyki.

> Dokument nie zawiera haseł, tokenów, kluczy prywatnych ani pełnych adresów połączeń do bazy. Sekrety należy przechowywać wyłącznie w `.env`, GitHub Actions Secrets albo dedykowanym menedżerze sekretów.

---

## 1. Architektura produkcyjna

```text
Użytkownik
   |
   v
managergospodarstwa.duckdns.org
   |
   v
Nginx :80 / :443
   |
   v
Gunicorn 127.0.0.1:8000
   |
   v
Django
   |
   v
Supabase PostgreSQL 17
```

Aktualne elementy środowiska:

- Oracle Cloud Always Free,
- Ubuntu 24.04,
- Nginx,
- Gunicorn,
- systemd,
- Django,
- Supabase PostgreSQL 17,
- DuckDNS,
- Let's Encrypt i Certbot,
- GitHub Actions,
- Cloudflare R2.

### Publiczne porty

```text
22  SSH
80  HTTP, tylko przekierowanie na HTTPS
443 HTTPS
```

Gunicorn nasłuchuje wyłącznie lokalnie:

```text
127.0.0.1:8000
```

Port Gunicorna nie może być wystawiony publicznie.

---

## 2. Adres produkcyjny i HTTPS

Adres aplikacji:

```text
https://managergospodarstwa.duckdns.org
```

Sprawdzenie przekierowania HTTP:

```bash
curl -I http://managergospodarstwa.duckdns.org
```

Oczekiwany wynik:

```text
301 Moved Permanently
Location: https://managergospodarstwa.duckdns.org/
```

Sprawdzenie HTTPS:

```bash
curl -I https://managergospodarstwa.duckdns.org
```

Kod `302` do strony logowania jest poprawną odpowiedzią aplikacji.

### Certyfikat TLS

Certyfikat obsługuje Certbot i Let's Encrypt.

Test odnowienia:

```bash
sudo certbot renew --dry-run
```

Status timera:

```bash
systemctl status certbot.timer --no-pager
```

---

## 3. Konfiguracja Django w produkcji

Plik `.env` znajduje się poza repozytorium.

Najważniejsze ustawienia:

```env
DEBUG=False
ALLOWED_HOSTS=managergospodarstwa.duckdns.org,127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=https://managergospodarstwa.duckdns.org
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECRET_KEY=***
DATABASE_URL=***
```

Nigdy nie należy:

- commitować `.env`,
- wpisywać sekretów bezpośrednio do workflow,
- publikować pełnego `DATABASE_URL`,
- wklejać kluczy prywatnych do issue, logów ani dokumentacji.

---

## 4. Usługi systemowe

### Gunicorn

Usługa:

```text
manager-gospodarstwa.service
```

Status:

```bash
sudo systemctl status manager-gospodarstwa --no-pager
```

Restart:

```bash
sudo systemctl restart manager-gospodarstwa
```

Logi:

```bash
sudo journalctl -u manager-gospodarstwa -n 200 --no-pager
sudo journalctl -u manager-gospodarstwa -f
```

### Nginx

Test konfiguracji:

```bash
sudo nginx -t
```

Status i przeładowanie:

```bash
sudo systemctl status nginx --no-pager
sudo systemctl reload nginx
```

Logi:

```bash
sudo tail -n 200 /var/log/nginx/error.log
sudo tail -n 200 /var/log/nginx/access.log
```

---

## 5. Użytkownik wdrożeniowy

Automatyczne wdrożenia korzystają z osobnego użytkownika:

```text
deploy
```

Użytkownik `deploy`:

- loguje się kluczem SSH,
- korzysta z osobnego klucza przeznaczonego dla GitHub Actions,
- może uruchomić przez `sudo` tylko skrypt deploymentu,
- nie powinien posiadać pełnych praw administratora.

Klucze publiczne:

```text
/home/deploy/.ssh/authorized_keys
```

Wymagane uprawnienia:

```bash
sudo chmod 700 /home/deploy/.ssh
sudo chmod 600 /home/deploy/.ssh/authorized_keys
sudo chown -R deploy:deploy /home/deploy/.ssh
```

Reguła sudoers:

```text
/etc/sudoers.d/manager-gospodarstwa-deploy
```

Zawartość:

```text
deploy ALL=(root) NOPASSWD: /usr/local/bin/deploy-manager-gospodarstwa
```

Walidacja:

```bash
sudo chmod 440 /etc/sudoers.d/manager-gospodarstwa-deploy
sudo visudo -c
```

---

## 6. Skrypt wdrożeniowy

Ścieżka:

```text
/usr/local/bin/deploy-manager-gospodarstwa
```

Skrypt wykonuje:

1. blokadę równoległych wdrożeń przez `flock`,
2. pobranie najnowszego `main`,
3. zapis aktualnego commita,
4. instalację zależności,
5. `manage.py check`,
6. kontrolę brakujących migracji,
7. `manage.py migrate`,
8. `collectstatic`,
9. restart usługi,
10. healthcheck strony,
11. rollback kodu po błędzie.

Ręczne uruchomienie:

```bash
sudo /usr/local/bin/deploy-manager-gospodarstwa
```

### Ograniczenie rollbacku

Rollback cofa kod, ale nie może bezpiecznie cofnąć każdej migracji bazy.

Migracje produkcyjne powinny być:

- kompatybilne wstecznie,
- niedestrukcyjne w pierwszym wdrożeniu,
- poprzedzone backupem przy ryzykownych zmianach,
- testowane na PostgreSQL 17,
- wykonywane etapami przy usuwaniu pól lub zmianie typów danych.

Bezpieczny schemat:

1. dodać nowe pole lub tabelę,
2. wdrożyć kod obsługujący stary i nowy stan,
3. przenieść dane,
4. dopiero w kolejnym wdrożeniu usunąć stare pole.

---

## 7. CI/CD

### Testy

Workflow testowy znajduje się w `.github/workflows/` i uruchamia się przy:

- pull requeście do `main`,
- pushu do `main`,
- ręcznym `workflow_dispatch`.

Testy korzystają z PostgreSQL 17 i wykonują m.in.:

- instalację zależności,
- sprawdzenie połączenia z bazą,
- `manage.py check`,
- `makemigrations --check --dry-run`,
- pełny zestaw `pytest`.

### Automatyczne wdrożenie

Workflow:

```text
.github/workflows/deploy-oracle.yml
```

Proces:

```text
develop
   |
   v
Pull Request do main
   |
   v
GitHub Actions - testy
   |
   v
merge do main
   |
   v
Deploy to Oracle
   |
   v
SSH jako deploy
   |
   v
/usr/local/bin/deploy-manager-gospodarstwa
```

### Sekrety deploymentu

```text
ORACLE_HOST
ORACLE_USER
ORACLE_SSH_KEY_B64
ORACLE_KNOWN_HOSTS
```

Znaczenie:

- `ORACLE_HOST` - adres instancji,
- `ORACLE_USER` - `deploy`,
- `ORACLE_SSH_KEY_B64` - prywatny klucz wdrożeniowy bez hasła, zapisany jako Base64,
- `ORACLE_KNOWN_HOSTS` - przypięty klucz hosta SSH.

Klucz używany przez workflow nie może wymagać interaktywnego hasła.

Ręczne uruchomienie:

```text
GitHub -> Actions -> Deploy to Oracle -> Run workflow
```

### Diagnostyka deploymentu

`Permission denied (publickey)`:

- sprawdzić `authorized_keys`,
- sprawdzić właściwy klucz prywatny w sekretach,
- sprawdzić, czy klucz nie ma hasła,
- sprawdzić `ORACLE_USER=deploy`,
- sprawdzić uprawnienia `.ssh`.

`fatal: detected dubious ownership`:

```bash
sudo git config --system --add safe.directory /srv/managerGospodarstwa
```

---

## 8. Automatyczne backupy bazy

Workflow:

```text
.github/workflows/database-backup.yml
```

Backup uruchamia się:

- codziennie przez `cron`,
- ręcznie przez `workflow_dispatch`.

Źródło:

```text
Supabase PostgreSQL 17
```

Do dumpa używana jest pełna ścieżka:

```text
/usr/lib/postgresql/17/bin/pg_dump
```

Zapobiega to przypadkowemu użyciu starszego klienta PostgreSQL dostępnego na runnerze.

### Pliki backupu

Właściwa kopia:

```text
manager-gospodarstwa_YYYY-MM-DD_HH-MM-SS_UTC.dump
```

Suma kontrolna:

```text
manager-gospodarstwa_YYYY-MM-DD_HH-MM-SS_UTC.dump.sha256
```

Plik `.sha256` nie jest drugim backupem. Służy do wykrywania uszkodzenia albo zmiany pliku `.dump`.

---

## 9. GitHub Artifacts

Backup jest zapisywany jako GitHub Actions Artifact przez:

```text
14 dni
```

Lokalizacja:

```text
GitHub -> Actions -> Database backup -> konkretne uruchomienie -> Artifacts
```

Artifact zawiera:

- `.dump`,
- `.dump.sha256`.

Artifact jest kopią krótkoterminową i nie powinien być jedyną lokalizacją backupu.

---

## 10. Cloudflare R2

Bucket:

```text
manager-gospodarstwa-backups
```

Bucket pozostaje prywatny. Nie należy włączać publicznego `r2.dev`.

Struktura:

```text
daily/
weekly/
monthly/
```

Retencja:

```text
daily   - 14 najnowszych kopii
weekly  - 4 najnowsze kopie
monthly - 6 najnowszych kopii
```

Każdej kopii `.dump` odpowiada `.dump.sha256`.

Workflow usuwa starsze pliki po przekroczeniu limitu liczby kopii.

### Limit bezpieczeństwa

Workflow kontroluje rozmiar bucketa i zgłasza błąd po przekroczeniu:

```text
5 GB
```

To zabezpieczenie w workflow, a nie twardy limit rozliczeniowy po stronie Cloudflare.

### Sekrety backupu

```text
PRODUCTION_DATABASE_URL
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_ENDPOINT
R2_BUCKET_NAME
```

Token R2 powinien mieć dostęp wyłącznie do `manager-gospodarstwa-backups` i uprawnienia Object Read & Write.

---

## 11. Ręczne uruchomienie backupu

```text
GitHub -> Actions -> Database backup -> Run workflow
```

Po zmianie workflow należy uruchomić nowy run, a nie `Re-run failed jobs`, ponieważ stary run może korzystać ze starej wersji pliku.

Po wykonaniu sprawdzić:

1. zielony status,
2. obecność Artifactu,
3. plik w `daily/` w R2,
4. obecność `.dump` i `.dump.sha256`,
5. poprawny licznik kopii,
6. rozmiar bucketa poniżej 5 GB.

---

## 12. Sprawdzenie SHA-256

Linux:

```bash
sha256sum --check nazwa_pliku.dump.sha256
```

macOS:

```bash
shasum -a 256 -c nazwa_pliku.dump.sha256
```

Oczekiwany wynik:

```text
nazwa_pliku.dump: OK
```

Przy niezgodnej sumie nie należy używać pliku do restore.

---

## 13. Przywracanie backupu

> Przywracanie produkcyjnej bazy jest operacją wysokiego ryzyka. Najpierw wykonać aktualny backup i przetestować restore na osobnej bazie.

Kontrola zawartości:

```bash
/usr/lib/postgresql/17/bin/pg_restore --list backup.dump
```

Przykład odtworzenia do pustej bazy testowej:

```bash
pg_restore \
  --dbname="postgresql://USER:PASSWORD@HOST:PORT/TEST_DATABASE" \
  --no-owner \
  --no-acl \
  --clean \
  --if-exists \
  backup.dump
```

`--clean` usuwa istniejące obiekty w bazie docelowej. Nie wolno używać go na produkcji bez świadomej decyzji.

Zalecana procedura:

1. pobrać `.dump` i `.sha256`,
2. sprawdzić SHA-256,
3. utworzyć pustą bazę testową,
4. wykonać restore,
5. uruchomić zapytania kontrolne,
6. podłączyć lokalnie aplikację do odtworzonej bazy,
7. sprawdzić logowanie i główne moduły,
8. dopiero potem planować restore produkcji.

---

## 14. Typowe błędy backupu

### `server version mismatch`

```text
server version: 17.x; pg_dump version: 16.x
```

Rozwiązanie:

```text
/usr/lib/postgresql/17/bin/pg_dump
/usr/lib/postgresql/17/bin/pg_restore
```

### `gpg: cannot open /dev/tty`

Instalacja klucza repozytorium PostgreSQL musi działać nieinteraktywnie:

```bash
gpg --batch --yes --dearmor ...
```

### `invalid type for value: None`

Pusty prefiks R2 może zwrócić `Contents=null`. Skrypt musi traktować to jako zero plików i filtrować `None`.

### Błąd dostępu do R2

Sprawdzić:

- `R2_ACCESS_KEY_ID`,
- `R2_SECRET_ACCESS_KEY`,
- `R2_ENDPOINT`,
- `R2_BUCKET_NAME`,
- zakres tokenu,
- uprawnienia Object Read & Write,
- format endpointu `https://ACCOUNT_ID.r2.cloudflarestorage.com`.

### Brak `weekly/` albo `monthly/`

To jest poprawne, gdy:

- nie jest niedziela dla kopii tygodniowej,
- nie jest pierwszy dzień miesiąca dla kopii miesięcznej.

Kopia dzienna powstaje przy każdym poprawnym uruchomieniu.

---

## 15. Checklista po wdrożeniu

```text
[ ] Testy GitHub Actions są zielone
[ ] Deploy to Oracle jest zielony
[ ] HTTPS odpowiada
[ ] Logowanie działa
[ ] manager-gospodarstwa.service jest active
[ ] nginx.service jest active
[ ] Brak nowych błędów 500
[ ] Migracje zakończyły się poprawnie
[ ] Pliki statyczne działają
```

Polecenia:

```bash
sudo systemctl is-active manager-gospodarstwa
sudo systemctl is-active nginx
curl -I https://managergospodarstwa.duckdns.org/login/
sudo journalctl -u manager-gospodarstwa -n 100 --no-pager
```

---

## 16. Checklista awaryjna

### Strona nie odpowiada

1. sprawdzić status instancji Oracle,
2. sprawdzić DuckDNS,
3. sprawdzić Nginx,
4. sprawdzić Gunicorn,
5. sprawdzić logi,
6. sprawdzić miejsce na dysku,
7. sprawdzić połączenie z Supabase.

```bash
sudo systemctl status nginx --no-pager
sudo systemctl status manager-gospodarstwa --no-pager
sudo nginx -t
df -h
free -h
sudo journalctl -u manager-gospodarstwa -n 200 --no-pager
sudo tail -n 200 /var/log/nginx/error.log
```

### Błąd po wdrożeniu

1. sprawdzić log workflow,
2. sprawdzić commit na serwerze,
3. sprawdzić usługę,
4. uruchomić skrypt deploymentu ręcznie,
5. nie cofać migracji w ciemno,
6. zatrzymać kolejne wdrożenia przy podejrzeniu utraty danych,
7. zabezpieczyć najnowszy backup.

```bash
cd /srv/managerGospodarstwa
git rev-parse HEAD
git status
```

### Podejrzenie uszkodzenia danych

1. nie wykonywać kolejnych migracji,
2. wykonać aktualny backup, jeśli baza odpowiada,
3. pobrać ostatnią poprawną kopię,
4. sprawdzić SHA-256,
5. odtworzyć na bazie testowej,
6. porównać dane,
7. dopiero potem podejmować decyzję o restore produkcji.

---

## 17. Monitoring i bezpieczeństwo - do wdrożenia

Poniższe elementy są rekomendowane, ale nie są jeszcze potwierdzone jako skonfigurowane.

### Monitoring dostępności

Rekomendowane:

- UptimeRobot,
- Better Stack.

Monitorowany adres:

```text
https://managergospodarstwa.duckdns.org/login/
```

Alerty:

- brak odpowiedzi,
- kod 5xx,
- długi czas odpowiedzi,
- problem z HTTPS,
- wygasający certyfikat.

### Monitoring błędów Django

Rekomendowane:

```text
Sentry
```

Monitorować:

- wyjątki,
- błędy 500,
- stack trace,
- wersję wdrożenia,
- miejsce błędu.

Nie wysyłać do Sentry:

- haseł,
- tokenów,
- wartości `.env`,
- pełnego `DATABASE_URL`,
- danych wrażliwych.

### Fail2ban

Do skonfigurowania dla SSH i prób brute force.

Po wdrożeniu:

```bash
sudo systemctl status fail2ban --no-pager
sudo fail2ban-client status
```

### Automatyczne aktualizacje

Rekomendowane:

```text
unattended-upgrades
```

Należy kontrolować aktualizacje bezpieczeństwa i wymagane restarty.

### Alarmy Oracle Cloud

Rekomendowane metryki:

- CPU,
- dostępność instancji,
- dysk,
- pamięć i swap, jeśli agent je raportuje,
- restart lub zatrzymanie instancji.

Przykładowe progi:

```text
CPU > 85% przez kilka minut
Dysk > 80%
Dysk krytyczny > 90%
```

### Audyt SSH

Docelowo:

```text
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
```

Zmiany SSH wdrażać ostrożnie, pozostawiając aktywną sesję do potwierdzenia nowego logowania.

---

## 18. Rotacja sekretów

Sekrety wymienić, gdy:

- zostały opublikowane,
- pojawiły się w logach,
- klucz prywatny opuścił bezpieczne miejsce,
- osoba z dostępem przestała współpracować,
- istnieje podejrzenie nieautoryzowanego dostępu.

Po rotacji zaktualizować:

- GitHub Actions Secrets,
- `authorized_keys`,
- token R2,
- hasło lub connection string bazy,
- zmienne na serwerze.

Stary klucz lub token należy unieważnić.

---

## 19. Pliki w repozytorium i poza nim

W repozytorium:

```text
.github/workflows/deploy-oracle.yml
.github/workflows/database-backup.yml
docs/PRODUCTION_DEPLOYMENT_AND_BACKUPS.md
```

Poza repozytorium:

```text
/srv/managerGospodarstwa/.env
/usr/local/bin/deploy-manager-gospodarstwa
/etc/systemd/system/manager-gospodarstwa.service
/etc/nginx/sites-available/manager-gospodarstwa
/etc/sudoers.d/manager-gospodarstwa-deploy
/home/deploy/.ssh/authorized_keys
/etc/letsencrypt/
```

Sekrety GitHub nie są częścią repozytorium.

---

## 20. Minimalna procedura utrzymania

Codziennie automatycznie:

- testy przy zmianach,
- deployment po poprawnym merge do `main`,
- backup bazy,
- GitHub Artifact,
- Cloudflare R2,
- kontrola retencji i rozmiaru.

Raz w tygodniu:

- sprawdzić ostatni backup,
- sprawdzić ostatni deployment,
- przejrzeć błędy,
- sprawdzić wolne miejsce.

Raz w miesiącu:

- pobrać backup,
- sprawdzić SHA-256,
- odtworzyć na testowej bazie,
- sprawdzić aplikację,
- przejrzeć klucze SSH,
- sprawdzić aktualizacje bezpieczeństwa.

---

## 21. Zasada nadrzędna

Backup jest wiarygodny dopiero wtedy, gdy:

1. powstał bez błędów,
2. ma poprawną sumę SHA-256,
3. `pg_restore --list` odczytuje zawartość,
4. został odtworzony testowo,
5. aplikacja działa na odtworzonej bazie.

Samo istnienie pliku `.dump` nie gwarantuje możliwości odzyskania danych.
