from rest_framework import viewsets, permissions, generics,status, serializers, parsers, filters
from rest_framework.response import Response
import os
from rest_framework.decorators import action, api_view, permission_classes,authentication_classes
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth.hashers import make_password, check_password
from django.db import transaction, models
from django.utils import timezone
from django.conf import settings
from datetime import timedelta, datetime, time, date
import uuid, logging
import re
import jwt
import secrets
from .models import *
from .serializers import *
from rest_framework_simplejwt.tokens import RefreshToken
logger = logging.getLogger(__name__)
from livekit import api  # ← Nouveau package LiveKit
# Clés API LiveKit (à mettre dans settings.py ou .env)
LIVEKIT_API_KEY = os.getenv('LIVEKIT_API_KEY', 'APImyschool2026')
LIVEKIT_API_SECRET = os.getenv('LIVEKIT_API_SECRET', 'secretmyschool2026xK9mP3qR7vL2nW8')
LIVEKIT_URL = os.getenv('LIVEKIT_URL', 'wss://live.sabil-al-ilm.org')

from rest_framework.exceptions import PermissionDenied
from django.db.models.functions import TruncDate, Cast


from django.db.models import Exists, OuterRef, Sum, F, Case, When, Value, IntegerField, FloatField,Count, F, Q,Prefetch, DecimalField
import mimetypes
from django.http import FileResponse, Http404, JsonResponse
from django.core.files.storage import default_storage
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from decimal import Decimal,ROUND_HALF_UP
 
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.cache import cache

from django.utils.timezone import localdate

from django_filters.rest_framework import DjangoFilterBackend
import calendar

from dateutil.relativedelta import relativedelta


from .billing_rules import calculer_tarifs

from sabil.authentication import CustomJWTAuthentication  


 
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail
from rest_framework.throttling import AnonRateThrottle
import random

from django.shortcuts import get_object_or_404
from django.core.files.base import ContentFile
from django.views.decorators.csrf import csrf_exempt
from livekit.api import TokenVerifier, WebhookReceiver
from sabil.authentication import LiveKitWebhookAuthentication
from rest_framework.permissions import AllowAny

# ... (tes constantes LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)




import asyncio

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_recording(request, classe_id):
    classe = get_object_or_404(Classes, id=classe_id)
    today = timezone.now().date()

    derniere_presence = Presences.objects.filter(
        classe=classe, date_seance=today
    ).order_by('-heure_connexion').first()

    room_name = derniere_presence.jitsi_room_id if derniere_presence else None
    if not room_name:
        return Response({"error": "Aucune session active trouvée pour cette classe."}, status=400)

    async def _run():
        lkapi = api.LiveKitAPI(LIVEKIT_URL, api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
        try:
            res = await lkapi.egress.list_egress(
                api.ListEgressRequest(room_name=room_name)
            )
            actifs = [e for e in res.items if e.status == api.EgressStatus.EGRESS_ACTIVE]

            if actifs:
                stopped_ids = []
                for e in actifs:
                    await lkapi.egress.stop_egress(
                        api.StopEgressRequest(egress_id=e.egress_id)
                    )
                    stopped_ids.append(e.egress_id)
                return {"action": "stopped", "egress_ids": stopped_ids}

            # ── Démarrer l'audio ──
            timestamp = int(datetime.now().timestamp())
            filename = f"audio_{classe_id}_{timestamp}.ogg"
            req_audio = api.RoomCompositeEgressRequest(
                room_name=room_name,
                audio_only=True,
                file_outputs=[api.EncodedFileOutput(
                    file_type=api.EncodedFileType.OGG,
                    filepath=f"/recordings/{filename}",
                )]
            )
            info_audio = await lkapi.egress.start_room_composite_egress(req_audio)

            resultats = [{"type": "audio", "egress_id": info_audio.egress_id, "filename": filename}]

            # ── NOUVEAU : rattraper un écran déjà partagé ──
            participants = await lkapi.room.list_participants(
                api.ListParticipantsRequest(room=room_name)
            )
            for p in participants.participants:
                for t in p.tracks:
                    if t.source == api.TrackSource.SCREEN_SHARE:
                        ts = int(datetime.now().timestamp())
                        screen_filename = f"screen_{classe_id}_{ts}.webm"
                        req_screen = api.TrackEgressRequest(
                            room_name=room_name,
                            track_id=t.sid,
                            file=api.DirectFileOutput(filepath=f"/recordings/{screen_filename}")
                        )
                        info_screen = await lkapi.egress.start_track_egress(req_screen)
                        resultats.append({
                            "type": "screen",
                            "egress_id": info_screen.egress_id,
                            "filename": screen_filename
                        })

            return {"action": "started", "jobs": resultats}
        finally:
            await lkapi.aclose()

    try:
        result = asyncio.run(_run())
    except Exception as e:
        print(f"❌ Erreur LiveKit Egress (classe {classe_id}): {str(e)}")
        return Response({"error": "Impossible de gérer l'enregistrement.", "details": str(e)}, status=500)

    if result["action"] == "stopped":
        Enregistrements.objects.filter(
            egress_id__in=result["egress_ids"], deleted_at__isnull=True
        ).update(statut='termine', ended_at=timezone.now())
        return Response({"status": "stopped", "message": "Enregistrement arrêté. Les fichiers seront disponibles sous peu."})
    else:
        derniere_seance = Seances.objects.filter(classe=classe).order_by('-created_at').first()
        for job in result["jobs"]:
            Enregistrements.objects.create(
                classe=classe,
                seance=derniere_seance,
                demarre_par=request.user,
                egress_id=job["egress_id"],
                url_video=job["filename"],
                statut='en_cours'
            )
        nb_screens = sum(1 for j in result["jobs"] if j["type"] == "screen")
        msg = "Enregistrement audio démarré."
        if nb_screens:
            msg += f" {nb_screens} partage(s) d'écran déjà actif(s) capté(s) automatiquement."
        msg += " Tout nouveau partage d'écran sera aussi enregistré automatiquement."
        return Response({"status": "started", "jobs": result["jobs"], "message": msg})



# ──────────────────────────────────────────────────────────────
# 2. WEBHOOK LIVEKIT (Reçoit la fin de l'enregistrement)
# ──────────────────────────────────────────────────────────────
def get_classe_from_room(room_name):
    presence = Presences.objects.filter(
        jitsi_room_id=room_name
    ).order_by('-heure_connexion').first()
    return presence.classe if presence else None


@api_view(['POST'])
@authentication_classes([LiveKitWebhookAuthentication])
@permission_classes([AllowAny])
@csrf_exempt
def livekit_webhook(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        payload = json.loads(request.body)
        event = payload.get('event')
        # ═══ AJOUTE CETTE LIGNE ICI, tout de suite après avoir lu event ═══
        print(f"🔔 WEBHOOK: event={payload.get('event')}, source={payload.get('track', {}).get('source')}")


        # ═══════════════════════════════════════════════════════════
        # 1. Un nouveau partage d'écran démarre → on lance un egress dédié
        # ═══════════════════════════════════════════════════════════
        if event == 'track_published':
            track = payload.get('track', {})
            participant = payload.get('participant', {})
            room = payload.get('room', {})
        
            is_screen_share = track.get('source') == 'SCREEN_SHARE'
            room_name = room.get('name')
            classe = get_classe_from_room(room_name)
        
            is_prof = bool(
                classe and classe.professeur and
                participant.get('identity') == str(classe.professeur.id)
            )
        
            if is_screen_share and is_prof and classe:
                #audio_actif = Enregistrements.objects.filter(
                #    classe=classe, statut='en_cours', url_video__startswith='audio_'
                #).exists()
        
                #if audio_actif:
                async def _start_screen():
                    lkapi = api.LiveKitAPI(LIVEKIT_URL, api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
                    try:
                        timestamp = int(datetime.now().timestamp())
                        filename = f"screen_{classe.id}_{timestamp}.webm"
                        req = api.TrackEgressRequest(
                            room_name=room_name,
                            track_id=track.get('sid'),
                            file=api.DirectFileOutput(filepath=f"/recordings/{filename}")
                        )
                        info = await lkapi.egress.start_track_egress(req)
                        return {"egress_id": info.egress_id, "filename": filename}
                    finally:
                        await lkapi.aclose()
    
                try:
                    result = asyncio.run(_start_screen())
                    derniere_seance = Seances.objects.filter(classe=classe).order_by('-created_at').first()
                    Enregistrements.objects.create(
                        classe=classe,
                        seance=derniere_seance,
                        demarre_par=classe.professeur,
                        egress_id=result["egress_id"],
                        url_video=result["filename"],
                        statut='en_cours'
                    )
                    print(f"✅ Egress écran démarré : {result['filename']}")
                except Exception as e:
                    print(f"❌ Impossible de démarrer l'egress écran auto: {str(e)}")
        
            return JsonResponse({'status': 'ok'}, status=200)

        # ═══════════════════════════════════════════════════════════
        # 2. Un partage d'écran s'arrête → on stoppe SON fichier précisément
        # ═══════════════════════════════════════════════════════════
        if event == 'track_unpublished':
            track = payload.get('track', {})
            room = payload.get('room', {})
            is_screen_share = track.get('source') == 'SCREEN_SHARE'

            if is_screen_share:
                room_name = room.get('name')
                classe = get_classe_from_room(room_name)

                if classe:
                    enreg_screen = Enregistrements.objects.filter(
                        classe=classe, statut='en_cours', url_video__startswith='screen_'
                    ).order_by('-started_at').first()

                    if enreg_screen:
                        async def _stop_screen():
                            lkapi = api.LiveKitAPI(LIVEKIT_URL, api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
                            try:
                                await lkapi.egress.stop_egress(
                                    api.StopEgressRequest(egress_id=enreg_screen.egress_id)
                                )
                            finally:
                                await lkapi.aclose()

                        try:
                            asyncio.run(_stop_screen())
                        except Exception as e:
                            print(f"❌ Impossible d'arrêter l'egress écran: {str(e)}")

            return JsonResponse({'status': 'ok'}, status=200)

        # ═══════════════════════════════════════════════════════════
        # 3. Un fichier (audio OU écran) vient de se terminer
        # → On sauvegarde juste en BDD, SANS créer de message dans le chat
        # → Le message final (fusionné) sera créé par 'room_finished'
        # ═══════════════════════════════════════════════════════════
        if event == 'egress_ended':
            egress_info = payload.get('egressInfo') or payload.get('egress') or payload
            
            egress_id = egress_info.get('egressId') or egress_info.get('egress_id')
            
            duree_ns = egress_info.get('duration')
            duree = int(float(duree_ns) / 1_000_000_000) if duree_ns else None
            
            files_list = egress_info.get('fileResults') or egress_info.get('file_results') or []
            filename = ""
            if files_list and len(files_list) > 0:
                filename = files_list[0].get('filename') or files_list[0].get('location') or ""
            else:
                filename = egress_info.get('file', {}).get('filename') or egress_info.get('file', {}).get('location') or ""

            print(f"🎣 WEBHOOK egress_ended traité ! egress_id: {egress_id}, filename: {filename}, duree: {duree}s")

            if not egress_id:
                return JsonResponse({'status': 'ignored'}, status=200)

            try:
                enregistrement = Enregistrements.objects.get(egress_id=egress_id, deleted_at__isnull=True)
            except Enregistrements.DoesNotExist:
                print(f"⚠️ Aucun enregistrement trouvé en BDD pour egress_id: {egress_id}")
                return JsonResponse({'status': 'ignored'}, status=200)

            file_name_only = filename.split('/')[-1] if filename else enregistrement.url_video.split('/')[-1]

            # ✅ On garde juste le NOM du fichier (pas l'URL complète)
            # → ffmpeg a besoin du nom brut pour retrouver le fichier physique
            enregistrement.url_video = file_name_only
            enregistrement.statut = 'termine'
            enregistrement.ended_at = timezone.now()
            if duree:
                enregistrement.duree_secondes = duree
            enregistrement.save()

            print(f"💾 Fichier sauvegardé en BDD (en attente de fusion) : {file_name_only}")

            # ⚠️ PLUS DE création de Message/Fichiers ici — ça se fera uniquement
            # à la fin du cours, dans le bloc 'room_finished' juste après, avec
            # la vidéo fusionnée (audio + écran synchronisés).

            return JsonResponse({'status': 'success'}, status=200)

        # ═══════════════════════════════════════════════════════════
        # 4. Le cours est terminé → on fusionne audio + écran(s) avec ffmpeg
        #    et on envoie UN SEUL message final dans le chat
        # ═══════════════════════════════════════════════════════════
        if event == 'room_finished':
            room = payload.get('room', {})
            room_name = room.get('name')
            classe = get_classe_from_room(room_name)

            if classe:
                seance = Seances.objects.filter(classe=classe).order_by('-created_at').first()

                audio = Enregistrements.objects.filter(
                    classe=classe, seance=seance, statut='termine',
                    url_video__startswith='audio_'
                ).order_by('-started_at').first()

                if audio:
                    screens = list(Enregistrements.objects.filter(
                        classe=classe, seance=seance, statut='termine',
                        url_video__startswith='screen_'
                    ).order_by('started_at'))

                    audio_filename = audio.url_video
                    audio_start = audio.created_at
                    total_duration = audio.duree_secondes or 0

                    segments = []
                    for s in screens:
                        if not s.ended_at:
                            continue
                        offset = (s.created_at - audio_start).total_seconds()
                        duration = (s.ended_at - s.created_at).total_seconds()
                        if offset < 0 or duration <= 0:
                            continue
                        segments.append({
                            "filename": s.url_video,
                            "start_offset": round(offset, 2),
                            "duration": round(duration, 2)
                        })

                    if total_duration > 0:
                        timestamp = int(datetime.now().timestamp())
                        output_filename = f"merged_{classe.id}_{timestamp}.mp4"

                        try:
                            import requests
                            resp = requests.post(
                                "https://processor.sabil-al-ilm.org/merge",
                                json={
                                    "audio_filename": audio_filename,
                                    "total_duration": total_duration,
                                    "segments": segments,
                                    "output_filename": output_filename
                                },
                                timeout=300
                            )
                            if resp.status_code == 200:
                                public_url = f"https://recordings.sabil-al-ilm.org/{output_filename}"
                                expediteur = classe.professeur or Users.objects.filter(is_staff=True).first()

                                Enregistrements.objects.create(
                                    classe=classe, seance=seance,
                                    demarre_par=classe.professeur,
                                    egress_id=f"merged_{timestamp}",
                                    url_video=output_filename,
                                    statut='termine',
                                    duree_secondes=int(total_duration)
                                )
                                Messages.objects.create(
                                    expediteur=expediteur,
                                    classe=classe,
                                    type_canal='chat_groupe',
                                    type_message='texte',
                                    contenu=(
                                        f"🎬 Replay complet du cours disponible\n"
                                        f"📚 Classe : *{classe.nom}*\n\n"
                                        f"Vidéo avec l'écran partagé synchronisé à l'audio.\n"
                                        f"🔗 {public_url}\n\n"
                                        f"⚠️ *Disponible pendant 7 jours.*"
                                    ),
                                    is_systeme=True,
                                )
                                print(f"✅ Fusion ffmpeg réussie: {output_filename}")
                            else:
                                print(f"❌ Fusion échouée: {resp.text}")
                        except Exception as e:
                            print(f"❌ Erreur appel processor: {str(e)}")
                else:
                    print(f"⚠️ Pas d'audio trouvé pour fusion, room {room_name}")

            return JsonResponse({'status': 'ok'}, status=200)

        return JsonResponse({'status': 'ignored'}, status=200)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON payload'}, status=400)
    except Exception as e:
        print(f"❌ Erreur Webhook LiveKit: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
     

# ─────────────────────────────────────────────
# HELPER : calcul du retard en minutes
# ─────────────────────────────────────────────
def _compute_retard(seance, heure_connexion_dt):
    """
    Retourne le retard en minutes si l'utilisateur s'est connecté
    plus de 10 minutes après l'heure de début réelle de la séance.
    Retourne None sinon (à l'heure ou moins de 11 min de retard).
    """
    if not seance.heure_debut_reelle or not seance.date_seance:
        return None
 
    # Reconstruction de l'heure de début en datetime aware
    debut_naive = timezone.datetime.combine(seance.date_seance, seance.heure_debut_reelle)
    debut_aware = timezone.make_aware(debut_naive) if timezone.is_naive(debut_naive) else debut_naive
 
    delta_seconds = (heure_connexion_dt - debut_aware).total_seconds()
    retard_minutes = int(delta_seconds // 60)
 
    # Seuil : retard significatif = plus de 10 minutes
    return retard_minutes if retard_minutes > 10 else None
 

# ==========================================================
# PERMISSIONS PERSONNALISÉES
# ==========================================================
class IsDirection(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'direction'

class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'

class IsProfesseur(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'professeur'

class IsEleve(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'eleve'

class CanManageInscriptions(permissions.BasePermission):
    """
    Permission personnalisée pour les inscriptions :
    - Direction/Admin : CRUD complet
    - Professeur : lecture seule sur SES classes
    - Élève : lecture seule sur SES inscriptions
    """
    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        if user.role in ('direction', 'admin'):
            return True
        # Prof et élève peuvent lire (GET, HEAD, OPTIONS)
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        return False  # Écriture refusée pour prof/élève

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.role in ('direction', 'admin'):
            return True
        if user.role == 'professeur':
            return obj.classe.professeur == user
        if user.role == 'eleve':
            return obj.eleve == user
        return False

class CanManageAccount(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ('direction', 'admin')

class ClassChatPermission(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.role in ('direction', 'admin'):
            return True
        if user.role == 'professeur' and obj.professeur == user:
            return True
        if user.role == 'eleve' and Inscriptions.objects.filter(eleve=user, classe=obj).exists():
            return True
        return False

# ==========================================================
# AUTHENTIFICATION & MOT DE PASSE
# ==========================================================
""" class CustomLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        
        if not email or not password:
            return Response({'error': 'Email et mot de passe requis.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            user = Users.objects.get(email=email, is_active=True)
        except Users.DoesNotExist:
            return Response({'error': 'Identifiants invalides.'}, status=status.HTTP_401_UNAUTHORIZED)

        #if not check_password(password, user.password_hash):
        #    return Response({'error': 'Identifiants invalides.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not check_password(password, user.password):
            return Response({'error': 'Identifiants invalides.'}, status=status.HTTP_401_UNAUTHORIZED)
            
        user.last_login = timezone.now()
        user.first_login_done = True
        user.save(update_fields=['last_login', 'first_login_done'])
        
        LogsActivite.objects.create(user=user, action='login', details_json={'ip': request.META.get('REMOTE_ADDR')})
        
        return Response({
            'message': 'Connexion réussie.',
            'role': user.role,
            'must_change_password': user.must_change_password,
            'token': 'JWT_OR_SESSION_TOKEN_PLACEHOLDER' 
        }) """


class CustomLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        if not email or not password:
            return Response({'error': 'Email et mot de passe requis.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # ⚠️ on ne filtre plus is_active=True ici, on veut pouvoir
            # distinguer "compte inexistant" de "compte désactivé"
            user = Users.objects.get(email=email)
        except Users.DoesNotExist:
            return Response({'error': 'Identifiants invalides.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not check_password(password, user.password):
            return Response({'error': 'Identifiants invalides.'}, status=status.HTTP_401_UNAUTHORIZED)

        # 🚫 Compte désactivé
        if not user.is_active:
            if user.role != 'eleve':
                # Tous les autres rôles : refus + flag pour afficher un modal côté front
                return Response(
                    {
                        'error': 'Votre compte a été désactivé. Veuillez contacter la direction.',
                        'account_disabled': True,
                    },
                    status=status.HTTP_403_FORBIDDEN
                )
            # Élève désactivé : on laisse passer, l'accès sera restreint côté front
            # (redirection + menu limité à "Mes Factures")

        user.last_login = timezone.now()
        user.first_login_done = True
        user.save(update_fields=['last_login', 'first_login_done'])

        LogsActivite.objects.create(
            user=user,
            action='login',
            details_json={'ip': request.META.get('REMOTE_ADDR')}
        )

        refresh = RefreshToken.for_user(user)

        return Response({
            'message': 'Connexion réussie.',
            'role': user.role,
            'must_change_password': user.must_change_password,
            'token': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': str(user.id),
                'email': user.email,
                'display_name': user.display_name,
                'role': user.role,
                'must_change_password': user.must_change_password,
                'is_active': user.is_active,  # ← ajouté : nécessaire pour restreindre l'accès élève côté front
            }
        })


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        user = request.user
        old_pw = request.data.get('old_password')
        new_pw = request.data.get('new_password')
        
        if not check_password(old_pw, user.password):
            return Response({'error': 'Ancien mot de passe incorrect.'}, status=status.HTTP_400_BAD_REQUEST)
            
        if len(new_pw) < 6:
            return Response({'error': 'Le mot de passe doit contenir au moins 6 caractères.'}, status=status.HTTP_400_BAD_REQUEST)
            
        user.password = make_password(new_pw)
        user.must_change_password = False
        user.save(update_fields=['password', 'must_change_password'])
        return Response({'message': 'Mot de passe mis à jour.'})


class ForceChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        if not request.user.must_change_password:
            return Response({'error': 'Aucune obligation de changement.'}, status=status.HTTP_400_BAD_REQUEST)
        new_pw = request.data.get('new_password')
        if not new_pw or len(new_pw) < 6:
            return Response({'error': 'Mot de passe trop court.'}, status=status.HTTP_400_BAD_REQUEST)
        request.user.password = make_password(new_pw)
        request.user.must_change_password = False
        request.user.save(update_fields=['password', 'must_change_password'])
        return Response({'message': 'Mot de passe forcé changé. Accès débloqué.'})

class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request):
        return Response({'message': 'Déconnexion réussie.'})

# ==========================================================
# DASHBOARDS PAR RÔLE
# ==========================================================


class DirectionDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsDirection]

    # ── Calcul heures réalisées identique à FactureEmiseViewSet._get_duree_et_heures ──
    def _duree_heures(self, p):
        if p.enregistrement_system is False:
            temps_minutes = p.temps_prof or 0
            return Decimal(str(round(temps_minutes / 60, 4)))
        else:
            hx = p.heure_connexion
            hdx = p.heure_deconnexion
            if hx and hdx:
                return Decimal(str(round(
                    (hdx - hx).total_seconds() / 3600, 4
                )))
            return Decimal('0')

    def get(self, request):
        f = {
            'professor_id': request.query_params.get('professor_id', ''),
            'eleve_id':     request.query_params.get('eleve_id', ''),
            'class_id':     request.query_params.get('class_id', ''),
            'programme':    request.query_params.get('programme', ''),
            'start_date':   request.query_params.get('start_date', ''),
            'end_date':     request.query_params.get('end_date', ''),
        }

        # ── Base querysets ────────────────────────────────────────────────────

        factures_qs = Factures.objects.select_related(
            'classe', 'professeur'
        ).filter(statut__in=['envoyee', 'payee'])

        classes_qs = Classes.objects.filter(
            statut='active', deleted_at__isnull=True
        ).select_related('professeur')

        inscriptions_qs = Inscriptions.objects.filter(
            statut='active',
            classe__statut='active',
            classe__deleted_at__isnull=True
        ).select_related('classe', 'eleve')

        factures_eleve_qs = FactureEleve.objects.select_related(
            'facture', 'facture__classe', 'eleve'
        )

        # Presences valides (même logique que FactureEmiseViewSet)
        absence_valide = AbsencesProfs.objects.filter(
            presence=OuterRef('pk'),
        ).exclude(
            Q(temps_effectif=False) & Q(durree_eleve__isnull=True)
        )
        absence_valide_system = AbsencesProfs.objects.filter(
            presence=OuterRef('pk'),
        ).exclude(Q(resp_query_fin_prof=False))

        presences_qs = Presences.objects.filter(
            seance__isnull=False,
        ).filter(
            (
                Q(enregistrement_system=False)
                & Exists(absence_valide)
            ) | (
                Q(heure_connexion__isnull=False)
                & Q(heure_deconnexion__isnull=False)
                & Q(jitsi_room_id__isnull=False)
                & (
                    Q(enregistrement_system__isnull=True)
                    | Q(enregistrement_system=True)
                )
                & Exists(absence_valide_system)
            )
        ).select_related('classe', 'seance', 'user')

        # ── Filtres ───────────────────────────────────────────────────────────

        if f['professor_id']:
            factures_qs      = factures_qs.filter(professeur_id=f['professor_id'])
            classes_qs       = classes_qs.filter(professeur_id=f['professor_id'])
            inscriptions_qs  = inscriptions_qs.filter(classe__professeur_id=f['professor_id'])
            factures_eleve_qs= factures_eleve_qs.filter(facture__professeur_id=f['professor_id'])
            presences_qs     = presences_qs.filter(classe__professeur_id=f['professor_id'])

        if f['eleve_id']:
            inscriptions_qs   = inscriptions_qs.filter(eleve_id=f['eleve_id'])
            factures_eleve_qs = factures_eleve_qs.filter(eleve_id=f['eleve_id'])

        if f['class_id']:
            factures_qs      = factures_qs.filter(classe_id=f['class_id'])
            classes_qs       = classes_qs.filter(id=f['class_id'])
            inscriptions_qs  = inscriptions_qs.filter(classe_id=f['class_id'])
            factures_eleve_qs= factures_eleve_qs.filter(facture__classe_id=f['class_id'])
            presences_qs     = presences_qs.filter(classe_id=f['class_id'])

        if f['programme']:
            factures_qs      = factures_qs.filter(classe__programme__icontains=f['programme'])
            classes_qs       = classes_qs.filter(programme__icontains=f['programme'])
            inscriptions_qs  = inscriptions_qs.filter(classe__programme__icontains=f['programme'])
            presences_qs     = presences_qs.filter(classe__programme__icontains=f['programme'])

        if f['start_date']:
            factures_qs  = factures_qs.filter(date_debut__date__gte=f['start_date'])
            presences_qs = presences_qs.filter(created_at__date__gte=f['start_date'])

        if f['end_date']:
            factures_qs  = factures_qs.filter(date_fin__date__lte=f['end_date'])
            presences_qs = presences_qs.filter(created_at__date__lte=f['end_date'])

        # ── 1. Stats profs ────────────────────────────────────────────────────

        montant_due_prof   = factures_qs.aggregate(t=Sum('part_prof'))['t'] or Decimal('0')
        montant_due_dir    = factures_qs.aggregate(t=Sum('part_direction'))['t'] or Decimal('0')
        montant_total      = factures_qs.aggregate(t=Sum('montant_total'))['t'] or Decimal('0')

        nb_factures_envoyees = factures_qs.filter(statut='envoyee').count()
        nb_factures_payees   = factures_qs.filter(statut='payee').count()

        prof_breakdown = (
            factures_qs
            .values('professeur__id', 'professeur__display_name')
            .annotate(
                part_prof_total=Sum('part_prof'),
                part_dir_total=Sum('part_direction'),
                nb_factures=Count('id'),
            )
            .order_by('-part_prof_total')
        )
        professeurs_concernes = [
            {
                'id':           str(p['professeur__id']),
                'nom_complet':  p['professeur__display_name'] or '',
                'part_prof':    float(p['part_prof_total'] or 0),
                'part_dir':     float(p['part_dir_total'] or 0),
                'nb_factures':  p['nb_factures'],
            }
            for p in prof_breakdown
        ]

        # ── 2. Stats classes ──────────────────────────────────────────────────

        nb_classes_global  = Classes.objects.filter(
            statut='active', deleted_at__isnull=True
        ).count()
        nb_classes_filtre  = classes_qs.count()

        # ── 3. Stats élèves ───────────────────────────────────────────────────

        nb_eleves_global  = Inscriptions.objects.filter(
            statut='active',
            classe__statut='active',
            classe__deleted_at__isnull=True
        ).values('eleve').distinct().count()

        nb_eleves_filtre  = inscriptions_qs.values('eleve').distinct().count()

        # ── 4. Stats factures élèves ──────────────────────────────────────────

        montant_eleve_a_payer = (
            factures_eleve_qs
            .filter(statut__in=['envoyee', 'partiel'])
            .aggregate(t=Sum('montant_a_payer'))['t'] or Decimal('0')
        )
        montant_eleve_paye = (
            factures_eleve_qs
            .filter(statut__in=['paye', 'confirmee'])
            .aggregate(t=Sum('montant_payer'))['t'] or Decimal('0')
        )


        # ── 4bis. Détail élèves à payer (pour le modal) ────────────────────

        factures_eleve_a_payer_qs = (
            factures_eleve_qs
            .filter(statut__in=['envoyee', 'partiel'])
            .select_related(
                'eleve',
                'facture',
                'facture__classe',
                'facture__classe__professeur',
                'facture__professeur',
            )
            .order_by('eleve__display_name')
        )
 
        eleves_a_payer_detail = []
        for fe in factures_eleve_a_payer_qs:
            facture = fe.facture
            classe = facture.classe if facture else None
            # La facture porte directement le professeur ; on retombe sur
            # celui de la classe si jamais facture.professeur est vide.
            professeur = (
                getattr(facture, 'professeur', None)
                or (classe.professeur if classe else None)
            )
            eleve = fe.eleve
 
            telephone = ''
            if eleve:
                indicatif = (eleve.indicatif or '').strip()
                tel = (eleve.telephone or '').strip()
                if tel:
                    telephone = f"{indicatif} {tel}".strip()

            presence = fe.presence  # adapte le nom de la relation si besoin
            if presence and presence.heure_connexion_prof:
                debut = presence.heure_connexion_prof
                fin = debut + timedelta(minutes=presence.temps_prof or 0)
                cours = f"séance du {debut.strftime('%d/%m/%Y %H:%M')} au {fin.strftime('%H:%M')}"
            elif presence and presence.heure_connexion and presence.heure_deconnexion:
                cours = f"séance du {presence.heure_connexion.strftime('%d/%m/%Y %H:%M')} au {presence.heure_deconnexion.strftime('%H:%M')}"
            else:
                cours = ''
 
            eleves_a_payer_detail.append({
                'facture_eleve_id': str(fe.id),
                'eleve_nom':        (eleve.display_name) if eleve else '',
                'classe_nom':       classe.nom if classe else '',
                # NB : adapter ce champ si "le cours" correspond à un autre
                # attribut chez vous (ex: classe.matiere, classe.programme,
                # ou le nom d'une séance liée à la facture).
                'cours':            cours,
                'montant_a_payer':  float(fe.montant_a_payer or 0),
                'professeur_nom':   professeur.display_name if professeur else '',
                'telephone':        telephone,
            })

        # ── 5. Séances actives ────────────────────────────────────────────────

        seances_qs = Seances.objects.filter(
            statut='active', classe__isnull=False
        )
        if f['professor_id']:
            seances_qs = seances_qs.filter(classe__professeur_id=f['professor_id'])
        if f['class_id']:
            seances_qs = seances_qs.filter(classe_id=f['class_id'])
        nb_seances = seances_qs.count()

        # ── 6. Évolution heures (logique FactureEmiseViewSet) ─────────────────

        presences_list = list(presences_qs.order_by('created_at'))

        from collections import defaultdict
        # Regrouper par (prof, date)
        heures_par_prof_date = defaultdict(lambda: defaultdict(Decimal))
        prof_noms = {}

        for p in presences_list:
            date_str = timezone.localtime(p.created_at).date().isoformat()
            prof_id  = str(p.user_id)
            prof_noms[prof_id] = p.user.display_name or p.user.email
            duree = self._duree_heures(p)
            heures_par_prof_date[date_str][prof_id] += duree

        evolution_heures = []
        for date_str in sorted(heures_par_prof_date.keys()):
            for prof_id, heures in heures_par_prof_date[date_str].items():
                evolution_heures.append({
                    'date':          date_str,
                    'professeur_id': prof_id,
                    'professeur':    prof_noms.get(prof_id, ''),
                    'heures':        round(float(heures), 2),
                })

        # ── 7. Liste élèves pour filtre ───────────────────────────────────────
        # Élèves inscrits dans les classes du prof filtré (ou tous si pas de filtre)
        eleves_qs = Users.objects.filter(
            inscriptions__statut='active',
            inscriptions__classe__statut='active',
            inscriptions__classe__deleted_at__isnull=True,
            role='eleve',
            is_active=True,
        )
        if f['professor_id']:
            eleves_qs = eleves_qs.filter(
                inscriptions__classe__professeur_id=f['professor_id']
            )
        eleves_options = list(
            eleves_qs.distinct()
            .values('id', 'display_name', 'email')
            .order_by('display_name')
        )

        # ── Réponse ───────────────────────────────────────────────────────────

        return Response({
            # Finances profs
            'montant_due_prof_total':   float(montant_due_prof),
            'montant_due_directrice':   float(montant_due_dir),
            'montant_total_factures':   float(montant_total),
            'nb_factures_envoyees':     nb_factures_envoyees,
            'nb_factures_payees':       nb_factures_payees,
            'professeurs_concernes':    professeurs_concernes,

            # Classes
            'nb_classes_global':        nb_classes_global,
            'nb_classes_filtre':        nb_classes_filtre,

            # Élèves
            'nb_eleves_global':         nb_eleves_global,
            'nb_eleves_filtre':         nb_eleves_filtre,

            # Factures élèves
            'montant_eleve_a_payer':    float(montant_eleve_a_payer),
            'montant_eleve_paye':       float(montant_eleve_paye),
            'eleves_a_payer_detail':    eleves_a_payer_detail,

            # Séances
            'nb_seances_actives':       nb_seances,

            # Graph
            'evolution_heures':         evolution_heures,

            # Options filtre élève (dynamique selon prof filtré)
            'eleves_options':           eleves_options,
        })

class ProfesseurListView(ListAPIView):
    serializer_class = ProfesseurSelectSerializer
    permission_classes = [IsAuthenticated, IsDirection]
    queryset = Users.objects.filter(role='professeur', is_active=True).order_by('display_name')
    pagination_class = None  # ← Désactive la pagination pour ce endpoint

class ClasseListView(ListAPIView):
    serializer_class = ClasseSelectSerializer
    permission_classes = [IsAuthenticated, IsDirection]
    queryset = Classes.objects.filter(statut='active', deleted_at__isnull=True).order_by('nom')
    pagination_class = None  # ← Désactive la pagination pour ce endpoint



class PlanningViewSet(viewsets.ModelViewSet):
    serializer_class = PlanningItemSerializer
    permission_classes = [permissions.IsAuthenticated]
 
    def get_queryset(self):
        queryset = Seances.objects.select_related(
            'classe', 'classe__professeur',
            'professeur_disponible',          # ← jointure pour le nouveau champ
        ).prefetch_related(
            Prefetch('presences_set', queryset=Presences.objects.all(), to_attr='presence_list')
        )
        start_str = self.request.query_params.get('start_date')
        end_str   = self.request.query_params.get('end_date')
        today     = timezone.now().date()
 
        start_date = datetime.fromisoformat(start_str).date() if start_str else today - timedelta(days=7)
        end_date   = datetime.fromisoformat(end_str).date()   if end_str   else today + timedelta(days=7)
 
        queryset = queryset.filter(
            Q(date_seance__gte=start_date, date_seance__lte=end_date) |
            Q(date_seance__isnull=True)
        )
 
        # ✅ Exclure les séances supprimées
        queryset = queryset.exclude(statut='supprimer')

         # ✅ Exclure les séances dont la classe est supprimée
        queryset = queryset.exclude(classe__statut='supprimer')
 
        professeur_id = self.request.query_params.get('professeur_id')
        if professeur_id:
            # Filtre sur classe.professeur OU sur professeur_disponible
            queryset = queryset.filter(
                Q(classe__professeur__id=professeur_id) |
                Q(professeur_disponible__id=professeur_id)
            )
 
        statut = self.request.query_params.get('statut_realisation')
        if statut:
            queryset = queryset.filter(statut_realisation=statut)
 
        return queryset.distinct()
 
    # ──────────────────────────────────────────────────────────
    # POST /api/planning/create/
    # Body JSON :
    #   Avec classe   : { "classe": "<uuid>", "jour_seance": "lundi", ... }
    #   Disponibilité : { "professeur_disponible": "<uuid>", "jour_seance": "lundi", ... }
    # ──────────────────────────────────────────────────────────
    @action(detail=False, methods=['post'], url_path='create', url_name='create')
    def create_seance(self, request):
        serializer = SeanceCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
 
        data = serializer.validated_data
        seance = Seances(
            jour_seance          = data['jour_seance'],
            heure_debut_reelle   = data['heure_debut_reelle'],
            duree_reelle_minutes = data['duree_reelle_minutes'],
            statut               = data.get('statut', 'active'),
        )
 
        if data.get('classe'):
            try:
                seance.classe = Classes.objects.get(pk=data['classe'])
            except Classes.DoesNotExist:
                return Response({'classe': 'Classe introuvable.'}, status=status.HTTP_400_BAD_REQUEST)
 
        if data.get('professeur_disponible'):
            try:
                seance.professeur_disponible = Users.objects.get(pk=data['professeur_disponible'])
            except Users.DoesNotExist:
                return Response({'professeur_disponible': 'Objet introuvable.'}, status=status.HTTP_400_BAD_REQUEST)
 
        seance.save()

        today = timezone.now().date()
        msg = f"Nouveau créneau pour la classe {seance.classe.nom}"
        direction = Users.objects.get(role='direction', is_active=True)
        Notifications.objects.create(destinataire=direction, type='nouveau_creneau',classe=seance.classe, titre='Nouveau créneau', contenu=msg, lu=False)

        inscriptions = Inscriptions.objects.filter(classe=seance.classe)

        for inscription in inscriptions:
            Notifications.objects.create(
                destinataire=inscription.eleve,
                type='nouveau_creneau',
                titre='Nouveau créneau',
                contenu=msg,
                classe=seance.classe,
                lu=False
            )


        return Response({'id': str(seance.id), 'statut': seance.statut}, status=status.HTTP_201_CREATED)
 
    # ──────────────────────────────────────────────────────────
    # PATCH /api/planning/{id}/update/
    # ──────────────────────────────────────────────────────────
    @action(detail=True, methods=['patch'], url_path='update', url_name='update')
    def update_seance(self, request, pk=None):
        
        try:
            seance = Seances.objects.get(pk=pk)
        except Seances.DoesNotExist:
            return Response({'detail': 'Séance introuvable.'}, status=status.HTTP_404_NOT_FOUND)
 
        serializer = SeanceUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
 
        validated = serializer.validated_data
        if not validated:
            return Response({'detail': 'Aucun champ à mettre à jour.'}, status=status.HTTP_400_BAD_REQUEST)
 
        for field, value in validated.items():
            setattr(seance, field, value)
        seance.save(update_fields=list(validated.keys()))
        today = timezone.now().date()
        
        msg = f"Changement de créneau  pour la classe {seance.classe.nom}"
        direction = Users.objects.get(role='direction', is_active=True)
        
        Notifications.objects.create(destinataire=direction, classe=seance.classe, type='changement_creneau', titre='Changement de créneau', contenu=msg, lu=False)
  
        inscriptions = Inscriptions.objects.filter(classe=seance.classe)
        
        notifications = [
            Notifications(
                destinataire=inscription.eleve,
                type='changement_creneau',
                titre='Changement de créneau',
                classe=seance.classe,
                contenu=msg,
                lu=False
            )
            for inscription in inscriptions
        ]
        
        Notifications.objects.bulk_create(notifications)
 
        return Response({
            'id':                    str(seance.id),
            'statut':                seance.statut,
            'duree_reelle_minutes':  seance.duree_reelle_minutes,
            'heure_debut_reelle':    str(seance.heure_debut_reelle) if seance.heure_debut_reelle else None,
        }, status=status.HTTP_200_OK)



class AbsenceSignalerViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET  /api/absences/           → liste paginée avec filtres
    POST /api/absences/create/    → signaler une absence
    """
    serializer_class = AbsenceSignalerSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = AbsenceSignaler.objects.select_related(
            'admin',
            'seance',
            'seance__classe',
            'seance__classe__professeur',
            'seance__professeur_disponible',
        ).order_by('-date_absence')

        # ── Filtre par mois (ex: ?mois=2025-04)
        mois_str = self.request.query_params.get('mois')
        if mois_str:
            try:
                debut = datetime.strptime(mois_str, '%Y-%m')
                fin   = debut + relativedelta(months=1)
                qs = qs.filter(date_absence__gte=debut, date_absence__lt=fin)
            except ValueError:
                pass

        # ── Filtre par année (ex: ?annee=2025)
        annee = self.request.query_params.get('annee')
        if annee:
            qs = qs.filter(date_absence__year=annee)

        # ── Filtre par professeur_id
        professeur_id = self.request.query_params.get('professeur_id')
        if professeur_id:
            qs = qs.filter(
                Q(seance__classe__professeur__id=professeur_id) |
                Q(seance__professeur_disponible__id=professeur_id)
            )

        # ── Filtre par plage de dates
        start_str = self.request.query_params.get('start_date')
        end_str   = self.request.query_params.get('end_date')
        if start_str:
            qs = qs.filter(date_absence__date__gte=start_str)
        if end_str:
            qs = qs.filter(date_absence__date__lte=end_str)

        return qs.distinct()

    # ──────────────────────────────────────────────────────────
    # POST /api/absences/create/
    # Body : { "seance": "<uuid>", "date_absence": "...", "remarque": "..." }
    # ──────────────────────────────────────────────────────────
    @action(detail=False, methods=['post'], url_path='create', url_name='create')
    def create_absence(self, request):
        serializer = AbsenceSignalerCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            seance = Seances.objects.get(pk=data['seance'])
        except Seances.DoesNotExist:
            return Response({'seance': 'Séance introuvable.'}, status=status.HTTP_400_BAD_REQUEST)

        absence = AbsenceSignaler.objects.create(
            admin         = request.user,
            seance        = seance,
            date_absence  = data['date_absence'],
            remarque      = data.get('remarque', ''),
        )
        out = AbsenceSignalerSerializer(absence)
        today = timezone.now().date()
        msg = f"Absence signaler pour la classe {seance.classe.nom} a la date du {data['date_absence']}"
        direction = Users.objects.get(role='direction', is_active=True)
        Notifications.objects.create(destinataire=direction, type='absence_prof', titre='absence', contenu=msg, lu=False)

        return Response(out.data, status=status.HTTP_201_CREATED)

    # ──────────────────────────────────────────────────────────
    # DELETE /api/absences/{id}/supprimer/
    # ──────────────────────────────────────────────────────────
    @action(detail=True, methods=['delete'], url_path='supprimer', url_name='supprimer')
    def supprimer(self, request, pk=None):
        try:
            absence = AbsenceSignaler.objects.get(pk=pk)
        except AbsenceSignaler.DoesNotExist:
            return Response({'detail': 'Introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        absence.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)



JOURS_MAP = {
    'lundi': 0, 'mardi': 1, 'mercredi': 2,
    'jeudi': 3, 'vendredi': 4, 'samedi': 5, 'dimanche': 6,
}


def get_dates_for_jour(jour: str, year: int, month: int) -> list[date]:
    """Retourne toutes les dates du mois correspondant au jour (ex: 'lundi')."""
    idx = JOURS_MAP.get(jour.lower())
    if idx is None:
        return []
    _, nb_days = calendar.monthrange(year, month)
    return [
        date(year, month, d)
        for d in range(1, nb_days + 1)
        if date(year, month, d).weekday() == idx
    ]


def seances_realisees_dates(professeur_id: str, year: int, month: int) -> set[tuple]:
    """
    Retourne un set de (seance_id, date_str) des séances réalisées
    en se basant sur la même logique que PlanningViewSet.
    date_str = "YYYY-MM-DD"
    """
    from datetime import datetime
    debut = date(year, month, 1)
    _, nb = calendar.monthrange(year, month)
    fin   = date(year, month, nb)

    absence_prof_valide = AbsencesProfs.objects.filter(
        presence=OuterRef('pk'),
    ).exclude(
        Q(temps_effectif=False) & Q(durree_eleve__isnull=True)
    )

    absence_prof_valide_system = AbsencesProfs.objects.filter(
        presence=OuterRef('pk'),
    ).exclude(
        Q(resp_query_fin_prof=False)
    )

    presences = (
        Presences.objects
        .filter(
            classe__professeur_id=professeur_id,
            seance__isnull=False,
            created_at__date__gte=debut,
            created_at__date__lte=fin,
        )
        .filter(
            (
                Q(enregistrement_system=False)
                & Exists(absence_prof_valide)
            )
            |
            (
                Q(heure_connexion__isnull=False)
                & Q(heure_deconnexion__isnull=False)
                & Q(jitsi_room_id__isnull=False)
                & (
                    Q(enregistrement_system__isnull=True)
                    | Q(enregistrement_system=True)
                )
                & Exists(absence_prof_valide_system)
            )
        )
        .values('seance_id', 'created_at')
    )

    result = set()
    for p in presences:
        sid  = str(p['seance_id'])
        dstr = p['created_at'].date().isoformat()
        result.add((sid, dstr))
    return result


# ─────────────────────────────────────────────────────────────
# GET /api/absences/admin-calendar/?professeur_id=&year=&month=
# ─────────────────────────────────────────────────────────────

class AbsenceAdminCalendarView(APIView):
    """
    Retourne pour un prof + mois/année :
    - seances_manquees  : séances prévues non réalisées
    - absences_signalees: AbsenceSignaler actifs du mois
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        professeur_id = request.query_params.get('professeur_id')
        year  = int(request.query_params.get('year',  timezone.now().year))
        month = int(request.query_params.get('month', timezone.now().month))

        if not professeur_id:
            return Response({'detail': 'professeur_id requis.'}, status=400)

        # ── 1. Séances du prof pour le mois
        #       Exclure supprimées et disponibilités (professeur_disponible != null)
        seances = (
            Seances.objects
            .filter(
                classe__professeur_id=professeur_id,
                statut__in=['active', 'horaire_valide', 'horaire_non_valide'],
            )
            .exclude(statut='supprimer')
            .exclude(classe__statut='supprimer')
            .filter(professeur_disponible__isnull=True)   # pas de dispo
            .select_related('classe', 'classe__professeur')
        )

        _, nb = calendar.monthrange(year, month)
        # Récupérer les absences justifiées du mois pour ce prof
        justifiees = set(
            AbsenceSignaler.objects
            .filter(
                seance__classe__professeur_id=professeur_id,
                statut='justifie',
                date_absence__date__gte=date(year, month, 1),
                date_absence__date__lte=date(year, month, nb),
            )
            .values_list('seance_id', 'date_absence__date')
        )
        # Convertir en set de tuples (str, str)
        justifiees = {(str(sid), d.isoformat()) for sid, d in justifiees}

        # ── 2. Dates réalisées dans le mois
        realisees = seances_realisees_dates(professeur_id, year, month)

        # ── 3. Construire les séances manquées (prévues non réalisées)
        manquees = []
       
        for s in seances:
            jour = (s.jour_seance or '').strip().lower()
            dates_du_mois = get_dates_for_jour(jour, year, month)
            for d in dates_du_mois:
                # Ne pas proposer les dates futures (> aujourd'hui)
                if d > date.today():
                    continue
                dstr = d.isoformat()
                if (str(s.id), dstr) not in realisees:
                    if (str(s.id), dstr) in justifiees:
                        continue
                    manquees.append({
                        'seance_id':   str(s.id),
                        'date':        dstr,
                        'jour_seance': s.jour_seance,
                        'heure':       str(s.heure_debut_reelle)[:5] if s.heure_debut_reelle else None,
                        'duree':       s.duree_reelle_minutes,
                        'classe_nom':  s.classe.nom if s.classe else None,
                        'professeur':  (
                            s.classe.professeur.display_name
                            or s.classe.professeur.email
                        ) if s.classe and s.classe.professeur else None,
                        'seance_classe_id': str(s.classe.id) if s.classe else None,
                    })

        # ── 4. Absences déjà signalées (statut=actif) dans le mois
        
        abs_qs = AbsenceSignaler.objects.filter(
            seance__classe__professeur_id=professeur_id,
            statut='actif',
            date_absence__date__gte=date(year, month, 1),
            date_absence__date__lte=date(year, month, nb),
        ).select_related(
            'admin', 'seance', 'seance__classe',
            'seance__classe__professeur',
            'seance__professeur_disponible',
        )
        abs_data = AbsenceSignalerSerializer(abs_qs, many=True).data

        return Response({
            'seances_manquees':   manquees,
            'absences_signalees': abs_data,
        })


# ─────────────────────────────────────────────────────────────
# POST /api/absences/signaler/
# Body : { seance_id, date_absence }
# ─────────────────────────────────────────────────────────────

class SignalerAbsenceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        seance_id    = request.data.get('seance_id')
        date_absence = request.data.get('date_absence')
        statut_demande = request.data.get('statut', 'actif')

        if not seance_id or not date_absence:
            return Response({'detail': 'seance_id et date_absence requis.'}, status=400)

        try:
            seance = Seances.objects.get(pk=seance_id)
        except Seances.DoesNotExist:
            return Response({'detail': 'Séance introuvable.'}, status=404)

        # Idempotent : si déjà actif pour cette séance + date → retourner l'existant
        existing = AbsenceSignaler.objects.filter(
            seance=seance,
            date_absence__date=date_absence,
        ).exclude(statut='inactif').first()
        if existing:
            if existing.statut != statut_demande:
                existing.statut = statut_demande
                existing.admin = request.user
                existing.save(update_fields=['statut', 'admin'])
            return Response(AbsenceSignalerSerializer(existing).data, status=200)

        # Réactiver si inactif
        revoked = AbsenceSignaler.objects.filter(
            seance=seance,
            date_absence__date=date_absence,
            statut='inactif',
        ).first()
        if revoked:
            revoked.statut = 'actif'
            revoked.admin  = request.user
            revoked.save(update_fields=['statut', 'admin'])
            return Response(AbsenceSignalerSerializer(revoked).data, status=200)

        absence = AbsenceSignaler.objects.create(
            admin        = request.user,
            seance       = seance,
            date_absence = date_absence,
            statut       = statut_demande,
        )
        today = timezone.now().date()
        
        msg = f"absence signaler pour la classe {seance.classe.nom} a la date du {date_absence}"
        direction = Users.objects.get(role='direction', is_active=True)
        Notifications.objects.create(destinataire=direction, type='absence_prof', titre='absence signalee', contenu=msg, lu=False)

        return Response(AbsenceSignalerSerializer(absence).data, status=201)


# ─────────────────────────────────────────────────────────────
# PATCH /api/absences/{id}/revoquer/
# ─────────────────────────────────────────────────────────────

class RevoquerAbsenceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        try:
            absence = AbsenceSignaler.objects.get(pk=pk)
        except AbsenceSignaler.DoesNotExist:
            return Response({'detail': 'Absence introuvable.'}, status=404)

        absence.statut = 'inactif'
        absence.save(update_fields=['statut'])
        return Response({'id': str(absence.id), 'statut': absence.statut})



class AdminDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    def get(self, request):
        classes_gerees = Classes.objects.filter(admin=request.user, deleted_at__isnull=True)
        return Response({
            'nombre_professeurs': classes_gerees.values('professeur').distinct().count(),
            'classes_en_pause': classes_gerees.filter(couleur='orange').count(),
            'classes_a_signaler': classes_gerees.filter(couleur='rouge').count()
        })

class ProfDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsProfesseur]
    def get(self, request):
        mes_classes = Classes.objects.filter(professeur=request.user, deleted_at__isnull=True)
        return Response({
            'compteur_admin': Classes.objects.filter(admin=request.user).count(),
            'mes_classes_actives': mes_classes.filter(statut='active').count(),
            'devoirs_en_attente': Devoirs.objects.filter(classe__professeur=request.user, statut='soumis', note__isnull=True).count()
        })

class EleveDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsEleve]
    def get(self, request):
        inscriptions = Inscriptions.objects.filter(eleve=request.user)
        classes_ids = inscriptions.values_list('classe_id', flat=True)
        return Response({
            'classes_actives': Classes.objects.filter(id__in=classes_ids, statut='active').count(),
            'prochain_cours': Seances.objects.filter(classe__id__in=classes_ids, date_seance__gte=timezone.now().date()).order_by('date_seance', 'heure_debut_reelle').first(),
            'notifications': Notifications.objects.filter(destinataire=request.user, lu=False).count()
        })

# ==========================================================
# VIEWSETS GÉNÉRAUX (Avec gestion rôles)
# ==========================================================
class UserViewSet(viewsets.ModelViewSet):
    queryset = Users.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer  # ← AJOUTER CETTE LIGNE
    
    def get_queryset(self):
        user = self.request.user
        role_param = self.request.query_params.get('role')
        is_active_param = self.request.query_params.get('is_active')

        # 🔥 IMPORTANT : bypass pour actions detail (reactivate, retrieve, update, delete)
        if self.action in ['retrieve', 'update', 'partial_update', 'destroy', 'reactivate']:
            queryset = Users.objects.all()
        else:
            # =========================
            # 🔐 Filtrage par rôle
            # =========================
            if user.role == 'direction':
                queryset = Users.objects.all()

            elif user.role == 'admin':
                # Professeurs rattachés à cet admin
                profs_ids = Users.objects.filter(
                    role='professeur',
                    admin_id=user.id
                ).values_list('id', flat=True)

                # Élèves inscrits dans les classes de ces profs
                eleves_ids = Inscriptions.objects.filter(
                    classe__professeur_id__in=profs_ids
                ).values_list('eleve_id', flat=True)

                queryset = Users.objects.filter(
                    id__in=list(profs_ids) + list(eleves_ids) + [user.id]
                ).distinct()

            elif user.role == 'professeur':
                eleves_ids = Inscriptions.objects.filter(
                    classe__professeur=user
                ).values_list('eleve_id', flat=True)
                queryset = Users.objects.filter(
                    id__in=list(eleves_ids) + [user.id]
                ).distinct()

            elif user.role == 'eleve':
                queryset = Users.objects.filter(id=user.id)

            else:
                return Users.objects.none()

            # filtre role
            if role_param:
                queryset = queryset.filter(role=role_param)

            # filtre actif uniquement pour list
            if is_active_param is not None:
                queryset = queryset.filter(is_active=is_active_param.lower() == 'true')
            else:
                queryset = queryset.filter(is_active=True)


        exclude_classe = self.request.query_params.get('exclude_classe')
        if exclude_classe:
            already_in = Inscriptions.objects.filter(classe_id=exclude_classe).values_list('eleve_id', flat=True)
            queryset = queryset.exclude(id__in=already_in)
            
        return queryset

    @action(detail=False, methods=['get'], permission_classes=[IsDirection])
    def admins(self, request):
        """Retourne la liste des utilisateurs avec rôle 'admin'"""
        admins = Users.objects.filter(role='admin', is_active=True).values('id', 'display_name', 'email')
        return Response(list(admins))
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def directions(self, request):
        directions = Users.objects.filter(role='direction', is_active=True).values('id', 'display_name', 'email', 'role')
        return Response(list(directions))

    @action(detail=False, methods=['post'], permission_classes=[IsDirection])
    def create_account(self, request):
        with transaction.atomic():
            role = request.data.get('role')

            if role not in ('admin', 'professeur', 'eleve'):
                return Response({'error': 'Rôle invalide.'}, status=400)

            email = request.data.get('email')
            if Users.objects.filter(email=email).exists():
                return Response({'error': 'Email déjà utilisé.'}, status=400)

            default_pw = make_password('sabil')

            # ✅ Création utilisateur principal
            user = Users.objects.create(
                email=email,
                password=default_pw,
                role=role,
                display_name=request.data.get('display_name'),
                nom_diplome=request.data.get('nom_diplome'),
                lien_paypal=request.data.get('lien_paypal'),
                rib=request.data.get('rib'),
                must_change_password=True,
                is_active=True,
                code_prof=request.data.get('code_prof'),
                created_by=request.user,
                homme_femme=request.data.get('homme_femme'),
                telephone=request.data.get('telephone'),
                indicatif=request.data.get('indicatif')
            )

            # =====================================
            # 🔥 CAS ÉLÈVE → créer parent auto
            # =====================================
            if role == 'eleve':
                nom_parent = request.data.get('nom_parent')
                # ✅ créer parent seulement si fourni
                if nom_parent and nom_parent.strip():

                    parent_email = f"parent_{uuid.uuid4().hex[:10]}@sabil.com"

                    parent = Users.objects.create(
                        email=parent_email,
                        password=default_pw,
                        role='parent',
                        display_name=nom_parent,
                        must_change_password=True,
                        is_active=True,
                        created_by=request.user
                    )

                    user.parent = parent
                    user.save(update_fields=['parent'])
                    msg = f"Nouveau compte: {parent.display_name} ajouter "
                    Notifications.objects.create(destinataire=parent, type='nouveau_user', titre='Nouveau compte', contenu=msg, lu=False)

                

            LogsActivite.objects.create(
                user=request.user,
                action='create_user',
                table_cible='Users',
                id_cible=user.id,
                details_json={'role': role}
            )


            
            msg = f"Nouveau compte: {user.display_name} ajouter "
            Notifications.objects.create(destinataire=user, type='nouveau_user', titre='Nouveau compte', contenu=msg, lu=False)

      
            return Response({
                'message': 'Compte créé. Mot de passe : sabil',
                'user_id': str(user.id)
            }, status=201)

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()

        # 🔒 Sécurité : éviter auto-suppression
        if user == request.user:
            return Response(
                {"error": "Vous ne pouvez pas désactiver votre propre compte."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.is_active = False
        user.save(update_fields=['is_active'])

        LogsActivite.objects.create(
            user=request.user,
            action='deactivate_user',
            table_cible='Users',
            id_cible=user.id
        )

        return Response({"message": "Compte désactivé"}, status=200)
                
    @action(detail=True, methods=['post'])
    def reactivate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=['is_active'])

        LogsActivite.objects.create(
            user=request.user,
            action='reactivate_user',
            table_cible='Users',
            id_cible=user.id
        )

        return Response({"message": "Compte réactivé"})            
                


# ============================================================
# 2. THROTTLING — limite le nombre de tentatives (anti-spam / anti-bruteforce)
# ============================================================
 
class ForgotPasswordThrottle(AnonRateThrottle):
    scope = 'forgot_password'
    rate = '5/hour'  # ajuste selon ton besoin
 
 
class ResetPasswordThrottle(AnonRateThrottle):
    scope = 'reset_password'
    rate = '10/hour'
  
 
# ============================================================
# 3. VUES — à ajouter dans views.py
# ============================================================
 
class ForgotPasswordView(APIView):
    """
    POST /auth/forgot-password
    body: { "email": "..." }
 
    Génère un code à 6 chiffres et l'envoie par email si le compte existe.
    Répond TOUJOURS le même message, que l'email existe ou non,
    pour ne pas révéler quels comptes sont enregistrés.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ForgotPasswordThrottle]
 
    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
 
        if not email:
            return Response({"error": "Email requis."}, status=status.HTTP_400_BAD_REQUEST)
 
        user = Users.objects.filter(email__iexact=email, is_active=True).first()
 
        if user:
            code = f"{random.randint(0, 999999):06d}"
 
            PasswordResetCode.objects.create(
                user=user,
                code_hash=make_password(code),
                expires_at=timezone.now() + timedelta(minutes=15),
            )
 
            send_mail(
                subject="Réinitialisation de votre mot de passe - Sabil Al Ilm",
                message=(
                    f"Bonjour,\n\n"
                    f"Voici votre code de réinitialisation : {code}\n"
                    f"Ce code est valide pendant 15 minutes.\n\n"
                    f"Si vous n'avez pas demandé cette réinitialisation, ignorez cet email."
                ),
                from_email=None,  # utilise DEFAULT_FROM_EMAIL défini dans settings.py
                recipient_list=[user.email],
                fail_silently=False,
            )
 
        # ⚠️ Réponse identique, que le compte existe ou non
        return Response(
            {"message": "Si ce compte existe, un code a été envoyé par email."},
            status=status.HTTP_200_OK,
        )
 
 
class ResetPasswordView(APIView):
    """
    POST /auth/reset-password
    body: { "email": "...", "code": "123456", "new_password": "..." }
 
    Vérifie le code (non expiré, non utilisé) puis change le mot de passe.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ResetPasswordThrottle]
 
    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        code = (request.data.get('code') or '').strip()
        new_password = request.data.get('new_password') or ''
 
        if not email or not code or not new_password:
            return Response(
                {"error": "Email, code et nouveau mot de passe requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        if len(new_password) < 6:
            return Response(
                {"error": "Le mot de passe doit contenir au moins 6 caractères."},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        user = Users.objects.filter(email__iexact=email, is_active=True).first()
 
        # Message volontairement générique : ne pas distinguer "email inconnu" de "code invalide"
        generic_error = {"error": "Code invalide ou expiré."}
 
        if not user:
            return Response(generic_error, status=status.HTTP_400_BAD_REQUEST)
 
        reset_entry = PasswordResetCode.objects.filter(
            user=user,
            used=False,
            expires_at__gte=timezone.now(),
        ).order_by('-created_at').first()
 
        if not reset_entry or not check_password(code, reset_entry.code_hash):
            return Response(generic_error, status=status.HTTP_400_BAD_REQUEST)
 
        # ✅ Code valide → changer le mot de passe
        user.password = make_password(new_password)
        user.must_change_password = False
        user.save(update_fields=['password', 'must_change_password'])
 
        reset_entry.used = True
        reset_entry.save(update_fields=['used'])
 
        # Invalide aussi les autres codes en attente pour ce user (bonne pratique)
        PasswordResetCode.objects.filter(
            user=user, used=False
        ).exclude(id=reset_entry.id).update(used=True)
 
        LogsActivite.objects.create(
            user=user,
            action='reset_password',
            table_cible='Users',
            id_cible=user.id,
        )
 
        return Response(
            {"message": "Mot de passe réinitialisé avec succès."},
            status=status.HTTP_200_OK,
        )


class ClassViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ClassSerializer  # ← AJOUTER CETTE LIGNE
    
    def get_queryset(self):
        user = self.request.user

        include_deleted = self.request.query_params.get('include_deleted')

        qs = Classes.objects.filter(
            deleted_at__isnull=True
        ).order_by('-created_at')

        # ✅ cacher les supprimées seulement si on ne les demande pas
        if include_deleted != 'true':
            qs = qs.exclude(statut='supprimer')

        # 🔥 direction
        professeur_id = self.request.query_params.get('professeur_id')

        if professeur_id and user.role == 'direction':
            return qs.filter(professeur_id=professeur_id)

        # rôles
        if user.role == 'admin':
            return qs.filter(professeur__admin_id=user.id)

        if user.role == 'professeur':
            return qs.filter(professeur=user)

        if user.role == 'eleve':
            ids = Inscriptions.objects.filter(
                eleve=user
            ).values_list('classe_id', flat=True)

            return qs.filter(id__in=ids)

        return qs

    def perform_create(self, serializer):

        # 🔥 récupérer le professeur
        professeur = serializer.validated_data.get('professeur')

        if not professeur:
            raise ValidationError({
                "professeur": "Le professeur est obligatoire."
            })

        # 🔥 récupérer code_prof
        code_prof = professeur.code_prof.lower().strip()

        # 🔥 chercher les classes existantes
        existing_classes = Classes.objects.filter(
            professeur=professeur,
            nom__iregex=rf'^{code_prof}[0-9]+$'
        )

        # 🔥 trouver le plus grand numéro
        max_num = 0

        for c in existing_classes:
            match = re.search(r'(\d+)$', c.nom)

            if match:
                num = int(match.group(1))

                if num > max_num:
                    max_num = num

        # 🔥 nouveau nom
        generated_name = f"{code_prof}{max_num + 1}"

        # 🔥 générer jitsi_room_id
        jitsi_id = serializer.validated_data.get('jitsi_room_id')

        if not jitsi_id:
            jitsi_id = f"sabil-{uuid.uuid4().hex[:12]}"

        serializer.save(
            nom=generated_name,
            created_by=self.request.user,
            jitsi_room_id=jitsi_id,
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )

        msg = f"Ajout de la classe {generated_name}"
        Notifications.objects.create(destinataire=professeur, type='nouvelle_classe', titre='ajout classe', contenu=msg, lu=False)


class InscriptionViewSet(viewsets.ModelViewSet):
    queryset = Inscriptions.objects.all()
    permission_classes = [permissions.IsAuthenticated, CanManageInscriptions]
    serializer_class = InscriptionSerializer  # ← AJOUTER CETTE LIGNE

    def get_queryset(self):
        """Filtrage par classe via ?classe={id} + expansion de l'élève
        + filtrage par genre : n'affiche que les élèves du même genre que le professeur"""
        qs = super().get_queryset()
        classe_id = self.request.query_params.get('classe')
    
        if classe_id:
            qs = qs.filter(classe_id=classe_id)
    
            # 🔍 Récupère le professeur de cette classe pour connaître son genre
            classe = Classes.objects.select_related('professeur').filter(id=classe_id).first()
    
            if classe and classe.professeur and classe.professeur.homme_femme:
                genre_prof = classe.professeur.homme_femme
                qs = qs.filter(eleve__homme_femme=genre_prof)
    
        return qs.select_related('eleve')  # ✅ Optimisation N+1

    def perform_create(self, serializer):
        inscription = serializer.save(
            id=uuid.uuid4(),
            created_at=timezone.now(),
            statut = 'active'
        )

        msg_prof = f"Inscription de l'eleve {inscription.eleve.display_name}"
        msg_eleve = f"vous etes inscrit a la classe {inscription.classe.nom}"
        Notifications.objects.create(destinataire=inscription.classe.professeur, type='inscription_eleve', titre='inscription eleve', contenu=msg_prof, lu=False)
        Notifications.objects.create(destinataire=inscription.eleve, type='inscription_eleve', titre='inscription eleve', contenu=msg_eleve, lu=False)



class SeanceViewSet(viewsets.ModelViewSet):
    queryset = Seances.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SeanceSerializer  # ← AJOUTER CETTE LIGNE


class SeanceJourViewSet(viewsets.ModelViewSet):
    serializer_class = SeanceJourSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'eleve':
            # Séances des classes dans lesquelles l'élève est inscrit
            return Seances.objects.filter(
                classe__inscriptions__eleve=user
            ).select_related('classe').distinct()
        # Professeur : ses propres classes
        return Seances.objects.filter(
            classe__professeur=user
        ).select_related('classe')

    @action(detail=False, methods=['get'])
    def today(self, request):
        day_names = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
        today_idx = datetime.today().weekday()
        jour_seance = day_names[today_idx]

        user = request.user

        if user.role == 'eleve':
            qs = Seances.objects.filter(
                classe__inscriptions__eleve=user,
                jour_seance=jour_seance
            ).select_related('classe').distinct()
        else:
            # Professeur
            qs = Seances.objects.filter(
                classe__professeur=user,
                jour_seance=jour_seance
            ).select_related('classe')

        qs = qs.exclude(statut='supprimer').order_by('heure_debut_reelle')


        today = timezone.now().date()

        # Récupère les IDs de séances déjà réalisées aujourd'hui
        # selon la logique exacte de get_queryset() de PresencesViewSet

        absence_prof_valide = AbsencesProfs.objects.filter(
            presence=OuterRef('pk'),
        ).exclude(
            Q(temps_effectif=False) & Q(durree_eleve__isnull=True)
        )
        absence_prof_valide_system = AbsencesProfs.objects.filter(
            presence=OuterRef('pk'),
        ).exclude(
            Q(resp_query_fin_prof=False)
        )

        presences_realisees = Presences.objects.filter(
            seance__in=qs,
            created_at__date=today,
        ).filter(
            (
                Q(enregistrement_system=False)
                & Exists(absence_prof_valide)
                
            )
            |
            (
                Q(heure_connexion__isnull=False)
                & Q(heure_deconnexion__isnull=False)
                & Q(jitsi_room_id__isnull=False)
                & (
                    Q(enregistrement_system__isnull=True)
                    | Q(enregistrement_system=True)
                )
                & Exists(absence_prof_valide_system)
            )
        ).values_list('seance_id', flat=True)

        qs = qs.exclude(id__in=presences_realisees)
        
        serializer = self.get_serializer(qs, many=True)


        
        return Response(serializer.data)

class CatalogueCoursViewSet(viewsets.ModelViewSet):
    queryset = CatalogueCours.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CatalogueCoursSerializer  # ← CETTE LIGNE
    
    def get_queryset(self):
        # Optionnel : filtrer par niveau ou rôle
        user = self.request.user
        qs = CatalogueCours.objects.all()
        if user.role == 'eleve':
            # Montrer uniquement les cours accessibles (prérequis validés)
            # Logique à personnaliser
            pass
        return qs.order_by('niveau')
    
    @action(detail=False, methods=['get'], permission_classes=[IsEleve])
    def parcours(self, request):
        """Retourne l'arbre complet des cours avec progression pour l'élève."""
        cours = CatalogueCours.objects.all().prefetch_related('est_prerequis_de_set')
        serializer = self.get_serializer(cours, many=True, context={'request': request})
        return Response(serializer.data)


class MyDiplomesView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DiplomeSerializer

    def get_queryset(self):
        return Diplomes.objects.filter(eleve=self.request.user).order_by('-delivre_at')


class DiplomeViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DiplomeSerializer
    
    # ✅ Indispensable : permet à DRF de comprendre le FormData (texte + fichier)
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        user = self.request.user
        qs = Diplomes.objects.select_related('eleve', 'classe', 'professeur').order_by('-created_at')

        if hasattr(user, 'role') and user.role == 'professeur':
            qs = qs.filter(professeur=user)
        if hasattr(user, 'role') and user.role == 'eleve':
            qs = qs.filter(eleve=user)

        # Filtres optionnels
        classe_id = self.request.query_params.get('classe_id')
        eleve_id = self.request.query_params.get('eleve_id')
        if classe_id:
            qs = qs.filter(classe_id=classe_id)
        if eleve_id:
            qs = qs.filter(eleve_id=eleve_id)

        return qs

    # ✅ On ne touche PAS à la méthode create(). 
    # DRF appellera automatiquement :
    # 1. serializer = self.get_serializer(data=request.data)
    # 2. serializer.is_valid(raise_exception=True)
    # 3. self.perform_create(serializer)  <--- C'est ici qu'on intervient

    def perform_create(self, serializer):
        # 1. On récupère le fichier brut envoyé par le frontend (GenerateurDiplome.tsx)
        fichier = self.request.FILES.get('image_diplome')
        
        # 2. On sauvegarde l'instance via le serializer. 
        # C'est cette ligne qui déclenche l'enregistrement physique du fichier sur le disque 
        # et la sauvegarde des champs texte (classe, eleve, matiere, etc.)
        instance = serializer.save(
            professeur=self.request.user,
            created_at=timezone.now(),
        )
        
        # 3. Si un fichier a bien été fourni, on extrait et on sauvegarde ses métadonnées
        if fichier:
            instance.nom_original = fichier.name
            instance.nom_stockage = instance.image_diplome.name # Le nom tel qu'enregistré par Django (avec le dossier %Y/%m/)
            instance.type_fichier = fichier.name.split('.')[-1].lower() if '.' in fichier.name else ''
            instance.mime_type = fichier.content_type
            instance.taille_bytes = fichier.size
            
            # On met à jour uniquement ces champs en base pour une requête SQL ultra-rapide
            instance.save(update_fields=[
                'nom_original', 'nom_stockage', 'type_fichier', 'mime_type', 'taille_bytes'
            ])


class ElevesByClasseView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, classe_id):
        eleves = (
            Users.objects.filter(
                inscriptions__classe_id=classe_id,
                inscriptions__statut='active',
                role='eleve',
                is_active=True,
            )
            .distinct()
            .values('id', 'display_name', 'email')
            .order_by('display_name')
        )
        return Response([
            {
                'id':           str(e['id']),
                'display_name': e['display_name'] or e['email'],
                'email':        e['email'],
            }
            for e in eleves
        ])


class ContratViewSet(viewsets.ModelViewSet):
    queryset = Contrats.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ContratSerializer  # ← AJOUTER CETTE LIGNE

    @action(detail=False, methods=['post'])
    def sign(self, request):
        eleve_id = request.data.get('eleve')
        classe_id = request.data.get('classe')
        
        if not classe_id:
            return Response({'error': 'eleve et classe requis.'}, status=400)
        
        # Vérifier que l'inscription existe
        try:
            inscription = Inscriptions.objects.get(eleve_id=eleve_id, classe_id=classe_id)
        except Inscriptions.DoesNotExist:
            return Response({'error': 'Inscription introuvable.'}, status=404)
        
        # Créer le contrat
        Contrats.objects.create(
            id=uuid.uuid4(),
            eleve_id=eleve_id,
            classe_id=classe_id,
            version_reglement=request.data.get('version_reglement', '1.0'),
            contenu_snapshot=request.data.get('contenu_snapshot', ''),
            ip_signature=request.META.get('REMOTE_ADDR'),  # ✅ nom correct
            signe_at=timezone.now(),                        # ✅ nom correct
        )
        
        # Mettre à jour l'inscription
        inscription.contrat_signe = True
        inscription.contrat_signe_at = timezone.now()
        inscription.contrat_ip=request.META.get('REMOTE_ADDR')  # ✅ tracer l'IP aussi
        inscription.save(update_fields=['contrat_signe', 'contrat_signe_at', 'contrat_ip'])
        
        return Response({'message': 'Contrat signé électroniquement.'}, status=201)

    
class MessageViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MessageSerializer  # ← AJOUTER CETTE LIGNE
    def get_queryset(self):
        user = self.request.user
        classe_id = self.request.query_params.get('classe_id')
        qs = Messages.objects.filter(deleted_at__isnull=True)
        if classe_id:
            qs = qs.filter(classe_id=classe_id)
             # ✅ Vérifier si message déjà envoyé
             # ✅ Seulement pour les élèves
            if user.role == 'eleve':
                already_exists = Messages.objects.filter(
                    classe_id=classe_id,
                    type_message='systeme',
                    contenu__contains=f'WELCOME_{user.id}'
                ).exists()

                if not already_exists:

                    classe = Classes.objects.get(id=classe_id)

                    # ✅ utilisateur direction
                    direction_user = Users.objects.filter(
                        role='direction'
                    ).first()

                    if direction_user:
                        Messages.objects.create(
                            id=uuid.uuid4(),
                            expediteur=direction_user,
                            classe=classe,
                            type_canal='chat_groupe',
                            type_message='systeme',
                            contenu=(
                                f"""
                                Nous espérons que vous allez bien 

                                Quelques paroles pleines de sagesse pour se motiver 

                                « Le serviteur ne fera pas un seul pas le jour de la résurrection auprès de son Seigneur sans qu'il ne soit interrogé sur cinq choses : sur son existence : comment l'a t'il passée ? 
                                sur sa jeunesse : comment l'a-t-il utilisée ?  
                                ses biens : par quels moyens les a-t-il gagnés et
                                dans quoi les a-t-il dépensés ? 
                                son savoir : qu'a-t-il appliqué de ce qu'il a appris ?» 
                                [voir as-sahiha n.946]

                                Muhammad ibn an-Nadr al-Harithi a dit : 
                                Le début de la science est le silence, 
                                puis l’écoute attentive,
                                puis sa mémorisation,
                                puis sa mise en pratique,
                                puis sa transmission.» 

                                Ja’far as-Sadiq a dit : « Le coeur est une terre fertile, la science est sa graine, et la révision est son eau. Si la terre est privée de son eau, la graine se dessèche. »

                                Shaikh Muqbil a dit رحمه الله :
                                « Ô mes enfants, je jure par Allah que si la science pouvait être versée dans un verre, je la verserais pour vous... »

                                D'après Abou Hourayra :
                                « Ô Allah, rend profitable ce que tu m'as appris... »

                                Après toutes ces belles paroles 
                                Baarak Allahou fikoum de noter votre prénom ou kounia 

                                QuAllah vous accorde une science utile et bénéfique آمين
                                """
                            ),
                            is_systeme=True,
                            fichier=None,
                            reply_to=None,
                            created_at=timezone.now(),
                        )


                        # ✅ Message 2
                        Messages.objects.create(
                            id=uuid.uuid4(),
                            expediteur=direction_user,
                            classe=classe,
                            type_canal='chat_groupe',
                            type_message='systeme',
                            contenu=f"""WELCOME_{user.id}

                            Rappel de début de session sur le comportement 

                            Les Salafs apprenaient le comportement et les politesse 20 ans avant d’apprendre la science. 

                            Il y a beaucoup de professeur qui arrêtent d’enseigner à cause du comportement des élèves.

                            On essaye d'être 10min avant le cours...

                            Mettez une alarme à votre téléphone...

                            L’étudiant se doit d’être en avance sur son professeur.

                            (Suite de ton texte...)

                            QuAllah nous accorde le bon comportement et la sincérité آمين
                            """,
                            is_systeme=True,
                            created_at=timezone.now(),
                        )

        return qs.select_related('expediteur',
                                'fichier',
                                'reply_to',
                                'reply_to__expediteur',
                                'reply_to__fichier',
                                ).order_by('created_at')

    def perform_create(self, serializer):
        classe_id = self.request.data.get('classe_id') or self.request.data.get('classe')
        fichier_upload = self.request.FILES.get('fichier')
        
        if not classe_id:
            raise serializers.ValidationError({'classe': 'Classe requise.'})
        
        try:
            classe = Classes.objects.get(id=classe_id)
        except Classes.DoesNotExist:
            raise serializers.ValidationError({'classe': 'Classe introuvable.'})

        type_message = self.request.data.get('type_message', 'texte')
        is_voice_note = str(self.request.data.get('is_voice_note', 'false')).lower() == 'true'
        fichier_expires_at = None

        # Règle : Expiration dans 14 jours SAUF si c'est une note vocale
        if fichier_upload and type_message in ['fichier', 'image', 'audio', 'video'] and not is_voice_note:
            fichier_expires_at = timezone.now() + timedelta(days=14)
        
        fichier_instance = None
        if fichier_upload:
            # Détermination du type
            mime_type = fichier_upload.content_type or mimetypes.guess_type(fichier_upload.name)[0] or 'application/octet-stream'
            type_fichier = 'autre'
            if mime_type.startswith('image/'): type_fichier = 'image'
            elif mime_type.startswith('video/'): type_fichier = 'video'
            elif mime_type.startswith('audio/'): type_fichier = 'audio'
            else: type_fichier = 'document'

            # 🆕 CORRECTION : Générer le nom de stockage (obligatoire dans votre modèle)
            file_id = uuid.uuid4()
            ext = os.path.splitext(fichier_upload.name)[1]
            nom_stockage = f"chat_{file_id}{ext}"

            fichier_instance = Fichiers.objects.create(
                id=file_id,
                uploade_par=self.request.user,
                classe=classe,
                nom_original=fichier_upload.name,
                nom_stockage=nom_stockage, # 🆕 OBLIGATOIRE
                fichier_local=fichier_upload, 
                type_fichier=type_fichier,
                mime_type=mime_type,
                taille_bytes=fichier_upload.size,
                fichier_expires_at=fichier_expires_at,
                is_voice_note=is_voice_note,
                created_at=timezone.now(),
            )
        
        # 🆕 CORRECTION : Passer aussi fichier_expires_at et is_voice_note au Message

        # Récupérer reply_to depuis la requête
        reply_to_id = self.request.data.get('reply_to')
        reply_to_instance = None
        if reply_to_id:
            try:
                reply_to_instance = Messages.objects.get(id=reply_to_id)
            except Messages.DoesNotExist:
                pass
        serializer.save(
            id=uuid.uuid4(),
            expediteur=self.request.user,
            classe=classe,
            type_canal='chat_groupe',
            type_message=type_message,
            contenu=self.request.data.get('contenu', ''),
            fichier=fichier_instance,
            is_systeme=False,
            reply_to=reply_to_instance,
            created_at=timezone.now(),
        )

         
        msg = f"nouveau message de {self.request.user.display_name}"
        direction = Users.objects.get(role='direction', is_active=True)
        if self.request.user.role =="direction":
            Notifications.objects.create(destinataire=classe.professeur, type='new_message_chat_classe', classe=classe, titre='Nouveau message de groupe', contenu=msg, lu=False)
            inscriptions = Inscriptions.objects.filter(classe=classe)
        
            notifications = [
                Notifications(
                    destinataire=inscription.eleve,
                    type='new_message_chat_classe',
                    titre='Nouveau message de groupe',
                    classe=seance.classe,
                    contenu=msg,
                    lu=False
                )
                for inscription in inscriptions
            ]
            
            Notifications.objects.bulk_create(notifications)
        elif self.request.user.role =="eleve":
            Notifications.objects.create(destinataire=direction, type='new_message_chat_classe', classe=classe, titre='Nouveau message de groupe', contenu=msg, lu=False)
            Notifications.objects.create(destinataire=classe.professeur, type='new_message_chat_classe', classe=classe, titre='Nouveau message de groupe', contenu=msg, lu=False)
        else:
            Notifications.objects.create(destinataire=direction, type='new_message_chat_classe', classe=classe, titre='Nouveau message de groupe', contenu=msg, lu=False)
            inscriptions = Inscriptions.objects.filter(classe=classe)
        
            notifications = [
                Notifications(
                    destinataire=inscription.eleve,
                    type='new_message_chat_classe',
                    titre='Nouveau message de groupe',
                    classe=classe,
                    contenu=msg,
                    lu=False
                )
                for inscription in inscriptions
            ]
            
            Notifications.objects.bulk_create(notifications)
  
 


    def perform_destroy(self, instance):
        """Soft delete pour le DELETE /messages/<id>/ (suppression unique)."""
        if self.request.user.role not in ('direction', 'admin'):
            raise PermissionDenied("Seuls direction et admin peuvent supprimer des messages.")
        instance.deleted_at = timezone.now()
        instance.save(update_fields=['deleted_at'])

    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        """Suppression multiple style WhatsApp : POST {ids: [...]}"""
        if request.user.role not in ('direction', 'admin'):
            return Response(
                {'detail': "Permission refusée."},
                status=status.HTTP_403_FORBIDDEN
            )
        ids = request.data.get('ids', [])
        if not ids:
            return Response(
                {'detail': "Aucun message sélectionné."},
                status=status.HTTP_400_BAD_REQUEST
            )
        updated = Messages.objects.filter(
            id__in=ids, deleted_at__isnull=True
        ).update(deleted_at=timezone.now())
        return Response({'deleted': updated}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='lu')
    def mark_lu(self, request, pk=None):
        msg = self.get_object()
        user_id = str(request.user.id)
        changed = False
        if user_id not in (msg.recu_par or []):
            msg.recu_par = list(msg.recu_par or []) + [user_id]
            changed = True
        if user_id not in (msg.lu_par_ids or []):
            msg.lu_par_ids = list(msg.lu_par_ids or []) + [user_id]
            changed = True
        if changed:
            msg.save(update_fields=['recu_par', 'lu_par_ids'])
        return Response({'ok': True})

class PrivateMessageViewSet(viewsets.ModelViewSet):
    queryset = MessagesPrives.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PrivateMessageSerializer

    def get_queryset(self):
        user = self.request.user
        qs = MessagesPrives.objects.filter(deleted_at__isnull=True).order_by('created_at')

        if user.role == 'admin':
            destinataire_id = self.request.query_params.get('destinataire')
            if destinataire_id:
                return qs.filter(
                    models.Q(expediteur=user, destinataire_id=destinataire_id) |
                    models.Q(expediteur_id=destinataire_id, destinataire=user)
                )
            return qs.filter(models.Q(expediteur=user) | models.Q(destinataire=user))

        elif user.role == 'eleve':
            return qs.filter(models.Q(expediteur=user) | models.Q(destinataire=user))
        elif user.role == 'direction':
            expediteur_id = self.request.query_params.get('expediteur')
            if expediteur_id:
                return qs.filter(
                    models.Q(expediteur=user, destinataire_id=expediteur_id) |
                    models.Q(expediteur_id=expediteur_id, destinataire=user)
                )
            return qs.filter(models.Q(expediteur=user) | models.Q(destinataire=user))

        return qs.none()

    def perform_create(self, serializer):
        exp = self.request.user
        dest_id = self.request.data.get('destinataire')

        if exp.role == 'eleve':
            if not dest_id:
                admin = Users.objects.filter(role='admin', is_active=True).first()
                if not admin:
                    raise serializers.ValidationError('Aucun admin disponible.')
                dest_id = admin.id
            elif not Users.objects.filter(id=dest_id, role='admin').exists():
                raise serializers.ValidationError('Destinataire invalide.')
        elif exp.role == 'admin':
            if not dest_id:
                raise serializers.ValidationError('Destinataire requis.')
            if not Users.objects.filter(id=dest_id, role__in=['eleve', 'direction']).exists():
                raise serializers.ValidationError('Destinataire invalide.')
        elif exp.role == 'direction':
            if not dest_id:
                admin = Users.objects.filter(role='admin', is_active=True).first()
                if not admin:
                    raise serializers.ValidationError('Aucun admin disponible.')
                dest_id = admin.id
            elif not Users.objects.filter(id=dest_id, role='admin').exists():
                raise serializers.ValidationError('Destinataire invalide.')
        else:
            raise serializers.ValidationError('Vous ne pouvez pas envoyer de messages privés.')

        # ── Gestion fichier / type_message (identique à MessageViewSet) ──
        fichier_upload = self.request.FILES.get('fichier')
        type_message = self.request.data.get('type_message', 'texte')
        is_voice_note = str(self.request.data.get('is_voice_note', 'false')).lower() == 'true'
        fichier_expires_at = None

        if fichier_upload and type_message in ['fichier', 'image', 'audio', 'video'] and not is_voice_note:
            fichier_expires_at = timezone.now() + timedelta(days=14)

        fichier_instance = None
        if fichier_upload:
            mime_type = fichier_upload.content_type or mimetypes.guess_type(fichier_upload.name)[0] or 'application/octet-stream'
            if mime_type.startswith('image/'): type_fichier = 'image'
            elif mime_type.startswith('video/'): type_fichier = 'video'
            elif mime_type.startswith('audio/'): type_fichier = 'audio'
            else: type_fichier = 'document'

            file_id = uuid.uuid4()
            ext = os.path.splitext(fichier_upload.name)[1]
            nom_stockage = f"prive_{file_id}{ext}"

            fichier_instance = Fichiers.objects.create(
                id=file_id,
                uploade_par=exp,
                classe=None,
                nom_original=fichier_upload.name,
                nom_stockage=nom_stockage,
                fichier_local=fichier_upload,
                type_fichier=type_fichier,
                mime_type=mime_type,
                taille_bytes=fichier_upload.size,
                fichier_expires_at=fichier_expires_at,
                is_voice_note=is_voice_note,
                created_at=timezone.now(),
            )

        # ── reply_to ──
        reply_to_id = self.request.data.get('reply_to')
        reply_to_instance = None
        if reply_to_id:
            try:
                reply_to_instance = MessagesPrives.objects.get(id=reply_to_id)
            except MessagesPrives.DoesNotExist:
                pass

        serializer.save(
            id=uuid.uuid4(),
            expediteur=exp,
            destinataire_id=dest_id,
            type_message=type_message,
            fichier=fichier_instance,
            reply_to=reply_to_instance,
            lu=False,
            lu_at=None,
            created_at=timezone.now(),
        )

    def perform_destroy(self, instance):
        """Soft delete (DELETE /messages-prives/<id>/)."""
        if self.request.user.role != 'admin':
            raise PermissionDenied("Seul l'admin peut supprimer des messages.")
        instance.deleted_at = timezone.now()
        instance.save(update_fields=['deleted_at'])

    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        if request.user.role != 'admin':
            return Response({'detail': "Permission refusée."}, status=status.HTTP_403_FORBIDDEN)
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'detail': "Aucun message sélectionné."}, status=status.HTTP_400_BAD_REQUEST)
        updated = MessagesPrives.objects.filter(id__in=ids, deleted_at__isnull=True).update(deleted_at=timezone.now())
        return Response({'deleted': updated}, status=status.HTTP_200_OK)


class AnnoncesGroupeViewSet(viewsets.ModelViewSet):
    """
    CRUD annonces — direction uniquement.
    GET  /annonces-groupe/                          → liste
    POST /annonces-groupe/                          → créer (multipart)
    GET  /annonces-groupe/{id}/                     → détail + destinataires
    DEL  /annonces-groupe/{id}/                     → supprimer
    GET  /annonces-groupe/classes/                  → classes avec nb_eleves
    GET  /annonces-groupe/eleves-par-classe/{id}/   → élèves actifs d'une classe
    """
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [IsDirection]
 
    def get_queryset(self):
        return AnnoncesGroupe.objects.prefetch_related(
            'annoncesEleves_set__eleve'
        ).order_by('-created_at')
 
    def get_serializer_class(self):
        if self.action == 'list':
            return AnnoncesGroupeListSerializer
        return AnnoncesGroupeSerializer
 
    @action(detail=False, methods=['get'], url_path='classes')
    def classes(self, request):
        """Liste des classes actives avec nb élèves."""
        qs = Classes.objects.filter(
            statut='active',
            deleted_at__isnull=True
        ).select_related('professeur').order_by('nom')
        return Response(ClasseSimpleSerializer(qs, many=True).data)
 
    @action(detail=False, methods=['get'], url_path='eleves-par-classe/(?P<classe_id>[^/.]+)')
    def eleves_par_classe(self, request, classe_id=None):
        """Élèves actifs inscrits dans une classe donnée."""
        inscrits = Inscriptions.objects.filter(
            classe_id=classe_id,
            statut='active'
        ).select_related('eleve').order_by('eleve__display_name')
 
        eleves = [i.eleve for i in inscrits]
        return Response(EleveSimpleSerializer(eleves, many=True).data)
 
 
# ── ViewSet Élève ──────────────────────────────────────────────────────────────
 
class AnnoncesEleveViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Annonces reçues par l'élève connecté.
    GET  /mes-annonces/          → liste (non lues en premier)
    GET  /mes-annonces/{id}/     → détail + marquer lu automatiquement
    POST /mes-annonces/{id}/lire/ → marquer comme lu explicitement
    """
    serializer_class = AnnonceEleveDetailSerializer
    permission_classes = [IsAuthenticated]
 
    def get_queryset(self):
        return AnnoncesEleves.objects.filter(
            eleve=self.request.user
        ).select_related('annonces_groupe').order_by('statut', '-annonces_groupe__created_at')
 
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Marquer lu automatiquement à l'ouverture
        if not instance.statut:
            instance.statut = True
            instance.save(update_fields=['statut'])
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
 
    @action(detail=True, methods=['post'], url_path='lire')
    def lire(self, request, pk=None):
        """POST /mes-annonces/{id}/lire/ — marquer explicitement comme lu."""
        instance = self.get_object()
        instance.statut = True
        instance.save(update_fields=['statut'])
        return Response({'statut': True})


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notifications.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationSerializer  # ← AJOUTER CETTE LIGNE

    def get_queryset(self):
        return Notifications.objects.filter(destinataire=self.request.user).order_by('-created_at')
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notif = self.get_object()
        notif.lu = True
        notif.lu_at = timezone.now()
        notif.save(update_fields=['lu', 'lu_at'])
        return Response({'message': 'Lu.'})

class AbsenceProfViewSet(viewsets.ModelViewSet):
    queryset = AbsencesProfs.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AbsenceProfSerializer  # ← AJOUTER CETTE LIGNE

    def get_queryset(self):
        if self.request.user.role in ('direction', 'admin'):
            return AbsencesProfs.objects.all()
        return AbsencesProfs.objects.none()




class ClassAbsencesProfFeedbackView(APIView):
    """
    POST /classes/<uuid:pk>/absences-profs/
    Body: {
        "seance_id": "...",
        "type": "resp_query_10_prof"|"resp_query_fin_prof",
        "students": [{"student_id": "...", "present": true|false}, ...]
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, pk):
        # 1. Vérifier l'accès à la classe
        try:
            classe = Classes.objects.get(id=pk)
        except Classes.DoesNotExist:
            return Response({'error': 'Classe introuvable'}, status=404)
        
        if request.user.role not in ('professeur', 'admin', 'direction'):
            return Response({'error': 'Accès réservé aux professeurs'}, status=403)
        
        # 2. Récupérer les données
        feedback_type = request.data.get('type')
        seance_id = request.data.get('seance_id')
        students = request.data.get('students', [])
        
        if feedback_type not in ('resp_query_10_prof', 'resp_query_fin_prof'):
            return Response({'error': 'Type de feedback invalide'}, status=400)
        
        # 3. Trouver la présence du professeur pour cette séance
        prof_presence = Presences.objects.filter(
            seance_id=seance_id,
            classe=classe,
            user=request.user
        ).first()
        
        if not prof_presence:
            # Fallback : présence du prof aujourd'hui dans cette classe
            prof_presence = Presences.objects.filter(
                classe=classe,
                user=request.user,
                date_seance=timezone.now().date()
            ).order_by('-created_at').first()
        
        if not prof_presence:
            return Response({'error': 'Présence du professeur non trouvée'}, status=400)
        
        # 4. Traiter chaque élève
        results = []
        for student_data in students:
            student_id = student_data.get('student_id')
            is_present = student_data.get('present')
            
            # ✅ Validation stricte de l'UUID
            try:
                student_uuid = uuid.UUID(str(student_id).strip())
            except (ValueError, AttributeError):
                print(f"⚠️ UUID invalide ignoré: {student_id}")
                continue  # Skip cet élève, ne pas faire planter toute la requête
            
            if not isinstance(is_present, bool):
                continue
            
            try:
                # ✅ Utiliser eleve_id= pour passer l'UUID directement
                absence_prof, created = AbsencesProfs.objects.get_or_create(
                    presence=prof_presence,
                    eleve_id=student_uuid,  # ← _id suffix pour ForeignKey
                    defaults={'created_at': timezone.now(), feedback_type: True}
                )

                
                # ✅ Mise à jour fiable avec .update()
                AbsencesProfs.objects.filter(id=absence_prof.id).update(
                    **{feedback_type: is_present}
                )


                
                results.append({
                    'student_id': str(student_uuid),
                    feedback_type: is_present,
                    'created': created
                })
                
            except Exception as e:
                print(f"❌ Erreur pour élève {student_uuid}: {e}")
                # Continue avec les autres élèves au lieu de tout planter
                continue
        
        return Response({
            'status': 'ok',
            'feedback_type': feedback_type,
            'processed': len(results),
            'results': results
        })



# ─────────────────────────────────────────────────────────────────────────────
# GestionDevoirViewSet
# ─────────────────────────────────────────────────────────────────────────────

class GestionDevoirViewSet(viewsets.ModelViewSet):
    """
    CRUD devoirs + actions spécifiques prof :
      GET  /devoirs/?classe_id=<id>           → liste des devoirs d'une classe
      GET  /devoirs/<id>/eleves/              → élèves ayant participé au devoir
      POST /devoirs/<id>/upload-correction/   → upload fichier corrigé par le prof pour un élève
      GET  /devoirs/fichiers/<file_id>/download/ → téléchargement fichier élève
      PATCH /devoirs/<id>/corriger/           → passer le devoir en statut "corrige"
      PATCH /devoirs/<id>/noter/              → mettre à jour la note d'un élève
    """

    permission_classes = [IsAuthenticated]
    serializer_class = GestionDevoirSerializer
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    # ── Queryset de base ───────────────────────────────────────────────────────

    def get_queryset(self):
        user = self.request.user
        classe_id = self.request.query_params.get('classe_id')

        # Récupère les séances de la classe puis les devoirs associés
        qs = Devoirs.objects.select_related('seance', 'seance__classe').order_by('-created_at')

        if classe_id:
            seance_ids = Seances.objects.filter(classe_id=classe_id).values_list('id', flat=True)
            qs = qs.filter(seance_id__in=seance_ids)

        if user.role in ('direction', 'admin'):
            return qs
        elif user.role == 'professeur':
            return qs.filter(seance__classe__professeur=user)
        else:
            return qs.filter(
                seance__classe__inscriptions__eleve=user,
                statut__in=['soumis', 'cloturer', 'corrige'],
            )

    # ── Liste des élèves ayant participé à un devoir ──────────────────────────

    @action(detail=True, methods=['get'], url_path='eleves')
    def eleves(self, request, pk=None):
        """
        Retourne les élèves présents lors de la séance du devoir
        (matching par date_seance jour/mois/année uniquement).
        Pour chaque élève : infos + fichiers soumis + note.
        """
        devoir = self.get_object()
        seance_id = devoir.seance_id

        # Date du devoir (jour/mois/année seulement)
        devoir_date: date = devoir.created_at.date()

        # Présences pour cette séance dont la date correspond (sans les heures)
        presences = Presences.objects.filter(
            seance_id=seance_id,
            date_seance=devoir_date,
        )

        presence_ids = presences.values_list('id', flat=True)

        # AbsencesProfs reliées à ces présences
        absences = AbsencesProfs.objects.filter(
            presence_id__in=presence_ids,
        ).select_related('eleve')

        result = []
        for absence in absences:
            eleve = absence.eleve
            if not eleve:
                continue

            # Fichiers soumis par l'élève (statut_correction=False)
            fichiers_eleve = FichiersDevoir.objects.filter(
                devoir=devoir,
                eleve=eleve,
                statut_correction=False,
            )

            # Fichiers corrigés par le prof pour cet élève (statut_correction=True)
            fichiers_corriges = FichiersDevoir.objects.filter(
                devoir=devoir,
                eleve=eleve,
                statut_correction=True,
            )

            result.append({
                'absence_id': str(absence.id),
                'presence_id': str(absence.presence_id),
                'eleve': {
                    'id': str(eleve.id),
                    'display_name': eleve.display_name or eleve.email,
                    'email': eleve.email,
                },
                'note': absence.note_eleve,
                'fichiers_eleve': FichierDevoirSerializer(fichiers_eleve, many=True).data,
                'fichiers_corriges': FichierDevoirSerializer(fichiers_corriges, many=True).data,
            })

        return Response(result)

    # ── Upload fichier corrigé par le prof pour un élève ──────────────────────

    @action(detail=True, methods=['post'], url_path='upload-correction')
    def upload_correction(self, request, pk=None):
        """
        Upload un ou plusieurs fichiers corrigés par le prof pour un élève donné.
        Paramètre POST : eleve_id (UUID), files (multipart)
        """
        devoir = self.get_object()

        if request.user.role != 'professeur':
            return Response({'error': 'Réservé aux professeurs'}, status=403)

        eleve_id = request.data.get('eleve_id')
        if not eleve_id:
            return Response({'error': 'eleve_id requis'}, status=400)

        try:
            eleve = Users.objects.get(id=eleve_id)
        except Users.DoesNotExist:
            return Response({'error': 'Élève introuvable'}, status=404)

        files = request.FILES.getlist('files')
        if not files:
            return Response({'error': 'Aucun fichier fourni'}, status=400)

        uploaded = []
        for f in files:
            ext = os.path.splitext(f.name)[1]
            nom_stockage = f"devoirs/{devoir.id}/corrections/{eleve.id}/{uuid.uuid4()}{ext}"
            mime_type, _ = mimetypes.guess_type(f.name)

            saved_path = default_storage.save(nom_stockage, f)

            fichier_obj = FichiersDevoir.objects.create(
                devoir=devoir,
                eleve=eleve,
                nom_original=f.name,
                nom_stockage=saved_path,
                type_fichier='document',
                mime_type=mime_type or 'application/octet-stream',
                taille_bytes=f.size,
                statut_correction=True,
            )
            uploaded.append(FichierDevoirSerializer(fichier_obj).data)

        return Response({'uploaded': uploaded}, status=201)

    # ── Téléchargement d'un fichier ────────────────────────────────────────────

    @action(detail=False, methods=['get'], url_path='fichiers/(?P<file_id>[^/.]+)/download')
    def download_file(self, request, file_id=None):
        try:
            fichier = FichiersDevoir.objects.select_related('devoir__seance__classe').get(id=file_id)
        except FichiersDevoir.DoesNotExist:
            raise Http404("Fichier non trouvé")

        if not default_storage.exists(fichier.nom_stockage):
            raise Http404("Fichier physique introuvable sur le serveur")

        return FileResponse(
            default_storage.open(fichier.nom_stockage, 'rb'),
            as_attachment=True,
            filename=fichier.nom_original,
        )

    # ── Passer le devoir en statut "corrige" ──────────────────────────────────

    @action(detail=True, methods=['patch'], url_path='corriger')
    def corriger(self, request, pk=None):
        devoir = self.get_object()

        if request.user.role != 'professeur':
            return Response({'error': 'Réservé aux professeurs'}, status=403)

        if devoir.statut == 'corrige':
            return Response({'error': 'Devoir déjà corrigé'}, status=400)

        devoir.statut = 'corrige'
        devoir.corrige_at = timezone.now()
        devoir.save(update_fields=['statut', 'corrige_at'])

        return Response(GestionDevoirSerializer(devoir).data)

    # ── Mettre à jour la note d'un élève ─────────────────────────────────────

    @action(detail=True, methods=['patch'], url_path='noter')
    def noter(self, request, pk=None):
        """
        Body JSON: { "absence_id": "<uuid>", "note": "15/20" }
        On filtre AbsencesProfs par id pour s'assurer de la cohérence.
        """
        devoir = self.get_object()

        if request.user.role != 'professeur':
            return Response({'error': 'Réservé aux professeurs'}, status=403)

        absence_id = request.data.get('absence_id')
        note = request.data.get('note', '')

        if not absence_id:
            return Response({'error': 'absence_id requis'}, status=400)

        # Sécurité : on vérifie que l'absence correspond bien à une présence
        # de la séance du devoir, à la même date (jour/mois/année)
        devoir_date = devoir.created_at.date()
        try:
            absence = AbsencesProfs.objects.select_related('presence').get(
                id=absence_id,
                presence__seance_id=devoir.seance_id,
                presence__date_seance=devoir_date,
            )
        except AbsencesProfs.DoesNotExist:
            return Response({'error': 'Absence introuvable ou non liée à ce devoir'}, status=404)

        absence.note_eleve = note
        absence.save(update_fields=['note_eleve'])

        return Response({'absence_id': str(absence.id), 'note': absence.note_eleve})



class DevoirViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = DevoirSerializer
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    def get_queryset(self):
        user = self.request.user
        seance_id = self.request.query_params.get('seance_id')
        
        qs = Devoirs.objects.select_related('seance', 'seance__classe').prefetch_related('fichiersdevoir_set')
        
        # Filtre par séance si fourni
        if seance_id:
            qs = qs.filter(seance_id=seance_id)
        
        # Permissions par rôle
        if user.role in ('direction', 'admin'):
            return qs
        elif user.role == 'professeur':
            return qs.filter(seance__classe__professeur=user)
        else:  # eleve
            # Un élève voit les devoirs des séances où il est inscrit
            return qs.filter(
                seance__classe__inscriptions__eleve=user,
                statut__in=['soumis', 'cloturer']  # Ne voit que les devoirs soumis/cloturés
            )

    def perform_create(self, serializer):
        # Seul un prof peut créer, et on lie à sa classe
        if self.request.user.role != 'professeur':
            raise serializers.ValidationError("Seul un professeur peut créer un devoir")
        devoir = serializer.save()


        

        if self.request.user.role == "professeur":
            admin = self.request.user
            Notifications.objects.create(
            id=uuid.uuid4(),
            destinataire=admin,
            type='nouveau_devoir',
            titre='Nouveau Devoir',
            contenu=f'Nouveau Devoir',
            lu=False,
            classe=devoir.seance.classe,
            created_at=timezone.now(),)

            direction = Users.objects.get(role='direction', is_active=True)
            Notifications.objects.create(
                id=uuid.uuid4(),
                destinataire=direction,
                type='nouveau_devoir',
                titre='Nouveau Devoir',
                contenu=f'Nouveau Devoir',
                lu=False,
                classe=devoir.seance.classe,
                created_at=timezone.now(),
            )
            
            inscriptions = Inscriptions.objects.filter(classe=devoir.seance.classe)
            
            notifications = [
                Notifications(
                    destinataire=inscription.eleve,
                    type='nouveau_devoir',
                    titre='Nouveau Devoir',
                    classe=devoir.seance.classe,
                    contenu=f'Nouveau Devoir',
                    lu=False,
                    created_at=timezone.now(),
                )
                for inscription in inscriptions
            ]

    # ─────────────────────────────────────────────────────────────────────
    # 🔼 UPLOAD FICHIERS PROF (multipart, multiple)
    @action(detail=True, methods=['post'], url_path='upload-files')
    def upload_files(self, request, pk=None):
        devoir = self.get_object()
        
        if request.user.role != 'professeur' or devoir.seance.classe.professeur != request.user:
            return Response({'error': 'Non autorisé'}, status=403)
        if devoir.statut == 'cloturer':
            return Response({'error': 'Devoir clôturé'}, status=400)
        
        files = request.FILES.getlist('files')
        if not files:
            return Response({'error': 'Aucun fichier fourni'}, status=400)
        
        uploaded = []
        for f in files:
            ext = os.path.splitext(f.name)[1]
            nom_stockage = f"devoirs/{devoir.id}/prof/{uuid.uuid4()}{ext}"
            mime_type, _ = mimetypes.guess_type(f.name)
            
            # ✅ default_storage pointe automatiquement vers settings.MEDIA_ROOT
            saved_path = default_storage.save(nom_stockage, f)
            
            fichier_obj = FichiersDevoir.objects.create(
                devoir=devoir,
                eleve=None,
                nom_original=f.name,
                nom_stockage=saved_path,  # ← stocke le chemin relatif à media/
                type_fichier='document',
                mime_type=mime_type or 'application/octet-stream',
                taille_bytes=f.size,
                created_at=timezone.now()
            )
            uploaded.append(FichierDevoirSerializer(fichier_obj).data)
        
        return Response({'uploaded': uploaded}, status=201)


    # ─────────────────────────────────────────────────────────────────────
    # 🔼 UPLOAD COPIE ÉLÈVE (multipart, multiple) ✅
    @action(detail=True, methods=['post'], url_path='student-upload')
    def student_upload(self, request, pk=None):
        devoir = self.get_object()
        if request.user.role != 'eleve':
            return Response({'error': 'Réservé aux élèves'}, status=403)
        
        is_inscrit = Seances.objects.filter(
            id=devoir.seance_id,
            classe__inscriptions__eleve=request.user
        ).exists()
        if not is_inscrit:
            return Response({'error': 'Non inscrit à cette séance'}, status=403)
        if devoir.statut != 'soumis':
            return Response({'error': 'Devoir non disponible'}, status=400)
        
        files = request.FILES.getlist('files')
        if not files:
            return Response({'error': 'Aucun fichier fourni'}, status=400)
        
        uploaded = []
        for f in files:
            ext = os.path.splitext(f.name)[1]
            nom_stockage = f"devoirs/{devoir.id}/eleves/{request.user.id}/{uuid.uuid4()}{ext}"
            mime_type, _ = mimetypes.guess_type(f.name)
            
            saved_path = default_storage.save(nom_stockage, f)
            
            fichier_obj = FichiersDevoir.objects.create(
                devoir=devoir,
                eleve=request.user,
                nom_original=f.name,
                nom_stockage=saved_path,
                type_fichier='document',
                mime_type=mime_type or 'application/octet-stream',
                taille_bytes=f.size,
                created_at=timezone.now()
            )
            uploaded.append(FichierDevoirSerializer(fichier_obj).data)
        
        return Response({'uploaded': uploaded}, status=201)


    # ─────────────────────────────────────────────────────────────────────
    # 🔽 DOWNLOAD FICHIER
    @action(detail=False, methods=['get'], url_path='fichiers/(?P<file_id>[^/.]+)/download')
    def download_file(self, request, file_id=None):
        try:
            fichier = FichiersDevoir.objects.select_related('devoir__seance__classe').get(id=file_id)
        except FichiersDevoir.DoesNotExist:
            raise Http404("Fichier non trouvé")
        
        user = request.user
        # ... (tes vérifications de permissions restent identiques) ...
        
        # ✅ Ouvre le fichier depuis media/ sans hardcoder
        if not default_storage.exists(fichier.nom_stockage):
            raise Http404("Fichier physique introuvable sur le serveur")
            
        return FileResponse(
            default_storage.open(fichier.nom_stockage, 'rb'),
            as_attachment=True,
            filename=fichier.nom_original
        )
    
    # ─────────────────────────────────────────────────────────────────────
    # ✏️ UPDATE partiel pour statut (soumettre / clôturer)
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Vérif permissions pour modification statut
        if request.user.role == 'professeur':
            if instance.seance.classe.professeur != request.user:
                return Response({'error': 'Non autorisé'}, status=403)
        elif request.user.role == 'eleve':
            # Élève ne peut pas modifier le statut
            if 'statut' in request.data:
                return Response({'error': 'Vous ne pouvez pas modifier le statut'}, status=403)
        
        # Auto-set submitted_at si passage à 'soumis'
        if request.data.get('statut') == 'soumis' and not instance.submitted_at:
            self.get_object().submitted_at = timezone.now()
            self.get_object().save(update_fields=['submitted_at'])
        
        return super().partial_update(request, *args, **kwargs)



class PresenceViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PresenceSerializer

    def get_queryset(self):
        # Sécurité : un utilisateur ne voit que ses propres présences (sauf admin/direction)
        user = self.request.user
        if user.role in ('admin', 'direction'):
            return Presences.objects.all()
        return Presences.objects.filter(user=user)

    @action(detail=True, methods=['post'], url_path='feedback')
    def feedback(self, request, pk=None):
        """
        POST /presences/<uuid:pk>/feedback/
        Body: { "type": "resp_query_10_eleve"|"resp_query_fin_eleve", "response": "oui"|"non" }
        """
        presence = self.get_object()
        
        # Sécurité : seul l'élève concerné (ou admin) peut modifier sa présence
        if request.user != presence.user and request.user.role not in ('admin', 'direction'):
            return Response({'error': 'Accès refusé'}, status=403)
        
        feedback_type = request.data.get('type')
        response_value = request.data.get('response')  # 'oui' ou 'non'
        
        # Validation
        if feedback_type not in ('resp_query_10_eleve', 'resp_query_fin_eleve'):
            return Response({'error': 'Type de feedback invalide'}, status=400)
        if response_value not in ('oui', 'non'):
            return Response({'error': 'Réponse doit être "oui" ou "non"'}, status=400)
        
        # Conversion oui/non → True/False
        bool_value = (response_value == 'oui')
        
        # Mise à jour du champ dynamique
        #setattr(presence, feedback_type, bool_value)
        #presence.save(update_fields=[feedback_type])
        Presences.objects.filter(id=presence.id).update(**{feedback_type: bool_value})
        
        return Response({
            'status': 'ok',
            'field_updated': feedback_type,
            'value': bool_value
        })



class SuiviPresenceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/suivi-presences/
    Retourne les présences éligibles à la facturation pour le professeur connecté.
    """
    serializer_class = SuiviPresenceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        # Sous-requête : existe-t-il un AbsencesProfs validé prof pour cette présence ?
        absence_prof_valide = AbsencesProfs.objects.filter(
            presence=OuterRef('pk'),
        )

        return (
            Presences.objects
            .filter(
                seance__isnull=False,
            )
            .filter(Exists(absence_prof_valide))   # au moins 1 absence_prof valide
            .select_related('classe', 'seance', 'user')
            .order_by('-created_at')
        )



class ProfFacturePresenceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/prof-facture-presences/
    Retourne les présences éligibles à la facturation pour le professeur connecté.
    """
    serializer_class = ProfFacturePresenceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        # Sous-requête : existe-t-il un AbsencesProfs validé prof pour cette présence ?
        
        absence_prof_valide = AbsencesProfs.objects.filter(
                presence=OuterRef('pk'),
            ).exclude(
                Q(temps_effectif=False) & Q(durree_eleve__isnull=True)
            )
        absence_prof_valide_system = AbsencesProfs.objects.filter(
                presence=OuterRef('pk'),
            ).exclude(
                Q(resp_query_fin_prof=False)
            )

        return (
            Presences.objects
            .filter(
                classe__professeur=user,
                seance__isnull=False,
            )
            .filter(
                (
                    Q(enregistrement_system=False)
                    & Exists(absence_prof_valide)
                )
                |
                (
                    Q(heure_connexion__isnull=False)
                    & Q(heure_deconnexion__isnull=False)
                    & Q(jitsi_room_id__isnull=False)
                    & (
                        Q(enregistrement_system__isnull=True)
                        | Q(enregistrement_system=True)
                    )
                    & Exists(absence_prof_valide_system)
                )
            )
            .select_related('classe', 'seance', 'user')
            .order_by('-created_at')
        )



class FactureEmiseViewSet(viewsets.ModelViewSet):
    """
    GET  /api/factures/                           → liste factures du prof
    POST /api/factures/                           → crée une facture
    GET  /api/factures/{id}/                      → détail
    POST /api/factures/{id}/remind/               → rappel
    POST /api/factures/preview/                   → aperçu avant création
    POST /api/factures/preview/participants/      → participants + montants
    POST /api/factures/{id}/participants/payment/ → mise à jour montants élèves
    GET  /api/factures/{id}/detail-seances/       → détail séances
    POST /api/factures/{id}/submit/               → soumet la facture
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'list' and self.request.user.role == 'professeur':
            return FactureAvecPaiementsSerializer
        if self.action == 'create':
            return FactureCreateSerializer
        return FactureSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Factures.objects.select_related('classe', 'professeur').order_by('-created_at')

        if user.role == 'admin':
            qs = qs.filter(professeur__admin_id=user.id)
            classe_id = self.request.query_params.get('classe_id')
            if classe_id:
                qs = qs.filter(classe_id=classe_id)
            return qs

        if user.role == 'direction':
            # Direction voit TOUTES les factures (filtrable par classe)
            classe_id = self.request.query_params.get('classe_id')
            if classe_id:
                qs = qs.filter(classe_id=classe_id)
            return qs

        # Professeur → ses propres factures
        return qs.filter(professeur=user)

    # ─────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────

    def _presences_dans_intervalle(self, user, classe_id, date_debut, date_fin):
        
        absence_prof_valide = AbsencesProfs.objects.filter(
            presence=OuterRef('pk'),
        ).exclude(
            Q(temps_effectif=False) & Q(durree_eleve__isnull=True)
        )

        absence_prof_valide_system = AbsencesProfs.objects.filter(
            presence=OuterRef('pk'),
        ).exclude(
            Q(resp_query_fin_prof=False)
        )

        return (
            Presences.objects
            .filter(
                classe__professeur=user,
                classe_id=classe_id,
                seance__isnull=False,
                created_at__date__gte=date_debut,
                created_at__date__lte=date_fin,
            )
            .filter(
                (
                    Q(enregistrement_system=False)
                    & Exists(absence_prof_valide)
                )
                |
                (
                    Q(heure_connexion__isnull=False)
                    & Q(heure_deconnexion__isnull=False)
                    & Q(jitsi_room_id__isnull=False)
                    & (
                        Q(enregistrement_system__isnull=True)
                        | Q(enregistrement_system=True)
                    )
                    & Exists(absence_prof_valide_system)
                )
            )
            .select_related('classe', 'seance', 'user')
            .order_by('-created_at')
        )

    def _get_duree_et_heures(self, p):
        """Retourne (duree_heures, heure_connexion, heure_deconnexion) pour une présence."""
        if p.enregistrement_system is False:
            temps_minutes    = p.temps_prof or 0
            duree_heures     = Decimal(str(round(temps_minutes / 60, 4)))
            heure_cx         = p.heure_connexion_prof
            heure_dcx        = (
                heure_cx + timedelta(minutes=temps_minutes) if heure_cx else None
            )
        else:
            heure_cx  = p.heure_connexion
            heure_dcx = p.heure_deconnexion
            duree_heures = (
                Decimal(str(round(
                    (heure_dcx - heure_cx).total_seconds() / 3600, 4
                )))
                if heure_cx and heure_dcx else Decimal('0')
            )
        return duree_heures, heure_cx, heure_dcx

    
    def _build_lignes(self, presences, nb_inscrits: int, type_cours: str):
        from collections import defaultdict

        # Regrouper par seance_id + date du cours
        presences_par_seance = defaultdict(list)
        for p in presences:
            cle = f"{p.seance_id}|{timezone.localtime(p.created_at).date()}"
            presences_par_seance[cle].append(p)

        lignes          = []
        total_heures    = Decimal('0')
        total_collecte  = Decimal('0')
        total_part_dir  = Decimal('0')
        total_part_prof = Decimal('0')

        for cle, seance_presences in presences_par_seance.items():
            duree_totale    = Decimal('0')
            nb_participants = 0
            premiere        = seance_presences[0]

            for p in seance_presences:
                absence = (
                    AbsencesProfs.objects
                    .filter(presence=p)
                    .exclude(Q(temps_effectif=False) & Q(durree_eleve__isnull=True))
                    .first()
                )
                if not absence:
                    continue

                duree_heures, heure_cx, heure_dcx = self._get_duree_et_heures(p)
                duree_totale += duree_heures

                nb_p = (
                    AbsencesProfs.objects
                    .filter(presence=p)
                    .exclude(Q(temps_effectif=False) & Q(durree_eleve__isnull=True))
                    .values('eleve')
                    .distinct()
                    .count()
                )
                nb_participants = max(nb_participants, nb_p)

            if duree_totale == 0:
                continue

            # Plafonner à la durée prévue de la séance
            if premiere.seance and premiere.seance.duree_reelle_minutes:
                duree_max = Decimal(str(round(premiere.seance.duree_reelle_minutes / 60, 4)))
                duree_totale = min(duree_totale, duree_max)

            # Heure affichage : première connexion → dernière déconnexion
            _, heure_cx_display, _       = self._get_duree_et_heures(seance_presences[0])
            _, _, heure_dcx_display      = self._get_duree_et_heures(seance_presences[-1])

            tarifs = calculer_tarifs(
                nb_inscrits=nb_inscrits,
                nb_participants=nb_participants,
                duree_heures=duree_totale,
                type_cours=type_cours,
            )

            total_heures    += duree_totale
            total_collecte  += tarifs['total_collecte']
            total_part_dir  += tarifs['part_direction']
            total_part_prof += tarifs['part_prof']

            lignes.append({
                'presence_id':              premiere.id,
                'seance_id':                premiere.seance_id,
                'date_seance':              premiere.created_at,
                'heure_connexion_prof':     heure_cx_display.strftime('%H:%M') if heure_cx_display else None,
                'heure_deconnexion':        heure_dcx_display.strftime('%H:%M') if heure_dcx_display else None,
                'duree_heures':             duree_totale,
                'nb_participants':          nb_participants,
                'nb_inscrits':              nb_inscrits,
                'type_cours_effectif':      tarifs['type_cours_effectif'],
                'tarif_eleve_par_personne': tarifs['tarif_eleve_par_personne'],
                'total_collecte_seance':    tarifs['total_collecte'],
                'part_direction_seance':    tarifs['part_direction'],
                'part_prof_seance':         tarifs['part_prof'],
            })

        return lignes, total_heures, total_collecte, total_part_dir, total_part_prof

    # ─────────────────────────────────────────────────────────────────────
    # POST /api/factures/preview/
    # ─────────────────────────────────────────────────────────────────────
    @action(detail=False, methods=['post'], url_path='preview')
    def preview(self, request):
        serializer = FactureCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        presences = self._presences_dans_intervalle(
            request.user, d['classe_id'], d['date_debut'], d['date_fin']
        )
        if not presences.exists():
            return Response(
                {'error': 'Aucune séance validée dans cet intervalle pour cette classe.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        classe      = Classes.objects.get(pk=d['classe_id'])
        nb_inscrits = Inscriptions.objects.filter(classe=classe).count()
        type_cours  = classe.type_cours or ''

        lignes, total_heures, total_collecte, part_direction, part_prof = \
            self._build_lignes(presences, nb_inscrits, type_cours)

        return Response({
            'lignes':                   FactureLigneSerializer(lignes, many=True).data,
            'total_heures':             total_heures,
            'nb_inscrits':              nb_inscrits,
            'type_cours':               type_cours,
            'total_collecte':           total_collecte,
            'part_direction':           part_direction,
            'part_prof':                part_prof,
            # rétrocompat
            'montant_total':            total_collecte,
            #'taux_horaire':             classe.taux_horaire,
            'honoraire':                total_heures,
            'nb_participants':          max(
                (l['nb_participants'] for l in lignes), default=0
            ),
        })

    # ─────────────────────────────────────────────────────────────────────
    # POST /api/factures/preview/participants/
    # ─────────────────────────────────────────────────────────────────────
    @action(detail=False, methods=['post'], url_path='preview/participants')
    def preview_participants(self, request):
        serializer = FactureCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        presences = self._presences_dans_intervalle(
            request.user, d['classe_id'], d['date_debut'], d['date_fin']
        )
        if not presences.exists():
            return Response(
                {'error': 'Aucune séance validée dans cet intervalle pour cette classe.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        participants_data = []
        for p in presences:
            absence = (
                AbsencesProfs.objects
                .filter(presence=p)
                .exclude(Q(temps_effectif=False) & Q(durree_eleve__isnull=True))
                .select_related('eleve')
                .first()
            )
            if not absence:
                continue

            participants_data.append({
                'absence_prof_id': absence.id,
                'eleve_id':        absence.eleve_id,
                'eleve_nom':       absence.eleve.get_full_name(),
                'eleve_email':     absence.eleve.email,
                'montant_a_paye':  absence.montant_a_paye,
                'presence_id':     p.id,
                'seance_id':       p.seance_id,
            })

        return Response(
            FactureParticipantSerializer(participants_data, many=True).data,
            status=status.HTTP_200_OK,
        )


    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """GET /api/factures-emises/stats/ — compteurs pour le dashboard prof."""
        prof = request.user
        
        # Classes actives du prof
        classes_actives = Classes.objects.filter(
            professeur=prof,
            statut='active',
            deleted_at__isnull=True
        )
        nb_classes = classes_actives.count()
        
        # Élèves inscrits dans ces classes actives
        nb_inscrits = Inscriptions.objects.filter(
            classe__in=classes_actives,
            statut='active'
        ).values('eleve').distinct().count()
        
        # Factures envoyées (en attente de paiement)
        nb_factures_envoyees = Factures.objects.filter(
            professeur=prof,
            statut='envoyee'
        ).count()
        
        # Factures payées
        nb_factures_payees = Factures.objects.filter(
            professeur=prof,
            statut='payee'
        ).count()
        
        # Montant total payé
        montant_paye = Factures.objects.filter(
            professeur=prof,
            statut='payee'
        ).aggregate(total=Sum('montant_total'))['total'] or 0

        return Response({
            'nb_classes_actives': nb_classes,
            'nb_inscrits': nb_inscrits,
            'nb_factures_envoyees': nb_factures_envoyees,
            'nb_factures_payees': nb_factures_payees,
            'montant_total_paye': montant_paye,
        })


    # ─────────────────────────────────────────────────────────────────────
    # POST /api/factures/{id}/participants/payment/
    # ─────────────────────────────────────────────────────────────────────
    @action(detail=True, methods=['post'], url_path='participants/payment')
    def update_participants_payment(self, request, pk=None):
        facture    = self.get_object()
        serializer = ParticipantsPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payeur_id          = data['payeur_id']
        participants_input = data['participants']
        montant_total      = facture.montant_total or Decimal('0')
        nb_p               = len(participants_input)
        default_amount     = montant_total / nb_p if nb_p > 0 else Decimal('0')

        updated_ids = []
        with transaction.atomic():
            for item in participants_input:
                try:
                    absence = AbsencesProfs.objects.select_for_update().get(
                        id=item['absence_prof_id'],
                        presence__classe=facture.classe,
                    )
                    absence.montant_a_paye  = (
                        item['montant_a_paye']
                        if item['montant_a_paye'] is not None
                        else default_amount
                    )
                    absence.facture_id      = facture
                    absence.payeur_id       = payeur_id
                    absence.statut_payement = 'emise'
                    absence.save(update_fields=[
                        'montant_a_paye', 'facture_id', 'payeur_id', 'statut_payement'
                    ])
                    updated_ids.append(str(absence.id))
                except AbsencesProfs.DoesNotExist:
                    continue

        return Response({
            'detail':        'Paiements mis à jour avec succès',
            'updated_count': len(updated_ids),
            'updated_ids':   updated_ids,
        }, status=status.HTTP_200_OK)

    # ─────────────────────────────────────────────────────────────────────
    # POST /api/factures/   (create)
    # ─────────────────────────────────────────────────────────────────────
    def create(self, request, *args, **kwargs):
        serializer = FactureCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        presences = self._presences_dans_intervalle(
            request.user, d['classe_id'], d['date_debut'], d['date_fin']
        )
        if not presences.exists():
            return Response(
                {'error': 'Aucune séance validée dans cet intervalle pour cette classe.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        classe      = Classes.objects.get(pk=d['classe_id'])
        nb_inscrits = Inscriptions.objects.filter(classe=classe).count()
        type_cours  = classe.type_cours or ''

        lignes, total_heures, total_collecte, part_direction, part_prof = \
            self._build_lignes(presences, nb_inscrits, type_cours)

        presence_ids    = [str(p.id)        for p in presences]
        seance_ids      = [str(p.seance_id) for p in presences]
        nb_participants = max((l['nb_participants'] for l in lignes), default=0)

        date_debut = timezone.make_aware(
            datetime.combine(d['date_debut'], datetime.min.time())
        )
        date_fin = timezone.make_aware(
            datetime.combine(d['date_fin'], datetime.min.time())
        )

        facture_existante = Factures.objects.filter(
            classe=classe,
            professeur=request.user,
            date_debut__lte=date_fin,
            date_fin__gte=date_debut,
            statut='brouillon',  # on ne touche pas aux factures déjà soumises
        ).first()

        if facture_existante:
            # Mettre à jour avec les nouveaux calculs
            facture_existante.nb_eleves_inscrits   = nb_inscrits
            facture_existante.nbr_eleves_participe = nb_participants
            #facture_existante.taux_horaire         = classe.taux_horaire
            facture_existante.honoraire            = total_heures
            facture_existante.montant_total        = total_collecte
            facture_existante.part_direction       = part_direction
            facture_existante.part_prof            = part_prof
            facture_existante.presence_ids         = presence_ids
            facture_existante.seance_ids           = seance_ids
            facture_existante.save(update_fields=[
                'nb_eleves_inscrits', 'nbr_eleves_participe',
                'honoraire', 'montant_total', 'part_direction', 'part_prof',
                'presence_ids', 'seance_ids',
            ])
            facture = facture_existante
        elif Factures.objects.filter(
            classe=classe,
            professeur=request.user,
            date_debut__lte=date_fin,
            date_fin__gte=date_debut,
        ).exists():
            # Facture déjà soumise/payée → ne pas toucher
            return Response(
                {'error': 'Une facture soumise ou payée existe déjà pour cette période.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        else:
            facture = Factures.objects.create(
                id                   = uuid.uuid4(),
                classe               = classe,
                professeur           = request.user,
                nb_eleves_inscrits   = nb_inscrits,
                nbr_eleves_participe = nb_participants,
                #taux_horaire         = classe.taux_horaire,
                honoraire            = total_heures,
                montant_total        = total_collecte,
                part_direction       = part_direction,
                part_prof            = part_prof,
                statut               = 'brouillon',
                lien_paypal          = d.get('lien_paypal', ''),
                rib                  = d.get('rib', ''),
                date_debut           = date_debut,
                date_fin             = date_fin,
                envoyee_chat         = False,
                presence_ids         = presence_ids,
                seance_ids           = seance_ids,
            )

        # Participants payment optionnel dans le même payload
        participants_payload = request.data.get('participants_payment')
        if participants_payload:
            pps = ParticipantsPaymentSerializer(data={
                'facture_id':  str(facture.id),
                'payeur_id':   participants_payload.get('payeur_id'),
                'participants': participants_payload.get('participants', []),
            })
            if pps.is_valid():
                with transaction.atomic():
                    nb_p   = len(pps.validated_data['participants'])
                    defaut = total_collecte / nb_p if nb_p > 0 else Decimal('0')
                    for item in pps.validated_data['participants']:
                        try:
                            absence = AbsencesProfs.objects.get(
                                id=item['absence_prof_id']
                            )
                            absence.montant_a_paye  = (
                                item['montant_a_paye']
                                if item['montant_a_paye'] is not None
                                else defaut
                            )
                            absence.facture_id      = facture
                            absence.payeur_id       = pps.validated_data['payeur_id']
                            absence.statut_payement = 'emise'
                            absence.save(update_fields=[
                                'montant_a_paye', 'facture_id',
                                'payeur_id', 'statut_payement',
                            ])
                        except AbsencesProfs.DoesNotExist:
                            continue


        msg = f"Nouvelle facture emise par professeur {request.user.display_name}"
        direction = Users.objects.get(role='direction', is_active=True)
        
        Notifications.objects.create(destinataire=direction, type='new_facture_emise', titre='Nouvelle facture emise', contenu=msg, lu=False)


        return Response(
            FactureSerializer(facture).data,
            status=status.HTTP_201_CREATED,
        )

    # ─────────────────────────────────────────────────────────────────────
    # POST /api/factures/{id}/remind/
    # ─────────────────────────────────────────────────────────────────────
    @action(detail=True, methods=['post'], url_path='remind')
    def remind(self, request, pk=None):
        self.get_object()
        return Response({'detail': 'Rappel envoyé.'})

    # ─────────────────────────────────────────────────────────────────────
    # GET /api/factures/{id}/detail-seances/
    # ─────────────────────────────────────────────────────────────────────
    @action(detail=True, methods=['get'], url_path='detail-seances')
    def detail_seances(self, request, pk=None):
        facture = self.get_object()

        # ── Élèves inscrits ───────────────────────────────────────────────
        inscriptions = (
            Inscriptions.objects
            .filter(classe=facture.classe)
            .select_related('eleve')
            .order_by('eleve__display_name')
        )
        eleves_inscrits = []
        for insc in inscriptions:
            eleve  = insc.eleve
            parent = Users.objects.filter(children=eleve).first()
            eleves_inscrits.append({
                'eleve_id':    str(eleve.id),
                'eleve_nom':   eleve.get_full_name(),
                'eleve_email': eleve.email,
                'parent_id':   str(parent.id) if parent else None,
            })

        # ── Séances ───────────────────────────────────────────────────────
        presence_ids = facture.presence_ids
        seance_ids   = facture.seance_ids
        nb_inscrits  = len(eleves_inscrits)
        type_cours   = facture.classe.type_cours or ''

        presences_qs  = (
            Presences.objects
            .filter(id__in=presence_ids)
            .select_related('seance')
        )
        presences_map = {str(p.id): p for p in presences_qs}

        absences_qs = (
            AbsencesProfs.objects
            .filter(presence_id__in=presence_ids)
            .exclude(Q(temps_effectif=False) & Q(durree_eleve__isnull=True))
            .values('presence_id', 'eleve_id','resp_query_fin_prof')
        )
        participants_par_presence: dict = {}
        for ab in absences_qs:
            pid = str(ab['presence_id'])
            eid = str(ab['eleve_id'])
            resp_query_fin_prof = ab['resp_query_fin_prof']
            participants_par_presence.setdefault(pid, [])
            if eid not in participants_par_presence[pid] and resp_query_fin_prof == True:
                participants_par_presence[pid].append(eid)

        seances_data = []
        for i, pid in enumerate(presence_ids):
            p = presences_map.get(str(pid))
            if not p:
                continue

            duree_heures, heure_cx, heure_dcx = self._get_duree_et_heures(p)
            nb_participants = len(participants_par_presence.get(str(pid), []))

            tarifs = calculer_tarifs(
                nb_inscrits=nb_inscrits,
                nb_participants=nb_participants,
                duree_heures=duree_heures,
                type_cours=type_cours,
            )

            seances_data.append({
                'presence_id':              str(p.id),
                'seance_id':                str(seance_ids[i]),
                'date_seance':              p.created_at,
                'duree_heures':             duree_heures,
                'heure_connexion':          heure_cx.strftime('%H:%M')  if heure_cx  else None,
                'heure_deconnexion':        heure_dcx.strftime('%H:%M') if heure_dcx else None,
                'participants_ids':         participants_par_presence.get(str(pid), []),
                'type_cours_effectif':      tarifs['type_cours_effectif'],
                'tarif_eleve_par_personne': tarifs['tarif_eleve_par_personne'],
                'total_collecte_seance':    tarifs['total_collecte'],
                'part_direction_seance':    tarifs['part_direction'],
                'part_prof_seance':         tarifs['part_prof'],
            })

        all_participant_ids = set()
        for pid in presence_ids:
            all_participant_ids.update(participants_par_presence.get(str(pid), []))

        return Response({
            'eleves_inscrits':        eleves_inscrits,
            'seances':                seances_data,
            'montant_total':          facture.montant_total,
            'part_direction':         facture.part_direction,
            'part_prof':              facture.part_prof,
            'nb_inscrits':            nb_inscrits,
            'nb_participants_global': len(all_participant_ids),
            'type_cours':             type_cours,
        }, status=status.HTTP_200_OK)

    # ─────────────────────────────────────────────────────────────────────
    # POST /api/factures/{id}/submit/
    # ─────────────────────────────────────────────────────────────────────
    @action(detail=True, methods=['post'], url_path='submit')
    def submit(self, request, pk=None):
        facture = self.get_object()

        if facture.statut != 'brouillon':
            return Response(
                {'error': 'Cette facture a déjà été soumise.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SubmitFactureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        methode       = d['methode']
        montant_total = facture.montant_total or Decimal('0')
        type_cours    = facture.classe.type_cours or ''

        inscriptions = (
            Inscriptions.objects
            .filter(classe=facture.classe)
            .select_related('eleve')
        )
        if not inscriptions.exists():
            return Response(
                {'error': 'Aucun élève inscrit dans cette classe.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        nb_inscrits = inscriptions.count()

        presence_ids = facture.presence_ids
        absences_qs  = (
            AbsencesProfs.objects
            .filter(presence_id__in=presence_ids)
            .exclude(Q(temps_effectif=False) & Q(durree_eleve__isnull=True))
            .values('presence_id', 'eleve_id')
        )
        participants_par_seance: dict[str, list[str]] = {}
        all_participant_ids: set[str] = set()
        for ab in absences_qs:
            pid = str(ab['presence_id'])
            eid = str(ab['eleve_id'])
            participants_par_seance.setdefault(pid, [])
            if eid not in participants_par_seance[pid]:
                participants_par_seance[pid].append(eid)
            all_participant_ids.add(eid)

        nb_participants_global = len(all_participant_ids) or 1

        # ── Montant par élève selon méthode ───────────────────────────────
        if methode == 'inscrits':
            montant_commun = (
                Decimal('0') if type_cours == 'gratuit'
                else montant_total / nb_inscrits
            )
        elif methode == 'participants':
            montant_commun = (
                Decimal('0') if type_cours == 'gratuit'
                else montant_total / nb_participants_global
            )
        elif methode == 'manuel':
            montants_map = {
                str(m['eleve_id']): Decimal(str(m['montant_a_payer']))
                for m in d.get('montants', [])
            }

        presences_qs  = Presences.objects.filter(id__in=presence_ids)
        presences_map = {str(p.id): p for p in presences_qs}

        created = []
        with transaction.atomic():
            FactureEleve.objects.filter(facture=facture).delete()

            for insc in inscriptions:
                eleve     = insc.eleve
                eleve_id  = str(eleve.id)
                parent    = Users.objects.filter(children=eleve).first()
                parent_id = parent.id if parent else eleve.id

                for pid in presence_ids:
                    presence = presences_map.get(str(pid))
                    if not presence:
                        continue

                    participants_cette_seance = participants_par_seance.get(str(pid), [])
                    est_participant           = eleve_id in participants_cette_seance

                    if methode == 'inscrits':
                        montant = montant_commun
                    elif methode == 'participants':
                        montant = montant_commun if est_participant else Decimal('0')
                    elif methode == 'manuel':
                        montant = (
                            Decimal('0') if type_cours == 'gratuit'
                            else montants_map.get(eleve_id, Decimal('0'))
                        )

                    created.append(
                        FactureEleve(
                            id               = uuid.uuid4(),
                            eleve            = eleve,
                            parent_id        = parent_id,
                            presence         = presence,
                            date_debut       = facture.date_debut,
                            date_fin         = facture.date_fin,
                            statut           = 'envoyee',
                            montant_a_payer  = montant,
                            montant_payer    = 0,
                            methode_payement = methode,
                            facture          = facture,
                        )
                    )

                    msg = f"Nouvelle facture soumise par professeur {presence.classe.professeur.display_name}"
                 
            
                    Notifications.objects.create(destinataire=eleve, type='new_facture_soumise', classe=presence.classe, titre='Nouvelle facture soumise', contenu=msg, lu=False)
        

            
            FactureEleve.objects.bulk_create(created)
            facture.statut = 'envoyee'
            facture.save(update_fields=['statut'])
            
            


        msg = f"Nouvelle facture soumise par professeur {presence.classe.professeur.display_name}"
        direction = Users.objects.get(role='direction', is_active=True)
            
        Notifications.objects.create(destinataire=direction, type='new_facture_soumise', titre='Nouvelle facture soumise', contenu=msg, lu=False)
        
        return Response({
            'detail':     (
                f'{len(created)} FactureEleve créée(s) '
                f'({len(presence_ids)} séance(s) × {nb_inscrits} élève(s)).'
            ),
            'nb_seances': len(presence_ids),
            'nb_eleves':  nb_inscrits,
            'nb_lignes':  len(created),
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='recall')
    def recall(self, request, pk=None):
        facture = self.get_object()

        if facture.statut != 'envoyee':
            return Response(
                {'error': 'Seules les factures envoyées peuvent être rappelées.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            # Marquer les FactureEleve comme rappelées (pas supprimées)
            FactureEleve.objects.filter(
                facture=facture,
                statut='envoyee'   # on ne touche pas celles déjà payées/confirmées
            ).update(statut='rappellee')

            facture.statut = 'brouillon'
            facture.save(update_fields=['statut'])

            
        msg = f"Nouvelle facture soumise mais rappeler par le professeur {facture.professeur.display_name}"
        direction = Users.objects.get(role='direction', is_active=True)
            
        Notifications.objects.create(destinataire=direction, type='new_facture_soumise_recall', classe=facture.classe, titre='Nouvelle facture soumise mais rappeler', contenu=msg, lu=False)
        

        return Response(FactureSerializer(facture).data, status=status.HTTP_200_OK)


class AdminFacturePresenceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/admin/prof-facture-presences/?professeur_id=<uuid>
    Même logique que ProfFacturePresenceViewSet mais pour n'importe quel prof.
    """
    
    serializer_class = ProfFacturePresenceSerializer
    permission_classes = [permissions.IsAuthenticated]  # ou IsAdminUser

    def get_queryset(self):
        professeur_id = self.request.query_params.get('professeur_id')
        if not professeur_id:
            return Presences.objects.none()

        absence_prof_valide = AbsencesProfs.objects.filter(
            presence=OuterRef('pk'),
        ).exclude(Q(temps_effectif=False) & Q(durree_eleve__isnull=True))

        absence_prof_valide_system = AbsencesProfs.objects.filter(
            presence=OuterRef('pk'),
        ).exclude(Q(resp_query_fin_prof=False))

        return (
            Presences.objects
            .filter(
                classe__professeur_id=professeur_id,
                seance__isnull=False,
            )
            .filter(
                (Q(enregistrement_system=False) & Exists(absence_prof_valide))
                |
                (
                    Q(heure_connexion__isnull=False)
                    & Q(heure_deconnexion__isnull=False)
                    & Q(jitsi_room_id__isnull=False)
                    & (Q(enregistrement_system__isnull=True) | Q(enregistrement_system=True))
                    & Exists(absence_prof_valide_system)
                )
            )
            .select_related('classe', 'seance', 'user')
            .order_by('-created_at')
        )



class AdminFactureEmiseViewSet(FactureEmiseViewSet):
    """
    GET  /api/admin/factures/?professeur_id=<uuid>
    POST /api/admin/factures/preview/
    POST /api/admin/factures/
    etc.
    Hérite de FactureEmiseViewSet mais remplace get_queryset
    et injecte le professeur depuis le query param au lieu de request.user.
    """

    def get_serializer_class(self):
        # Même logique que le parent — toujours utiliser le serializer enrichi pour list
        if self.action == 'list':
            return FactureAvecPaiementsSerializer  # ← avec nb_paiements_*
        if self.action == 'create':
            return FactureCreateSerializer
        return FactureSerializer

    def _get_professeur(self):
        """Résout le prof : query param pour admin, sinon request.user."""
        professeur_id = self.request.query_params.get('professeur_id') \
                     or self.request.data.get('professeur_id')
        if professeur_id:
            return Users.objects.get(pk=professeur_id)
        return self.request.user

    def get_queryset(self):
        professeur_id = self.request.query_params.get('professeur_id')
        if not professeur_id:
            return Factures.objects.none()
        return (
            Factures.objects
            .filter(professeur_id=professeur_id)
            .select_related('classe', 'professeur')
            .order_by('-created_at')
        )

    # Override preview et create pour utiliser le bon prof
    @action(detail=False, methods=['post'], url_path='preview')
    def preview(self, request):
        serializer = FactureCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        prof = self._get_professeur()

        presences = self._presences_dans_intervalle(
            prof, d['classe_id'], d['date_debut'], d['date_fin']
        )
        if not presences.exists():
            return Response(
                {'error': 'Aucune séance validée dans cet intervalle.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        classe = Classes.objects.get(pk=d['classe_id'])
        lignes, total_heures = self._build_lignes(presences)
        taux_horaire  = Decimal(str(classe.taux_horaire or 0))
        montant_total = total_heures * taux_horaire
        return Response({
            'lignes':        FactureLigneSerializer(lignes, many=True).data,
            'total_heures':  total_heures,
            #'taux_horaire':  taux_horaire,
            'honoraire':     total_heures,
            'montant_total': montant_total,
            'nb_inscrits':   lignes[0]['nb_inscrits'] if lignes else 0,
            'nb_participants': max((l['nb_participants'] for l in lignes), default=0),
        })

   



class FactureAdminViewSet(viewsets.ModelViewSet):
    """
    ViewSet réservé aux administrateurs pour la gestion complète des factures.
    Endpoints générés :
        GET    /api/admin/factures/              → liste
        GET    /api/admin/factures/{id}/         → détail
        PATCH  /api/admin/factures/{id}/         → modification partielle
        DELETE /api/admin/factures/{id}/         → suppression
        POST   /api/admin/factures/{id}/valider/ → validation
        POST   /api/admin/factures/{id}/rappel/  → rappel
    """
    serializer_class   = FactureAdminSerializer
    permission_classes = [IsAuthenticated]
    http_method_names  = ['get', 'patch', 'delete', 'post', 'head', 'options']
 
    def get_queryset(self):
        return (
            Factures.objects
            .select_related('classe', 'professeur')
            .order_by('-created_at')
        )
 
    def perform_update(self, serializer):
        serializer.save(updated_at=timezone.now())
 
    @action(detail=True, methods=['post'], url_path='valider')
    def valider(self, request, pk=None):
        facture = self.get_object()
        if facture.statut == 'validee':
            return Response(
                {'detail': 'Cette facture est déjà validée.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        facture.statut     = 'validee'
        facture.updated_at = timezone.now()
        facture.save(update_fields=['statut', 'updated_at'])
        return Response(self.get_serializer(facture).data, status=status.HTTP_200_OK)
 
    @action(detail=True, methods=['post'], url_path='rappel')
    def rappel(self, request, pk=None):
        facture = self.get_object()
        # TODO: brancher votre logique d'envoi
        return Response({'detail': 'Rappel envoyé.'}, status=status.HTTP_200_OK)




class FactureEleveViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Gestion des FactureEleve côté élève connecté.
 
    GET  /api/factures-eleve/              → liste paginée des FactureEleve de l'élève
    GET  /api/factures-eleve/{id}/         → détail
    POST /api/factures-eleve/{id}/payer/   → enregistre un paiement (met à jour montant_payer)
                                             recalcule le statut automatiquement
 
    Côté professeur (confirmation) :
    POST /api/factures-eleve/{id}/confirmer/ → passe statut = 'confirmee'
    """
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = FactureEleveListSerializer
 
    def get_queryset(self):
        user = self.request.user
        qs = FactureEleve.objects.select_related(
            'facture', 'facture__classe', 'facture__professeur', 'presence', 'eleve'
        ).order_by('-created_at')
    
        if user.role == 'eleve':
            qs = qs.filter(eleve=user)
        elif user.role == 'professeur':
            qs = qs.filter(facture__professeur=user)
    
        # Filtre optionnel par facture_id (pour le panel prof)
        facture_id = self.request.query_params.get('facture_id')
        if facture_id:
            qs = qs.filter(facture_id=facture_id)
    
        return qs


    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """GET /api/factures-eleve/stats/ — compteurs dashboard élève."""
        from django.db.models import Sum, Q
        eleve = request.user

        # Classes actives où l'élève est inscrit
        inscriptions_actives = Inscriptions.objects.filter(
            eleve=eleve,
            statut='active',
            classe__statut='active',
            classe__deleted_at__isnull=True
        ).select_related('classe')

        nb_classes = inscriptions_actives.count()
        programmes = [
            i.classe.programme
            for i in inscriptions_actives
            if i.classe.programme
        ]
        classes_ids = inscriptions_actives.values_list('classe_id', flat=True)

        # Factures à payer
        montant_a_payer = FactureEleve.objects.filter(
            eleve=eleve,
            statut__in=['en_attente', 'partiel']
        ).aggregate(total=Sum('montant_a_payer'))['total'] or 0

        # Factures payées
        montant_paye = FactureEleve.objects.filter(
            eleve=eleve,
            statut__in=['paye', 'confirmee']
        ).aggregate(total=Sum('montant_payer'))['total'] or 0

        # Séances actives toutes classes de l'élève
        nb_seances = Seances.objects.filter(
            classe_id__in=classes_ids,
            statut='active',
            classe__isnull=False
        ).count()

        return Response({
            'nb_classes_actives': nb_classes,
            'programmes': programmes,
            'montant_a_payer': montant_a_payer,
            'montant_paye': montant_paye,
            'nb_seances': nb_seances,
        })
    # ----------------------------------------------------------
    # POST /api/factures-eleve/{id}/payer/
    # ----------------------------------------------------------
    @action(detail=True, methods=['post'], url_path='payer')
    def payer(self, request, pk=None):
        """
        Enregistre un paiement (partiel ou total).
        - Additionne le montant envoyé au montant_payer existant
        - Recalcule et met à jour le statut selon le résultat
        - Seul l'élève concerné ou son parent peut payer
        """
        facture_eleve = self.get_object()
 
        # Vérification : seul l'élève concerné ou son parent peut payer
        user = request.user
        if user.role == 'eleve' and facture_eleve.eleve != user:
            return Response(
                {'error': 'Vous ne pouvez payer que vos propres factures.'},
                status=status.HTTP_403_FORBIDDEN,
            )
 
        serializer = PayerFactureEleveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        montant_verse = Decimal(str(serializer.validated_data['montant_payer']))
 
        montant_a_payer = Decimal(str(facture_eleve.montant_a_payer or 0))
        montant_deja_paye = Decimal(str(facture_eleve.montant_payer or 0))
 
        # On ne dépasse pas le montant dû
        nouveau_montant_paye = min(
            montant_deja_paye + montant_verse,
            montant_a_payer
        )
 
        # Calcul du statut
        if montant_a_payer <= 0:
            nouveau_statut = 'emise'
        elif nouveau_montant_paye >= montant_a_payer:
            nouveau_statut = 'payee'
        else:
            nouveau_statut = 'emise'   # partiel → reste emise jusqu'à confirmation prof
 
        facture_eleve.montant_payer = nouveau_montant_paye
        facture_eleve.statut        = nouveau_statut
        fichier_upload = request.FILES.get('justificatif')
        if fichier_upload:
            file_id = uuid.uuid4()
            ext = os.path.splitext(fichier_upload.name)[1]
            fichier = FacturesFichier.objects.create(
                id=file_id,
                uploade_par=request.user,
                classe=facture_eleve.presence.classe,
                nom_original=fichier_upload.name,
                nom_stockage=f"justificatif_{file_id}{ext}",
                fichier_local=fichier_upload,
                type_fichier='image' if fichier_upload.content_type.startswith('image/') else 'document',
                mime_type=fichier_upload.content_type,
                taille_bytes=fichier_upload.size,
                created_at=timezone.now(),
            )
            facture_eleve.justificatif = fichier
        facture_eleve.save(update_fields=['montant_payer', 'statut'])
        
        msg = f"nouvelle facture payee par l'eleve {request.user.display_name}"
        Notifications.objects.create(destinataire=facture_eleve.presence.classe.professeur, type='facture_payee', classe=facture_eleve.presence.classe, titre='Facture payee', contenu=msg, lu=False)

        direction = Users.objects.get(role='direction', is_active=True)
        Notifications.objects.create(destinataire=direction, type='facture_payee', titre='Facture payee', classe=facture_eleve.presence.classe, contenu=msg, lu=False)

 
        return Response(
            FactureEleveListSerializer(facture_eleve).data,
            status=status.HTTP_200_OK,
        )
 
    # ----------------------------------------------------------
    # POST /api/factures-eleve/{id}/confirmer/
    # ----------------------------------------------------------
    @action(detail=True, methods=['post'], url_path='confirmer')
    def confirmer(self, request, pk=None):
        """
        Le professeur confirme le paiement reçu.
        Passe le statut à 'confirmee'.
        Réservé aux professeurs propriétaires de la facture.
        """
        facture_eleve = self.get_object()
 
        if request.user.role != 'professeur':
            return Response(
                {'error': 'Seul le professeur peut confirmer un paiement.'},
                status=status.HTTP_403_FORBIDDEN,
            )
 
        if facture_eleve.facture.professeur != request.user:
            return Response(
                {'error': 'Vous ne pouvez confirmer que les paiements de vos propres factures.'},
                status=status.HTTP_403_FORBIDDEN,
            )
 
        if facture_eleve.statut not in ('payee', 'emise'):
            return Response(
                {'error': f'Impossible de confirmer une facture au statut {facture_eleve.statut}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        facture_eleve.statut = 'confirmee'
        facture_eleve.save(update_fields=['statut'])

        msg = f"Confirmation de payement de facture par professeur {facture_eleve.facture.professeur}"
        Notifications.objects.create(destinataire=facture_eleve.eleve, type='facture_confirmee', classe=facture_eleve.presence.classe, titre='Facture confirmee', contenu=msg, lu=False)


        direction = Users.objects.get(role='direction', is_active=True)
        Notifications.objects.create(destinataire=direction, type='facture_confirmee',classe=facture_eleve.presence.classe, titre='Facture confirmee', contenu=msg, lu=False)

 
        return Response(
            FactureEleveListSerializer(facture_eleve).data,
            status=status.HTTP_200_OK,
        )


    # ----------------------------------------------------------
    # POST /api/factures-eleve/confirmer-tout/
    # Confirme en une fois tous les paiements payés d'une facture
    # ----------------------------------------------------------
    @action(detail=False, methods=['post'], url_path='confirmer-tout')
    def confirmer_tout(self, request):
        """
        Payload : { facture_id: "uuid" }
        Confirme tous les FactureEleve dont statut = 'payee'
        pour la facture donnée.
        """
        if request.user.role != 'professeur':
            return Response({'error': 'Seul le professeur peut confirmer.'}, status=403)
    
        facture_id = request.data.get('facture_id')
        if not facture_id:
            return Response({'error': 'facture_id requis.'}, status=400)
    
        try:
            facture = Factures.objects.get(id=facture_id, professeur=request.user)
        except Factures.DoesNotExist:
            return Response({'error': 'Facture introuvable.'}, status=404)
    
        # Confirmer tous les payés (montant_payer >= montant_a_payer)
        a_confirmer = FactureEleve.objects.filter(
            facture=facture,
            statut='payee',
        )
        count = a_confirmer.count()
        a_confirmer.update(statut='confirmee')
    
        # Vérifier si toutes sont confirmées → facture payée
        self._check_and_update_facture_statut(facture)
    
        today = timezone.now().date()
        msg = f" Confirmation de payement de facture par professeur {request.user.display_name}"
        Notifications.objects.create(destinataire=facture_eleve.presence.classe.eleve, type='facture_confirmee', classe=facture_eleve.presence.classe, titre='Facture confirmee', contenu=msg, lu=False)

        return Response({
            'detail': f'{count} paiement(s) confirmé(s).',
            'count': count,
        }, status=status.HTTP_200_OK)
    
    
    # ----------------------------------------------------------
    # Helper : si tous les FactureEleve sont confirmés → Facture payee
    # ----------------------------------------------------------
    def _check_and_update_facture_statut(self, facture):
        """
        Vérifie si tous les FactureEleve de cette facture sont à 'confirmee'.
        Si oui, passe la Facture en statut 'payee'.
        """
        total     = FactureEleve.objects.filter(facture=facture).count()
        confirmee = FactureEleve.objects.filter(facture=facture, statut='confirmee').count()
    
        if total > 0 and total == confirmee:
            facture.statut = 'payee'
            facture.save(update_fields=['statut'])

        msg = f"facture totalement payee"

        direction = Users.objects.get(role='direction', is_active=True)
        Notifications.objects.create(destinataire=direction, type='facture_totalement_payee',classe=facture.classe, titre='Facture totalement payee', contenu=msg, lu=False)

 

class AdminElevesAPayerView(APIView):
    permission_classes = [IsAuthenticated]
 
    def get(self, request):
        admin = request.user
 
        # Sécurité : seul un compte 'admin' peut appeler cet endpoint
        if getattr(admin, 'role', None) != 'admin':
            return Response({'detail': 'Accès réservé aux admins.'}, status=403)
 
        # 1) Les professeurs rattachés à cet admin
        profs_qs = Users.objects.filter(
            admin_id=admin.id,
            role='professeur',
            is_active=True,
        )
 
        # 2) Les factures élèves dont la facture "prof" appartient à un des
        #    professeurs de l'admin, sur une classe non supprimée
        factures_qs = (
            FactureEleve.objects
            .filter(
                facture__professeur__in=profs_qs,
                facture__classe__deleted_at__isnull=True,
            )
            .select_related(
                'eleve',
                'facture',
                'facture__classe',
                'facture__professeur',
            )
        )
 
        data = []
        for fe in factures_qs:
            montant_a_payer = fe.montant_a_payer or Decimal('0')
            montant_payer = fe.montant_payer or Decimal('0')
            reste = montant_a_payer - montant_payer
 
            if reste <= 0:
                continue
 
            classe = fe.facture.classe
            prof = fe.facture.professeur
 
            data.append({
                'facture_eleve_id': str(fe.id),
                'eleve_id': str(fe.eleve_id),
                'eleve_nom': fe.eleve.display_name or fe.eleve.email,
                'eleve_is_active': fe.eleve.is_active,
                'telephone': fe.eleve.telephone or '',
                'classe_id': str(classe.id) if classe else '',
                'classe_nom': classe.nom if classe else '—',
                'cours': classe.get_type_cours_display() if classe and classe.type_cours else '',
                'professeur_id': str(prof.id) if prof else '',
                'professeur_nom': prof.display_name if prof else '—',
                'montant_a_payer': float(reste),
                'statut': fe.statut,
            })
 
        return Response(data)

class QuestionEntreeViewSet(viewsets.ModelViewSet):
    queryset = QuestionsEntree.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = QuestionEntreeSerializer  # ← AJOUTER CETTE LIGNE

class FactureViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FactureSerializer  # ← AJOUTER CETTE LIGNE

    def get_queryset(self):
        user = self.request.user
        if user.role in ('direction', 'admin'): return Factures.objects.all()
        if user.role == 'professeur': return Factures.objects.filter(professeur=user)
        # Élève voit factures de ses classes
        ids = Inscriptions.objects.filter(eleve=user).values_list('classe_id', flat=True)
        return Factures.objects.filter(classe__id__in=ids)

class RappelPaiementViewSet(viewsets.ModelViewSet):
    queryset = RappelsPaiement.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsDirection]
    serializer_class = RappelPaiementSerializer  # ← AJOUTER CETTE LIGNE

class PaiementViewSet(viewsets.ModelViewSet):
    queryset = Paiements.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PaiementSerializer  # ← AJOUTER CETTE LIGNE

    def perform_create(self, serializer):
        serializer.save(confirme_par=self.request.user, paid_at=timezone.now())
        # Mettre à jour facture
        facture = serializer.validated_data['facture']
        facture.statut = 'paye'
        facture.save(update_fields=['statut'])

class PlanningDispoViewSet(viewsets.ModelViewSet):
    queryset = PlanningDispos.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PlanningDispoSerializer  # ← AJOUTER CETTE LIGNE

class HistoriqueCreneauViewSet(viewsets.ModelViewSet):
    queryset = HistoriqueCreneaux.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsDirection]
    serializer_class = HistoriqueCreneauSerializer  # ← AJOUTER CETTE LIGNE

class EnregistrementViewSet(viewsets.ModelViewSet):
    queryset = Enregistrements.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EnregistrementSerializer  # ← AJOUTER CETTE LIGNE

    def get_queryset(self):
        user = self.request.user
        if user.role in ('direction', 'admin'): return Enregistrements.objects.filter(deleted_at__isnull=True)
        if user.role == 'professeur': return Enregistrements.objects.filter(classe__professeur=user, deleted_at__isnull=True)
        return Enregistrements.objects.filter(classe__inscription__eleve=user, deleted_at__isnull=True)

class TableauBlancViewSet(viewsets.ModelViewSet):
    queryset = TableauBlanc.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TableauBlancSerializer  # ← AJOUTER CETTE LIGNE

    def get_queryset(self):
        seance_id = self.request.query_params.get('seance_id')
        return TableauBlanc.objects.filter(seance_id=seance_id)

class FichierViewSet(viewsets.ModelViewSet):
    queryset = Fichiers.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FichierSerializer  # ← AJOUTER CETTE LIGNE



class IsDirection(permissions.BasePermission):
    """Seule la Direction peut créer/modifier des tâches."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'direction'
 
 
class IsAdminOrDirection(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ('admin', 'direction')
 
 
class TacheDirectionViewSet(viewsets.ModelViewSet):
    """
    CRUD complet sur les tâches direction.
    - list / retrieve : admin (ses tâches) ou direction (toutes)
    - create / update / destroy : direction uniquement
    - marquer_faite : admin assigné ou direction
    """
    serializer_class = TacheDirectionSerializer
 
    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsDirection()]
        return [IsAdminOrDirection()]
 
    def get_queryset(self):
        user = self.request.user
        qs = TachesDirection.objects.select_related(
            'created_by', 'faite_par'
        ).prefetch_related(
            'tachedirectionassignee_set__user'
        ).order_by('-created_at')
 
        if user.role == 'admin':
            # Un admin ne voit que les tâches qui lui sont assignées
            qs = qs.filter(tachedirectionassignee__user=user)
 
        # Filtres optionnels via query params
        faite = self.request.query_params.get('faite')
        if faite is not None:
            qs = qs.filter(faite=faite.lower() in ('true', '1'))
 
        return qs.distinct()
 
    def perform_create(self, serializer):
        tache = serializer.save(created_by=self.request.user)

        assignees = tache.tachedirectionassignee_set.all()

        for assignee in assignees:
            admin = assignee.user

            Notifications.objects.create(
                destinataire=admin,
                type='taches',
                titre='Nouvelle tâche',
                contenu=f"Nouvelle tâche : {tache.titre}",
                lu=False
            )
 
    @action(detail=True, methods=['post'], url_path='marquer-faite')
    def marquer_faite(self, request, pk=None):
        """
        POST /taches-direction/{id}/marquer-faite/
        Body: { "faite": true | false }
        """
        tache = self.get_object()
        user = request.user
 
        # Vérifier que l'admin est bien assigné (sauf direction)
        if user.role == 'admin':
            if not TacheDirectionAssignee.objects.filter(
                tache=tache, user=user
            ).exists():
                return Response(
                    {'detail': "Vous n'êtes pas assigné à cette tâche."},
                    status=status.HTTP_403_FORBIDDEN
                )
 
        ser = MarquerFaiteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        faite = ser.validated_data['faite']
 
        tache.faite = faite
        tache.faite_par = user if faite else None
        tache.faite_at = timezone.now() if faite else None
        tache.save()

        direction = Users.objects.get(role='direction', is_active=True)
        msg = f"Tache effectue par {tache.faite_par.display_name}"
        Notifications.objects.create(destinataire=direction, type='taches', titre='Taches effectue', contenu=msg, lu=False)

 
        return Response(TacheDirectionSerializer(tache).data)
 
    @action(
        detail=False,
        methods=['get'],
        url_path='admins-assignables',
        permission_classes=[IsDirection]
    )
    def admins_assignables(self, request):
        """GET /taches-direction/admins-assignables/ — liste des users role=admin actifs."""
        admins = Users.objects.filter(role='admin', is_active=True).order_by('display_name')
        return Response(AdminUserSerializer(admins, many=True).data)



class LogActiviteViewSet(viewsets.ModelViewSet):
    queryset = LogsActivite.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsDirection]
    serializer_class = LogActiviteSerializer  # ← AJOUTER CETTE LIGNE

class RapportAutoViewSet(viewsets.ModelViewSet):
    queryset = RapportsAuto.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsDirection]
    serializer_class = RapportAutoSerializer  # ← AJOUTER CETTE LIGNE

# ==========================================================
# ACTIONS SPÉCIFIQUES & LOGIQUE MÉTIER
# ==========================================================
class CheckCreneauProfView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsProfesseur]
    def post(self, request, pk):
        classe = Classes.objects.get(id=pk)
        # Logique de validation : si le prof confirme, on met à jour et on notifie direction si changement
        is_correct = request.data.get('est_correct', False)
        if not is_correct:
            return Response({'message': 'Veuillez modifier le créneau via le planning.'}, status=400)
        classe.creneau_confirme_prof = True
        classe.save(update_fields=['creneau_confirme_prof'])
        return Response({'message': 'Créneau confirmé par le professeur.'})
        
class StartSessionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @staticmethod
    def generate_livekit_token(user, room_name: str, is_moderator: bool = False):
        """Génère un token JWT LiveKit pour l'authentification"""
        grants = api.VideoGrants(
            room_join=True,
            room=room_name,
            room_admin=is_moderator,
            can_publish=is_moderator or user.role == 'eleve',
            can_subscribe=True,
            can_publish_data=True,
            can_publish_sources=(
                ['camera', 'microphone', 'screen_share']
                if is_moderator or user.role == 'eleve'
                else ['camera', 'microphone']
            ),
        )
        token = (
            api.AccessToken(api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
            .with_identity(str(user.id))
            .with_name(user.display_name or user.email.split('@')[0])
            .with_metadata(f'role:{user.role}')
            .with_grants(grants)
            .with_ttl(timedelta(hours=4))
            .to_jwt()
        )
        return token

    def post(self, request, pk):
        user = request.user

        # ── 1. Vérification accès classe ──────────────────────────────────
        try:
            classe = Classes.objects.get(id=pk)
        except Classes.DoesNotExist:
            return Response({'error': 'Classe introuvable.'}, status=404)

        if user.role not in ('professeur', 'direction', 'admin'):
            if not Inscriptions.objects.filter(eleve=user, classe=classe).exists():
                return Response({'error': 'Accès refusé.'}, status=403)

        # ── 2. Récupération de la Séance (créée ailleurs, pas ici) ────────
        today = timezone.now().date()
        seance_id = request.data.get('seance_id')  # envoyé depuis le front
        seance = None

        if seance_id:
            seance = Seances.objects.filter(id=seance_id, classe=classe).first()

        if not seance:
            # Fallback : séance du jour pour cette classe si elle existe
            seance = Seances.objects.filter(classe=classe, date_seance=today).first()

        # ── 3. Nom de room LiveKit ─────────────────────────────────────────
        room_name = classe.jitsi_room_id or f"sabil-{classe.id}-{today.strftime('%Y%m%d')}"

        # ── 4. Calcul du retard ────────────────────────────────────────────
        heure_connexion = timezone.now()
        retard = None

        if seance and seance.heure_debut_reelle and seance.date_seance:
            debut_naive = timezone.datetime.combine(seance.date_seance, seance.heure_debut_reelle)
            debut_aware = timezone.make_aware(debut_naive) if timezone.is_naive(debut_naive) else debut_naive
            delta = int((heure_connexion - debut_aware).total_seconds() // 60)
            retard = delta if delta > 10 else None

        # ── 5. Création de la Présence (nouvelle ligne à chaque connexion) ─
        presence = Presences.objects.create(
            id=uuid.uuid4(),
            classe=classe,
            user=user,
            seance=seance,                   # None si pas de séance trouvée
            date_seance=today,
            heure_connexion=heure_connexion,
            retard_minutes=retard,
            jitsi_room_id=room_name,
            created_at=heure_connexion,
        )

       

        if user.role == "direction":
            direction = Users.objects.get(role='direction', is_active=True)
            Notifications.objects.create(
                id=uuid.uuid4(),
                destinataire=direction,
                type='cours_demarrer',
                titre='Cours démarré',
                contenu=f'Salle ouverte pour {classe.nom}',
                lu=False,
                classe=classe,
                created_at=timezone.now(),
            )

        if user.role == "professeur":
            Notifications.objects.create(
            id=uuid.uuid4(),
            destinataire_id=user.admin_id,
            type='cours_demarrer',
            titre='Cours démarré',
            contenu=f'Salle ouverte pour {classe.nom}',
            lu=False,
            classe=classe,
            created_at=timezone.now(),)

            inscriptions = Inscriptions.objects.filter(classe=classe)
            notifications = [
                Notifications(
                    destinataire=inscription.eleve,
                    type='cours_demarrer',
                    titre='Cours démarré',
                    classe=seance.classe,
                    contenu=f'Salle ouverte pour {classe.nom}',
                    lu=False,
                    created_at=timezone.now(),
                )
                for inscription in inscriptions
            ]

        # ── 7. Token LiveKit ───────────────────────────────────────────────
        is_moderator = user.role in ('professeur', 'admin', 'direction')
        livekit_token = StartSessionView.generate_livekit_token(user, room_name, is_moderator)

        return Response({
            'seance_id': str(seance.id) if seance else None,
            'presence_id': str(presence.id),
            'room_name': room_name,
            'livekit_token': livekit_token,
            'livekit_url': LIVEKIT_URL,
            'is_moderator': is_moderator,
            'duration_limit_min': 2000,
        })
# ─────────────────────────────────────────────
# POST /classes/<pk>/end-session/
# Body JSON : { "presence_id": "...", "audio_url": "..." }
# ─────────────────────────────────────────────
class EndSessionView(APIView):
    permission_classes = [permissions.IsAuthenticated]
 
    def post(self, request, pk):
        presence_id = request.data.get('presence_id')
        audio_url = request.data.get('audio_url', '')   # URL ou chemin du fichier audio
 
        if not presence_id:
            return Response({'error': 'presence_id requis.'}, status=400)
 
        try:
            presence = Presences.objects.get(id=presence_id, user=request.user)
        except Presences.DoesNotExist:
            return Response({'error': 'Présence introuvable.'}, status=404)
 
        heure_deconnexion = timezone.now()
 
        # ── Mise à jour de la Présence ─────────────────────────────────────
        presence.heure_deconnexion = heure_deconnexion
        presence.audio_seance = audio_url or presence.audio_seance
        presence.enregistrement_system = True
        presence.save(update_fields=['heure_deconnexion', 'audio_seance','enregistrement_system'])

        # CALCUL durée présence
        duree_presence_minutes = None
        if presence.heure_connexion:
            duree_presence_minutes = int(
                (heure_deconnexion - presence.heure_connexion).total_seconds() // 60
            )
 
        # ── Mise à jour de la durée réelle dans Seances ───────────────────
        seance = presence.seance
        if seance and seance.heure_debut_reelle and seance.date_seance:
            debut_naive = timezone.datetime.combine(seance.date_seance, seance.heure_debut_reelle)
            debut_aware = timezone.make_aware(debut_naive) if timezone.is_naive(debut_naive) else debut_naive
            duree = int((heure_deconnexion - debut_aware).total_seconds() // 60)
            # On ne réduit pas une durée déjà enregistrée (cas multi-participant)
            if not seance.duree_reelle_minutes or duree > seance.duree_reelle_minutes:
                seance.duree_reelle_minutes = duree
                seance.save(update_fields=['duree_reelle_minutes'])
 
        return Response({
            'status': 'ok',
            'heure_connexion': presence.heure_connexion.isoformat() if presence.heure_connexion else None,
            'heure_deconnexion': heure_deconnexion.isoformat(),
            'duree_presence_minutes': duree_presence_minutes
        })


# ─────────────────────────────────────────────
# GET /classes/<pk>/seances/
# Liste des séances d'une classe
# ─────────────────────────────────────────────
class ClassSeancesView(APIView):
    permission_classes = [permissions.IsAuthenticated]
 
    def get(self, request, pk):
        try:
            classe = Classes.objects.get(id=pk)
        except Classes.DoesNotExist:
            return Response({'error': 'Classe introuvable.'}, status=404)
 
        seances = Seances.objects.filter(classe=classe).order_by('-date_seance')
        data = [
            {
                'id': str(s.id),
                'date_seance': s.date_seance.isoformat() if s.date_seance else None,
                'jour_seance': s.jour_seance,
                'heure_debut_reelle': s.heure_debut_reelle.strftime('%H:%M') if s.heure_debut_reelle else None,
                'duree_reelle_minutes': s.duree_reelle_minutes,
                'statut': s.statut,
            }
            for s in seances
        ]
        return Response({'results': data})



class PauseClassView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk):
        user = request.user
        classe = Classes.objects.get(id=pk)
        if user.role not in ('professeur', 'admin'):
            return Response({'error': 'Droit insuffisant.'}, status=403)
        classe.statut = 'en_pause'
        classe.save(update_fields=['statut'])
        
        direction = Users.objects.get(role='direction', is_active=True)
        msg = f"Classe {classe.nom}  mis en pause"
        Notifications.objects.create(destinataire=direction, type='classe_mise_en_pause', classe=classe, titre='Classe mis en pause', contenu=msg, lu=False)

        return Response({'message': 'Classe mise en pause.'})


class FlagDeleteClassView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk):

        if request.user.role not in ['professeur', 'admin']:
            return Response(
                {'detail': 'Permission refusée.'},
                status=403
            )

        classe = Classes.objects.get(id=pk)
        classe.statut = 'a_supprimer'
        classe.save(update_fields=['statut'])
        # Notification Direction
         
        direction = Users.objects.get(role='direction', is_active=True)
        msg = f"Classe {classe.nom}  a supprimer"
        Notifications.objects.create(destinataire=direction, type='classe_a_supprimer', classe=classe, titre='Classe à supprimer signalée', contenu=msg, lu=False)
        return Response({'message': 'Classe signalée pour suppression.'})

class ReactivateClassView(APIView):
    permission_classes = [permissions.IsAuthenticated]
 
    def post(self, request, pk):
        user = request.user
        if user.role not in ('professeur', 'admin', 'direction'):
            return Response({'error': 'Droit insuffisant.'}, status=403)
        try:
            classe = Classes.objects.get(id=pk)
        except Classes.DoesNotExist:
            return Response({'error': 'Classe introuvable.'}, status=404)
 
        classe.statut = 'active'
        classe.couleur = None   # ou 'bleu' selon votre logique
        classe.save(update_fields=['statut'])
        return Response({'message': 'Classe réactivée.'})


class PermanentDeleteClassView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def delete(self, request, pk):
        user = request.user
        if user.role not in ('direction', 'admin'):
            return Response({'error': 'Droit insuffisant.'}, status=403)
        classe = Classes.objects.get(id=pk)
        classe.deleted_at = timezone.now()
        classe.statut = 'supprimer'
        classe.save(update_fields=['deleted_at', 'statut'])
        LogsActivite.objects.create(user=user, action='delete_class', table_cible='Classes', id_cible=classe.id)
        return Response({'message': 'Classe supprimée définitivement.'})

class SubmitPreClassCheckView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsEleve]
    def post(self, request):
        classe_id = request.data.get('classe_id')
        prof_retard = request.data.get('prof_en_retard', False)
        prof_absent = request.data.get('prof_absent', False)
        retard_min = int(request.data.get('retard_minutes', 0) or 0)
        
        q = QuestionsEntree.objects.create(
            eleve=request.user, classe_id=classe_id, 
            prof_en_retard=prof_retard, prof_absent=prof_absent, retard_minutes=retard_min,
            notif_envoyee_admin=True, notif_envoyee_at=timezone.now(), created_at=timezone.now()
        )
        if prof_absent or prof_retard:
            # Trouver admin de la classe
            classe = Classes.objects.get(id=classe_id)
            if classe.admin:
                Notifications.objects.create(
                    destinataire=classe.admin, type='alert_prof', titre='Alerte Professeur', 
                    contenu=f'Élève {request.user.display_name} signale absence/retard prof pour {classe.nom}', lu=False
                )
            # Enregistrement absence prof
            if prof_absent:
                AbsencesProfs.objects.create(
                    professeur=classe.professeur, classe=classe, signale_par=request.user,
                    date_absence=timezone.now().date(), type='absence', source='eleve_check', created_at=timezone.now()
                )
        return Response({'message': 'Réponse enregistrée. Accès au chat ouvert si créneau confirmé.'})

class SyncPlanningFromClassView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsProfesseur]
    def post(self, request):
        # Sync automatique créneaux classes -> PlanningDispos
        classes = Classes.objects.filter(professeur=request.user)
        for c in classes:
            if c.jour_semaine and c.heure_debut and c.duree_minutes:
                heure_fin = (datetime.combine(datetime.today(), c.heure_debut) + timedelta(minutes=c.duree_minutes)).time()
                PlanningDispos.objects.update_or_create(
                    professeur=request.user, jour_semaine=c.jour_semaine, heure_debut=c.heure_debut,
                    defaults={'heure_fin': heure_fin, 'disponible': True, 'couleur': 'vert', 'updated_at': timezone.now()}
                )
                # Historique changement
                HistoriqueCreneaux.objects.create(
                    classe=c, modifie_par=request.user, ancien_jour=None, ancienne_heure=None,
                    nouveau_jour=c.jour_semaine, nouvelle_heure=c.heure_debut, notif_direction_envoyee=True,
                    notif_envoyee_at=timezone.now(), created_at=timezone.now()
                )
        # Notif direction couleur rose
        for dir_user in Users.objects.filter(role='direction'):
            Notifications.objects.create(destinataire=dir_user, type='planning_update', titre='Planning mis à jour', contenu='Nouveaux créneaux importés. Case rose si non lu.', lu=False)
        return Response({'message': 'Planning synchronisé.'})

class TogglePlanningSlotView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsProfesseur]
    def post(self, request):
        jour = request.data.get('jour_semaine')
        heure = request.data.get('heure_debut') # format HH:MM:SS
        slot, created = PlanningDispos.objects.get_or_create(
            professeur=request.user, jour_semaine=jour, heure_debut=heure,
            defaults={'heure_fin': (datetime.combine(datetime.today(), datetime.strptime(heure, '%H:%M:%S').time()) + timedelta(minutes=30)).time(), 'disponible': True, 'couleur': 'vert', 'updated_at': timezone.now()}
        )
        slot.disponible = not slot.disponible
        slot.couleur = 'vert' if slot.disponible else 'blanc'
        slot.updated_at = timezone.now()
        slot.save(update_fields=['disponible', 'couleur', 'updated_at'])
        return Response({'disponible': slot.disponible, 'couleur': slot.couleur})

class AutoGenerateInvoicesView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsProfesseur]
    def post(self, request):
        # Génère factures à partir des seances terminées du mois
        mois = timezone.now().replace(day=1)
        classes = Classes.objects.filter(professeur=request.user)
        for c in classes:
            seances = Seances.objects.filter(classe=c, date_seance__lt=mois, statut='terminee')
            if seances.exists():
                lignes = [{'date': s.date_seance.isoformat(), 'duree': s.duree_reelle_minutes} for s in seances]
                montant = sum(l['duree'] for l in lignes) / 60 * float(c.taux_horaire or 0)
                Factures.objects.create(
                    classe=c, professeur=request.user, periode_mois=mois, lignes_cours=lignes,
                    nb_eleves=Inscriptions.objects.filter(classe=c).count(), taux_horaire=c.taux_horaire,
                    montant_total=montant, statut='envoye', lien_paypal=request.data.get('lien_paypal'),
                    rib=request.data.get('rib'), envoyee_chat=True, envoyee_chat_at=timezone.now(),
                    created_at=timezone.now(), updated_at=timezone.now()
                )
                # Envoi message auto dans chat
                Messages.objects.create(expediteur=request.user, classe=c, type_canal='classe', type_message='systeme', contenu=f'Facture du mois {mois.month} disponible.', is_systeme=True, created_at=timezone.now())
        return Response({'message': 'Factures générées et envoyées.'})

class SendPaymentRemindersView(APIView):
    permission_classes = [permissions.IsAuthenticated] # Celery trigger normally
    def post(self, request):
        # Logique rappels J+5 puis J+3
        now = timezone.now()
        factures = Factures.objects.filter(statut='envoye')
        for f in factures:
            jours_ecoules = (now - f.envoyee_chat_at).days
            rappels = RappelsPaiement.objects.filter(facture=f)
            next_num = rappels.count() + 1
            if (jours_ecoules >= 5 and next_num == 1) or (jours_ecoules > 5 and (jours_ecoules - 5) % 3 == 0):
                RappelsPaiement.objects.create(facture=f, numero_rappel=next_num, envoye_at=now, statut='envoye', created_at=now)
                Messages.objects.create(expediteur=Users.objects.filter(role='admin').first(), classe=f.classe, type_canal='classe', type_message='systeme', contenu=f'Rappel {next_num} : facture en attente.', is_systeme=True, created_at=now)
        return Response({'message': 'Rappels envoyés selon règle J+5 puis J+3.'})

class CheckClassInactivityView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        limite = timezone.now() - timedelta(days=8)
        inactives = Classes.objects.filter(derniere_activite_at__lt=limite, deleted_at__isnull=True)
        if inactives.exists():
            for admin in Users.objects.filter(role='admin'):
                Notifications.objects.create(destinataire=admin, type='inactivite', titre='Classes inactives > 8j', contenu=str([c.nom for c in inactives[:5]]), lu=False)
        return Response({'count': inactives.count(), 'classes': [c.nom for c in inactives]})

class AcknowledgeTacheView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk):
        tache = TacheDirection.objects.get(id=pk)
        if not tache.faite:
            tache.faite = True
            tache.faite_par = request.user
            tache.faite_at = timezone.now()
            tache.save(update_fields=['faite', 'faite_par', 'faite_at'])
            # Éteindre lumière clignotante (logique frontend WS)
        return Response({'message': 'Tâche acquittée. Lumière désactivée.'})

class DailyAbsenceReportView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsDirection]
    def get(self, request):
        today = timezone.now().date()
        absences = AbsencesProfs.objects.filter(date_absence=today).values_list('professeur__display_name', flat=True).distinct()
        if absences:

            today = timezone.now().date()
            msg = f"Date: {today} | Profs absents: {', '.join(absences)}"
            for admin in Users.objects.filter(role='admin'):
                Notifications.objects.create(destinataire=admin, type='rapport_quotidien', titre='Absences du jour', contenu=msg, lu=False)
            RapportAuto.objects.create(type_rapport='daily', periode_debut=today, periode_fin=today, contenu_json={'absents': list(absences)}, created_at=timezone.now())
            return Response({'message': 'Rapport quotidien envoyé.', 'data': list(absences)})
        return Response({'message': 'Aucune absence aujourd\'hui.'})

class MonthlySummaryReportView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsDirection]
    def get(self, request):
        mois = request.query_params.get('mois', timezone.now().strftime('%Y-%m'))
        debut_mois = datetime.strptime(mois, '%Y-%m').date()
        fin_mois = (debut_mois + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        absences = AbsencesProfs.objects.filter(date_absence__range=[debut_mois, fin_mois])
        data = {}
        for a in absences:
            nom = a.professeur.display_name
            if nom not in data: data[nom] = {'dates': [], 'total': 0}
            data[nom]['dates'].append(a.date_absence.isoformat())
            data[nom]['total'] += 1
        RapportAuto.objects.create(type_rapport='monthly', periode_debut=debut_mois, periode_fin=fin_mois, contenu_json=data, created_at=timezone.now())
        return Response({'rapport_mensuel': data, 'message': 'Rapport généré et prêt à envoi.'})

# Placeholders pour autres endpoints non détaillés mais nécessaires
class GenerateMonthlyAbsenceReportView(APIView): 
    permission_classes = [IsDirection]; 
    def get(self, r): 
        return Response({'status': 'ok'})



# redis : class tableau 

class TableauConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.classe_id = self.scope['url_route']['kwargs']['classe_id']
        self.seance_id = self.scope['url_route']['kwargs']['seance_id']

        # ── Récupérer le token depuis l'URL ──────────────────────────────
        query_string = self.scope.get('query_string', b'').decode()
        token = None
        for part in query_string.split('&'):
            if part.startswith('token='):
                token = part.split('=', 1)[1]
                break

        if not token:
            await self.close(code=4001)
            return

        # ── Décoder le token et récupérer l'utilisateur ──────────────────
        self.user = await self.get_user_from_token(token)
        if not self.user:
            await self.close(code=4001)
            return

        # ── Vérifier l'accès à la classe ─────────────────────────────────
        if not await self.check_access():
            await self.close(code=4003)
            return

        self.group_name = f"tableau_{self.classe_id}_{self.seance_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            event_type = data.get('type')

            if event_type == 'request_state':
                state = cache.get(f"tableau_state_{self.group_name}")
                if state:
                    await self.send(text_data=json.dumps({
                        'type': 'canvas_state',
                        'dataUrl': state,
                    }))
                return

            if event_type in ('canvas_state', 'undo'):
                cache.set(
                    f"tableau_state_{self.group_name}",
                    data.get('dataUrl', ''),
                    timeout=60 * 60 * 8
                )

            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'tableau_event',
                    'data': data,
                    'sender_channel': self.channel_name,
                }
            )

        except (json.JSONDecodeError, KeyError):
            pass

    async def tableau_event(self, event):
        if event.get('sender_channel') == self.channel_name:
            if event['data'].get('type') != 'cursor':
                return
        await self.send(text_data=json.dumps(event['data']))

    @database_sync_to_async
    def get_user_from_token(self, token):
        """Décode le JWT et retourne l'utilisateur Django."""
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            # Décoder le token SimpleJWT
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            return User.objects.get(id=user_id)
        except Exception as e:
            print(f"Token invalide : {e}")
            return None

    @database_sync_to_async
    def check_access(self):
        try:
            from .models import Classes, Inscriptions

            if not self.user or not hasattr(self.user, "id"):
                return False

            classe = Classes.objects.get(id=self.classe_id)

            # ── Professeur de la classe ──────────────────────────────────
            if classe.professeur_id == self.user.id:
                return True

            # ── Élève inscrit à la classe ────────────────────────────────
            return Inscriptions.objects.filter(
                classe_id=self.classe_id,
                eleve_id=self.user.id,
            ).exists()

        except Exception as e:
            print(f"Erreur check_access: {e}")
            return False




def get_presence_manuelle_today(seance_id: str) -> Presences | None:
    """
    Retourne la dernière présence de la séance dont :
      - enregistrement_system = False
      - DATE(created_at) = aujourd'hui
    ou None si aucune.
    """
    today = localdate()
    return (
        Presences.objects
        .filter(
            seance_id=seance_id,
            enregistrement_system=False,
            created_at__date=today,
        )
        .order_by('-created_at')
        .first()
    )


class PresenceManuelleViewSet(viewsets.ModelViewSet):
    queryset = Presences.objects.filter(enregistrement_system=False)
    serializer_class = PresenceManuelleSerializer
    """
    GET  /api/presences/manuelle/?seance_id=<uuid>
         → présence manuelle d'aujourd'hui (ou null)

    POST /api/presences/manuelle/
         body: { seance_id, heure_connexion_prof?, temps_prof? }
         → crée une nouvelle présence manuelle si aucune aujourd'hui,
           sinon met à jour la dernière

    PATCH /api/presences/manuelle/<id>/
         body: { heure_connexion_prof?, temps_prof? }
         → met à jour la présence manuelle
    """
    permission_classes = [IsAuthenticated]

    def list(self, request):
        seance_id = request.query_params.get('seance_id')
        if not seance_id:
            return Response({'detail': 'seance_id requis.'}, status=status.HTTP_400_BAD_REQUEST)

        presence = get_presence_manuelle_today(seance_id)
        if not presence:
            return Response(None, status=status.HTTP_200_OK)

        return Response(PresenceManuelleSerializer(presence).data)

    def create(self, request):
        seance_id = request.data.get('seance_id')
        if not seance_id:
            return Response({'detail': 'seance_id requis.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            seance = Seances.objects.get(id=seance_id)
        except Seances.DoesNotExist:
            return Response({'detail': 'Séance introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        # Cherche une présence manuelle existante aujourd'hui
        presence = get_presence_manuelle_today(seance_id)

        if presence:
            # Update la présence existante
            serializer = PresenceManuelleSerializer(presence, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        else:

            heure_str = request.data.get('heure_connexion_prof')

            heure_connexion = None
            if heure_str:
                heure_str = heure_str.strip()  # enlève les espaces bizarres (\xa0)
                
                try:
                    heure = datetime.strptime(heure_str, "%H:%M:%S").time()
                    heure_connexion = timezone.make_aware(
                        datetime.combine(localdate(), heure)
                    )
                except ValueError:
                    return Response(
                        {'detail': "Format heure invalide. Utilise HH:MM:SS"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            # Crée une nouvelle présence manuelle
            presence = Presences.objects.create(
                classe=seance.classe,
                user=request.user,
                seance=seance,
                enregistrement_system=False,
                date_seance=localdate(),
                created_at=timezone.now(),
                heure_connexion_prof=heure_connexion,
                temps_prof=request.data.get('temps_prof') or None,
            )
            return Response(PresenceManuelleSerializer(presence).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        try:
            presence = Presences.objects.get(id=pk, enregistrement_system=False)
        except Presences.DoesNotExist:
            return Response({'detail': 'Présence introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = PresenceManuelleSerializer(presence, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AbsencesElevesViewSet(viewsets.ViewSet):

    """
    GET  /api/absences-eleves/?seance_id=<uuid>
         → liste tous les élèves inscrits à la classe de la séance.
           Pour chaque élève, retourne l'éventuelle ligne AbsencesProfs
           liée à la présence manuelle d'aujourd'hui.
           Si aucune présence manuelle aujourd'hui → 404 avec has_presence=False.

    POST /api/absences-eleves/
         body: { presence_id, eleve_id, temps_effectif?, durree_eleve? }
         → crée ou met à jour la ligne AbsencesProfs pour cet élève

    PATCH /api/absences-eleves/<id>/
         body: { temps_effectif?, durree_eleve? }
         → met à jour une ligne existante
    """
    permission_classes = [IsAuthenticated]

    def list(self, request):
        seance_id = request.query_params.get('seance_id')
        if not seance_id:
            return Response({'detail': 'seance_id requis.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            seance = Seances.objects.select_related('classe').get(id=seance_id)
        except Seances.DoesNotExist:
            return Response({'detail': 'Séance introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        # Présence manuelle d'aujourd'hui
        presence = get_presence_manuelle_today(seance_id)
        if not presence:
            return Response(
                {'has_presence': False, 'eleves': []},
                status=status.HTTP_200_OK
            )

        # Tous les élèves inscrits à la classe
        inscriptions = (
            Inscriptions.objects
            .filter(classe=seance.classe, statut='active')
            .select_related('eleve')
            .order_by('eleve__display_name')
        )

        # AbsencesProfs existantes pour cette présence
        absences_map: dict = {
            str(a.eleve_id): a
            for a in AbsencesProfs.objects.filter(presence=presence).select_related('eleve')
        }

        result = []
        for inscription in inscriptions:
            eleve = inscription.eleve
            eleve_id_str = str(eleve.id)
            absence = absences_map.get(eleve_id_str)
            result.append({
                'absence_id':    str(absence.id) if absence else None,
                'eleve_id':      eleve_id_str,
                'eleve_nom':     eleve.display_name or eleve.email,
                'temps_effectif': absence.temps_effectif if absence else None,
                'durree_eleve':  absence.durree_eleve if absence else None,
                'presence_id':   str(presence.id),
            })

        return Response({'has_presence': True, 'eleves': result})

    def create(self, request):
        """Crée ou met à jour une ligne AbsencesProfs."""
        presence_id = request.data.get('presence_id')
        eleve_id    = request.data.get('eleve_id')

        if not presence_id or not eleve_id:
            return Response({'detail': 'presence_id et eleve_id requis.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            presence = Presences.objects.get(id=presence_id)
        except Presences.DoesNotExist:
            return Response({'detail': 'Présence introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        absence, created = AbsencesProfs.objects.get_or_create(
            presence=presence,
            eleve_id=eleve_id,
            enregistrement_system=False,
            defaults={'created_at': timezone.now()},
        )

        # Mise à jour des champs
        if 'temps_effectif' in request.data:
            absence.temps_effectif = request.data['temps_effectif']
        if 'durree_eleve' in request.data:
            val = request.data['durree_eleve']
            absence.durree_eleve = int(val) if val not in (None, '', 'null') else None
        absence.save()

        return Response(AbsenceEleveSerializer(absence).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def partial_update(self, request, pk=None):
        try:
            absence = AbsencesProfs.objects.get(id=pk)
        except AbsencesProfs.DoesNotExist:
            return Response({'detail': 'Absence introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        allowed = {'temps_effectif', 'durree_eleve'}
        data = {k: v for k, v in request.data.items() if k in allowed}
        serializer = AbsenceEleveSerializer(absence, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
