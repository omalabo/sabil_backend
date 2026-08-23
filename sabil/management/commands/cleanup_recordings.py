import os
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from sabil.models import Enregistrement

class Command(BaseCommand):
    help = 'Supprime les traces DB des enregistrements vidéo de plus de 7 jours'

    def handle(self, *args, **kwargs):
        limit_date = timezone.now() - timedelta(days=7)
        old_recordings = Enregistrement.objects.filter(date_creation__lt=limit_date)
        
        count = 0
        for rec in old_recordings:
            # On supprime l'entrée de la base de données
            rec.delete()
            count += 1

        self.stdout.write(self.style.SUCCESS(f'Nettoyage DB terminé : {count} enregistrement(s) supprimé(s).'))
        self.stdout.write(self.style.WARNING('Note : La suppression des fichiers physiques doit être faite via un Cron Job système sur le dossier de volume.'))
