from datetime import datetime
from flask_login import UserMixin
from flask_bcrypt import generate_password_hash, check_password_hash
from app import db, login_manager

@login_manager.user_loader
def load_user(user_id):
    return Utilisateur.query.get(int(user_id))

# Table d'association pour les caractéristiques des propriétés
proprietes_caracteristiques = db.Table('proprietes_caracteristiques',
    db.Column('propriete_id', db.Integer, db.ForeignKey('proprietes.id', ondelete='CASCADE'), primary_key=True),
    db.Column('caracteristique_id', db.Integer, db.ForeignKey('caracteristiques.id', ondelete='CASCADE'), primary_key=True)
)

class Utilisateur(db.Model, UserMixin):
    __tablename__ = 'utilisateurs'
    
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    prenom = db.Column(db.String(100))
    email = db.Column(db.String(150), unique=True, nullable=False)
    telephone = db.Column(db.String(30))
    mot_de_passe_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(50), nullable=False)  # Administrateur, Directeur, Agent immobilier, Assistant, Comptable
    zone_affectation = db.Column(db.String(100))
    actif = db.Column(db.Boolean, default=True)
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relations
    visites = db.relationship('Visite', backref='agent', lazy=True)
    transactions = db.relationship('Transaction', backref='agent', lazy=True)
    commissions = db.relationship('Commission', backref='agent', lazy=True)
    activites = db.relationship('JournalActivite', backref='utilisateur', lazy=True)

    def set_password(self, password):
        self.mot_de_passe_hash = generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return check_password_hash(self.mot_de_passe_hash, password)

    def is_active(self):
        return self.actif

    def __repr__(self):
        return f"<Utilisateur {self.prenom} {self.nom} - {self.role}>"


class Client(db.Model):
    __tablename__ = 'clients'
    
    id = db.Column(db.Integer, primary_key=True)
    code_client = db.Column(db.String(20), unique=True)
    nom = db.Column(db.String(100), nullable=False)
    prenom = db.Column(db.String(100))
    telephone = db.Column(db.String(30))
    telephone_secondaire = db.Column(db.String(30))
    email = db.Column(db.String(150))
    adresse = db.Column(db.Text)
    ville = db.Column(db.String(100))
    profession = db.Column(db.String(100))
    zone_ciblee = db.Column(db.String(200))
    description = db.Column(db.Text)
    budget_min = db.Column(db.Numeric(15, 2))
    budget_max = db.Column(db.Numeric(15, 2))
    devise = db.Column(db.String(10), default='EUR')
    source_client = db.Column(db.String(100))
    observations = db.Column(db.Text)
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relations
    demandes = db.relationship('DemandeClient', backref='client', lazy=True, cascade="all, delete-orphan")
    visites = db.relationship('Visite', backref='client', lazy=True, cascade="all, delete-orphan")
    transactions = db.relationship('Transaction', backref='client', lazy=True)

    def __repr__(self):
        return f"<Client {self.prenom} {self.nom}>"


class DemandeClient(db.Model):
    __tablename__ = 'demandes_clients'
    
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='CASCADE'), nullable=False)
    type_operation = db.Column(db.String(20))  # Location, Achat, Vente, Gestion, Autre
    type_bien = db.Column(db.String(50))      # Maison, Appartement, Bureau, Local commercial, Studio
    zone_recherche = db.Column(db.Text)
    chambres = db.Column(db.Integer)
    salles_bain = db.Column(db.Integer)
    budget = db.Column(db.Numeric(15, 2))
    devise = db.Column(db.String(10), default='EUR')
    statut = db.Column(db.String(30), default='Recherche')  # Recherche, Trouvé, En négociation, Suspension, Conclue
    etat_demande = db.Column(db.String(30), default='Pas urgence')  # Urgence, Pas urgence
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)


class Proprietaire(db.Model):
    __tablename__ = 'proprietaires'
    
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    prenom = db.Column(db.String(100))
    telephone = db.Column(db.String(30))
    email = db.Column(db.String(150))
    adresse = db.Column(db.Text)
    numero_identite = db.Column(db.String(50))
    observations = db.Column(db.Text)
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relations
    proprietes = db.relationship('Propriete', backref='proprietaire', lazy=True)

    def __repr__(self):
        return f"<Proprietaire {self.prenom} {self.nom}>"


class Propriete(db.Model):
    __tablename__ = 'proprietes'
    
    id = db.Column(db.Integer, primary_key=True)
    reference_bien = db.Column(db.String(30), unique=True, nullable=False)
    proprietaire_id = db.Column(db.Integer, db.ForeignKey('proprietaires.id', ondelete='SET NULL'))
    titre = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    type_bien = db.Column(db.String(50), nullable=False)  # Maison, Appartement, Terrain, Villa, Bureau, Local commercial, Entrepôt, Immeuble
    type_operation = db.Column(db.String(20), nullable=False)  # Vente, Location
    adresse = db.Column(db.Text)
    ville = db.Column(db.String(100))
    quartier = db.Column(db.String(100))
    latitude = db.Column(db.Numeric(10, 7))
    longitude = db.Column(db.Numeric(10, 7))
    superficie = db.Column(db.Numeric(12, 2))
    nombre_chambres = db.Column(db.Integer)
    nombre_salles_bain = db.Column(db.Integer)
    nombre_garages = db.Column(db.Integer)
    prix = db.Column(db.Numeric(15, 2), nullable=False)
    devise = db.Column(db.String(10), default='EUR')
    statut = db.Column(db.String(30), default='Disponible')  # Disponible, Réservé, Vendu, Loué, Suspendu
    date_ajout = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relations M2M
    caracteristiques = db.relationship('Caracteristique', secondary=proprietes_caracteristiques, 
                                      backref=db.backref('proprietes', lazy='dynamic'))
    
    # Relations 1-M
    photos = db.relationship('PhotoPropriete', backref='propriete', lazy=True, cascade="all, delete-orphan")
    documents = db.relationship('DocumentPropriete', backref='propriete', lazy=True, cascade="all, delete-orphan")
    visites = db.relationship('Visite', backref='propriete', lazy=True, cascade="all, delete-orphan")
    transactions = db.relationship('Transaction', backref='propriete', lazy=True)

    def get_main_photo(self):
        main_photo = PhotoPropriete.query.filter_by(propriete_id=self.id, photo_principale=True).first()
        if main_photo:
            return main_photo.chemin_fichier
        # Retourner la première photo si pas de photo principale spécifiée
        first_photo = PhotoPropriete.query.filter_by(propriete_id=self.id).first()
        if first_photo:
            return first_photo.chemin_fichier
        return 'img/placeholder-property.jpg'

    def __repr__(self):
        return f"<Propriete {self.reference_bien} - {self.titre}>"


class Caracteristique(db.Model):
    __tablename__ = 'caracteristiques'
    
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), unique=True, nullable=False)

    def __repr__(self):
        return f"<Caracteristique {self.nom}>"


class PhotoPropriete(db.Model):
    __tablename__ = 'photos_proprietes'
    
    id = db.Column(db.Integer, primary_key=True)
    propriete_id = db.Column(db.Integer, db.ForeignKey('proprietes.id', ondelete='CASCADE'), nullable=False)
    chemin_fichier = db.Column(db.Text, nullable=False)
    photo_principale = db.Column(db.Boolean, default=False)
    date_upload = db.Column(db.DateTime, default=datetime.utcnow)


class DocumentPropriete(db.Model):
    __tablename__ = 'documents_proprietes'
    
    id = db.Column(db.Integer, primary_key=True)
    propriete_id = db.Column(db.Integer, db.ForeignKey('proprietes.id', ondelete='CASCADE'), nullable=False)
    nom_document = db.Column(db.String(255), nullable=False)
    type_document = db.Column(db.String(100))
    chemin_fichier = db.Column(db.Text, nullable=False)
    date_upload = db.Column(db.DateTime, default=datetime.utcnow)


class Visite(db.Model):
    __tablename__ = 'visites'
    
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='CASCADE'), nullable=False)
    propriete_id = db.Column(db.Integer, db.ForeignKey('proprietes.id', ondelete='CASCADE'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('utilisateurs.id', ondelete='SET NULL'))
    date_visite = db.Column(db.DateTime, nullable=False)
    compte_rendu = db.Column(db.Text)
    statut = db.Column(db.String(30), default='Planifiée')  # Planifiée, Effectuée, Annulée, Non présentée


class Transaction(db.Model):
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    reference_transaction = db.Column(db.String(50), unique=True, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='SET NULL'))
    propriete_id = db.Column(db.Integer, db.ForeignKey('proprietes.id', ondelete='SET NULL'))
    agent_id = db.Column(db.Integer, db.ForeignKey('utilisateurs.id', ondelete='SET NULL'))
    type_transaction = db.Column(db.String(20), nullable=False)  # Vente, Location
    montant = db.Column(db.Numeric(15, 2), nullable=False)
    devise = db.Column(db.String(10), default='EUR')
    date_transaction = db.Column(db.Date, nullable=False)
    statut = db.Column(db.String(30), default='En cours')  # En cours, Finalisée, Annulée
    observations = db.Column(db.Text)
    
    # Relations 1-M
    contrats = db.relationship('Contrat', backref='transaction', lazy=True, cascade="all, delete-orphan")
    paiements = db.relationship('Paiement', backref='transaction', lazy=True, cascade="all, delete-orphan")
    commissions = db.relationship('Commission', backref='transaction', lazy=True, cascade="all, delete-orphan")


class Contrat(db.Model):
    __tablename__ = 'contrats'
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id', ondelete='CASCADE'), nullable=False)
    numero_contrat = db.Column(db.String(50), nullable=False)
    date_signature = db.Column(db.Date, nullable=False)
    date_debut = db.Column(db.Date)
    date_fin = db.Column(db.Date)
    fichier_pdf = db.Column(db.Text)


class Paiement(db.Model):
    __tablename__ = 'paiements'
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id', ondelete='CASCADE'), nullable=False)
    montant = db.Column(db.Numeric(15, 2), nullable=False)
    devise = db.Column(db.String(10), default='EUR')
    mode_paiement = db.Column(db.String(50), nullable=False)  # Espèces, Virement, Chèque, Carte
    reference_paiement = db.Column(db.String(100))
    date_paiement = db.Column(db.Date, nullable=False)
    statut = db.Column(db.String(30), default='Validé')  # En attente, Validé, Rejeté


class Commission(db.Model):
    __tablename__ = 'commissions'
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id', ondelete='CASCADE'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('utilisateurs.id', ondelete='CASCADE'), nullable=False)
    pourcentage = db.Column(db.Numeric(5, 2), nullable=False)
    montant = db.Column(db.Numeric(15, 2), nullable=False)
    date_calcul = db.Column(db.Date, default=datetime.utcnow)


class JournalActivite(db.Model):
    __tablename__ = 'journal_activites'
    
    id = db.Column(db.Integer, primary_key=True)
    utilisateur_id = db.Column(db.Integer, db.ForeignKey('utilisateurs.id', ondelete='SET NULL'))
    action = db.Column(db.String(255), nullable=False)  # Connexion, Création, Modification, Suppression, Export
    table_concernee = db.Column(db.String(100))
    enregistrement_id = db.Column(db.Integer)
    date_action = db.Column(db.DateTime, default=datetime.utcnow)


class BienAirbnb(db.Model):
    __tablename__ = 'biens_airbnb'
    
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(30), unique=True, nullable=False)
    titre = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    type_bien = db.Column(db.String(50), nullable=False)  # Appartement, Maison, Studio, Villa, Chambre privée
    adresse = db.Column(db.Text)
    ville = db.Column(db.String(100))
    quartier = db.Column(db.String(100))
    capacite = db.Column(db.Integer, default=2)
    nombre_chambres = db.Column(db.Integer)
    nombre_lits = db.Column(db.Integer)
    nombre_salles_bain = db.Column(db.Integer)
    prix_par_nuit = db.Column(db.Numeric(15, 2), nullable=False)
    devise = db.Column(db.String(10), default='EUR')
    frais_menage = db.Column(db.Numeric(15, 2), default=0)
    proprietaire_id = db.Column(db.Integer, db.ForeignKey('proprietaires.id', ondelete='SET NULL'))
    agent_id = db.Column(db.Integer, db.ForeignKey('utilisateurs.id', ondelete='SET NULL'))
    statut = db.Column(db.String(30), default='Actif')  # Actif, Inactif, En maintenance
    lien_airbnb = db.Column(db.Text)
    wifi = db.Column(db.Boolean, default=False)
    parking = db.Column(db.Boolean, default=False)
    climatisation = db.Column(db.Boolean, default=False)
    piscine = db.Column(db.Boolean, default=False)
    observations = db.Column(db.Text)
    date_ajout = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relations
    proprietaire_airbnb = db.relationship('Proprietaire', backref='biens_airbnb', lazy=True)
    agent_gestionnaire = db.relationship('Utilisateur', backref='biens_airbnb_geres', lazy=True)
    reservations = db.relationship('ReservationAirbnb', backref='bien_airbnb', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<BienAirbnb {self.reference} - {self.titre}>"


class ReservationAirbnb(db.Model):
    __tablename__ = 'reservations_airbnb'
    
    id = db.Column(db.Integer, primary_key=True)
    bien_airbnb_id = db.Column(db.Integer, db.ForeignKey('biens_airbnb.id', ondelete='CASCADE'), nullable=False)
    nom_voyageur = db.Column(db.String(200), nullable=False)
    telephone_voyageur = db.Column(db.String(30))
    email_voyageur = db.Column(db.String(150))
    nombre_voyageurs = db.Column(db.Integer, default=1)
    date_arrivee = db.Column(db.Date, nullable=False)
    date_depart = db.Column(db.Date, nullable=False)
    nombre_nuits = db.Column(db.Integer)
    montant_total = db.Column(db.Numeric(15, 2), nullable=False)
    devise = db.Column(db.String(10), default='EUR')
    commission_airbnb = db.Column(db.Numeric(15, 2), default=0)
    montant_net = db.Column(db.Numeric(15, 2))
    statut = db.Column(db.String(30), default='Confirmée')  # Confirmée, En attente, Annulée, Terminée
    observations = db.Column(db.Text)
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ReservationAirbnb {self.nom_voyageur} - {self.date_arrivee}>"

# --- MODULE GESTION FINANCIERE ---

class CompteBancaire(db.Model):
    __tablename__ = 'comptes_bancaires'
    
    id = db.Column(db.Integer, primary_key=True)
    nom_banque = db.Column(db.String(100), nullable=False)
    numero_compte = db.Column(db.String(100), nullable=False, unique=True)
    titulaire = db.Column(db.String(100))
    solde = db.Column(db.Numeric(15, 2), default=0)
    devise = db.Column(db.String(10), default='EUR')
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)
    actif = db.Column(db.Boolean, default=True)

    # Relations
    mouvements = db.relationship('MouvementFinancier', backref='compte_bancaire', lazy=True)

    def __repr__(self):
        return f"<CompteBancaire {self.nom_banque} - {self.numero_compte}>"


class Caisse(db.Model):
    __tablename__ = 'caisses'
    
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False, unique=True)
    solde = db.Column(db.Numeric(15, 2), default=0)
    devise = db.Column(db.String(10), default='EUR')
    responsable_id = db.Column(db.Integer, db.ForeignKey('utilisateurs.id', ondelete='SET NULL'))
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)
    actif = db.Column(db.Boolean, default=True)

    # Relations
    mouvements = db.relationship('MouvementFinancier', backref='caisse', lazy=True)
    responsable = db.relationship('Utilisateur', foreign_keys=[responsable_id])

    def __repr__(self):
        return f"<Caisse {self.nom}>"


class MouvementFinancier(db.Model):
    __tablename__ = 'mouvements_financiers'
    
    id = db.Column(db.Integer, primary_key=True)
    type_mouvement = db.Column(db.String(20), nullable=False)  # Recette, Dépense, Transfert
    montant = db.Column(db.Numeric(15, 2), nullable=False)
    devise = db.Column(db.String(10), default='EUR')
    date_mouvement = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    categorie = db.Column(db.String(100))  # Loyer, Commission, Charge, Salaire, etc.
    description = db.Column(db.Text)
    reference_document = db.Column(db.String(100))
    methode_paiement = db.Column(db.String(50))  # Espèces, Virement, Carte, Chèque
    
    # Liens optionnels
    compte_bancaire_id = db.Column(db.Integer, db.ForeignKey('comptes_bancaires.id', ondelete='SET NULL'))
    caisse_id = db.Column(db.Integer, db.ForeignKey('caisses.id', ondelete='SET NULL'))
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id', ondelete='SET NULL'))
    utilisateur_id = db.Column(db.Integer, db.ForeignKey('utilisateurs.id', ondelete='SET NULL'))
    
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<MouvementFinancier {self.type_mouvement} - {self.montant}>"


class Facture(db.Model):
    __tablename__ = 'factures'
    
    id = db.Column(db.Integer, primary_key=True)
    numero_facture = db.Column(db.String(50), unique=True, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='SET NULL'))
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id', ondelete='SET NULL'))
    date_emission = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    date_echeance = db.Column(db.Date)
    
    montant_ht = db.Column(db.Numeric(15, 2), nullable=False)
    tva_pourcentage = db.Column(db.Numeric(5, 2), default=0)
    montant_tva = db.Column(db.Numeric(15, 2), default=0)
    montant_ttc = db.Column(db.Numeric(15, 2), nullable=False)
    devise = db.Column(db.String(10), default='EUR')
    
    statut = db.Column(db.String(30), default='Brouillon')  # Brouillon, Émise, Payée, Partiellement Payée, Annulée
    description = db.Column(db.Text)
    fichier_pdf = db.Column(db.Text)
    
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    # Relations
    client_facture = db.relationship('Client', foreign_keys=[client_id])
    transaction_facture = db.relationship('Transaction', foreign_keys=[transaction_id])
    recus = db.relationship('Recu', backref='facture', lazy=True)

    def __repr__(self):
        return f"<Facture {self.numero_facture}>"


class Recu(db.Model):
    __tablename__ = 'recus'
    
    id = db.Column(db.Integer, primary_key=True)
    numero_recu = db.Column(db.String(50), unique=True, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='SET NULL'))
    facture_id = db.Column(db.Integer, db.ForeignKey('factures.id', ondelete='SET NULL'))
    paiement_id = db.Column(db.Integer, db.ForeignKey('paiements.id', ondelete='SET NULL'))
    
    date_emission = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    montant = db.Column(db.Numeric(15, 2), nullable=False)
    devise = db.Column(db.String(10), default='EUR')
    methode_paiement = db.Column(db.String(50))
    
    description = db.Column(db.Text)
    fichier_pdf = db.Column(db.Text)
    
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    # Relations
    client_recu = db.relationship('Client', foreign_keys=[client_id])

    def __repr__(self):
        return f"<Recu {self.numero_recu}>"


class Budget(db.Model):
    __tablename__ = 'budgets'
    
    id = db.Column(db.Integer, primary_key=True)
    annee = db.Column(db.Integer, nullable=False)
    mois = db.Column(db.Integer)  # Optionnel, si NULL, budget annuel
    categorie = db.Column(db.String(100), nullable=False)
    montant_prevu = db.Column(db.Numeric(15, 2), nullable=False)
    devise = db.Column(db.String(10), default='EUR')
    description = db.Column(db.Text)
    
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Budget {self.categorie} {self.annee}>"
