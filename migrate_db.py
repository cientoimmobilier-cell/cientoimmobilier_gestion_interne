import os
from app import create_app, db
from sqlalchemy import text

app = create_app()

def migrate():
    with app.app_context():
        print("Migration de la base de données...")
        try:
            db.session.execute(text('ALTER TABLE utilisateurs ADD COLUMN zone_affectation VARCHAR(100);'))
            print("Colonne zone_affectation ajoutée à utilisateurs.")
        except Exception as e:
            db.session.rollback()
            print(f"Erreur/Ignoré (utilisateurs) : {e}")

        try:
            db.session.execute(text("ALTER TABLE clients ADD COLUMN devise VARCHAR(10) DEFAULT 'EUR';"))
            print("Colonne devise ajoutée à clients.")
        except Exception as e:
            db.session.rollback()
            print(f"Erreur/Ignoré (clients) : {e}")

        try:
            db.session.execute(text("ALTER TABLE demandes_clients ADD COLUMN devise VARCHAR(10) DEFAULT 'EUR';"))
            print("Colonne devise ajoutée à demandes_clients.")
        except Exception as e:
            db.session.rollback()
            print(f"Erreur/Ignoré (demandes_clients) : {e}")

        try:
            db.session.execute(text("ALTER TABLE transactions ADD COLUMN devise VARCHAR(10) DEFAULT 'EUR';"))
            print("Colonne devise ajoutée à transactions.")
        except Exception as e:
            db.session.rollback()
            print(f"Erreur/Ignoré (transactions) : {e}")

        try:
            db.session.execute(text("ALTER TABLE paiements ADD COLUMN devise VARCHAR(10) DEFAULT 'EUR';"))
            print("Colonne devise ajoutée à paiements.")
        except Exception as e:
            db.session.rollback()
            print(f"Erreur/Ignoré (paiements) : {e}")

        db.session.commit()
        print("Migration terminée.")

if __name__ == '__main__':
    migrate()
