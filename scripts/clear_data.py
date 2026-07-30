import os
from sqlalchemy import delete
from app import create_app, db
from app.models import (Client, DemandeClient, Proprietaire, 
                        Propriete, Transaction, Commission, 
                        Contrat, Paiement, Visite, JournalActivite, PhotoPropriete, DocumentPropriete)

app = create_app()

def clear_data():
    with app.app_context():
        print("Suppression des données de catalogue (hors Utilisateurs et Caractéristiques)...")
        try:
            # Delete in order of dependencies (child tables first)
            db.session.execute(delete(JournalActivite))
            db.session.execute(delete(PhotoPropriete))
            db.session.execute(delete(DocumentPropriete))
            db.session.execute(delete(Visite))
            db.session.execute(delete(Contrat))
            db.session.execute(delete(Paiement))
            db.session.execute(delete(Commission))
            db.session.execute(delete(Transaction))
            db.session.execute(delete(DemandeClient))
            
            # Remove association table entries for properties and characteristics
            # This is automatically handled by cascading or we can just empty the table
            db.session.execute(db.text('DELETE FROM proprietes_caracteristiques'))
            
            db.session.execute(delete(Propriete))
            db.session.execute(delete(Proprietaire))
            db.session.execute(delete(Client))
            
            db.session.commit()
            print("Données par défaut supprimées avec succès !")
        except Exception as e:
            db.session.rollback()
            print(f"Erreur lors de la suppression : {e}")

if __name__ == '__main__':
    clear_data()
