from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from sabil.models import Enregistrements  # ⚠️ Adapte le nom de ton app


class Command(BaseCommand):
    help = 'Supprime les enregistrements vidéo de plus de 7 jours (soft delete)'

    def handle(self, *args, **kwargs):
        limit_date = timezone.now() - timedelta(days=7)
        
        old_recordings = Enregistrements.objects.filter(
            started_at__lt=limit_date,
            deleted_at__isnull=True
        )
        
        count = 0
        for rec in old_recordings:
            rec.deleted_at = timezone.now()
            rec.statut = 'supprime'  # ← Ton enum existant
            rec.save()
            count += 1
            self.stdout.write(self.style.SUCCESS(
                f'Soft delete : {rec.id} - classe {rec.classe_id}'
            ))

        self.stdout.write(self.style.SUCCESS(
            f'Nettoyage terminé : {count} enregistrement(s) marqué(s) comme supprimé.'
        ))
