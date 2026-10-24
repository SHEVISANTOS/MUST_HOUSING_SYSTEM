# Gunicorn config for the Ubuntu/systemd deployment (not used by Vercel,
# which invokes api/index.py's WSGI app directly). Referenced by
# deploy/vot-house-finding.service via `gunicorn -c deploy/gunicorn.conf.py`.
import multiprocessing

bind = "unix:/run/vot-house-finding/gunicorn.sock"
workers = multiprocessing.cpu_count() * 2 + 1
timeout = 60

# PDF generation (reports, receipts, contracts) renders synchronously and
# can take a few seconds for larger reports - keep the timeout generous
# rather than gunicorn's 30s default, which could clip those requests.

accesslog = "/var/log/vot-house-finding/gunicorn-access.log"
errorlog = "/var/log/vot-house-finding/gunicorn-error.log"
loglevel = "info"
