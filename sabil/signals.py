# signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Notifications
from .views import send_expo_push_notification  # ou depuis utils.py si tu l'y déplaces


@receiver(post_save, sender=Notifications)
def notify_push_on_create(sender, instance, created, **kwargs):
    if not created:
        return  # on ignore les updates (ex: passage à lu=True)

    user = instance.destinataire
    if not user or not getattr(user, 'expo_push_token', None):
        return  # utilisateur sans token enregistré → on ignore silencieusement

    send_expo_push_notification(
        expo_token=user.expo_push_token,
        title=instance.titre,
        body=instance.contenu or '',
        target_url=instance.lien or '',
    )
