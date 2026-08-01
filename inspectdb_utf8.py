import os
from django.core.management import call_command
import django

# Set the environment variable for the settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pubproject.settings')

# Initialize Django
django.setup()

# Open the file with UTF-8 encoding
with open("sabil/models.py", "w", encoding="utf-8") as output_file:
    # Call the inspectdb command and redirect the output to the file
    call_command("inspectdb", stdout=output_file)