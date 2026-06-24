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

        # === Nouvelles migrations ===

        # Ajout zone_ciblee et description au modèle Client
        try:
            db.session.execute(text("ALTER TABLE clients ADD COLUMN zone_ciblee VARCHAR(200);"))
            print("Colonne zone_ciblee ajoutée à clients.")
        except Exception as e:
            db.session.rollback()
            print(f"Erreur/Ignoré (clients.zone_ciblee) : {e}")

        try:
            db.session.execute(text("ALTER TABLE clients ADD COLUMN description TEXT;"))
            print("Colonne description ajoutée à clients.")
        except Exception as e:
            db.session.rollback()
            print(f"Erreur/Ignoré (clients.description) : {e}")

        # Ajout etat_demande au modèle DemandeClient
        try:
            db.session.execute(text("ALTER TABLE demandes_clients ADD COLUMN etat_demande VARCHAR(30) DEFAULT 'Pas urgence';"))
            print("Colonne etat_demande ajoutée à demandes_clients.")
        except Exception as e:
            db.session.rollback()
            print(f"Erreur/Ignoré (demandes_clients.etat_demande) : {e}")

        # Nouvelles tables AirBNB
        try:
            db.session.execute(text('''
                CREATE TABLE IF NOT EXISTS biens_airbnb (
                    id SERIAL PRIMARY KEY,
                    reference VARCHAR(30) UNIQUE NOT NULL,
                    titre VARCHAR(255) NOT NULL,
                    description TEXT,
                    type_bien VARCHAR(50) NOT NULL,
                    adresse TEXT,
                    ville VARCHAR(100),
                    quartier VARCHAR(100),
                    capacite INTEGER DEFAULT 2,
                    nombre_chambres INTEGER,
                    nombre_lits INTEGER,
                    nombre_salles_bain INTEGER,
                    prix_par_nuit NUMERIC(15, 2) NOT NULL,
                    devise VARCHAR(10) DEFAULT 'EUR',
                    frais_menage NUMERIC(15, 2) DEFAULT 0,
                    proprietaire_id INTEGER REFERENCES proprietaires(id) ON DELETE SET NULL,
                    agent_id INTEGER REFERENCES utilisateurs(id) ON DELETE SET NULL,
                    statut VARCHAR(30) DEFAULT 'Actif',
                    lien_airbnb TEXT,
                    wifi BOOLEAN DEFAULT FALSE,
                    parking BOOLEAN DEFAULT FALSE,
                    climatisation BOOLEAN DEFAULT FALSE,
                    piscine BOOLEAN DEFAULT FALSE,
                    observations TEXT,
                    date_ajout TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            '''))
            print("Table biens_airbnb créée/vérifiée.")
        except Exception as e:
            db.session.rollback()
            print(f"Erreur/Ignoré (create biens_airbnb) : {e}")

        try:
            db.session.execute(text('''
                CREATE TABLE IF NOT EXISTS reservations_airbnb (
                    id SERIAL PRIMARY KEY,
                    bien_airbnb_id INTEGER NOT NULL REFERENCES biens_airbnb(id) ON DELETE CASCADE,
                    nom_voyageur VARCHAR(200) NOT NULL,
                    telephone_voyageur VARCHAR(30),
                    email_voyageur VARCHAR(150),
                    nombre_voyageurs INTEGER DEFAULT 1,
                    date_arrivee DATE NOT NULL,
                    date_depart DATE NOT NULL,
                    nombre_nuits INTEGER,
                    montant_total NUMERIC(15, 2) NOT NULL,
                    devise VARCHAR(10) DEFAULT 'EUR',
                    commission_airbnb NUMERIC(15, 2) DEFAULT 0,
                    montant_net NUMERIC(15, 2),
                    statut VARCHAR(30) DEFAULT 'Confirmée',
                    observations TEXT,
                    date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            '''))
            print("Table reservations_airbnb créée/vérifiée.")
        except Exception as e:
            db.session.rollback()
            print(f"Erreur/Ignoré (create reservations_airbnb) : {e}")

        db.session.commit()
        print("Migration terminée.")

if __name__ == '__main__':
    migrate()
