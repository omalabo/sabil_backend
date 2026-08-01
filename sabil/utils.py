import reverse_geocoder as rg

def country_code_from_latlon(lat: float, lon: float) -> str | None:
    """
    Retourne le code pays ISO alpha-2 (ex: 'NE') pour les coordonnées données.
    Utilise reverse_geocoder (offline). Renvoie None si impossible.
    """
    try:
        results = rg.search((lat, lon))  # retourne une liste
        if results and isinstance(results, list) and len(results) > 0:
            r = results[0]
            # reverse_geocoder donne 'cc' (country code) en alpha-2
            return r.get('cc')
    except Exception:
        pass
    return None
