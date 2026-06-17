from app import create_app, db
import os

app = create_app()

if __name__ == '__main__':
    # Récupérer le port depuis l'environnement ou utiliser 5000 par défaut
    port = int(os.environ.get('PORT', 5000))
    # En développement local, on écoute sur localhost
    app.run(host='127.0.0.1', port=port, debug=True)
