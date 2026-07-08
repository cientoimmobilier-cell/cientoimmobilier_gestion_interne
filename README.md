# Ciento-Immobilier - Logiciel de Gestion Immobilière

Bienvenue sur le dépôt du logiciel de Gestion Immobilière de Ciento-Immobilier. Il s'agit d'une application professionnelle développée en Python/Flask conçue pour administrer des biens immobiliers, gérer des propriétaires, des locataires, et suivre la comptabilité.

## 🚀 Fonctionnalités

- **Gestion des Biens** : Ajout, modification, suppression, statut (Disponible, Vendu, Loué).
- **Gestion des Propriétaires** : Profils complets et liaison automatique avec leurs biens.
- **Gestion des Clients** : Acquéreurs et locataires, avec historique de transactions.
- **Gestion des Ventes & Locations** : Contrats, suivis et relances.
- **Gestion de la Caisse & Banque** : Entrées/sorties (Recettes/Dépenses), soldes en temps réel.
- **Gestion des Commissions** : Calcul automatique des commissions pour les agents immobiliers.
- **Gestion Airbnb** : Biens et réservations de courte durée.
- **Gestion des Partenaires** : Agences externes, critères de commissions et documents.
- **Rapports et Statistiques** : Exportation de bilans financiers (Excel) et contrats (PDF).

## 📂 Structure du projet

La structure a été optimisée et nettoyée pour garantir les meilleures pratiques de développement Flask et préparer le déploiement en production :

```
project/
├── app/                      # Code source principal de l'application
│   ├── __init__.py           # Initialisation de Flask (app factory)
│   ├── models/               # Modèles de base de données (SQLAlchemy)
│   ├── routes/               # Contrôleurs (Blueprints par module)
│   ├── services/             # Logique métier (Génération PDF, Export Excel)
│   ├── forms/                # Formulaires (WTForms)
│   ├── utils/                # Fonctions d'assistance (Helpers)
│   ├── templates/            # Vues HTML (Jinja2)
│   └── static/               # Fichiers statiques (CSS, JS, Images, Uploads)
├── scripts/                  # Scripts utilitaires de maintenance locaux
│   ├── clear_data.py         # Réinitialisation des données de l'application
│   └── seed_sample_data.py   # Injection de données de démonstration
├── tests/                    # Scripts de tests unitaires (test_app.py)
├── instance/                 # Base de données locale de développement
├── docs/                     # Documentation technique
├── migrations/               # Fichiers de migration de base de données
├── config.py                 # Configuration principale
├── init_db.py                # Script d'initialisation de la base de données
├── render.yaml               # Fichier de configuration Render pour le déploiement
├── run.py                    # Point d'entrée de l'application
├── requirements.txt          # Dépendances Python optimisées (Python 3.12+)
└── .env.example              # Modèle de variables d'environnement
```

## 🛠️ Installation en local

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

### 6. Lancement du serveur Flask
```bash
python run.py
```
Accédez à l'application via `http://127.0.0.1:5000`.

### 7. Lancement des tests unitaires
Pour exécuter les vérifications de la base de données et le bon fonctionnement global, exécutez le framework de tests :
```bash
python -m unittest tests.test_app
```

## 🌐 Déploiement en Production (Render)

L'application intègre nativement la spécification `render.yaml` assurant un déploiement PaaS rapide, idéal avec une base de données PostgreSQL hébergée sur **Supabase** ou **Render DB**.

1. Poussez le projet sur un dépôt GitHub ou GitLab.
2. Créez un compte sur [Render](https://render.com/).
3. Connectez Render à votre dépôt Git.
4. L'outil "Blueprint" de Render va détecter le fichier `render.yaml` et déployer automatiquement :
   - Le serveur web avec **Gunicorn** (configuré avec les workers adéquats).
   - L'environnement Python en **version 3.12**.
   - Le script d'installation et d'initialisation automatique `init_db.py`.

N'oubliez pas d'indiquer la variable environnementale `DATABASE_URL` (format `postgresql://...`) fournie par Supabase ou Render.

---
**Développé avec soin pour Ciento-Immobilier.**
