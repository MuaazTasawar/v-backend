import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.development")

app = Celery("venturify")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks(
    [
        "apps.auth_app",
        "apps.profiles",
        "apps.startups",
        "apps.matchmaking",
        "apps.contracts",
        "apps.financials",
        "apps.marketplace",
        "apps.notifications",
        "celery_app",
    ]
)


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")