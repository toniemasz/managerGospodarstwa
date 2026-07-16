# Manager Gospodarstwa

## Opis projektu

Manager Gospodarstwa to aplikacja webowa wspierająca zarządzanie gospodarstwem trzody chlewnej. Łączy ewidencję macior i zdarzeń produkcyjnych z obsługą pasz, magazynu, sprzedaży, kosztów, zadań oraz raportów gospodarstwa.

Główne moduły aplikacji:

- `farms` — gospodarstwo, ustawienia, zadania, audyt, import, eksport i raporty,
- `sows` — maciory, zdarzenia produkcyjne, statusy i szczepienia,
- `feed` — składniki, magazyn, FIFO, receptury, produkcja i podawanie paszy,
- `sales` — sprzedaż tuczników i import rozliczeń PDF,
- `costs` — koszty, płatności i analiza opłacalności.

## Technologie

- **Backend:** Python 3.12, Django 6, Django Templates, Gunicorn
- **Baza danych:** PostgreSQL 17; produkcyjna baza PostgreSQL w Supabase
- **Testy:** pytest, pytest-django, PostgreSQL 17
- **Deployment:** GitHub Actions, Oracle Cloud, Ubuntu, Nginx, Gunicorn/systemd
- **Infrastruktura:** Docker dla lokalnej bazy, WhiteNoise dla plików statycznych, Cloudflare R2 dla kopii zapasowych

## Architektura

Projekt jest modułowym monolitem Django z rozdzielonymi aplikacjami domenowymi.

**Development**

```text
Django → PostgreSQL
```

**Production**

```text
Internet → Nginx → Gunicorn → Django → PostgreSQL (Supabase)
```

## Uruchomienie lokalne

### Start aplikacji lokalnie

Wymagane są Docker oraz zainstalowane zależności projektu. W katalogu głównym utwórz plik `.env`:

```env
DEBUG=True
```

W trybie deweloperskim `SECRET_KEY` ma bezpieczną wartość domyślną przeznaczoną wyłącznie do pracy lokalnej. `DATABASE_URL` jest ustawiany przez skrypt startowy i nie należy wskazywać nim produkcyjnej bazy.

Uruchom aplikację poleceniem:

```bash
./start.sh
```

Skrypt uruchamia PostgreSQL 17.6 w Dockerze, czeka na gotowość bazy, wykonuje migracje, przygotowuje dane demonstracyjne i pliki statyczne, a następnie uruchamia serwer Django. Zatrzymanie skryptu usuwa kontener, ale zachowuje dane w wolumenie Dockera.

## Testy

### Uruchamianie testów

```bash
./test.sh
```

Skrypt uruchamia odizolowany kontener PostgreSQL 17.6 i wykonuje testy pytest. Zestaw obejmuje testy jednostkowe oraz integracyjne procesów domenowych, widoków, uprawnień i izolacji danych gospodarstw. Dodatkowe argumenty można przekazać bezpośrednio do pytest, na przykład `./test.sh feed`.

## GitHub Actions

- [`.github/workflows/tests.yml`](.github/workflows/tests.yml) — uruchamia pełny zestaw testów z PostgreSQL przed merge do `main` oraz po zmianach na `main`.
- [`.github/workflows/deploy-oracle.yml`](.github/workflows/deploy-oracle.yml) — po pomyślnych testach gałęzi `main` automatycznie wdraża aplikację na serwer produkcyjny i sprawdza jej dostępność.
- [`.github/workflows/database-backup.yml`](.github/workflows/database-backup.yml) — codziennie tworzy, weryfikuje i archiwizuje kopię produkcyjnej bazy PostgreSQL.

## Deployment produkcyjny

Aplikacja działa na serwerze Oracle Cloud z Ubuntu. Ruch obsługuje Nginx, aplikację WSGI uruchamia Gunicorn zarządzany przez systemd, a dane są przechowywane w PostgreSQL w Supabase.

Deployment odbywa się automatycznie po pomyślnym zakończeniu testów dla zmian włączonych do `main`. GitHub Actions łączy się z serwerem przez SSH, uruchamia serwerowy skrypt wdrożeniowy, a na końcu wykonuje kontrolę dostępności aplikacji.

## Backup

GitHub Actions codziennie tworzy kopię produkcyjnej bazy PostgreSQL w formacie custom dump, sprawdza ją przez `pg_restore` i zapisuje sumę kontrolną SHA-256. Kopie trafiają do GitHub Artifacts na 14 dni oraz do Cloudflare R2.

Retencja w Cloudflare R2 obejmuje maksymalnie:

- 14 kopii dziennych,
- 4 kopie tygodniowe,
- 6 kopii miesięcznych.

## Development workflow

```text
feature branch
→ Pull Request
→ testy
→ merge do main
→ deployment
```

## Dokumentacja dodatkowa

- [Architektura aplikacji](docs/architecture.md)
- [Planowane usprawnienia](docs/future-upgrades.md)
