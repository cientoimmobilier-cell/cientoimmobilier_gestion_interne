import os
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
            JournalActivite.query.delete()
            PhotoPropriete.query.delete()
            DocumentPropriete.query.delete()
            Visite.query.delete()
            Contrat.query.delete()
            Paiement.query.delete()
            Commission.query.delete()
            Transaction.query.delete()
            DemandeClient.query.delete()
            
            # Remove association table entries for properties and characteristics
            # This is automatically handled by cascading or we can just empty the table
            db.session.execute(db.text('DELETE FROM proprietes_caracteristiques'))
            
            Propriete.query.delete()
            Proprietaire.query.delete()
            Client.query.delete()
            
            db.session.commit()
            print("Données par défaut supprimées avec succès !")
        except Exception as e:
            db.session.rollback()
            print(f"Erreur lors de la suppression : {e}")

if __name__ == '__main__':
    clear_data()
