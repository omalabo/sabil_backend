from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from django.conf import settings
from django.conf.urls.static import static
router = DefaultRouter()

# Gestion des utilisateurs & comptes
router.register(r'users', views.UserViewSet, basename='users')

# Classes & Inscriptions
router.register(r'classes', views.ClassViewSet, basename='classes')
router.register(r'inscriptions', views.InscriptionViewSet, basename='inscriptions')
router.register(r'seances', views.SeanceViewSet, basename='seances')
router.register(r'catalogue-cours', views.CatalogueCoursViewSet, basename='catalogue-cours')
router.register(r'diplomes', views.DiplomeViewSet, basename='diplomes')
router.register(r'contrats', views.ContratViewSet, basename='contrats')

# Messagerie & Annonces
router.register(r'messages', views.MessageViewSet, basename='messages')
router.register(r'messages-prives', views.PrivateMessageViewSet, basename='private-messages')
router.register(r'annonces-groupe', views.AnnoncesGroupeViewSet, basename='annonces-groupe')
router.register(r'mes-annonces',    views.AnnoncesEleveViewSet,  basename='mes-annonces')
router.register(r'notifications', views.NotificationViewSet, basename='notifications')

# Pédagogie & Suivi
router.register(r'devoirs', views.DevoirViewSet, basename='devoirs')
router.register(r'gestion-devoirs', views.GestionDevoirViewSet, basename='devoir')
router.register(r'presences', views.PresenceViewSet, basename='presences')
router.register(r'questions-entree', views.QuestionEntreeViewSet, basename='questions-entree')
router.register(r'absences-profs', views.AbsenceProfViewSet, basename='absences-profs')

# Facturation & Paiements
router.register(r'factures', views.FactureViewSet, basename='factures')
router.register(r'rappels-paiement', views.RappelPaiementViewSet, basename='rappels-paiement')
router.register(r'paiements', views.PaiementViewSet, basename='paiements')

# Planning & Créneaux
router.register(r'planning-dispos', views.PlanningDispoViewSet, basename='planning-dispos')
router.register(r'historique-creneaux', views.HistoriqueCreneauViewSet, basename='historique-creneaux')

# Classe Virtuelle & Outils
router.register(r'enregistrements', views.EnregistrementViewSet, basename='enregistrements')
router.register(r'tableau-blanc', views.TableauBlancViewSet, basename='tableau-blanc')
router.register(r'fichiers', views.FichierViewSet, basename='fichiers')

# Administration & Direction
router.register(r'logs-activite', views.LogActiviteViewSet, basename='logs-activite')
router.register(r'rapports-auto', views.RapportAutoViewSet, basename='rapports-auto')
router.register(
    r'prof-facture-presences',
    views.ProfFacturePresenceViewSet,
    basename='prof-facture-presences',
)

router.register(
    r'suivi-presences',
    views.SuiviPresenceViewSet,
    basename='suivi-presences',
)
router.register(r'factures-emises', views.FactureEmiseViewSet, basename='factures-emises')
router.register(r'admin/factures', views.FactureAdminViewSet, basename='adminis-factures')
router.register(r'factures-eleve', views.FactureEleveViewSet, basename='facture-eleve')
router.register(r'presences-manuelle', views.PresenceManuelleViewSet, basename='presences-manuelle')
router.register(r'absences-eleves',    views.AbsencesElevesViewSet,   basename='absences-eleves')
router.register(r'planning', views.PlanningViewSet, basename='planning')
router.register(r'seanceJour', views.SeanceJourViewSet, basename='seanceJour')
router.register(r'absences', views.AbsenceSignalerViewSet, basename='absences')

router.register(r'admin/prof-facture-presences', views.AdminFacturePresenceViewSet, basename='admin-facture-presences')
router.register(r'admin/factures', views.AdminFactureEmiseViewSet, basename='admin-factures')
router.register(r'taches-direction', views.TacheDirectionViewSet, basename='taches-direction')

urlpatterns = [
    # urls.py
    path('mes-diplomes/', views.MyDiplomesView.as_view(), name='my-diplomes'),
    # Enregistrement vidéo LiveKit
    path('api/classes/<uuid:classe_id>/toggle-recording/', views.toggle_recording, name='toggle_recording'),

    # Webhook LiveKit (appelé par le serveur LiveKit)
    path('api/livekit/webhook/', views.livekit_webhook, name='livekit_webhook'),
    
    path('classes/<uuid:classe_id>/eleves/', views.ElevesByClasseView.as_view(), name='classe-eleves'),
    # Authentification & Mot de passe
    path('auth/login/', views.CustomLoginView.as_view(), name='login'),
    path('auth/logout/', views.LogoutView.as_view(), name='logout'),
    path('auth/change-password/', views.ChangePasswordView.as_view(), name='change-password'),
    path('auth/force-change-password/', views.ForceChangePasswordView.as_view(), name='force-change-password'),
    path('auth/forgot-password', views.ForgotPasswordView.as_view()),
    path('auth/reset-password', views.ResetPasswordView.as_view()),
    # Tableaux de bord par rôle
    path('dashboards/direction/', views.DirectionDashboardView.as_view(), name='dashboard-direction'),
    path('dashboards/admin/', views.AdminDashboardView.as_view(), name='dashboard-admin'),
    path('dashboards/professeur/', views.ProfDashboardView.as_view(), name='dashboard-prof'),
    path('dashboards/eleve/', views.EleveDashboardView.as_view(), name='dashboard-eleve'),
    path('direction/dashboard/', views.DirectionDashboardView.as_view(), name='direction-dashboard'),
    path('direction/professeurs/', views.ProfesseurListView.as_view(), name='direction-professeurs'),
    path('direction/classes/', views.ClasseListView.as_view(), name='direction-classes'),
    path('admin-dashboard/eleves-a-payer/', views.AdminElevesAPayerView.as_view(), name='admin-eleves-a-payer'),

    # Actions spécifiques Classes
    path('classes/<uuid:pk>/check-creneau-prof/', views.CheckCreneauProfView.as_view(), name='check-creneau-prof'),
    path('classes/<uuid:pk>/start-session/', views.StartSessionView.as_view(), name='start-session'),
    path('classes/<uuid:pk>/pause/', views.PauseClassView.as_view(), name='pause-class'),
    path('classes/<uuid:pk>/flag-delete/', views.FlagDeleteClassView.as_view(), name='flag-delete-class'),
    path('classes/<uuid:pk>/reactivate/', views.ReactivateClassView.as_view(), name='classe-reactivate'),
    path('classes/<uuid:pk>/delete-permanently/', views.PermanentDeleteClassView.as_view(), name='delete-class-permanently'),

    # Questions pré-cours & Absences
    path('questions-entree/submit/', views.SubmitPreClassCheckView.as_view(), name='submit-pre-class'),
    path('absences-profs/generate-monthly/', views.GenerateMonthlyAbsenceReportView.as_view(), name='monthly-absence-report'),
    
    # Planification & Sync
    path('planning-dispos/sync-classes/', views.SyncPlanningFromClassView.as_view(), name='sync-planning-classes'),
    path('planning-dispos/toggle-slot/', views.TogglePlanningSlotView.as_view(), name='toggle-planning-slot'),

    # Facturation & Automatisations
    path('factures/auto-generate/', views.AutoGenerateInvoicesView.as_view(), name='auto-generate-invoices'),
    path('factures/send-reminders/', views.SendPaymentRemindersView.as_view(), name='send-payment-reminders'),
    path('inactivites/check/', views.CheckClassInactivityView.as_view(), name='check-inactivity'),

    path('absences/admin-calendar/', views.AbsenceAdminCalendarView.as_view()),
    path('absences/signaler/',       views.SignalerAbsenceView.as_view()),
    path('absences/<uuid:pk>/revoquer/', views.RevoquerAbsenceView.as_view()),
    
    # Rapports
    path('rapports/daily-absences/', views.DailyAbsenceReportView.as_view(), name='daily-absences'),
    path('rapports/monthly-summary/', views.MonthlySummaryReportView.as_view(), name='monthly-summary'),

    path('classes/<uuid:pk>/end-session/', views.EndSessionView.as_view()),
    path('classes/<uuid:pk>/seances/',     views.ClassSeancesView.as_view()),
    path('classes/<uuid:pk>/absences-profs/', views.ClassAbsencesProfFeedbackView.as_view(), name='class-absences-prof-feedback'),
    # Routes ViewSet
    path('', include(router.urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    
