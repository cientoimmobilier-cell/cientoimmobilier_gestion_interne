# Ciento-Immobilier - Logiciel de Gestion Immobilière

Bienvenue sur le dépôt du logiciel de Gestion Immobilière de Ciento-Immobilier. Il s'agit d'une application professionnelle développée en Python/Flask conçue pour administrer des biens immobiliers, gérer des propriétaires, des locataires, et suivre la comptabilité.

> **Architecture 100 % locale (desktop Windows)** : le logiciel fonctionne
> exclusivement via l'application de bureau (PyWebView). Toute la pile —
> Python → Flask local → PostgreSQL local → PyWebView → Windows — tourne sur la
> machine de l'utilisateur. **Aucun déploiement cloud (Render/Vercel), aucun
> serveur WSGI distant, aucune URL publique** n'est utilisé. La base de données
> est un PostgreSQL local, jamais une base cloud (`DATABASE_URL`/`POSTGRES_URL`
> ont été retirées).

## Fonctionnalités

- **Gestion des Biens** : Ajout, modification, suppression, statut (Disponible, Vendu, Loué).
- **Gestion des Propriétaires** : Profils complets et liaison automatique avec leurs biens.
- **Gestion des Clients** : Acquéreurs et locataires, avec historique de transactions.
- **Gestion des Ventes & Locations** : Contrats, suivis et relances.
- **Gestion de la Caisse & Banque** : Entrées/sorties (Recettes/Dépenses), soldes en temps réel.
- **Gestion des Commissions** : Calcul automatique des commissions pour les agents immobiliers.
- **Gestion Airbnb** : Biens et réservations de courte durée.
- **Gestion des Partenaires** : Agences externes, critères de commissions et documents.
- **Rapports et Statistiques** : Exportation de bilans financiers (Excel) et contrats (PDF).

## Structure du projet

La structure a été optimisée et nettoyée pour une application de bureau Windows 100 % locale :

```
project/
├── app/                      # Code source principal de l'application
│   ├── __init__.py           # Initialisation de Flask (app factory)
│   ├── models/               # Modèles de base de données (SQLAlchemy)
│   ├── routes/               # Contrôleurs (Blueprints par module)
│   ├── services/             # Logique métier (Génération PDF, Export Excel, Backup)
│   ├── forms/                # Formulaires (WTForms)
│   ├── utils/                # Fonctions d'assistance (Helpers)
│   ├── templates/            # Vues HTML (Jinja2)
│   └── static/               # Fichiers statiques (CSS, JS, Images, Uploads)
├── desktop/                  # Application desktop Windows (PyWebView, notifications)
├── scripts/                  # Scripts utilitaires de maintenance locaux
│   ├── clear_data.py         # Réinitialisation des données de l'application
│   └── seed_sample_data.py   # Injection de données de démonstration
├── tests/                    # Scripts de tests unitaires
├── migrations/               # Fichiers de migration de base de donnees
├── config.py                 # Configuration principale (locale, HTTP)
├── init_db.py                # Script d'initialisation de la base de données
├── app_desktop.py            # Point d'entrée de l'application desktop
├── run.py                    # Serveur de développement local (fallback)
├── requirements.txt          # Dépendances Python (dont desktop)
└── .env.example              # Modèle de variables d'environnement
```

## Installation en local

### 1. Cloner ou télécharger le dépôt
Placez-vous dans le dossier racine du projet.

### 2. Création de l'environnement virtuel
```bash
python -m venv venv
# Sur Windows :
venv\Scripts\activate
# Sur Mac/Linux :
source venv/bin/activate
```

### 3. Installation des dépendances
```bash
pip install -r requirements.txt
```

### 4. Configuration
Copiez le fichier `.env.example` pour créer votre propre fichier `.env` :
```bash
cp .env.example .env
```
Générez une `SECRET_KEY` forte (minimum 32 caractères) et configurez vos informations de connexion à la base de données (ex: PostgreSQL).

### 5. Initialisation de la base de données
```bash
python init_db.py
# (Optionnel) Pour insérer des données de test :
python scripts/seed_sample_data.py
```

### 6. Lancement de l'application desktop

```bash
python app_desktop.py
```

Le backend Flask local démarre en arrière-plan et l'application s'ouvre dans
une fenêtre Windows (PyWebView) — aucun navigateur externe, aucune adresse
publique. En développement, vous pouvez aussi lancer le serveur local seul :

```bash
python run.py
```
Accédez alors à l'application via `http://127.0.0.1:5000`.

### 7. Lancement des tests unitaires
Pour exécuter les vérifications de la base de données et le bon fonctionnement global, exécutez le framework de tests :
```bash
python -m unittest discover -s tests -q
```

## Build de l'application desktop

Compilez l'exécutable Windows (PyInstaller) puis l'installateur (Inno Setup) :

```bash
build.bat
installer\build_installer.bat
```

---

Developpe pour Ciento-Immobilier.
