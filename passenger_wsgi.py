import glob
import os
import site
import sys
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.environ.get("APP_VENV", os.path.join(BASE_DIR, "venv"))


def _add_venv_site_packages(venv_dir):
    patterns = [
        os.path.join(venv_dir, "lib", "python*", "site-packages"),
        os.path.join(venv_dir, "Lib", "site-packages"),
    ]
    for pattern in patterns:
        for site_packages in glob.glob(pattern):
            if os.path.isdir(site_packages):
                site.addsitedir(site_packages)


sys.path.insert(0, BASE_DIR)
if os.path.isdir(VENV_DIR):
    _add_venv_site_packages(VENV_DIR)

try:
    from wsgi import app as application
except Exception:
    traceback.print_exc()
    raise
