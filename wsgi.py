"""Point d'entrée WSGI pour Gunicorn (Render, Vercel, etc.)."""
from app import create_app

app = create_app()
