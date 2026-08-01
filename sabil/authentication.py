# authentication.py (sabil/authentication.py)
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed
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