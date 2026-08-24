# PRODUCT-HUNTER

Evergreen Product Hunter is a Flask app for comparing Meta Ad Library product candidates and ranking the strongest evergreen, problem-solving products.

## Render deployment

The repository is ready for Render.

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app --bind 0.0.0.0:$PORT`
- Health check: `/health`

You can deploy with `render.yaml` or create a normal Render Web Service from this repository.

## Local start

```powershell
py -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py app.py
```

Open `http://127.0.0.1:5000`.

## Database note

The app uses SQLite. On Render's normal ephemeral filesystem, saved rankings can reset after a redeploy or instance replacement. If you later add a persistent Render Disk, set the environment variable `DATABASE_PATH` to a path on that disk, for example `/var/data/product_hunter.db`.
