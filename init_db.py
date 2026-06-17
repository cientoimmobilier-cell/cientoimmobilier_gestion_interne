import os
from app import create_app, db
from app.models import Utilisateur, Caracteristique

app = create_app()

def init_database():
    with app.app_context():
        print("Initialisation de la base de données PostgreSQL...")
        
        # Tentative de création des tables
        try:
            db.create_all()
            print("Tables créées avec succès ou déjà existantes.")
        except Exception as e:
            print(f"Erreur lors de la création des tables : {e}")
            print("Vérifiez que votre serveur PostgreSQL est démarré et que la base de données existe.")
            return

        # Ajout des caractéristiques par défaut si non existantes
        default_caracteristiques = [
            'Piscine', 'Génératrice', 'Jardin', 'Puits', 
            'Climatisation', 'Caméra de surveillance', 'Internet Fibre'
        ]
        
        for name in default_caracteristiques:
            existing = Caracteristique.query.filter_by(nom=name).first()
            if not existing:
                carac = Caracteristique(nom=name)
                db.session.add(carac)
                print(f"Caractéristique ajoutée : {name}")
        
        # Ajout de l'utilisateur administrateur par défaut
        admin_email = 'admin@ciento.immo'
        existing_admin = Utilisateur.query.filter_by(email=admin_email).first()
        if not existing_admin:
            admin = Utilisateur(
                nom='Immobilier',
                prenom='Ciento Admin',
                email=admin_email,
                telephone='+33100000000',
                role='Administrateur',
                actif=True
            )
            # Définition du mot de passe par défaut
            default_pass = 'AdminCiento123!'
            admin.set_password(default_pass)
            db.session.add(admin)
            print(f"\n==========================================")
            print(f"Utilisateur Administrateur par défaut créé :")
            print(f"Email : {admin_email}")
            print(f"Mot de passe : {default_pass}")
            print(f"Rôle : Administrateur")
            print(f"Veuillez changer ce mot de passe après connexion.")
            print(f"==========================================\n")
        else:
            print("Compte administrateur par défaut déjà existant.")
            
        try:
            db.session.commit()
            print("Base de données initialisée avec succès.")
        except Exception as e:
            db.session.rollback()
            print(f"Erreur lors de l'enregistrement des données par défaut : {e}")

if __name__ == '__main__':
    init_database()
