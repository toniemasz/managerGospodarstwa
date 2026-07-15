```markdown
# Produkcja i automatyzacje

## Produkcja

Aplikacja działa pod adresem:

```text
https://managergospodarstwa.duckdns.org
```

Architektura:

```text
Internet
→ Nginx
→ Gunicorn
→ Django
→ PostgreSQL w Supabase
```

Serwer:

```text
Oracle Cloud
Ubuntu 24.04
```

Kod aplikacji:

```text
/srv/managerGospodarstwa
```

Usługa systemd:

```text
manager-gospodarstwa
```

Najważniejsze polecenia:

```bash
sudo systemctl status manager-gospodarstwa --no-pager
sudo systemctl restart manager-gospodarstwa
sudo journalctl -u manager-gospodarstwa -n 100 --no-pager

sudo systemctl status nginx --no-pager
sudo nginx -t

curl -I https://managergospodarstwa.duckdns.org
```

## Workflow testów

Plik:

```text
.github/workflows/main-tests.yml
```

Workflow uruchamia się po:

```text
pull requeście do main
pushu na main
uruchomieniu ręcznym
```

Wykonuje:

```text
instalację zależności
uruchomienie PostgreSQL 17
python manage.py check
kontrolę brakujących migracji
wszystkie testy pytest
```

Jego celem jest niedopuszczenie błędnej wersji aplikacji do produkcji.

## Workflow wdrożenia

Plik:

```text
.github/workflows/deploy-oracle.yml
```

Uruchamia się po poprawnym zakończeniu workflow testowego dla gałęzi `main`.

Wykonuje:

```text
połączenie SSH z Oracle
uruchomienie skryptu deploymentu
aktualizację kodu z main
instalację zależności
migracje bazy
collectstatic
restart Gunicorna
sprawdzenie strony produkcyjnej
```

Skrypt na serwerze:

```text
/usr/local/bin/deploy-manager-gospodarstwa
```

Ręczne wdrożenie:

```bash
sudo /usr/local/bin/deploy-manager-gospodarstwa
```

## Workflow backupu

Plik:

```text
.github/workflows/database-backup.yml
```

Uruchamia się:

```text
codziennie o 02:15 UTC
lub ręcznie z GitHub Actions
```

Wykonuje:

```text
połączenie z produkcyjną bazą Supabase
backup PostgreSQL 17 przez pg_dump
sprawdzenie backupu przez pg_restore
utworzenie sumy SHA-256
zapis do GitHub Artifacts
wysłanie kopii do Cloudflare R2
usuwanie starych kopii
kontrolę liczby i rozmiaru backupów
```

Retencja:

```text
GitHub Artifacts: 14 dni

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

Plik `.dump` zawiera bazę danych.

Plik `.sha256` służy do sprawdzenia, czy backup nie został uszkodzony.

Ręczne uruchomienie:

```text
GitHub
→ Actions
→ Database backup
→ Run workflow
```

## HTTPS

Certyfikat obsługuje Let's Encrypt i Certbot.

Test odnowienia:

```bash
sudo certbot renew --dry-run
```

W produkcyjnym `.env` powinny być ustawione:

```env
DEBUG=False
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
CSRF_TRUSTED_ORIGINS=https://managergospodarstwa.duckdns.org
```

## Sekrety GitHub

Deployment:

```text
ORACLE_HOST
ORACLE_USER
ORACLE_SSH_KEY_B64
ORACLE_KNOWN_HOSTS
```

Backup:

```text
PRODUCTION_DATABASE_URL
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_ENDPOINT
R2_BUCKET_NAME
```

Nie wolno dodawać do repozytorium:

```text
.env
DATABASE_URL
SECRET_KEY
kluczy SSH
tokenów Cloudflare
```

## Gdy produkcja nie działa

Sprawdź:

```bash
curl -I https://managergospodarstwa.duckdns.org

sudo systemctl status nginx --no-pager
sudo systemctl status manager-gospodarstwa --no-pager

sudo journalctl -u manager-gospodarstwa -n 200 --no-pager

df -h
free -h
```

W razie potrzeby:

```bash
sudo systemctl restart manager-gospodarstwa
sudo systemctl restart nginx
```

## Ważne

```text
Produkcja wdrażana jest tylko z main.
Rollback kodu nie cofa automatycznie migracji bazy.
Przed ryzykowną migracją należy uruchomić ręczny backup.
Backup należy okresowo testować przez odtworzenie do osobnej bazy.
```
