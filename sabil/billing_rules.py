from decimal import Decimal

# ── Programmes sans reversement à la direction ──────────────────────────────
TYPE_COURS_SANS_REVERSEMENT = {'alphabetisation', 'fluidification', 'gratuit'}
TYPE_COURS_SPECIAL          = {'alphabetisation', 'fluidification',
                                'groupe_special_3e', 'gratuit'}


def get_type_cours_auto(nb_inscrits: int) -> str:
    """Détermine le type standard depuis le nb d'inscrits."""
    if nb_inscrits == 1: return 'solo'
    if nb_inscrits == 2: return 'duo'
    if nb_inscrits == 3: return 'trio'
    return 'groupe'


def calculer_tarifs(nb_inscrits: int, nb_participants: int,
                    duree_heures: Decimal, type_cours: str = '') -> dict:
    """
    Calcule les 3 montants pour une séance.

    Paramètres
    ----------
    nb_inscrits    : inscrits dans la classe  (détermine solo/duo/trio/groupe)
    nb_participants: élèves présents à la séance
    duree_heures   : durée en heures (Decimal)
    type_cours     : valeur du champ Classes.type_cours
                     ('', 'solo', 'duo', 'trio', 'groupe',
                      'alphabetisation', 'fluidification',
                      'groupe_special_3e', 'gratuit')

    Retourne
    --------
    dict avec :
      type_cours_effectif      : type réellement appliqué
      tarif_eleve_par_personne : tarif unitaire horaire
      total_collecte           : ce que paient les élèves
      part_direction           : ce que le prof reverse
      part_prof                : ce que le prof garde
    """
    h = duree_heures

    # ── 100 % gratuit ────────────────────────────────────────────────────
    if type_cours == 'gratuit':
        return {
            'type_cours_effectif':      'gratuit',
            'tarif_eleve_par_personne': Decimal('0'),
            'total_collecte':           Decimal('0'),
            'part_direction':           Decimal('0'),
            'part_prof':                Decimal('0'),
        }

    # ── Alphabétisation adulte ───────────────────────────────────────────
    if type_cours == 'alphabetisation':
        tarif_pp = Decimal('5.00')
        total    = tarif_pp * nb_participants * h
        return {
            'type_cours_effectif':      'alphabetisation',
            'tarif_eleve_par_personne': round(tarif_pp, 4),
            'total_collecte':           round(total, 4),
            'part_direction':           Decimal('0'),
            'part_prof':                round(total, 4),
        }

    # ── Fluidification intensive ─────────────────────────────────────────
    if type_cours == 'fluidification':
        tarif_pp = Decimal('5.00')
        total    = tarif_pp * nb_participants * h
        return {
            'type_cours_effectif':      'fluidification',
            'tarif_eleve_par_personne': round(tarif_pp, 4),
            'total_collecte':           round(total, 4),
            'part_direction':           Decimal('0'),
            'part_prof':                round(total, 4),
        }

    # ── Groupe spécial 3€ ────────────────────────────────────────────────
    if type_cours == 'groupe_special_3e':
        tarif_pp = Decimal('3.00')
        total    = tarif_pp * nb_participants * h
        return {
            'type_cours_effectif':      'groupe_special_3e',
            'tarif_eleve_par_personne': round(tarif_pp, 4),
            'total_collecte':           round(total, 4),
            'part_direction':           Decimal('0'),   # surplus → PayPal prof
            'part_prof':                round(total, 4),
        }

    # ── Cours standard : type déterminé par nb_inscrits ──────────────────
    type_effectif = get_type_cours_auto(nb_inscrits)

    if nb_inscrits == 1:                        # Solo
        tarif_pp = Decimal('7.00')
        total    = tarif_pp * h
        part_dir = Decimal('2.00') * h

    elif nb_inscrits == 2:                      # Duo
        tarif_pp = Decimal('3.50')
        total    = tarif_pp * nb_participants * h
        part_dir = Decimal('2.00') * h

    elif nb_inscrits == 3:                      # Trio
        tarif_pp = Decimal('2.50')
        total    = tarif_pp * nb_participants * h
        part_dir = Decimal('2.00') * h

    elif nb_inscrits == 4:                      # Groupe 4
        tarif_pp = Decimal('2.00')
        total    = tarif_pp * nb_participants * h
        part_dir = Decimal('2.00') * h

    elif nb_inscrits == 5:                      # Groupe 5
        tarif_pp = Decimal('2.00')
        total    = tarif_pp * nb_participants * h
        part_dir = Decimal('4.00') * h

    elif nb_inscrits == 6:                      # Groupe 6
        tarif_pp = Decimal('2.00')
        total    = tarif_pp * nb_participants * h
        part_dir = total / 2

    else:                                       # Grand groupe 7+
        total    = Decimal(str(nb_inscrits)) * h
        tarif_pp = total / nb_participants if nb_participants else Decimal('0')
        part_dir = total / 2

    part_prof = total - part_dir

    return {
        'type_cours_effectif':      type_effectif,
        'tarif_eleve_par_personne': round(tarif_pp, 4),
        'total_collecte':           round(total,    4),
        'part_direction':           round(part_dir, 4),
        'part_prof':                round(part_prof,4),
    }