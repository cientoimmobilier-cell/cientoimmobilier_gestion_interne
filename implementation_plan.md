# Plan d'implémentation - Gestion de données immobilières (Ciento Immobilier)

Ce document décrit le plan technique pour concevoir et développer une application web locale de gestion de données immobilières pour l'agence **Ciento Immobilier**, sur la base des spécifications fournies dans les fichiers PDF `Gestion données immobilières.pdf` et `Gestion données immobilière_DB.pdf`.

L'application utilisera l'architecture suivante :
- **Backend** : Python 3.12, Flask, SQLAlchemy (avec PostgreSQL comme SGBD local).
- **Frontend** : HTML5, CSS3 personnalisé, JavaScript moderne, Bootstrap 5 (avec des personnalisations avancées pour un rendu visuel premium et dynamique).
- **Sécurité** : Authentification avec mot de passe haché par bcrypt et contrôle d'accès basé sur les rôles (RBAC).

---

## User Review Required

> [!IMPORTANT]
> **Base de données locale (PostgreSQL)** : L'application nécessite un serveur PostgreSQL installé en local. Nous utiliserons des variables d'environnement dans un fichier `.env` pour stocker les informations de connexion (hôte, utilisateur, mot de passe, port, nom de la base). Veuillez vous assurer qu'une instance PostgreSQL est active ou installable sur votre machine locale.

> [!WARNING]
> **Stockage des documents et photos** : Par défaut, les fichiers de photos et documents importés seront stockés dans un sous-dossier local du projet (`app/static/uploads/`). Si des volumes importants sont attendus, nous pourrons configurer un dossier externe spécifique sur le disque dur.

---

## Open Questions

> [!IMPORTANT]
> 1. **Identifiants de connexion PostgreSQL par défaut** : Pour le script d'initialisation de la base de données (`init_db.py`), quels paramètres de connexion par défaut devons-nous configurer ? (Exemple : utilisateur `postgres`, mot de passe `postgres`, base `ciento_immobilier` sur `localhost:5432`)
> 2. **Compte Administrateur initial** : Souhaitez-vous la création d'un compte Administrateur par défaut lors de l'initialisation de la base ? Si oui, quelle adresse email par défaut devons-nous utiliser (par exemple, `admin@ciento.immo`) ?
> 3. **Génération PDF & Excel** : 
>    - Pour la génération de PDF (contrats/reçus), avez-vous des modèles (templates) ou mentions légales spécifiques à inclure ?
>    - Pour l'import/export Excel, quels sont les modules prioritaires à équiper de cette fonctionnalité ?
> 4. **Ajustements de la structure de base de données** : Le modèle relationnel proposé dans le PDF de la DB contient 15 tables interconnectées. Confirmez-vous que nous devons créer l'ensemble de ces tables dès la phase d'initialisation ?

---

## Proposed Changes

Nous allons créer une structure modulaire Flask classique et robuste pour gérer facilement l'ensemble des modules décrits dans les spécifications.

```
Ciento-Immobilier/
├── app/
│   ├── __init__.py          # Initialisation de l'application Flask, DB et plugins
│   ├── models.py            # Modèles SQLAlchemy mappés sur le schéma PostgreSQL
│   ├── config.py            # Configurations de l'application (Dev, Prod, Secret keys)
│   ├── routes/              # Blueprints Flask pour chaque module
│   │   ├── __init__.py
│   │   ├── auth.py          # Connexion, déconnexion et gestion de profil
│   │   ├── dashboard.py     # Tableau de bord principal avec statistiques
│   │   ├── clients.py       # CRUD clients et demandes
│   │   ├── properties.py    # CRUD propriétés, caractéristiques, photos et documents
│   │   └── transactions.py  # CRUD transactions, contrats, paiements et commissions
│   ├── static/              # Fichiers statiques
│   │   ├── css/
│   │   │   └── custom.css   # Styles CSS personnalisés (Premium, animations, dark mode)
│   │   ├── js/
│   │   │   └── main.js      # Scripts JS (filtres dynamiques, interactions)
│   │   └── uploads/         # Dossier de stockage des médias et documents
│   └── templates/           # Templates HTML Bootstrap 5
│       ├── base.html        # Structure principale de navigation et sidebar
│       ├── auth/
│       │   └── login.html   # Page de connexion esthétique
│       ├── dashboard/
│       │   └── index.html   # Tableau de bord riche en statistiques et graphiques
│       ├── clients/
│       ├── properties/
│       └── transactions/
├── .env.example             # Exemple de configuration des variables d'environnement
├── requirements.txt         # Dépendances Python
├── init_db.py               # Script d'initialisation de la base PostgreSQL et seed initial
└── run.py                   # Point d'entrée de l'application
```

---

### Configuration & Base de données

#### [NEW] [requirements.txt](file:///c:/Users/PC/Pictures/Ciento-Immobilier/requirements.txt)
Fichier contenant les dépendances indispensables :
- `Flask` et `Flask-SQLAlchemy` (Backend et ORM)
- `Flask-Login` et `Flask-Bcrypt` (Authentification sécurisée)
- `psycopg2-binary` (Pilote de base de données PostgreSQL)
- `python-dotenv` (Gestion des variables d'environnement)
- `reportlab` (Génération de contrats/fiches PDF)
- `pandas` et `openpyxl` (Import/export Excel)

#### [NEW] [config.py](file:///c:/Users/PC/Pictures/Ciento-Immobilier/app/config.py)
Configuration de l'application Flask chargeant les clés de sécurité, le chemin de la base de données PostgreSQL et les dossiers de téléversement sécurisés.

#### [NEW] [models.py](file:///c:/Users/PC/Pictures/Ciento-Immobilier/app/models.py)
Définition des 15 modèles SQLAlchemy correspondants exactement au schéma détaillé dans le PDF `Gestion données immobilière_DB.pdf` :
1. `Utilisateur` (avec hachage de mot de passe et rôles : Administrateur, Directeur, Agent, Assistant, Comptable)
2. `Client` (avec code unique)
3. `DemandeClient` (critères de recherche)
4. `Proprietaire` (avec informations d'identité)
5. `Propriete` (détails physiques et géographiques)
6. `Caracteristique` (Piscine, Climatisation, etc.)
7. `ProprieteCaracteristique` (table de liaison)
8. `PhotoPropriete` (chemins des images et photo principale)
9. `DocumentPropriete` (fichiers PDF associés)
10. `Visite` (suivi des visites clients / agents)
11. `Transaction` (ventes et locations)
12. `Contrat` (suivi des contrats signés)
13. `Paiement` (historique des versements)
14. `Commission` (calcul des parts agents)
15. `JournalActivite` (logs de sécurité pour l'audit des actions utilisateur)

#### [NEW] [init_db.py](file:///c:/Users/PC/Pictures/Ciento-Immobilier/init_db.py)
Script autonome pour créer les tables de la base de données PostgreSQL si elles n'existent pas, et insérer les données de base (rôles par défaut, caractéristiques de base comme Climatisation, Piscine, etc., et un compte administrateur initial).

---

### Backend & Routes (Blueprints Flask)

#### [NEW] [app/__init__.py](file:///c:/Users/PC/Pictures/Ciento-Immobilier/app/__init__.py)
Configuration du conteneur Flask, configuration de SQLAlchemy, Flask-Login, enregistrement des Blueprints Flask pour structurer l'application.

#### [NEW] [routes/auth.py](file:///c:/Users/PC/Pictures/Ciento-Immobilier/app/routes/auth.py)
Endpoints pour la gestion de session (login, logout) avec restrictions basées sur le statut "actif" de l'utilisateur.

#### [NEW] [routes/dashboard.py](file:///c:/Users/PC/Pictures/Ciento-Immobilier/app/routes/dashboard.py)
Calcul et affichage des statistiques clés requises : nombre de biens disponibles, nombre de clients actifs, volume de ventes du mois, contrats de location en cours.

#### [NEW] [routes/clients.py](file:///c:/Users/PC/Pictures/Ciento-Immobilier/app/routes/clients.py)
Gestion du cycle de vie des fiches clients et de leurs demandes / critères de recherche associés.

#### [NEW] [routes/properties.py](file:///c:/Users/PC/Pictures/Ciento-Immobilier/app/routes/properties.py)
Gestion des biens immobiliers, téléchargement de photos (avec désignation de la photo principale), de documents et association de caractéristiques d'équipements.

#### [NEW] [routes/transactions.py](file:///c:/Users/PC/Pictures/Ciento-Immobilier/app/routes/transactions.py)
Saisie des transactions (ventes et locations), association des paiements, calcul automatique de la commission de l'agent commercial et liaison au contrat.

---

### Interface Utilisateur (Templates & Design System Premium)

#### [NEW] [static/css/custom.css](file:///c:/Users/PC/Pictures/Ciento-Immobilier/app/static/css/custom.css)
Feuille de style personnalisée conçue pour transcender le design standard de Bootstrap 5. Elle comprendra :
- Une palette de couleurs premium (tons sombres élégants, dégradés subtils, touches de couleur pour les statuts).
- Une typographie moderne (chargement de la police Google Font *Inter* ou *Outfit*).
- Des effets de transition fluides sur les boutons et les fiches pour offrir une interface dynamique.
- Des styles dédiés pour le tableau de bord (cartes de statistiques avec icônes, graphiques responsifs).
- Un affichage en mode carte (Grid layout) moderne pour les biens immobiliers.

#### [NEW] [templates/base.html](file:///c:/Users/PC/Pictures/Ciento-Immobilier/app/templates/base.html)
Mise en page globale de l'application avec :
- Une barre latérale (Sidebar) de navigation responsive avec des icônes élégantes pour chaque module.
- Une zone de notification pour afficher les messages flash de Flask (succès, erreurs).
- Un en-tête avec informations sur l'utilisateur connecté et son rôle.

#### [NEW] [templates/auth/login.html](file:///c:/Users/PC/Pictures/Ciento-Immobilier/app/templates/auth/login.html)
Une page de connexion moderne et épurée (style "Glassmorphism" ou carte centrée de haute qualité) pour valoriser la marque Ciento Immobilier.

#### [NEW] [templates/dashboard/index.html](file:///c:/Users/PC/Pictures/Ciento-Immobilier/app/templates/dashboard/index.html)
Tableau de bord comprenant des indicateurs de performance clés (KPI), des graphiques de tendances des transactions (via Chart.js ou similaire) et la liste des dernières activités.

---

## Verification Plan

### Automated Tests
Nous mettrons en place une suite de tests unitaires et d'intégration basiques pour valider les points critiques :
- Connexion/Déconnexion et permissions d'accès aux URL selon le rôle de l'utilisateur.
- Insertion et mise à jour d'un client et d'une propriété en base de données.
- Commande de test : `python -m unittest discover -s tests`

### Manual Verification
1. **Initialisation de la base** : Lancer le script `python init_db.py` et vérifier la création des tables et de l'utilisateur par défaut sous PostgreSQL (par exemple avec `pgAdmin` ou `psql`).
2. **Authentification** : Se connecter avec l'utilisateur par défaut, vérifier la redirection vers le tableau de bord et tester le blocage d'accès aux pages pour un visiteur non authentifié.
3. **Création de Données** : Saisir une fiche client complète, ajouter une propriété avec une photo d'illustration, planifier une visite virtuelle ou physique, et générer une transaction témoin pour s'assurer que les calculs de commissions s'effectuent correctement.
4. **Vérification de l'interface** : S'assurer du bon comportement réactif (responsive) de l'interface sur écran d'ordinateur et tablette locale, et vérifier l'esthétique générale par rapport aux critères d'élégance requis.
