from django.apps import AppConfig


class PubbudgetappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sabil'
    def ready(self):
        import sabil.signals  # ✅ adapte le chemin exact
