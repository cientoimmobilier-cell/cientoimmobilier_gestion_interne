import os
from sqlalchemy import select
from app import create_app, db
from app.models import (Utilisateur, Client, DemandeClient, Proprietaire, 
                        Propriete, Caracteristique, Transaction, Commission, 
                        Contrat, Paiement, Visite)
from datetime import datetime, date

app = create_app()

def seed_sample_data():
    with app.app_context():
        print("Génération de données de démonstration...")
        
        # Vérifier si l'utilisateur de base existe
        admin = db.session.execute(select(Utilisateur).where(Utilisateur.email == 'admin@ciento.immo')).scalars().first()
        if not admin:
            print("Veuillez lancer init_db.py d'abord pour créer la base de données et l'administrateur.")
            return
            
        # 1. Caractéristiques existantes ou nouvelles
        clim = db.session.execute(select(Caracteristique).where(Caracteristique.nom == 'Climatisation')).scalars().first()
        piscine = db.session.execute(select(Caracteristique).where(Caracteristique.nom == 'Piscine')).scalars().first()
        jardin = db.session.execute(select(Caracteristique).where(Caracteristique.nom == 'Jardin')).scalars().first()
        internet = db.session.execute(select(Caracteristique).where(Caracteristique.nom == 'Internet Fibre')).scalars().first()
        
        # 2. Création de Propriétaires
        p1 = Proprietaire(
            nom='GIRAUD',
            prenom='Aurélien',
            telephone='+33 6 45 99 22 11',
            email='aurelien.giraud@orange.fr',
            adresse='12 Rue de la Paix, 75002 Paris',
            numero_identite='AB123456'
        )
        p2 = Proprietaire(
            nom='BERNARD',
            prenom='Sophie',
            telephone='+33 6 12 34 56 00',
            email='sophie.bernard@gmail.com',
            adresse='88 Avenue des Champs-Élysées, 75008 Paris',
            numero_identite='CD789012'
        )
        db.session.add_all([p1, p2])
        db.session.flush()
        
        # 3. Création de Propriétés
        prop1 = Propriete(
            reference_bien='BIEN-2026-0001',
            proprietaire_id=p1.id,
            titre='Superbe duplex lumineux avec terrasse',
            description='Magnifique appartement en duplex situé en plein cœur du Marais. Très lumineux, avec séjour cathédrale, terrasse de 15m² exposée Sud, cuisine équipée ouverte, 3 chambres spacieuses et 2 salles de bain. Rare sur le marché.',
            type_bien='Appartement',
            type_operation='Vente',
            adresse='14 Rue des Francs Bourgeois, 75003 Paris',
            ville='Paris',
            quartier='Marais',
            superficie=82.5,
            nombre_chambres=3,
            nombre_salles_bain=2,
            nombre_garages=1,
            prix=420000,
            statut='Vendu'  # Sera marqué vendu par la transaction finale
        )
        if clim: prop1.caracteristiques.append(clim)
        if internet: prop1.caracteristiques.append(internet)
        
        prop2 = Propriete(
            reference_bien='BIEN-2026-0002',
            proprietaire_id=p2.id,
            titre='Maison contemporaine avec piscine et jardin',
            description='Superbe villa d\'architecte construite en 2020. Vaste séjour de 60m² donnant sur une terrasse en bois et piscine chauffée. Cuisine haut de gamme, 4 chambres dont une suite parentale au rez-de-chaussée. Jardin arboré sans vis-à-vis. Prestations luxueuses.',
            type_bien='Villa',
            type_operation='Vente',
            adresse='45 Avenue du Général de Gaulle, 33200 Bordeaux',
            ville='Bordeaux',
            quartier='Caudéran',
            superficie=180.0,
            nombre_chambres=4,
            nombre_salles_bain=3,
            nombre_garages=2,
            prix=850000,
            statut='Disponible'
        )
        if piscine: prop2.caracteristiques.append(piscine)
        if jardin: prop2.caracteristiques.append(jardin)
        if clim: prop2.caracteristiques.append(clim)
        
        prop3 = Propriete(
            reference_bien='BIEN-2026-0003',
            proprietaire_id=p1.id,
            titre='Studio étudiant meublé proche métro',
            description='Charmant studio meublé de 24m², refait à neuf, situé au 3ème étage d\'un immeuble sécurisé. Comprenant une pièce principale avec kitchenette équipée, un coin nuit confortable et une salle d\'eau moderne. À 2 min à pied du métro.',
            type_bien='Appartement',
            type_operation='Location',
            adresse='8 Rue de la République, 69100 Villeurbanne',
            ville='Lyon',
            quartier='Villeurbanne',
            superficie=24.0,
            nombre_chambres=1,
            nombre_salles_bain=1,
            nombre_garages=0,
            prix=750,
            statut='Disponible'
        )
        if internet: prop3.caracteristiques.append(internet)
        
        db.session.add_all([prop1, prop2, prop3])
        db.session.flush()

        # 4. Création de Clients
        c1 = Client(
            code_client='CLI-2026-0001',
            nom='MARTIN',
            prenom='Thomas',
            telephone='+33 7 88 55 44 33',
            email='thomas.martin@outlook.com',
            adresse='5 Rue Lafayette',
            ville='Paris',
            profession='Ingénieur logiciel',
            budget_min=380000,
            budget_max=450000,
            source_client='Site Internet',
            observations='Recherche urgente de duplex ou grand T3 dans Paris Centre pour sa famille.'
        )
        c2 = Client(
            code_client='CLI-2026-0002',
            nom='DUBOIS',
            prenom='Emma',
            telephone='+33 6 77 11 22 33',
            email='emma.dubois@gmail.com',
            adresse='12 Place de la Bourse',
            ville='Bordeaux',
            profession='Architecte d\'intérieur',
            budget_min=700000,
            budget_max=900000,
            source_client='Recommandation',
            observations='Souhaite acheter une maison contemporaine lumineuse à Bordeaux avec piscine.'
        )
        db.session.add_all([c1, c2])
        db.session.flush()

        # 5. Demandes Clients
        dem1 = DemandeClient(
            client_id=c1.id,
            type_operation='Vente',
            type_bien='Appartement',
            zone_recherche='Paris 3ème, Marais',
            chambres=3,
            salles_bain=2,
            budget=450000,
            statut='Satisfaite'
        )
        dem2 = DemandeClient(
            client_id=c2.id,
            type_operation='Vente',
            type_bien='Villa',
            zone_recherche='Bordeaux Caudéran ou Bouscat',
            chambres=4,
            salles_bain=3,
            budget=900000,
            statut='En cours'
        )
        db.session.add_all([dem1, dem2])
        
        # 6. Visites
        v1 = Visite(
            client_id=c1.id,
            propriete_id=prop1.id,
            agent_id=admin.id,
            date_visite=datetime(2026, 6, 10, 14, 30),
            compte_rendu="Le client adore la terrasse et l'agencement en duplex. Fait une offre directement.",
            statut='Effectuée'
        )
        v2 = Visite(
            client_id=c2.id,
            propriete_id=prop2.id,
            agent_id=admin.id,
            date_visite=datetime(2026, 6, 18, 10, 00),
            compte_rendu="Visite programmée pour faire découvrir les prestations de la villa.",
            statut='Planifiée'
        )
        db.session.add_all([v1, v2])
        db.session.flush()

        # 7. Création de Transaction pour BIEN-2026-0001 (Thomas Martin)
        tx = Transaction(
            reference_transaction='TX-2026-0001',
            client_id=c1.id,
            propriete_id=prop1.id,
            agent_id=admin.id,
            type_transaction='Vente',
            montant=415000,
            date_transaction=date(2026, 6, 12),
            statut='Finalisée',
            observations="Négociation réussie. Baisse de prix de 5 000 € acceptée par Aurélien GIRAUD."
        )
        db.session.add(tx)
        db.session.flush()

        # 8. Commission associée
        comm = Commission(
            transaction_id=tx.id,
            agent_id=admin.id,
            pourcentage=5.00,
            montant=20750,
            date_calcul=date(2026, 6, 12)
        )
        db.session.add(comm)

        # 9. Contrat associé
        contrat = Contrat(
            transaction_id=tx.id,
            numero_contrat='CNT-2026-0109',
            date_signature=date(2026, 6, 12),
            date_debut=date(2026, 7, 1),
            fichier_pdf='uploads/documents/CONTRAT_EXEMPLE.pdf'
        )
        db.session.add(contrat)

        # 10. Paiement associé (acompte ou séquestre)
        pay = Paiement(
            transaction_id=tx.id,
            montant=41500,
            mode_paiement='Virement',
            reference_paiement='VIR-SEQUESTRE-909281',
            date_paiement=date(2026, 6, 13),
            statut='Validé'
        )
        db.session.add(pay)

        try:
            db.session.commit()
            print("Données de démonstration insérées avec succès en base de données !")
            print("Vous pouvez maintenant lancer le serveur Flask et vous connecter.")
        except Exception as e:
            db.session.rollback()
            print(f"Erreur d'insertion des données de démonstration : {e}")

if __name__ == '__main__':
    seed_sample_data()
