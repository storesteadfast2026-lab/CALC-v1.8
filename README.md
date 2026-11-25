# CALC v1.8

Clean rebuild baseline for Steadfast Australia's freight estimating application.
The current implementation preserves useful, tested Django modules from v1.7
without copying its database, uploaded operational files, generated static files,
reports or embedded FTP credentials.

## Application version and Toolkit deployment

`app/VERSION` is the single source of truth for the application release. The
current format is `v<major>.<minor>.<two-digit release>`, for example
`v1.8.01`. Releases advance from `v1.8.01` through `v1.8.99`; the next release
is `v1.9.00`.

After completing and testing a change, increment the version once:

```powershell
.\tools\Increment-Version.ps1
```

Image creation, upload, publication and deployment are all performed through
Toolkit. `app/VERSION` is the value Toolkit must use as the release/image tag.
The same tag must be assigned to both the `web` and `ftp_scheduler` containers.
Do not deploy or recreate the `db` container for an application-only release.

Toolkit must not generate a separate version number. If its build configuration
cannot read `app/VERSION` automatically, copy the exact value from that file
into Toolkit's version/tag field before starting the build.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app\manage.py migrate
python app\manage.py setup_access_roles
python app\manage.py createsuperuser
python app\manage.py runserver
```

Local development uses `app/calc.sqlite3` by default. Open
`http://127.0.0.1:8000/health/` for a health check and `/admin/` for setup.

## Docker setup

Copy `.env.example` to `.env`, replace the secrets, then run:

```powershell
docker compose up --build
```

Docker publishes the app on `http://127.0.0.1:8018/` by default and uses
PostgreSQL internally. Set `CALC_PORT` in `.env` to choose another host port.
No FTP server is bundled; operational source delivery
must be configured separately so credentials and network addresses are not stored
in this repository.

## Daily FTP file registration

An external SFTP service deposits completed files in the dedicated `ftp_inbox`.
The `web` and `ftp_scheduler` containers mount that inbox read-only at
`/app/ftp_inbox`; immutable application snapshots remain separately under
`/app/uploaded_data`. Django
Admin exposes one **Imports → Import Centre** screen for the shared schedule,
enabled files, individual manual uploads, immediate FTP inbox checks and recent
import review. Every due run processes all enabled client/file mappings together.
The initial schedule is 08:00 Australia/Adelaide, Monday to Friday; its days,
time and retry interval can be changed in Admin.

For safe delivery, upload with a temporary filename and rename it to the final
configured filename only after the transfer is complete. The scheduler runs in
the `ftp_scheduler` Docker service. A single due-check can also be run with:

```powershell
docker compose exec web python manage.py process_ftp_imports
```

Registration stores an immutable, SHA-256-deduplicated `ExternalDataFile`
snapshot and audit event. It does **not** validate, Apply or activate Products,
Fuel, Rates, Zones, Stock or Suburbs; those existing controlled Django workflows
remain separate. FTP server addresses and credentials are intentionally not
managed by this feature.

Toolkit must map the SFTP account's `/uploads` directory and the application
`/app/ftp_inbox` directory to the same persistent volume. SFTP needs write
access; `web` and `ftp_scheduler` must receive the same volume read-only. Do not
mount `/app/uploaded_data` into the SFTP container. Do not publish the Django,
database, Docker API, Redis, or printer ports publicly. Public port 2222 should
be retained only when SFTP is required and protected with an authenticated,
chrooted, no-shell account; ports 80/443 are reserved for the web proxy.

## Import Centre navigation

Import Centre shows each file's business name and exact filename. **Open latest
file** opens the most recent received copy; **File history** lists saved copies.
The shared Products and Stock header identifies the filename, snapshot and file
status, with buttons back to Import Centre and file history. SHA-256 and upload
details are available under **Technical details**.

Products has **Summary**, **File rows (preview)** and **Compare with customer
products** tabs. Its row preview is the saved validation sample, not every row
in the workbook. Stock has **Summary**, **File rows** and **Compare with Products
file** tabs. Existing filters, pagination and customer comparison controls remain
available in their respective views. Viewing source rows or the global Stock /
Products comparison does not change operational data. Existing explicit review,
import and activation actions retain their permissions and behaviour.

## Operational procedure test

Run the quote procedure against 100 unique historical destinations without
changing the database or treating price differences as failures:

```powershell
docker compose exec web python manage.py run_operational_quote_tests --client STH --locations 100
```

The default source is
`/app/uploaded_data/Aditional Data for check/_current.xls`. Use `--source` for
another dispatch workbook and `--client` for another active calculator customer.
JSON, CSV and Markdown reports are written to
`reports/operational_tests`. The primary outcome is `QUOTED_COMPLETE` when at
least one complete result is available, `QUOTED_PROVISIONAL` when every result
is provisional, `NOT_QUOTED` when no quote result is available, or `FAILED`
when execution or a calculation invariant fails. The independent
`review_required` flag preserves postcode ambiguity, provisional charges,
failed checks and operational source warnings without obscuring whether the
destination was quoted.

## Safety boundary

- Imported data is versioned and must never silently fall back to the workbook.
- Unknown required charges are not treated as zero.
- Customer access is enforced in backend services.
- No production rate, zone, fuel, customer or estimate data is included.
- The inherited engine remains an alpha baseline until it is verified against
  complete TransLogic examples and the acceptance criteria in `docs/APP PLAN.md`.
