# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.


import uuid
from django.contrib.auth.models import AbstractBaseUser
from django.db import models



class AbsencesProfs(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    presence = models.ForeignKey('Presences', models.DO_NOTHING, db_column='id_presence')
    eleve = models.ForeignKey('Users', models.DO_NOTHING, db_column='id_eleve')
    resp_query_10_prof = models.BooleanField(blank=True, null=True)
    resp_query_fin_prof = models.BooleanField(blank=True, null=True)
    created_at = models.DateTimeField()
    note_eleve = models.CharField(max_length=50, blank=True, null=True)
    enregistrement_system = models.BooleanField(blank=True, null=True)
    temps_effectif = models.BooleanField(blank=True, null=True)
    durree_eleve = models.IntegerField(blank=True, null=True)
    montant_a_paye = models.IntegerField(blank=True, null=True)
    facture = models.ForeignKey('Factures', models.DO_NOTHING,db_column='facture_id', )
    montant_paye = models.IntegerField(blank=True, null=True)
    payeur = models.ForeignKey(
        'Users',
        models.DO_NOTHING,
        related_name='absences_comme_payeur',db_column='payeur'
    )
    statut_payement = models.CharField(max_length=50, blank=True, null=True)



    class Meta:
        managed = False
        db_table = 'absences_profs'
        db_table_comment = 'Alimenté automatiquement par les réponses élèves (question entrée) et par les admins. Utilisé pour le tableau mensuel direction.'

        
class AnnoncesGroupe(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    titre= models.CharField(max_length=200, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    nom_original = models.CharField(max_length=255)
    nom_stockage = models.CharField(max_length=255)
    fichier_local = models.FileField(upload_to='chat_fichiers/%Y/%m/') 
    type_fichier = models.TextField()  # This field type is a guess.
    mime_type = models.CharField(max_length=100, blank=True, null=True)
    taille_bytes = models.BigIntegerField(blank=True, null=True)
    anonce_expired = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'annonces_groupe'
        db_table_comment = 'Annonces direction'

class AnnoncesEleves(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    annonces_groupe= models.ForeignKey('AnnoncesGroupe', models.DO_NOTHING,related_name='annoncesEleves_set')
    created_at = models.DateTimeField(auto_now_add=True)
    statut = models.BooleanField(default=False)
    eleve = models.ForeignKey('Users', models.DO_NOTHING )

    class Meta:
        managed = False
        db_table = 'annonces_eleves'
        db_table_comment = 'Annonces pour eleves'


class CatalogueCours(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    niveau = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'catalogue_cours'
        db_table_comment = 'Parcours pédagogique. Permet d afficher la barre de progression dans l espace élève.'


TYPE_COURS_CHOICES = [
    ('alphabetisation',  'Alphabétisation adulte'),
    ('fluidification',   'Fluidification intensive'),
    ('groupe_special_3e','Groupe spécial 3€'),
    ('gratuit',          '100% Gratuit'),
]
class Classes(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=100)
    programme = models.CharField(max_length=200, blank=True, null=True)
    niveau = models.CharField(max_length=100, blank=True, null=True)
    professeur = models.ForeignKey('Users', models.DO_NOTHING, blank=True, null=True)
    taux_horaire = models.DecimalField(max_digits=20, decimal_places=10, blank=True, null=True)
    statut = models.TextField()  # This field type is a guess.
    jitsi_room_id = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.ForeignKey('Users', models.DO_NOTHING, db_column='created_by', related_name='classes_created_by_set', blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    deleted_at = models.DateTimeField(blank=True, null=True)
    tarif_horaire = models.DecimalField(blank=True, null=True,max_digits=20, decimal_places=10)
    derniere_activite_at = models.DateTimeField(null=True, blank=True)
    type_cours = models.CharField(
        max_length=30,
        choices=TYPE_COURS_CHOICES,
        blank=True,
        null=True,
    )
    

    class Meta:
        managed = False
        db_table = 'classes'
        db_table_comment = 'Table centrale. Chaque classe = 1 groupe cours avec 1 prof, 1 créneau, N élèves.'


class Contrats(models.Model):
    id = models.UUIDField(primary_key=True)
    eleve = models.ForeignKey('Users', models.DO_NOTHING)
    classe = models.ForeignKey(Classes, models.DO_NOTHING)
    version_reglement = models.CharField(max_length=20)
    contenu_snapshot = models.TextField()
    signe_at = models.DateTimeField()
    ip_signature = models.GenericIPAddressField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'contrats'
        unique_together = (('eleve', 'classe', 'version_reglement'),)
        db_table_comment = 'Signature électronique du règlement. Historique conservé même si le règlement change.'


class Devoirs(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seance = models.ForeignKey('Seances', models.DO_NOTHING)
    titre = models.CharField(max_length=255, blank=True, null=True)
    corrige_at = models.DateTimeField(blank=True, null=True)
    submitted_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    STATUT_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('soumis', 'Soumis'),
        ('cloturer', 'Clôturé'),
        ('corrige', 'Corrigé'),
    ]
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='brouillon')
    class Meta:
        managed = False
        db_table = 'devoirs'


class FichiersDevoir(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    devoir = models.ForeignKey('Devoirs', models.DO_NOTHING)
    eleve = models.ForeignKey('Users', models.DO_NOTHING,null=True)
    nom_original = models.CharField(max_length=255)
    nom_stockage = models.CharField(max_length=255)
    type_fichier = models.TextField()  # This field type is a guess.
    mime_type = models.CharField(max_length=100, blank=True, null=True)
    taille_bytes = models.BigIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    statut_correction = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = 'fichiers_devoir'
        db_table_comment = 'Métadonnées des fichiers de devoir'




class Diplomes(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    eleve = models.ForeignKey('Users', models.DO_NOTHING,related_name='eleve_id')
    classe = models.ForeignKey(Classes, models.DO_NOTHING)
    professeur = models.ForeignKey('Users', models.DO_NOTHING, related_name='professeur_id')
    matiere = models.CharField(max_length=200, blank=True, null=True)
    nom_eleve_diplome = models.CharField(max_length=150)
    note_orale = models.CharField(max_length=50, blank=True, null=True)
    note_ecrite = models.CharField(max_length=50, blank=True, null=True)
    appreciation = models.TextField(blank=True, null=True)
    delivre_at = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField()

    # ✅ NOUVEAU : image du diplôme généré (PNG)
    image_diplome = models.FileField(  # ou models.ImageField si Pillow est installé
        upload_to='diplomes/%Y/%m/',
        blank=True,
        null=True,
        help_text="Fichier du diplôme généré"
    )

    # 2. Tes champs de métadonnées (excellente pratique)
    nom_original = models.CharField(max_length=255, blank=True, null=True)
    nom_stockage = models.CharField(max_length=255, blank=True, null=True)
    type_fichier = models.CharField(max_length=50, blank=True, null=True, help_text="Ex: png, jpg, pdf")
    mime_type = models.CharField(max_length=100, blank=True, null=True, help_text="Ex: image/png")
    taille_bytes = models.BigIntegerField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        managed = False
        db_table = 'diplomes'


class Enregistrements(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4)
    classe = models.ForeignKey(
        Classes, 
        models.DO_NOTHING,
        related_name='enregistrements_video'  # ← ÉVITE le conflit
    )
    seance = models.ForeignKey(
        'Seances', 
        models.DO_NOTHING, 
        blank=True, 
        null=True,
        related_name='enregistrements_video'  # ← ÉVITE le conflit
    )
    demarre_par = models.ForeignKey(
        'Users', 
        models.DO_NOTHING, 
        db_column='demarre_par',
        related_name='enregistrements_demarres'  # ← ÉVITE le conflit
    )
    egress_id = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        unique=True
    )  # ← NOUVEAU
    url_video = models.TextField(blank=True, null=True)
    duree_secondes = models.IntegerField(blank=True, null=True)
    taille_bytes = models.BigIntegerField(blank=True, null=True)
    statut = models.TextField()
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(blank=True, null=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'enregistrements'
        db_table_comment = 'Seuls prof / admin / direction peuvent lancer un enregistrement. Élèves informés par message système.'

    def __str__(self):
        return f"Enregistrement {self.classe_id} - {self.started_at.strftime('%Y-%m-%d %H:%M')}"
        
class Factures(models.Model):
    id = models.UUIDField(primary_key=True)
    classe = models.ForeignKey(Classes, models.DO_NOTHING)
    professeur = models.ForeignKey('Users', models.DO_NOTHING)
    nb_eleves_inscrits = models.IntegerField()
    #taux_horaire = models.DecimalField(max_digits=20, decimal_places=10)
    montant_total = models.DecimalField(max_digits=20, decimal_places=10, blank=True, null=True)
    statut = models.TextField()  # This field type is a guess.
    lien_paypal = models.CharField(max_length=500, blank=True, null=True)
    rib = models.TextField(blank=True, null=True)
    date_echeance = models.DateField(blank=True, null=True)
    envoyee_chat = models.BooleanField()
    envoyee_chat_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    nbr_eleves_participe = models.IntegerField()
    date_debut = models.DateTimeField()
    date_fin = models.DateTimeField()
    honoraire = models.DecimalField(max_digits=20, decimal_places=10)
    presence_ids = models.JSONField(default=list)   # [uuid1, uuid2, ...]
    seance_ids   = models.JSONField(default=list)
    part_direction = models.DecimalField(max_digits=20, decimal_places=10, blank=True, null=True)
    part_prof = models.DecimalField(max_digits=20, decimal_places=10, blank=True, null=True)


    class Meta:
        managed = False
        db_table = 'factures'
        db_table_comment = 'Facture remplie par le prof (dates, durées, nb élèves). Envoyée automatiquement dans le chat de classe.'


class Fichiers(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    uploade_par = models.ForeignKey('Users', models.DO_NOTHING, db_column='uploade_par')
    classe = models.ForeignKey(Classes, models.DO_NOTHING, blank=True, null=True)
    nom_original = models.CharField(max_length=255)
    nom_stockage = models.CharField(max_length=255)
    fichier_local = models.FileField(upload_to='chat_fichiers/%Y/%m/') 
    type_fichier = models.TextField()  # This field type is a guess.
    mime_type = models.CharField(max_length=100, blank=True, null=True)
    taille_bytes = models.BigIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    fichier_expires_at = models.DateTimeField(null=True, blank=True)
    is_voice_note = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = 'fichiers'
        db_table_comment = 'Métadonnées des fichiers. Les fichiers réels sont sur Backblaze B2 ou Cloudflare R2.'


class FacturesFichier(models.Model):
    id = models.UUIDField(primary_key=True)
    uploade_par = models.ForeignKey('Users', models.DO_NOTHING, db_column='uploade_par')
    classe = models.ForeignKey(Classes, models.DO_NOTHING, blank=True, null=True)
    nom_original = models.CharField(max_length=255)
    nom_stockage = models.CharField(max_length=255)
    fichier_local = models.FileField(upload_to='factures_fichiers/%Y/%m/') 
    type_fichier = models.TextField()  # This field type is a guess.
    mime_type = models.CharField(max_length=100, blank=True, null=True)
    taille_bytes = models.BigIntegerField(blank=True, null=True)
    created_at = models.DateTimeField()
    fichier_expires_at = models.DateTimeField(null=True, blank=True)
    is_voice_note = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = 'factures_fichier'
        db_table_comment = 'Métadonnées des fichiers de factures'

class FactureEleve(models.Model):
    id = models.UUIDField(primary_key=True)
    eleve = models.ForeignKey('Users', models.DO_NOTHING, db_column='eleve_id', related_name='factures_eleve' )
    parent = models.ForeignKey('Users', models.DO_NOTHING, db_column='parent_id',related_name='factures_parent')
    presence = models.ForeignKey('Presences', models.DO_NOTHING, db_column='presence_id')
    created_at = models.DateTimeField(auto_now_add=True)
    date_debut = models.DateTimeField()
    date_fin = models.DateTimeField()
    statut = models.CharField(max_length=50)
    montant_a_payer = models.DecimalField(max_digits=20, decimal_places=10, blank=True, null=True)
    montant_payer = models.DecimalField(max_digits=20, decimal_places=10, blank=True, null=True)
    methode_payement = models.CharField(max_length=50)
    facture = models.ForeignKey('Factures', models.DO_NOTHING, db_column='facture_id')
    justificatif = models.ForeignKey('FacturesFichier', models.DO_NOTHING, null=True, blank=True, related_name='factures_justificatif')

    class Meta:
        managed = False
        db_table = 'facture_eleve'

class HistoriqueCreneaux(models.Model):
    id = models.UUIDField(primary_key=True)
    classe = models.ForeignKey(Classes, models.DO_NOTHING)
    modifie_par = models.ForeignKey('Users', models.DO_NOTHING, db_column='modifie_par')
    ancien_jour = models.SmallIntegerField(blank=True, null=True)
    ancienne_heure = models.TimeField(blank=True, null=True)
    nouveau_jour = models.SmallIntegerField(blank=True, null=True)
    nouvelle_heure = models.TimeField(blank=True, null=True)
    notif_direction_envoyee = models.BooleanField()
    notif_envoyee_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'historique_creneaux'
        db_table_comment = 'Chaque changement de créneau par un prof est enregistré et notifie la direction automatiquement.'


class Inscriptions(models.Model):
    id = models.UUIDField(primary_key=True,editable=False)
    eleve = models.ForeignKey('Users', models.DO_NOTHING, db_column='eleve_id')
    classe = models.ForeignKey(Classes, models.DO_NOTHING)
    statut = models.TextField()  # This field type is a guess.
    date_inscription = models.DateField(auto_now_add=True)
    nom_diplome = models.CharField(max_length=150, blank=True, null=True)
    contrat_signe = models.BooleanField(blank=True, null=True)
    contrat_signe_at = models.DateTimeField(blank=True, null=True)
    contrat_ip = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'inscriptions'
        unique_together = (('eleve', 'classe'),)
        db_table_comment = 'Relation N:N entre élèves et classes. Contient aussi la signature du règlement.'


class LogsActivite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey('Users', models.DO_NOTHING, blank=True, null=True)
    action = models.CharField(max_length=100)
    table_cible = models.CharField(max_length=100, blank=True, null=True)
    id_cible = models.UUIDField(blank=True, null=True)
    details_json = models.JSONField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'logs_activite'
        db_table_comment = 'Journal d audit de toutes les actions importantes. Utile pour la direction.'


class Messages(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    expediteur = models.ForeignKey('Users', models.DO_NOTHING)
    classe = models.ForeignKey(Classes, models.DO_NOTHING)
    TYPE_CANAL_CHOICES = [
        ('chat_groupe', 'Chat Groupe'),
        ('chat_admin', 'Chat Admin'),
        ('chat_direction', 'Chat Direction'),
        ('message_administration', 'Message Administration'),
    ]

    type_canal = models.CharField(max_length=50, choices=TYPE_CANAL_CHOICES)

    #type_canal = models.TextField()  # This field type is a guess.
    #type_message = models.TextField()  # This field type is a guess.\

    TYPE_MESSAGE_CHOICES = [
    ('texte', 'Texte'),
    ('fichier', 'Fichier'),
    ('image', 'Image'),
    ('systeme', 'Système'),
    ('annonce', 'Annonce'),
    ('audio', 'Audio'),
    ('video', 'Video'),
    ]

    type_message = models.CharField(max_length=20, choices=TYPE_MESSAGE_CHOICES)
    contenu = models.TextField(blank=True, null=True)
    fichier = models.ForeignKey(Fichiers, models.DO_NOTHING, blank=True, null=True)
    is_systeme = models.BooleanField()
    reply_to = models.ForeignKey('self', models.DO_NOTHING, db_column='reply_to', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(blank=True, null=True)
    recu_par = models.JSONField(default=list)   # liste d'user_ids qui ont reçu
    lu_par_ids = models.JSONField(default=list) # liste d'user_ids qui ont lu

    class Meta:
        managed = False
        db_table = 'messages'
        db_table_comment = 'Chat de groupe et canaux spéciaux. Historique complet conservé même pour les nouveaux membres.'


class MessagesPrives(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    expediteur = models.ForeignKey('Users', on_delete=models.CASCADE, related_name='messages_prives_envoyes')
    destinataire = models.ForeignKey('Users', on_delete=models.CASCADE, related_name='messagesprives_destinataire_set')
    contenu = models.TextField(blank=True, default='')
    type_message = models.CharField(max_length=20, default='texte')  # texte, image, video, audio, fichier
    fichier = models.ForeignKey('Fichiers', on_delete=models.SET_NULL, null=True, blank=True)
    reply_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, db_column='reply_to')
    lu = models.BooleanField(default=False)
    lu_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'messages_prives'
        ordering = ['created_at']

class NotificationType(models.TextChoices):
    CHANGEMENT_CRENEAU = "changement_creneau"
    NOUVEAU_CRENEAU = "nouveau_creneau"

class Notifications(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    destinataire = models.ForeignKey('Users', models.DO_NOTHING)
    type = models.CharField(
    max_length=250,
    choices=NotificationType.choices
)
    titre = models.CharField(max_length=255)
    contenu = models.TextField(blank=True, null=True)
    lien = models.CharField(max_length=500, blank=True, null=True)
    lu = models.BooleanField()
    lu_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    classe = models.ForeignKey('Classes', null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        managed = False
        db_table = 'notifications'


class Paiements(models.Model):
    id = models.UUIDField(primary_key=True)
    facture = models.ForeignKey(Factures, models.DO_NOTHING)
    confirme_par = models.ForeignKey('Users', models.DO_NOTHING, db_column='confirme_par', blank=True, null=True)
    montant = models.DecimalField(max_digits=20, decimal_places=10)
    methode = models.TextField()  # This field type is a guess.
    reference = models.CharField(max_length=255, blank=True, null=True)
    paid_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'paiements'


class PlanningDispos(models.Model):
    id = models.UUIDField(primary_key=True)
    professeur = models.ForeignKey('Users', models.DO_NOTHING)
    jour_semaine = models.SmallIntegerField()
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()
    couleur = models.TextField()  # This field type is a guess.
    disponible = models.BooleanField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'planning_dispos'
        unique_together = (('professeur', 'jour_semaine', 'heure_debut'),)
        db_table_comment = 'Planning lundi-dimanche 6h-22h par tranches de 30min. Prof clique pour rendre une case verte (dispo) ou blanche.'


class Presences(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    classe = models.ForeignKey(Classes, models.DO_NOTHING)
    user = models.ForeignKey('Users', models.DO_NOTHING)
    seance = models.ForeignKey('Seances', models.DO_NOTHING)
    heure_connexion = models.DateTimeField(blank=True, null=True)
    heure_deconnexion = models.DateTimeField(blank=True, null=True)
    heure_connexion_prof = models.DateTimeField(blank=True, null=True)
    temps_prof = models.IntegerField(blank=True, null=True)
    retard_minutes = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField()
    date_seance = models.DateField()
    jitsi_room_id = models.CharField(max_length=255, blank=True, null=True)
    resp_query_10_eleve = models.BooleanField(blank=True, null=True)
    resp_query_fin_eleve = models.BooleanField(blank=True, null=True)
    audio_seance = models.CharField(max_length=255, blank=True, null=True)
    enregistrement_system = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'presences'
        db_table_comment = 'Présence automatique dès connexion à la salle Jitsi. Peut être corrigée manuellement par le prof.'

class AbsenceSignaler(models.Model):
    STATUT_CHOICES = [('actif', 'Actif'), ('inactif', 'Inactif')]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    admin = models.ForeignKey('Users', models.DO_NOTHING)
    seance = models.ForeignKey('Seances', models.DO_NOTHING)
    date_absence = models.DateTimeField(blank=True, null=True)
    remarque = models.CharField(max_length=200, blank=True, null=True)
    statut   = models.CharField(max_length=20, choices=STATUT_CHOICES, default='actif')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'absence_signaler'
        db_table_comment = 'absence_signaler'




class QuestionsEntree(models.Model):
    id = models.UUIDField(primary_key=True)
    eleve = models.ForeignKey('Users', models.DO_NOTHING)
    classe = models.ForeignKey(Classes, models.DO_NOTHING)
    seance = models.ForeignKey('Seances', models.DO_NOTHING, blank=True, null=True)
    prof_absent = models.BooleanField(blank=True, null=True)
    prof_en_retard = models.BooleanField(blank=True, null=True)
    retard_minutes = models.IntegerField(blank=True, null=True)
    notif_envoyee_admin = models.BooleanField()
    notif_envoyee_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'questions_entree'
        db_table_comment = 'Question posée automatiquement à l élève avant d entrer en cours. Si prof absent/retard, notifie l admin.'


class RappelsPaiement(models.Model):
    id = models.UUIDField(primary_key=True)
    facture = models.ForeignKey(Factures, models.DO_NOTHING)
    numero_rappel = models.IntegerField()
    envoye_at = models.DateTimeField(blank=True, null=True)
    prochain_rappel_at = models.DateTimeField(blank=True, null=True)
    statut = models.TextField()  # This field type is a guess.
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'rappels_paiement'


class RapportsAuto(models.Model):
    id = models.UUIDField(primary_key=True)
    type_rapport = models.TextField()  # This field type is a guess.
    periode_debut = models.DateField()
    periode_fin = models.DateField()
    contenu_json = models.JSONField()
    envoye_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'rapports_auto'
        db_table_comment = 'Rapport quotidien absences profs + rapport mensuel fin de mois. Généré par tâche Celery.'


class Seances(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    classe = models.ForeignKey(
        Classes, models.DO_NOTHING,
        blank=True, null=True,
        related_name='seances_classe'           # ← ajout obligatoire
    )
    date_seance = models.DateField(blank=True,null=True)
    jour_seance = models.CharField(max_length=50, blank=True, null=True)
    heure_debut_reelle = models.TimeField(blank=True, null=True)
    duree_reelle_minutes = models.IntegerField(blank=True, null=True)
    statut = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    professeur_disponible = models.ForeignKey(
        'Users', models.DO_NOTHING,             # ← pointe vers Users (pas Classes)
        blank=True, null=True,
        related_name='disponibilites'           # ← ajout obligatoire
    )

    class Meta:
        managed = False
        db_table = 'seances'
        db_table_comment = 'Une séance = un cours réel qui a eu lieu (ou est planifié). Généré automatiquement ou manuellement.'


class Sessions(models.Model):
    id = models.UUIDField(primary_key=True)
    user = models.ForeignKey('Users', models.DO_NOTHING)
    token_hash = models.CharField(unique=True, max_length=255)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'sessions'


class TableauBlanc(models.Model):
    id = models.UUIDField(primary_key=True)
    seance = models.ForeignKey(Seances, models.DO_NOTHING)
    auteur = models.ForeignKey('Users', models.DO_NOTHING)
    snapshot_json = models.JSONField()
    type_action = models.TextField()  # This field type is a guess.
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'tableau_blanc'
        db_table_comment = 'Historique complet du tableau blanc par séance. Permet de revoir ce qui a été écrit.'


class TachesDirection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    titre = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    faite = models.BooleanField(default=False)

    faite_par = models.ForeignKey(
        'Users',
        models.SET_NULL,
        null=True,
        blank=True,
        related_name='taches_faites',
        db_column='faite_par' 
    )

    created_by = models.ForeignKey(
        'Users',
        models.SET_NULL,
        null=True,
        blank=True,
        related_name='taches_creees',
        db_column='created_by' 
    )

    faite_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    delais = models.DateTimeField(blank=True, null=True, db_column='delais')

    class Meta:
        db_table = "taches_direction"
 
 
class TacheDirectionAssignee(models.Model):
    """Table intermédiaire explicite pour la relation M2M tâche ↔ admins."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tache = models.ForeignKey(TachesDirection, on_delete=models.CASCADE)
    user = models.ForeignKey('Users', on_delete=models.CASCADE,db_column='user_id' )
    assigned_at = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'tache_direction_assignees'
        unique_together = ('tache', 'user')



class Users(AbstractBaseUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, max_length=255)
    
    password = models.CharField(max_length=255, db_column='password_hash')
    
    display_name = models.CharField(max_length=150, blank=True, null=True)
    nom_diplome = models.CharField(max_length=150, blank=True, null=True)
    role = models.TextField()
    must_change_password = models.BooleanField(default=False)
    first_login_done = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    created_by = models.ForeignKey('self', models.SET_NULL, db_column='created_by', blank=True, null=True,related_name='created_users'  )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # 🔄 Mapping pour last_login -> last_login_at
    last_login = models.DateTimeField(db_column='last_login_at', blank=True, null=True)
    admin_id = models.UUIDField(null=True)

    pays = models.CharField(max_length=50, blank=True, null=True)
    gmt = models.CharField(max_length=50, blank=True, null=True)
    homme_femme = models.CharField(max_length=150, blank=True, null=True)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children')
    lien_paypal = models.CharField(max_length=500, blank=True, null=True)
    rib = models.TextField(blank=True, null=True)
    code_prof = models.CharField(max_length=100, blank=True, null=True)
    telephone = models.CharField( blank=True, null=True)
    indicatif = models.CharField( blank=True, null=True)
    # ⚠️ OBLIGATOIRE pour l'auth Django
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['display_name', 'role']

    class Meta:
        managed = False
        db_table = 'users'
        db_table_comment = 'Tous les comptes de la plateforme. Créés uniquement par la Direction.'

    # Méthodes attendues par Django
    def get_full_name(self):
        return self.display_name or self.email

    def get_short_name(self):
        return self.display_name or self.email

    # Optionnel : permet l'accès au /admin/ Django pour la Direction uniquement
    @property
    def is_staff(self):
        return self.role == 'direction'


class PasswordResetCode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(Users, on_delete=models.CASCADE, related_name='user_id')
    code_hash = models.CharField(max_length=128)  # hash du code, jamais en clair
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
 
    class Meta:
        db_table = 'password_reset_code'
        ordering = ['-created_at']
 
    def __str__(self):
        return f"ResetCode({self.user.email}, used={self.used})"
