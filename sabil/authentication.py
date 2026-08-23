# authentication.py (sabil/authentication.py)
import jwt
from django.conf import settings

# ─────────────────────────────────────────────
# IMPORTS REST FRAMEWORK
# ─────────────────────────────────────────────
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

# ─────────────────────────────────────────────
# IMPORTS SIMPLEJWT (pour tes utilisateurs Django)
# ─────────────────────────────────────────────
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

# ─────────────────────────────────────────────
# IMPORTS MODÈLES
# ─────────────────────────────────────────────
from .models import Users



class CustomJWTAuthentication(JWTAuthentication):
    """
    Comportement identique à JWTAuthentication standard : un compte
    is_active=False est rejeté immédiatement sur CHAQUE requête
    ('User is inactive'), coupure instantanée dès la désactivation.

    UNE SEULE exception : un élève désactivé (role='eleve') est autorisé
    sur les endpoints factures (/api/factures-eleve/...), pour qu'il
    puisse continuer à consulter/payer ses factures. Tout le reste
    (dashboard, classes, diplômes, etc.) reste bloqué pour lui comme
    pour n'importe quel autre compte désactivé.
    """

    # Préfixes d'URL autorisés pour un élève désactivé
    ALLOWED_PATH_PREFIXES_FOR_INACTIVE_ELEVE = (
        '/api/factures-eleve',
    )

    def authenticate(self, request):
        header = self.get_header(request)
        if header is None:
            return None

        raw_token = self.get_raw_token(header)
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        user = self._get_user_ignoring_active(validated_token)

        if not user.is_active:
            path = request.path
            is_eleve_sur_factures = (
                getattr(user, 'role', None) == 'eleve'
                and path.startswith(self.ALLOWED_PATH_PREFIXES_FOR_INACTIVE_ELEVE)
            )
            if not is_eleve_sur_factures:
                # ⛔ Comportement standard restauré : coupure immédiate
                raise AuthenticationFailed('User is inactive', code='user_inactive')

        return user, validated_token

    def _get_user_ignoring_active(self, validated_token):
        user_id = validated_token.get('user_id')
        if user_id is None:
            raise InvalidToken('Token contained no recognizable user identification')

        try:
            return Users.objects.get(id=user_id)
        except Users.DoesNotExist:
            raise AuthenticationFailed('Utilisateur introuvable', code='user_not_found')


class LiveKitWebhookAuthentication(BaseAuthentication):
    """
    Authentifie uniquement les requêtes webhook provenant de LiveKit.
    Vérifie la signature JWT du token fourni par LiveKit avec l'API_SECRET.
    """
    def authenticate(self, request):
        # 1. Récupérer l'en-tête Authorization
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            # Pas de token : on retourne None, DRF gérera l'erreur 401/403 selon les permissions
            return None 

        token = auth_header.split(' ')[1]

        # Récupère le secret depuis les settings Django (ou utilise la valeur en dur en fallback)
        secret = getattr(settings, 'LIVEKIT_API_SECRET', 'secretmyschool2026xK9mP3qR7vL2nW8')

        try:
            # 2. Décoder et vérifier la signature avec l'API Secret de LiveKit
            payload = jwt.decode(
                token,
                secret,
                algorithms=['HS256'] # LiveKit utilise HS256 par défaut
            )
            
            # 3. Vérification de sécurité : s'assurer que c'est bien un payload de webhook LiveKit
            if 'event' not in payload:
                raise AuthenticationFailed('Payload invalide : ce n\'est pas un webhook LiveKit.')

            # 4. Authentification réussie. 
            # On retourne (None, payload) car il n'y a pas d'objet "User" Django associé à ce webhook.
            return (None, payload)

        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Le token du webhook LiveKit a expiré.')
        except jwt.InvalidTokenError:
            raise AuthenticationFailed('Signature du webhook LiveKit invalide.')
