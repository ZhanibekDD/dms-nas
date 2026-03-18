"""
Production server runner using gunicorn (Linux/Mac) or waitress (Windows).
Run from apps/web_admin/:  python serve_prod.py
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_admin.settings")

if sys.platform == "win32":
    from waitress import serve
    from web_admin.wsgi import application
    print("Starting waitress on http://0.0.0.0:8000")
    serve(application, host="0.0.0.0", port=8000, threads=4)
else:
    import subprocess
    subprocess.run([
        "gunicorn", "web_admin.wsgi:application",
        "--bind", "0.0.0.0:8000",
        "--workers", "2",
        "--timeout", "120",
        "--access-logfile", "web_access.log",
    ])
