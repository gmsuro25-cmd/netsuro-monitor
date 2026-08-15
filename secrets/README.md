# Production secrets

Create these files only on the production server:

- `postgres_password.txt`
- `admin_password.txt`
- `slack_webhook_url.txt`

Use one value per file with no labels or quotes. The `*.txt` files in this
directory are ignored by Git. Restrict them to the owner with `chmod 600`.
