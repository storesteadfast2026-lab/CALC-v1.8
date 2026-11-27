# Freight Calculator — Resource and Software Inventory

Review date: 26 November 2026 (Australia/Adelaide).

This inventory supports production operations, maintenance and security monitoring. It records evidence available during the review; it is not a complete software bill of materials or a certification of security. No production configuration was changed as part of the review.

## Evidence and scope

- **Production verified:** directly checked over HTTPS on the review date.
- **Local verified:** observed in the local checkout or running local containers; this does not establish the production configuration.
- **Reported:** supplied in the operator's SSH output during the incident investigation.
- **Historical:** recorded in project documentation and requiring confirmation against the current deployment.
- **Pending:** not independently verified.

Production `/health/` returned HTTP 200 and application version `v1.8.10`. Production `/ready/` returned HTTP 200 with database and migration checks marked `ok`. HTTPS certificate validation passed. These checks do not establish scheduler activity, backup availability, complete schema integrity or the correctness of future Toolkit deployments.

## Resource inventory

| Resource | Purpose | Evidence and current position | Operational checks |
| --- | --- | --- | --- |
| Linux VM `nexus-deployment-vm-1` | Hosts the application containers and persistent storage | Reported in SSH output. Current host OS release and patch level pending. Historical documentation identifies Debian 13. | Host security updates, CPU, memory, disk space, time synchronisation and restricted administrative access. |
| Docker Engine | Runs the web, scheduler, database and SFTP services | Local verified. Production engine version pending. | Supported release, daemon access, restart counts, container limits, image provenance and log retention. |
| Web container `steadfastfreight-038dc4c6` | Serves Django, the administration interface, calculator and manual imports | Container name reported. Production HTTPS endpoints verified at `v1.8.10`. | HTTP readiness, response errors, resource usage and the installed software versions. |
| Scheduler container `steadfastfreight-038dc4c6-ftp-scheduler` | Runs automatic import checks independently of the browser | Reported running during the incident. Local command is `python -u manage.py process_ftp_imports --watch --poll-seconds 60`. Current production activity pending. | Process availability, recent file checks, overdue schedules, repeated errors and restart counts. |
| PostgreSQL container `freight-postgres-test-038dc4c6` | Stores users, schedules, audit records, application configuration and business data | Name and `postgres:16-test` registry tag reported. Production database connectivity verified. The tag does not identify the installed PostgreSQL patch version. | Exact version, connections, capacity, backups, restore tests and restricted network access. |
| SFTP container `freight-sftp-038dc4c6` | Receives externally uploaded source files | Name reported. Its image was identified only by an image ID; software versions pending. | Successful uploads, account access, storage capacity, server updates and restricted network access. |
| Shared FTP inbox | Makes received files available to the application and scheduler | Local verified at `/app/ftp_inbox`, mounted read-only into both application services. Production volume mapping pending. | SFTP and application services must reference the same persistent files. Check visibility, permissions and completed uploads. |
| Uploaded file storage | Retains registered source files and snapshots | Local verified at `/app/uploaded_data`. Production persistence and backup arrangements pending. | Capacity, retention, access permissions and inclusion in recovery procedures. |
| PostgreSQL storage | Persists database contents independently of containers | Local Compose defines `postgres_data`. Production volume and backup locations pending. | Persistent volume mapping, free space and recoverability. A persistent volume alone is not a backup. |
| Toolkit and container registry | Deploy application images and manage services | Reported registry: `registry.adl.au.netoz.au`; application image namespace ends in `freight-calc:v1.8.10`. Toolkit's migration correction has not been independently reviewed. | Matching web/scheduler releases, successful migrations, deployment failure handling, readiness checks and a documented recovery procedure. |
| Reverse proxy | Routes public HTTPS requests to the web service | Historical documentation identifies Caddy. Current version and configuration pending. | Proxy updates, upstream readiness, request limits, access logs and certificate renewal. |
| DNS and domain | Publishes `steadfastfreight.com.au` | Production domain reachable during the review. DNS provider and access ownership pending. | Record accuracy, renewal, change access and service ownership. |
| TLS certificate | Protects public HTTPS traffic | Production verified. Certificate expires on 8 February 2027 in Adelaide time. | Automated renewal and expiry monitoring. Recheck after certificate replacement. |
| Fuel data source | Supplies externally sourced fuel data | Code specifies `https://www.poscat.com.au/fuelsc/fuel.csv`. Current production usage pending. | Availability, freshness and import failures. |
| SMTP service | Sends email when the feature is enabled | Configuration support exists. Production enablement and provider pending. | Delivery failures and provider availability if enabled. |
| External branding images | Supplies some interface images | Templates reference `steadfast.net.au`. | Broken images or external availability; this is a presentation dependency. |
| Container logs and Audit events | Records technical errors and application activity | Implemented locally. Production retention, central collection and alert delivery pending. | Searchable errors, retention, access control and alerts for recurring failures. Database audit records are not evidence of an independently tamper-proof archive. |
| Backup and recovery service | Recovers the database and required files after loss or corruption | No current backup or restoration evidence was verified. | Identify the service, scope, storage location, retention, responsible person and last successful restoration test. |

### Import processing behaviour

SFTP receives files into shared storage. The Django scheduler reads that storage; it does not require an open browser. The local polling interval is 60 seconds, while eligibility depends on the saved schedule, enabled days and retry settings.

In Import Centre, monitor **Scheduled**, **Last FTP check**, **FTP inbox**, **Latest received** and **Operational status** together. A received file or registered snapshot does not, by itself, confirm that its data has been reviewed or activated. An unchanged file can complete successfully by reusing an existing snapshot.

## Software inventory

### Runtime and infrastructure

| Software | Version or reference | Evidence | Production verification required |
| --- | --- | --- | --- |
| Freight Calculator | `v1.8.10` | Production verified through health and readiness endpoints; local verified. | Confirm image identity and matching scheduler release for each deployment. |
| Python | `3.12.16` | Local runtime verified. Dockerfile uses the mutable base tag `python:3.12-slim`. | Exact runtime and base image digest. |
| Container OS | Debian 13 (trixie) | Local runtime verified. | Exact production image OS and package versions. |
| Docker Engine | `29.9.2` | Local host verified. | Production host version. |
| PostgreSQL | `16.15` | Local SQL version verified. | Exact production SQL version; `16-test` is an image tag. |
| Caddy | `2.11.7` | Historical documentation only. | Current version and maintenance status. |
| SFTP server | Not established | Container identified; server implementation and version not verified. | Image provenance, server implementation, version and patch level. |
| Toolkit | Not established | Deployment role identified; code and installed release not reviewed. | Installed version and migration workflow. |

### Direct Python dependencies

The following versions are pinned in `requirements.txt` and were also observed in the local environment. Production installation must be checked separately.

| Package | Pinned version | Purpose |
| --- | --- | --- |
| Django | `5.1.4` | Web framework, administration, authentication and database models. |
| psycopg[binary] | `3.2.3` | PostgreSQL database driver. |
| python-dotenv | `1.0.1` | Configuration loading. |
| openpyxl | `3.1.5` | XLSX workbook processing. |
| xlrd | `2.0.1` | XLS workbook processing. |
| gunicorn | `23.0.0` | Production Python web server. |
| whitenoise | `6.8.2` | Static file serving. |
| django-cors-headers | `4.6.0` | CORS support package; not activated in the reviewed Django configuration. |
| reportlab | `4.4.9` | PDF generation. |

Pillow `13.0.0` was observed as a local transitive dependency. This document does not enumerate all transitive Python dependencies or operating system packages. Neither `defusedxml` nor `lxml` was installed in the reviewed local environment.

