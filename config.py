# config.py
from dotenv import load_dotenv
import os

# Charge le fichier .env à la racine
load_dotenv()

# Récupère le token Hugging Face
HF_TOKEN = "os.getenv("HF_TOKEN")"

if not HF_TOKEN:
    raise ValueError("Le token Hugging Face n'est pas défini dans .env")
