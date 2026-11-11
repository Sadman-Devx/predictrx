from django.apps import AppConfig


class DrugsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.drugs"

    def ready(self):
        from . import signals

        signals.connect()
