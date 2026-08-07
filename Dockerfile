# Utiliser une image Python légère et stable
FROM python:3.11-slim

# Variables d'environnement pour Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Répertoire de travail dans le conteneur
WORKDIR /app

# Installer les dépendances système nécessaires 
# (libmagic1 pour python-magic, et outils pour compiler scipy/numpy si besoin)
RUN apt-get update && apt-get install -y \
    libmagic1 \
    build-essential \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copier et installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copier tout le code du projet dans le conteneur
COPY . .

# Collecter les fichiers statiques pour la production
RUN python manage.py collectstatic --noinput

# Exposer le port 8000
EXPOSE 8001

# Commande de démarrage : Gunicorn avec des workers Uvicorn pour supporter les WebSockets (ASGI)
# "pubproject.asgi:application" correspond à ton fichier asgi.py
CMD ["gunicorn", "pubproject.asgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--timeout", "120"]
