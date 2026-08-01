from rest_framework import serializers
from django.contrib.auth.hashers import make_password, check_password
from .models import *
from datetime import datetime
from decimal import Decimal
from django.utils import timezone

from django.utils.timezone import localdate
# ================= AUTH & USERS =================
class UserSerializer(serializers.ModelSerializer):
    # ✅ Ajoute ce champ pour afficher le nom de l'admin assigné
    admin_nom = serializers.SerializerMethodField(read_only=True)
    parent_email = serializers.SerializerMethodField(read_only=True)
    class Meta:
        model = Users
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'first_login_done']

    def get_admin_nom(self, obj):
        """Récupère le nom de l'admin assigné via son UUID"""
        if not obj.admin_id:
            return None
        try:
            # On évite un crash si l'admin a été supprimé
            admin = Users.objects.get(id=obj.admin_id, role='admin')
            return admin.display_name
        except Users.DoesNotExist:
            return None
    def get_parent_email(self, obj):
        return obj.parent.email if obj.parent else None

class UserCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    display_name = serializers.CharField(max_length=150, required=False)
    nom_complet = serializers.CharField(max_length=150, required=False)
    role = serializers.ChoiceField(choices=['admin', 'professeur', 'eleve'])
    nom_diplome = serializers.CharField(max_length=150, required=False)
    admin_id = serializers.UUIDField(required=False)
    code_prof = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True
    )

class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=False)
    new_password = serializers.CharField(min_length=6)

class ForcePasswordChangeSerializer(serializers.Serializer):
    new_password = serializers.CharField(min_length=6)

# ================= CLASSES & INSCRIPTIONS =================
class ClassSerializer(serializers.ModelSerializer):
    professeur_nom = serializers.CharField(source='professeur.display_name', read_only=True, required=False)
    admin_nom = serializers.CharField(source='admin.display_name', read_only=True, required=False)
    nb_inscrits = serializers.SerializerMethodField()

    class Meta:
        model = Classes
        fields = '__all__'
        read_only_fields = ['id','created_by', 'created_at', 'updated_at', 'jitsi_room_id','nom']

    def get_nb_inscrits(self, obj):
        return Inscriptions.objects.filter(classe=obj).count()

class InscriptionSerializer(serializers.ModelSerializer):
    eleve_nom = serializers.CharField(source='eleve.display_name', read_only=True)
    classe_nom = serializers.CharField(source='classe.nom', read_only=True)
    statut = serializers.CharField(default='active')
    #eleve = UserSerializer(read_only=True)
    eleve_id = serializers.UUIDField(source='eleve.id', read_only=True)  # ✅ AJOUT

    class Meta:
        model = Inscriptions
        fields = '__all__'
        read_only_fields = ['id','created_at', 'contrat_signe_at']

class SeanceSerializer(serializers.ModelSerializer):
    classe_nom = serializers.CharField(source='classe.nom', read_only=True)
    class Meta:
        model = Seances
        fields = '__all__'
        read_only_fields = ['created_at']


class SeanceJourSerializer(serializers.ModelSerializer):
    classe_nom = serializers.CharField(source='classe.nom', read_only=True)
    classe_id = serializers.UUIDField(source='classe.id', read_only=True)

    class Meta:
        model = Seances
        fields = [
            'id', 'classe', 'classe_nom', 'classe_id', 
            'date_seance', 'jour_seance', 'heure_debut_reelle', 
            'duree_reelle_minutes', 'statut', 'created_at'
        ]
        read_only_fields = ['created_at']


class CatalogueCoursSerializer(serializers.ModelSerializer):
    """
    Serializer pour le catalogue de cours / parcours pédagogique.
    Gère la relation récursive prerequis et affiche la progression élève.
    """
    # Champ calculé : nom du prérequis (affichage simple)
    # prerequis_nom = serializers.CharField(source='prerequis.nom', read_only=True)
    
    # # Champ optionnel : liste des cours qui ont CE cours comme prérequis (rétro-liens)
    # est_prerequis_de = serializers.SerializerMethodField()
    
    # # Pour l'espace élève : progression dans ce cours (si inscrit)
    # progression_eleve = serializers.SerializerMethodField()
    
    # # Nombre total d'élèves inscrits dans ce cours (via Classes liées)
    # nb_eleves_inscrits = serializers.SerializerMethodField()

    class Meta:
        model = CatalogueCours
        fields = ['id', 'nom', 'description', 'niveau', 'created_at'] 
        #read_only_fields = ['created_at']

    # def get_est_prerequis_de(self, obj):
    #     """Retourne la liste des cours dont ce cours est le prérequis."""
    #     enfants = CatalogueCours.objects.filter(prerequis=obj).values('id', 'nom', 'niveau', 'ordre')
    #     return list(enfants)

    # def get_progression_eleve(self, obj):
    #     """
    #     Calcule la progression de l'élève connecté dans ce cours.
    #     Retourne un dict avec % de complétion et étapes acquises.
    #     (À appeler uniquement dans l'espace élève)
    #     """
    #     request = self.context.get('request')
    #     if not request or not hasattr(request, 'user') or request.user.role != 'eleve':
    #         return None
            
    #     # Logique exemple : progression basée sur les diplômes obtenus + devoirs validés
    #     # À adapter selon ta logique métier réelle
    #     diplome_obtenu = Diplomes.objects.filter(
    #         eleve=request.user, 
    #         classe__programme=obj.nom  # ou autre critère de liaison
    #     ).exists()
        
    #     devoirs_valides = Devoirs.objects.filter(
    #         eleve=request.user,
    #         classe__programme=obj.nom,
    #         statut='valide'
    #     ).count()
        
    #     total_devoirs = Devoirs.objects.filter(
    #         classe__programme=obj.nom
    #     ).count()
        
    #     if total_devoirs == 0:
    #         pourcentage = 100 if diplome_obtenu else 0
    #     else:
    #         pourcentage = min(100, int((devoirs_valides / total_devoirs) * 100))
    #         if diplome_obtenu:
    #             pourcentage = 100
                
    #     return {
    #         'pourcentage': pourcentage,
    #         'diplome_obtenu': diplome_obtenu,
    #         'devoirs_valides': devoirs_valides,
    #         'total_devoirs': total_devoirs,
    #         'statut': 'acquis' if pourcentage == 100 else 'en_cours' if pourcentage > 0 else 'non_commence'
    #     }

    # def get_nb_eleves_inscrits(self, obj):
    #     """Compte le nombre d'élèves actifs dans les classes liées à ce cours."""
    #     return Inscriptions.objects.filter(
    #         classe__programme=obj.nom,  # ou classe__catalogue=obj si tu ajoutes ce FK
    #         statut='actif'
    #     ).count()

    # def validate_ordre(self, value):
    #     """Valide que l'ordre est positif et cohérent avec le niveau."""
    #     if value is not None and value < 0:
    #         raise serializers.ValidationError("L'ordre doit être un entier positif.")
    #     return value

    # def validate(self, data):
    #     """
    #     Validation métier :
    #     - Un cours ne peut pas être son propre prérequis
    #     - L'ordre doit être cohérent avec le prérequis (ordre enfant > ordre parent)
    #     """
    #     prerequis = data.get('prerequis')
    #     ordre = data.get('ordre')
        
    #     # Auto-référence interdite
    #     if prerequis and self.instance and prerequis == self.instance:
    #         raise serializers.ValidationError({'prerequis': "Un cours ne peut pas être son propre prérequis."})
        
    #     # Cohérence ordre/niveau
    #     if prerequis and ordre is not None and prerequis.ordre is not None:
    #         if ordre <= prerequis.ordre:
    #             raise serializers.ValidationError({
    #                 'ordre': f"L'ordre ({ordre}) doit être supérieur à celui du prérequis '{prerequis.nom}' ({prerequis.ordre})."
    #             })
        
    #     return data

# ================= MESSAGERIE & NOTIFICATIONS =================
class MessageSerializer(serializers.ModelSerializer):
    expediteur_nom = serializers.CharField(source='expediteur.display_name', read_only=True)
    fichier_url = serializers.CharField(source='fichier.fichier_local.url', read_only=True)
    nom_fichier = serializers.CharField(source='fichier.nom_original', read_only=True)
    fichier_expires_at = serializers.DateTimeField(source='fichier.fichier_expires_at', read_only=True, allow_null=True)
    is_voice_note = serializers.BooleanField(source='fichier.is_voice_note', read_only=True)
    reply_to_preview = serializers.SerializerMethodField(read_only=True)
    recu_par = serializers.ListField(read_only=True, default=list)
    lu_par_ids = serializers.ListField(read_only=True, default=list)
    
    classe = serializers.PrimaryKeyRelatedField(
        queryset=Classes.objects.all(),
        required=False,  # ✅ géré dans perform_create
        allow_null=True,
    )
    
    class Meta:
        model = Messages
        fields = '__all__'
        read_only_fields = [
            'id', 'expediteur', 'type_canal', 'is_systeme', 'recu_par','lu_par_ids',
            'created_at', 'deleted_at', 
            'fichier_expires_at', 'is_voice_note',
            'fichier',  # <--- TRÈS IMPORTANT
            'reply_to_preview'
        ]

    def get_reply_to_preview(self, obj):
        if not obj.reply_to:
            return None
            
        
        expediteur_nom = "Utilisateur"
        if hasattr(obj.reply_to.expediteur, 'display_name'):
            expediteur_nom = obj.reply_to.expediteur.display_name
            
        nom_fichier = None
        if hasattr(obj.reply_to, 'fichier') and obj.reply_to.fichier:
            nom_fichier = obj.reply_to.fichier.nom_original

        return {
            'id': str(obj.reply_to.id),
            'expediteur_nom': expediteur_nom,
            'type_message': obj.reply_to.type_message,
            'contenu': obj.reply_to.contenu,
            'nom_fichier': nom_fichier,
            'fichier_url':  obj.reply_to.fichier.fichier_local.url if  obj.reply_to.fichier_id else None, 
        }


class PrivateMessageSerializer(serializers.ModelSerializer):
    expediteur_nom = serializers.CharField(source='expediteur.display_name', read_only=True)
    destinataire_nom = serializers.CharField(source='destinataire.display_name', read_only=True)
    fichier_url = serializers.CharField(source='fichier.fichier_local.url', read_only=True, allow_null=True)
    nom_fichier = serializers.CharField(source='fichier.nom_original', read_only=True, allow_null=True)
    fichier_expires_at = serializers.DateTimeField(source='fichier.fichier_expires_at', read_only=True, allow_null=True)
    is_voice_note = serializers.BooleanField(source='fichier.is_voice_note', read_only=True, default=False)
    reply_to_preview = serializers.SerializerMethodField(read_only=True)

    destinataire = serializers.PrimaryKeyRelatedField(
        queryset=Users.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = MessagesPrives
        fields = '__all__'
        read_only_fields = [
            'id', 'expediteur', 'lu', 'lu_at', 'created_at', 'deleted_at',
            'fichier', 'fichier_expires_at', 'is_voice_note', 'reply_to_preview',
        ]

    def get_reply_to_preview(self, obj):
        if not obj.reply_to:
            return None
        expediteur_nom = "Utilisateur"
        if hasattr(obj.reply_to.expediteur, 'display_name'):
            expediteur_nom = obj.reply_to.expediteur.display_name
        nom_fichier = None
        if obj.reply_to.fichier_id:
            nom_fichier = obj.reply_to.fichier.nom_original
        return {
            'id': str(obj.reply_to.id),
            'expediteur_nom': expediteur_nom,
            'type_message': obj.reply_to.type_message,
            'contenu': obj.reply_to.contenu,
            'nom_fichier': nom_fichier,
            'fichier_url': obj.reply_to.fichier.fichier_local.url if obj.reply_to.fichier_id else None,
        }
class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notifications
        fields = '__all__'
        read_only_fields = ['created_at', 'lu_at']


# ================= PÉDAGOGIE & SUIVI =================
# serializers.py

class FichierDevoirSerializer(serializers.ModelSerializer):
    fichier_url = serializers.SerializerMethodField()
    
    class Meta:
        model = FichiersDevoir
        fields = [
            'id', 'devoir', 'eleve', 'nom_original', 'nom_stockage',
            'type_fichier', 'mime_type', 'taille_bytes', 'created_at', 'fichier_url'
        ]
        read_only_fields = ['created_at', 'nom_stockage', 'taille_bytes', 'mime_type']
    
    def get_fichier_url(self, obj):
        # À adapter selon ton stockage (S3, Cloudinary, local...)
        if hasattr(obj, 'fichier') and obj.fichier:
            return obj.fichier.url
        return f"/api/fichiers/{obj.id}/download/"


class DevoirSerializer(serializers.ModelSerializer):
    fichiers = FichierDevoirSerializer(many=True, read_only=True)
    # Pour l'affichage dans la liste
    classe_nom = serializers.CharField(source='seance.classe.nom', read_only=True)
    professeur_nom = serializers.CharField(source='seance.classe.professeur.display_name', read_only=True)

    class Meta:
        model = Devoirs
        fields = '__all__'
        read_only_fields = ['created_at', 'submitted_at', 'corrige_at']

    def validate_statut(self, value):
        valid = ['brouillon', 'soumis', 'cloturer', 'corrige']
        if value not in valid:
            raise serializers.ValidationError(f"Statut doit être l'un de : {valid}")
        return value
        
    def validate_seance(self, value):
        request = self.context.get('request')
        if request and request.user.role == 'professeur':
            if value.classe.professeur != request.user:
                raise serializers.ValidationError("Vous ne pouvez créer un devoir que dans vos propres séances")
        return value


class GestionDevoirSerializer(serializers.ModelSerializer):
    seance_id = serializers.UUIDField(source='seance.id', read_only=True)
    classe_id = serializers.UUIDField(source='seance.classe.id', read_only=True)
 
    class Meta:
        model = Devoirs
        fields = [
            'id', 'titre', 'statut',
            'created_at', 'submitted_at', 'corrige_at',
            'seance_id', 'classe_id',
        ]
        read_only_fields = ['id', 'created_at', 'seance_id', 'classe_id']


class ElevesDevoirSerializer(serializers.Serializer):
    """Sérialiseur de présentation pour la liste des élèves d'un devoir."""
    absence_id = serializers.UUIDField()
    presence_id = serializers.UUIDField()
    eleve = serializers.DictField()
    note = serializers.CharField(allow_null=True)
    fichiers_eleve = FichierDevoirSerializer(many=True)
    fichiers_corriges = FichierDevoirSerializer(many=True)


class PresenceSerializer(serializers.ModelSerializer):
    classe_nom = serializers.CharField(source='classe.nom', read_only=True)
    user_nom = serializers.CharField(source='user.display_name', read_only=True)

    class Meta:
        model = Presences
        fields = '__all__'
        read_only_fields = ['created_at', 'heure_connexion', 'heure_deconnexion']

class QuestionEntreeSerializer(serializers.ModelSerializer):
    classe_nom = serializers.CharField(source='classe.nom', read_only=True)
    class Meta:
        model = QuestionsEntree
        fields = '__all__'
        read_only_fields = ['created_at', 'notif_envoyee_at']

class AbsenceProfSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = AbsencesProfs
        fields = '__all__'
        read_only_fields = ['created_at']

# ================= FACTURATION & PAIEMENTS =================

class FactureLigneSerializer(serializers.Serializer):
    """Ligne de détail : une présence dans l'intervalle."""
    presence_id      = serializers.UUIDField()
    seance_id        = serializers.UUIDField()
    date_seance      = serializers.DateTimeField()
    heure_connexion_prof  = serializers.DateTimeField(allow_null=True)
    heure_deconnexion = serializers.DateTimeField(allow_null=True)
    duree_heures     = serializers.DecimalField(max_digits=20, decimal_places=10)
    nb_participants  = serializers.IntegerField()
    nb_inscrits      = serializers.IntegerField()
 
 
class FactureCreateSerializer(serializers.Serializer):
    """Payload reçu depuis le front pour créer une facture."""
    classe_id   = serializers.UUIDField()
    date_debut  = serializers.DateField()   # YYYY-MM-DD
    date_fin    = serializers.DateField()
    lien_paypal = serializers.URLField(required=False, allow_blank=True)
    rib         = serializers.CharField(required=False, allow_blank=True)
 
 
class FactureSerializer(serializers.ModelSerializer):
    """Lecture d'une facture (liste / détail)."""
    classe_nom      = serializers.CharField(source='classe.nom', read_only=True)
    professeur_nom  = serializers.SerializerMethodField()
    periode_debut   = serializers.DateTimeField(source='date_debut', read_only=True)
    periode_fin     = serializers.DateTimeField(source='date_fin',   read_only=True)
    montant_total   = serializers.DecimalField(max_digits=20, decimal_places=10, read_only=True)
    #taux_horaire    = serializers.DecimalField(max_digits=20, decimal_places=10, read_only=True)
    honoraire       = serializers.DecimalField(max_digits=20, decimal_places=10, read_only=True)
    part_direction = serializers.DecimalField(max_digits=20, decimal_places=10, read_only=True)
    part_prof = serializers.DecimalField(max_digits=20, decimal_places=10, read_only=True)
 
    class Meta:
        model  = Factures
        fields = [
            'id', 'created_at',
            'classe', 'classe_nom',
            'professeur', 'professeur_nom',
            'nb_eleves_inscrits', 'nbr_eleves_participe',
            'honoraire', 'montant_total',
            'statut', 'lien_paypal', 'rib',
            'date_debut', 'date_fin',
            'date_echeance', 'envoyee_chat', 'envoyee_chat_at',
            'periode_debut', 'periode_fin','part_direction','part_prof',
        ]
 
    def get_professeur_nom(self, obj):
        u = obj.professeur
        return u.display_name or u.nom_complet or u.email


class FactureParticipantSerializer(serializers.Serializer):
    """Serializer pour la liste des participants d'une facture en preview."""
    absence_prof_id = serializers.UUIDField(read_only=True)
    eleve_id = serializers.UUIDField(read_only=True)
    eleve_nom = serializers.CharField(read_only=True)
    eleve_email = serializers.EmailField(read_only=True, allow_null=True)
    montant_a_paye = serializers.IntegerField(read_only=True, allow_null=True)
    presence_id = serializers.UUIDField(read_only=True)
    seance_id = serializers.UUIDField(read_only=True)

    class Meta:
        fields = [
            'absence_prof_id', 'eleve_id', 'eleve_nom', 'eleve_email',
            'montant_a_paye', 'presence_id', 'seance_id'
        ]


class ParticipantPaymentInputSerializer(serializers.Serializer):
    """Input pour mettre à jour le montant d'un participant."""
    absence_prof_id = serializers.UUIDField(required=True)
    montant_a_paye = serializers.IntegerField(allow_null=True, required=True)

    def validate_montant_a_paye(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Le montant ne peut pas être négatif")
        return value


class ParticipantsPaymentSerializer(serializers.Serializer):
    """Payload pour mettre à jour les paiements de tous les participants."""
    #facture_id = serializers.UUIDField(required=True)
    payeur_id = serializers.UUIDField(required=True)
    participants = ParticipantPaymentInputSerializer(many=True, required=True)

    def validate(self, data):
        participants = data.get('participants', [])
        # Validation front-end : si un montant est saisi, tous doivent l'être
        amounts = [p.get('montant_a_paye') for p in participants]
        has_any_filled = any(a is not None for a in amounts)
        all_filled = all(a is not None for a in amounts)
        
        if has_any_filled and not all_filled:
            raise serializers.ValidationError(
                "Si vous saisissez un montant pour un élève, veuillez remplir tous les champs (mettez 0 si gratuit)"
            )
        return data


class PaiementSerializer(serializers.ModelSerializer):
    facture_classe = serializers.CharField(source='facture.classe.nom', read_only=True)
    class Meta:
        model = Paiements
        fields = '__all__'
        read_only_fields = ['confirme_par', 'paid_at']

class RappelPaiementSerializer(serializers.ModelSerializer):
    class Meta:
        model = RappelsPaiement
        fields = '__all__'
        read_only_fields = ['created_at', 'envoye_at']

# ================= PLANNING & CRÉNEAUX =================
class PlanningDispoSerializer(serializers.ModelSerializer):
    professeur_nom = serializers.CharField(source='professeur.display_name', read_only=True)
    class Meta:
        model = PlanningDispos
        fields = '__all__'
        read_only_fields = ['updated_at']

class HistoriqueCreneauSerializer(serializers.ModelSerializer):
    classe_nom = serializers.CharField(source='classe.nom', read_only=True)
    modifie_par_nom = serializers.CharField(source='modifie_par.display_name', read_only=True)
    class Meta:
        model = HistoriqueCreneaux
        fields = '__all__'
        read_only_fields = ['created_at', 'notif_envoyee_at']

# ================= CLASSE VIRTUELLE & OUTILS =================
class EnregistrementSerializer(serializers.ModelSerializer):
    classe_nom = serializers.CharField(source='classe.nom', read_only=True)
    demarre_par_nom = serializers.CharField(source='demarre_par.display_name', read_only=True)
    class Meta:
        model = Enregistrements
        fields = '__all__'
        read_only_fields = ['started_at', 'ended_at', 'deleted_at', 'taille_bytes', 'duree_secondes']

class TableauBlancSerializer(serializers.ModelSerializer):
    auteur_nom = serializers.CharField(source='auteur.display_name', read_only=True)
    class Meta:
        model = TableauBlanc
        fields = '__all__'
        read_only_fields = ['created_at']

class FichierSerializer(serializers.ModelSerializer):
    uploade_par_nom = serializers.CharField(source='uploade_par.display_name', read_only=True)
    class Meta:
        model = Fichiers
        fields = '__all__'
        read_only_fields = ['created_at', 'taille_bytes', 'url_cloud', 'nom_stockage']

# ================= ADMIN & DIRECTION =================
# serializers.py  (à intégrer dans votre fichier serializers existant)


class AssigneeSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source='user.display_name', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = TacheDirectionAssignee
        fields = ['id', 'user', 'display_name', 'email', 'assigned_at']


class AdminUserSerializer(serializers.ModelSerializer):
    """Sérialiseur léger pour lister les admins assignables."""
    class Meta:
        model = Users
        fields = ['id', 'display_name', 'email']


class TacheDirectionSerializer(serializers.ModelSerializer):
    assignees = AssigneeSerializer(
        source='tachedirectionassignee_set',
        many=True,
        read_only=True
    )
    assignee_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False
    )
    created_by_name = serializers.CharField(
        source='created_by.display_name', read_only=True
    )
    faite_par_name = serializers.CharField(
        source='faite_par.display_name', read_only=True, default=None
    )

    class Meta:
        model = TachesDirection
        fields = [
            'id', 'titre', 'description',
            'faite', 'faite_par', 'faite_par_name',
            'created_by', 'created_by_name',
            'faite_at', 'created_at','delais',
            'assignees', 'assignee_ids',
        ]
        read_only_fields = ['id', 'created_at', 'faite_at', 'created_by']

    def create(self, validated_data):
        assignee_ids = validated_data.pop('assignee_ids', [])
        tache = TachesDirection.objects.create(**validated_data)
        for uid in assignee_ids:
            TacheDirectionAssignee.objects.get_or_create(tache=tache, user_id=uid)
        return tache

    def update(self, instance, validated_data):
        assignee_ids = validated_data.pop('assignee_ids', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if assignee_ids is not None:
            TacheDirectionAssignee.objects.filter(tache=instance).delete()
            for uid in assignee_ids:
                TacheDirectionAssignee.objects.get_or_create(tache=instance, user_id=uid)
        return instance


class MarquerFaiteSerializer(serializers.Serializer):
    faite = serializers.BooleanField()

class LogActiviteSerializer(serializers.ModelSerializer):
    user_nom = serializers.CharField(source='user.display_name', read_only=True)
    class Meta:
        model = LogsActivite
        fields = '__all__'
        read_only_fields = ['created_at']

class RapportAutoSerializer(serializers.ModelSerializer):
    class Meta:
        model = RapportsAuto
        fields = '__all__'
        read_only_fields = ['created_at', 'envoye_at']

class DiplomeSerializer(serializers.ModelSerializer):
    eleve_nom = serializers.CharField(source='eleve.display_name', read_only=True)
    classe_nom = serializers.CharField(source='classe.nom', read_only=True)
    professeur_nom = serializers.CharField(source='professeur.display_name', read_only=True)
    image_diplome = serializers.FileField(required=False, allow_null=True)
    class Meta:
        model = Diplomes
        fields = '__all__'
        read_only_fields = ['created_at', 'delivre_at','professeur','nom_original', 'nom_stockage', 'type_fichier', 'mime_type', 'taille_bytes']

class ContratSerializer(serializers.ModelSerializer):
    eleve_nom = serializers.CharField(source='eleve.display_name', read_only=True)
    classe_nom = serializers.CharField(source='classe.nom', read_only=True)
    class Meta:
        model = Contrats
        fields = '__all__'
        read_only_fields = ['signe_at', 'ip_signature', 'contenu_snapshot']



class ClasseSimpleSerializer(serializers.ModelSerializer):
    """Classe légère pour le sélecteur d'assignation."""
    professeur_nom = serializers.CharField(source='professeur.display_name', read_only=True, default=None)
    nb_eleves = serializers.SerializerMethodField()

    class Meta:
        model = Classes
        fields = ['id', 'nom', 'niveau', 'type_cours', 'statut', 'professeur_nom', 'nb_eleves']

    def get_nb_eleves(self, obj):
        return Inscriptions.objects.filter(classe=obj, statut='active').count()


class EleveSimpleSerializer(serializers.ModelSerializer):
    """Élève léger pour le sélecteur."""
    class Meta:
        model = Users
        fields = ['id', 'display_name', 'email']


class EleveParClasseSerializer(serializers.Serializer):
    """Retourne les élèves actifs d'une classe."""
    classe_id = serializers.UUIDField()
    classe_nom = serializers.CharField()
    eleves = EleveSimpleSerializer(many=True)


class AnnoncesElevesSerializer(serializers.ModelSerializer):
    eleve_nom = serializers.CharField(source='eleve.display_name', read_only=True)
    eleve_email = serializers.EmailField(source='eleve.email', read_only=True)

    class Meta:
        model = AnnoncesEleves
        fields = ['id', 'eleve', 'eleve_nom', 'eleve_email', 'statut', 'created_at']


class AnnoncesGroupeSerializer(serializers.ModelSerializer):
    destinataires = AnnoncesElevesSerializer(
        source='annoncesEleves_set',
        many=True,
        read_only=True
    )
    nb_destinataires = serializers.SerializerMethodField()
    nb_lus = serializers.SerializerMethodField()
    fichier_url = serializers.SerializerMethodField()

    # Write-only : liste d'IDs élèves
    """ eleve_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=True
    ) """

    class Meta:
        model = AnnoncesGroupe
        fields = [
            'id', 'titre',
            'nom_original', 'nom_stockage',
            'fichier_local', 'fichier_url',
            'type_fichier', 'mime_type', 'taille_bytes', 'created_at',
            'destinataires', 'nb_destinataires', 'nb_lus',
            #'eleve_ids',
        ]
        read_only_fields = ['id', 'created_at', 'nom_stockage', 'type_fichier', 'mime_type', 'taille_bytes', 'nom_original']

    def get_nb_destinataires(self, obj):
        return obj.annoncesEleves_set.count()

    def get_nb_lus(self, obj):
        return obj.annoncesEleves_set.filter(statut=True).count()

    def get_fichier_url(self, obj):
        request = self.context.get('request')
        if obj.fichier_local and request:
            return request.build_absolute_uri(obj.fichier_local.url)
        return None

    def create(self, validated_data):
        #eleve_ids = validated_data.pop('eleve_ids')
        fichier = self.context['request'].FILES.get('fichier_local')

        import uuid, os
        from django.utils import timezone

        if fichier:
            validated_data['nom_original'] = fichier.name
            validated_data['nom_stockage'] = f"{uuid.uuid4()}{os.path.splitext(fichier.name)[1]}"
            validated_data['mime_type'] = fichier.content_type
            validated_data['taille_bytes'] = fichier.size
            validated_data['type_fichier'] = fichier.content_type.split('/')[0]  # 'image', 'video', etc.
            validated_data['fichier_local'] = fichier

        annonce = AnnoncesGroupe.objects.create(**validated_data)

        """ for uid in eleve_ids:
            AnnoncesEleves.objects.get_or_create(
                annonces_groupe=annonce,
                eleve_id=uid,
                defaults={'statut': False}
            ) """

             # Tous les élèves inscrits activement
        inscriptions = Inscriptions.objects.filter(
            statut='active'
        ).select_related('eleve')

        eleves_ids = set(
            inscriptions.values_list('eleve_id', flat=True)
        )

        AnnoncesEleves.objects.bulk_create([
            AnnoncesEleves(
                annonces_groupe=annonce,
                eleve_id=eleve_id,
                statut=False
            )
            for eleve_id in eleves_ids
        ])
        return annonce


class AnnoncesGroupeListSerializer(serializers.ModelSerializer):
    """Sérialiseur allégé pour la liste (sans détail destinataires)."""
    nb_destinataires = serializers.SerializerMethodField()
    nb_lus = serializers.SerializerMethodField()
    fichier_url = serializers.SerializerMethodField()
    #est_expiree = serializers.SerializerMethodField()

    class Meta:
        model = AnnoncesGroupe
        fields = [
            'id', 'titre', 'nom_original',
            'type_fichier', 'mime_type', 'taille_bytes',
            'fichier_url', 'created_at',
            'nb_destinataires', 'nb_lus',
        ]

    def get_nb_destinataires(self, obj):
        return obj.annoncesEleves_set.count()

    def get_nb_lus(self, obj):
        return obj.annoncesEleves_set.filter(statut=True).count()

    def get_fichier_url(self, obj):
        request = self.context.get('request')
        if obj.fichier_local and request:
            return request.build_absolute_uri(obj.fichier_local.url)
        return None

"""     def get_est_expiree(self, obj):
        from django.utils import timezone
        return obj.anonce_expired < timezone.now() """


# ── Vue élève : annonce reçue ──────────────────────────────────────────────────

class AnnonceEleveDetailSerializer(serializers.ModelSerializer):
    """Ce qu'un élève voit de ses annonces."""
    titre = serializers.CharField(source='annonces_groupe.titre')
    fichier_url = serializers.SerializerMethodField()
    type_fichier = serializers.CharField(source='annonces_groupe.type_fichier')
    mime_type = serializers.CharField(source='annonces_groupe.mime_type')
    nom_original = serializers.CharField(source='annonces_groupe.nom_original')
    #anonce_expired = serializers.DateTimeField(source='annonces_groupe.anonce_expired')
    annonce_created_at = serializers.DateTimeField(source='annonces_groupe.created_at')
    #est_expiree = serializers.SerializerMethodField()

    class Meta:
        model = AnnoncesEleves
        fields = [
            'id', 'statut', 'created_at',
            'titre', 'fichier_url', 'type_fichier', 'mime_type',
            'nom_original', 'annonce_created_at',
        ]

    def get_fichier_url(self, obj):
        request = self.context.get('request')
        if obj.annonces_groupe.fichier_local and request:
            return request.build_absolute_uri(obj.annonces_groupe.fichier_local.url)
        return None

    """ def get_est_expiree(self, obj):
        from django.utils import timezone
        return obj.annonces_groupe.anonce_expired < timezone.now() """


class ProfFacturePresenceSerializer(serializers.ModelSerializer):
    """
    Présences validées (eleve + prof) enrichies pour la vue facturation prof.
    """
    classe_nom    = serializers.CharField(source='classe.nom', read_only=True)
    seance_titre  = serializers.SerializerMethodField()
    nb_participants = serializers.SerializerMethodField()
    nb_inscrits   = serializers.SerializerMethodField()

    class Meta:
        model  = Presences
        fields = [
            'id', 'created_at',
            'classe', 'classe_nom',
            'seance', 'seance_titre',
            'nb_participants',
            'nb_inscrits',
        ]
        read_only_fields = fields

    def get_seance_titre(self, obj):
        s = obj.seance
        if not s:
            return None
        # On utilise created_at de la PRESENCE (date réelle du cours)
        date = obj.created_at.strftime('%d/%m/%Y') if obj.created_at else '—'
        heure = s.heure_debut_reelle.strftime('%H:%M') if s.heure_debut_reelle else '—'
        return f"Séance du {date} à {heure}"

    def get_nb_participants(self, obj):
        """
        Nombre d'élèves distincts ayant un AbsencesProfs validé
        (resp_query_10_prof=True ET resp_query_fin_prof=True) pour cette présence.
        """
        from django.db.models import Q
        return AbsencesProfs.objects.filter(
            presence=obj,
        ).exclude(
            Q(temps_effectif=False) & Q(durree_eleve__isnull=True)
        ).values('eleve').distinct().count()

        

    def get_nb_inscrits(self, obj):
        return Inscriptions.objects.filter(classe=obj.classe).count()

class SuiviPresenceSerializer(serializers.ModelSerializer):
    """
    Présences validées (eleve + prof) enrichies pour la vue facturation prof.
    """
    classe_nom    = serializers.CharField(source='classe.nom', read_only=True)
    seance_titre  = serializers.SerializerMethodField()
    nb_participants = serializers.SerializerMethodField()
    nb_inscrits   = serializers.SerializerMethodField()

    class Meta:
        model  = Presences
        fields = [
            'id', 'created_at',
            'classe', 'classe_nom',
            'seance', 'seance_titre',
            'nb_participants',
            'nb_inscrits','resp_query_10_eleve','resp_query_fin_eleve'
        ]
        read_only_fields = fields

    def get_seance_titre(self, obj):
        s = obj.seance
        if not s:
            return None
        # On utilise created_at de la PRESENCE (date réelle du cours)
        date = obj.created_at.strftime('%d/%m/%Y') if obj.created_at else '—'
        heure = s.heure_debut_reelle.strftime('%H:%M') if s.heure_debut_reelle else '—'
        return f"Séance du {date} à {heure}"

    def get_nb_participants(self, obj):
        """
        Nombre d'élèves distincts ayant un AbsencesProfs validé
        (resp_query_10_prof=True ET resp_query_fin_prof=True) pour cette présence.
        """
        return AbsencesProfs.objects.filter(
            presence=obj,
        ).values('eleve').distinct().count()

    def get_nb_inscrits(self, obj):
        return Inscriptions.objects.filter(classe=obj.classe).count()




# ─── Serializer léger pour le <select> côté front ────────────────────────────
# Distinct de ClassSerializer (qui sert à autre chose) : on expose
# uniquement les champs utiles pour peupler un dropdown.
class ClasseLightSerializer(serializers.ModelSerializer):
    class Meta:
        model = Classes
        fields = ['id', 'nom', 'niveau', 'programme']



# ─── Facture : lecture ────────────────────────────────────────────────────────
class FactureEleveSerializer(serializers.ModelSerializer):
    classe_nom = serializers.SerializerMethodField()
    uploade_par_nom = serializers.SerializerMethodField()
    classe = serializers.UUIDField(source='facture.classe_id', read_only=True)
    eleve_nom = serializers.CharField(source='eleve.display_name', read_only=True)
    eleve_email = serializers.EmailField(source='eleve.email', read_only=True)

    class Meta:
        model = FactureEleve
        fields = [
            'id',
            'uploade_par',
            'uploade_par_nom',
            'classe',
            'classe_nom',
            'nom_original',
            'url_cloud',
            'mime_type',
            'taille_bytes',
            'created_at',
            'date_debut',
            'date_fin',
            'statut',
            'montant_encaisser',
            'presence_id',
             'eleve_id', 'eleve_nom', 'eleve_email',
            'parent_id','montant_a_payer', 'montant_payer',
            'methode_payement', 'facture_id'
        ]
        read_only_fields = ['id', 'created_at', 'uploade_par_nom', 'classe_nom', 'url_cloud']

    def get_classe_nom(self, obj):
        return getattr(obj.classe, 'nom', None) if obj.classe else None

    def get_uploade_par_nom(self, obj):
        if not obj.uploade_par:
            return None
        return getattr(obj.uploade_par, 'display_name', None) or getattr(obj.uploade_par, 'username', '')


# ─── Facture : création ───────────────────────────────────────────────────────
class FactureEleveCreateSerializer(serializers.ModelSerializer):
    document = serializers.FileField(write_only=True)

    class Meta:
        model = FactureEleve
        fields = ['classe', 'date_debut', 'date_fin', 'document', 'montant_encaisser']

    def validate_document(self, value):
        allowed = ['application/pdf', 'image/jpeg', 'image/png', 'image/jpg']
        if value.content_type not in allowed:
            raise serializers.ValidationError("Format non supporté. Acceptés : PDF, JPEG, PNG.")
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("Fichier trop lourd (max 10 Mo).")
        return value

    def create(self, validated_data):
        import uuid, os
        request = self.context['request']
        document = validated_data.pop('document')
        ext = os.path.splitext(document.name)[1]
        storage_name = f"factures/{uuid.uuid4()}{ext}"

        # TODO: remplacer par ton upload cloud réel (S3, GCS, etc.)
        url_cloud = storage_name

        return FactureEleve.objects.create(
            id=uuid.uuid4(),
            uploade_par=request.user,
            classe=validated_data.get('classe'),
            nom_original=document.name,
            nom_stockage=storage_name,
            url_cloud=url_cloud,
            type_fichier='document',
            mime_type=document.content_type,
            taille_bytes=document.size,
            montant_encaisser=validated_data.get('montant_encaisser'),
            date_debut=validated_data.get('date_debut'),
            date_fin=validated_data.get('date_fin'),
            statut='paye',
        )


class FactureEleveListSerializer(serializers.ModelSerializer):
    """
    Serializer pour la liste des FactureEleve côté élève.
    Calcule le statut dynamiquement selon montant_a_payer vs montant_payer.
    """
    classe_nom    = serializers.CharField(source='facture.classe.nom', read_only=True)
    prof_nom      = serializers.CharField(source='facture.professeur.get_full_name', read_only=True)
    date_seance   = serializers.DateTimeField(source='presence.created_at', read_only=True)
    statut_paiement = serializers.SerializerMethodField()
    classe = serializers.UUIDField(source='facture.classe_id', read_only=True)
    eleve_nom = serializers.CharField(source='eleve.display_name', read_only=True)
    justificatif_url = serializers.SerializerMethodField()
    
    class Meta:
        model  = FactureEleve
        fields = [
            'id',
            'classe_nom',
            'classe',
            'prof_nom',
            'date_seance',
            'presence_id',
            'facture_id',
            'date_debut',
            'date_fin',
            'montant_a_payer',
            'montant_payer',
            'methode_payement',
            'eleve_nom',
            'statut',              # statut brut du modèle (emise/confirmee)
            'statut_paiement',     # calculé : a_payer / partiel / paye
            'created_at',
            'justificatif_url'
        ]
 
    def get_statut_paiement(self, obj) -> str:
        """
        Calcule le statut de paiement à partir des montants :
          - 'paye'    : montant_payer >= montant_a_payer (et montant_a_payer > 0)
          - 'partiel' : 0 < montant_payer < montant_a_payer
          - 'a_payer' : montant_payer == 0
        """
        a_payer = obj.montant_a_payer or 0
        paye    = obj.montant_payer   or 0
 
        if a_payer <= 0:
            return 'a_payer'
        if paye >= a_payer:
            return 'paye'
        if paye > 0:
            return 'partiel'
        return 'a_payer'

    def get_justificatif_url(self, obj):
        if obj.justificatif and obj.justificatif.fichier_local:
            return obj.justificatif.fichier_local.url
        return None



class FactureAvecPaiementsSerializer(serializers.ModelSerializer):
    """
    Serializer enrichi pour la liste des factures côté prof.
    Ajoute des infos sur les paiements élèves en attente de confirmation.
    """
    classe = serializers.UUIDField(source='classe.id', read_only=True)
    classe_nom    = serializers.CharField(source='classe.nom', read_only=True)
    nb_paiements_a_confirmer = serializers.SerializerMethodField()
    nb_paiements_total       = serializers.SerializerMethodField()
    nb_paiements_confirmes   = serializers.SerializerMethodField()
    part_direction = serializers.DecimalField(
        max_digits=20,
        decimal_places=10,
        read_only=True
    )
    part_prof = serializers.DecimalField(
        max_digits=20,
        decimal_places=10,
        read_only=True
    )
 
    class Meta:
        model  = Factures
        fields = [
            'id', 'classe_nom','classe','date_debut', 'date_fin',
            'honoraire', 'montant_total',
            'statut', 'nb_eleves_inscrits', 'nbr_eleves_participe',
            'created_at',
            # champs paiements élèves
            'nb_paiements_a_confirmer',
            'nb_paiements_total',
            'nb_paiements_confirmes',
            'part_direction',
            'part_prof',
        ]
 
    def get_nb_paiements_a_confirmer(self, obj) -> int:
        """Nombre de FactureEleve avec statut 'payee' (payé mais pas encore confirmé par le prof)."""
        return FactureEleve.objects.filter(facture=obj, statut='payee').count()
 
    def get_nb_paiements_total(self, obj) -> int:
        return FactureEleve.objects.filter(facture=obj).count()
 
    def get_nb_paiements_confirmes(self, obj) -> int:
        return FactureEleve.objects.filter(facture=obj, statut='confirmee').count()
 


class PayerFactureEleveSerializer(serializers.Serializer):
    """
    Payload pour enregistrer un paiement partiel ou total.
    """
    montant_payer = serializers.DecimalField(
        max_digits=20, decimal_places=10
    )



from rest_framework import serializers
from .models import AbsenceSignaler


class AbsenceSignalerSerializer(serializers.ModelSerializer):
    # Nested read-only fields
    professeur_display_name = serializers.SerializerMethodField()
    professeur_id = serializers.SerializerMethodField()
    admin_display_name = serializers.SerializerMethodField()
    seance_jour = serializers.SerializerMethodField()
    seance_heure = serializers.SerializerMethodField()
    seance_duree = serializers.SerializerMethodField()
    seance_classe_nom = serializers.SerializerMethodField()
    mois = serializers.SerializerMethodField()  # "2025-04" for grouping
    seance_id = serializers.SerializerMethodField()
    seance_classe_id = serializers.SerializerMethodField() 

    class Meta:
        model = AbsenceSignaler
        fields = [
            'id',
            'date_absence',
            'remarque',
            'created_at',
            # admin
            'admin_display_name',
            # prof (resolved from seance.classe.professeur OR seance.professeur_disponible)
            'professeur_id',
            'professeur_display_name',
            # seance details
            'seance_id',
            'seance_jour',
            'seance_heure',
            'seance_duree',
            'seance_classe_nom',
            'seance_classe_id',
            # helper
            'mois',
        ]

    def get_seance_id(self, obj):
        return str(obj.seance.id)

    def get_professeur_display_name(self, obj):
        seance = obj.seance
        if hasattr(seance, 'professeur_disponible') and seance.professeur_disponible:
            return seance.professeur_disponible.display_name or seance.professeur_disponible.email
        if seance.classe and seance.classe.professeur:
            return seance.classe.professeur.display_name or seance.classe.professeur.email
        return None

    def get_professeur_id(self, obj):
        seance = obj.seance
        if hasattr(seance, 'professeur_disponible') and seance.professeur_disponible:
            return str(seance.professeur_disponible.id)
        if seance.classe and seance.classe.professeur:
            return str(seance.classe.professeur.id)
        return None

    def get_admin_display_name(self, obj):
        return obj.admin.display_name or obj.admin.email

    def get_seance_jour(self, obj):
        return obj.seance.jour_seance

    def get_seance_heure(self, obj):
        h = obj.seance.heure_debut_reelle
        if h:
            return str(h)[:5]  # "HH:MM"
        return None

    def get_seance_duree(self, obj):
        return obj.seance.duree_reelle_minutes

    def get_seance_classe_nom(self, obj):
        if obj.seance.classe:
            return obj.seance.classe.nom
        return None

    # nouvelle méthode :
    def get_seance_classe_id(self, obj):
        if obj.seance.classe:
            return str(obj.seance.classe.id)
        return None

    def get_mois(self, obj):
        d = obj.date_absence
        if isinstance(d, str):
            d = datetime.fromisoformat(d[:10])
        return d.strftime('%Y-%m')


class AbsenceSignalerCreateSerializer(serializers.Serializer):
    seance = serializers.UUIDField()
    date_absence = serializers.DateTimeField()
    remarque = serializers.CharField(max_length=200, required=False, allow_blank=True)



class PresenceDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Presences
        fields = ['id', 'created_at', 'heure_connexion', 'heure_deconnexion']
 
 
class FactureAdminSerializer(serializers.ModelSerializer):
    classe_nom       = serializers.CharField(source='classe.nom', read_only=True)
    professeur_nom   = serializers.SerializerMethodField()
    presences_detail = serializers.SerializerMethodField()
 
    class Meta:
        model  = Factures
        fields = [
            'id', 'classe', 'classe_nom',
            'professeur', 'professeur_nom',
            'nb_eleves_inscrits', 'montant_total',
            'statut', 'lien_paypal', 'rib',
            'date_echeance', 'envoyee_chat', 'envoyee_chat_at',
            'created_at', 'updated_at',
            'nbr_eleves_participe', 'date_debut', 'date_fin',
            'honoraire', 'presence_ids', 'seance_ids',
            'presences_detail',
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at',
            'classe_nom', 'professeur_nom',
            'presences_detail',
        ]
 
    def get_professeur_nom(self, obj):
        u = obj.professeur
        if not u:
            return ''

        return u.display_name or u.email
 
    def get_presences_detail(self, obj):
        """
        Retourne les présences dans le même ordre que presence_ids.
        Chaque présence : date_seance, heure_connexion, heure_deconnexion.
        nb_participants, nb_inscrits, montant_total etc. viennent directement
        de la facture elle-même, pas des présences.
        """
        if not obj.presence_ids:
            return []
        qs = Presences.objects.filter(id__in=obj.presence_ids)
        mapping = {str(p.id): p for p in qs}
        ordered = [mapping[pid] for pid in obj.presence_ids if pid in mapping]
        return PresenceDetailSerializer(ordered, many=True).data





class PresenceManuelleSerializer(serializers.ModelSerializer):
    """
    Présence manuelle du professeur (enregistrement_system=False).
    Utilisé pour GET et PATCH heure_connexion_prof / temps_prof.
    """
    heure_connexion_prof = serializers.CharField(required=False)
    class Meta:
        model = Presences
        fields = [
            'id',
            'heure_connexion_prof',
            'temps_prof',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_heure_connexion_prof(self, value):
        """
        Accepte HH:MM:SS et convertit en datetime timezone-aware.
        """

        if not value:
            return None

        value = value.strip()

        try:
            heure = datetime.strptime(value, "%H:%M:%S").time()

            return timezone.make_aware(
                datetime.combine(localdate(), heure)
            )

        except ValueError:
            raise serializers.ValidationError(
                "Format invalide. Utilise HH:MM:SS"
            )


class AbsenceEleveSerializer(serializers.ModelSerializer):
    """
    Ligne élève dans le modal Élèves d'une séance.
    Champs éditables : temps_effectif, durree_eleve.
    """
    eleve_id          = serializers.UUIDField(source='eleve.id', read_only=True)
    eleve_nom         = serializers.CharField(source='eleve.display_name', read_only=True)

    class Meta:
        model = AbsencesProfs
        fields = [
            'id',
            'eleve_id',
            'eleve_nom',
            'temps_effectif',
            'durree_eleve',
        ]
        read_only_fields = ['id', 'eleve_id', 'eleve_nom']


class DashboardFilterSerializer(serializers.Serializer):
    professor_id = serializers.UUIDField(required=False, allow_null=True)
    class_id = serializers.UUIDField(required=False, allow_null=True)
    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    programme = serializers.CharField(required=False, allow_blank=True, allow_null=True)

class DashboardResponseSerializer(serializers.Serializer):
    montant_due_prof_total = serializers.FloatField()
    montant_due_directrice = serializers.FloatField()
    professeurs_concernes = serializers.ListField(child=serializers.DictField())
    evolution_heures = serializers.ListField(child=serializers.DictField())

class ProfesseurSelectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Users
        fields = ['id', 'display_name']

class ClasseSelectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Classes
        fields = ['id', 'nom', 'programme']
 
 

class UserMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Users
        fields = ['id', 'display_name', 'email']

class ClassMiniSerializer(serializers.ModelSerializer):
    professeur = UserMiniSerializer(read_only=True)
    
    class Meta:
        model = Classes
        fields = ['id', 'nom', 'niveau', 'programme', 'professeur', 'statut']

class PresenceMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Presences
        fields = [
            'id', 'heure_connexion_prof', 'temps_prof', 'retard_minutes',
            'resp_query_10_eleve', 'resp_query_fin_eleve', 'enregistrement_system'
        ]
        
class PlanningItemSerializer(serializers.ModelSerializer):
    classe = ClassMiniSerializer(read_only=True)  # juste pour affichage
    presence = PresenceMiniSerializer(read_only=True)
    professeur_disponible = serializers.SerializerMethodField()
    
    # ✅ Calculs basés sur Seances.heure_debut_reelle et .duree_reelle_minutes
    heure_debut_reelle = serializers.TimeField(format='%H:%M', input_formats=['%H:%M'], required=False)
    statut_realisation = serializers.CharField(required=False) # Autorise 'deleted', 'planned', etc.
    ecart_minutes = serializers.SerializerMethodField()
    is_today = serializers.SerializerMethodField()
    
    class Meta:
        model = Seances
        fields = [
            'id', 'classe',
            'professeur_disponible',
            'date_seance', 'jour_seance',  # ← Seances
            'heure_debut_reelle', 'duree_reelle_minutes', 'statut',
            'presence', 'statut_realisation', 'ecart_minutes', 'is_today',
            'created_at'
        ]

    def get_professeur_disponible(self, obj):
         if not obj.professeur_disponible:
             return None
         return {
             'id':           str(obj.professeur_disponible.id),
             'display_name': getattr(obj.professeur_disponible, 'display_name', str(obj.professeur_disponible)),
         }
    
    def get_statut_realisation(self, obj):
        if not hasattr(obj, 'presence_list') or not obj.presence_list:
            return 'planned'
        presence = obj.presence_list[0]
        if presence.heure_connexion_prof:
            if presence.temps_prof:
                return 'completed'
            return 'in_progress'
        return 'absent'
    
    def get_ecart_minutes(self, obj):
        """Écart entre Seances.duree_reelle_minutes (prévu) et Presence.temps_prof (réel)"""
        if not hasattr(obj, 'presence_list') or not obj.presence_list:
            return None
        prevu = obj.duree_reelle_minutes
        reel = obj.presence_list[0].temps_prof
        if prevu and reel:
            return reel - prevu
        return None
    
    def get_is_today(self, obj):
        from django.utils import timezone
        return obj.date_seance == timezone.now().date()


class SeanceCreateSerializer(serializers.Serializer):
    """Création d'une séance avec ou sans classe."""
    classe                = serializers.UUIDField(required=False, allow_null=True)
    professeur_disponible = serializers.UUIDField(required=False, allow_null=True)
    jour_seance           = serializers.CharField(max_length=50)
    heure_debut_reelle    = serializers.TimeField()
    duree_reelle_minutes  = serializers.IntegerField(min_value=15)
    statut                = serializers.CharField(max_length=50, default='active')
 
    def validate(self, data):
        # Si ni classe ni professeur_disponible → erreur
        if not data.get('classe') and not data.get('professeur_disponible'):
            raise serializers.ValidationError(
                "Renseignez une classe ou un professeur_disponible."
            )
        return data
 
 
class SeanceUpdateSerializer(serializers.Serializer):
    """Mise à jour partielle d'une séance."""
    duree_reelle_minutes = serializers.IntegerField(required=False, min_value=15)
    heure_debut_reelle   = serializers.TimeField(required=False)
    statut               = serializers.CharField(required=False, max_length=50)
 
    def validate_statut(self, value):
        allowed = {'active', 'supprimer', 'annulee', 'terminee', 'horaire_valide', 'horaire_non_valide'}
        if value not in allowed:
            raise serializers.ValidationError(
                f"Statut invalide. Valeurs autorisées : {', '.join(allowed)}"
            )
        return value


# factures eleves serializer

class EleveInscritSerializer(serializers.Serializer):
    eleve_id    = serializers.UUIDField()
    eleve_nom   = serializers.CharField()
    eleve_email = serializers.EmailField()
    parent_id   = serializers.UUIDField(allow_null=True)
 
 
class SeanceDetailSerializer(serializers.Serializer):
    presence_id      = serializers.UUIDField()
    seance_id        = serializers.UUIDField()
    date_seance      = serializers.DateTimeField()
    duree_heures     = serializers.DecimalField(max_digits=20, decimal_places=10)
    heure_connexion  = serializers.CharField(allow_null=True)
    heure_deconnexion = serializers.CharField(allow_null=True)
    participants_ids = serializers.ListField(child=serializers.UUIDField())
 
 
class FactureDetailSeancesSerializer(serializers.Serializer):
    eleves_inscrits        = EleveInscritSerializer(many=True)
    seances                = SeanceDetailSerializer(many=True)
    montant_total          = serializers.DecimalField(max_digits=20, decimal_places=10)
    nb_inscrits            = serializers.IntegerField()
    nb_participants_global = serializers.IntegerField()
 
 
class MontantManuelSerializer(serializers.Serializer):
    eleve_id       = serializers.UUIDField()
    montant_a_payer = serializers.DecimalField(max_digits=20, decimal_places=10)
 
 
class SubmitFactureSerializer(serializers.Serializer):
    methode  = serializers.ChoiceField(choices=['inscrits', 'participants', 'manuel'])
    montants = MontantManuelSerializer(many=True, required=False, default=list)
 
 
