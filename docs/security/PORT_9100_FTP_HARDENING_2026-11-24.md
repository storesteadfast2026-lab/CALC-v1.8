# Port 9100 and FTP inbox hardening — 24 Nov 2026

## Verified observations

- The application Compose file publishes only the configurable Django port; it
  contains no port 9100 mapping.
- The production host did not accept a TCP connection on port 9100 during the
  external check on 24 Nov 2026.
- Public SFTP on port 2222 accepted a TCP connection and therefore remains part
  of the exposed production surface.
- FileZilla showed `products.xls` in `/uploads`, while Import Centre reported
  that `products.xls` was not found. This proves that the filename is correct
  but does not prove that the current application containers see the same
  persistent volume.

## Required Toolkit layout

1. Use one dedicated persistent volume for the FTP inbox.
2. Mount it read/write as `/uploads` in the SFTP container.
3. Mount the same volume read-only as `/app/ftp_inbox` in both `web` and
   `ftp_scheduler`.
4. Set `FTP_UPLOADED_DATA_DIR=/app/ftp_inbox` in both application containers.
5. Keep `/app/uploaded_data` private to the application. Never mount it in the
   SFTP container.
6. Do not publish port 9100 or internal application/database ports.
7. Keep port 2222 only if SFTP is required. Use an authenticated, chrooted,
   no-shell account and disable anonymous access.

## Toolkit verification after deployment

Run this read-only check in both `web` and `ftp_scheduler`:

```sh
python manage.py shell -c "from django.conf import settings; from pathlib import Path; p=Path(settings.FTP_UPLOADED_DATA_DIR); f=p/'products.xls'; print(p); print(f.exists(), f.stat().st_size if f.exists() else 0)"
```

Both containers must print `/app/ftp_inbox` and `True` before using **Process
from FTP**. Import Centre also displays the configured inbox and whether each
expected file is visible to the application.
