# Scripts utilitaires — Ciento Immobilier

Ce dossier contient des scripts de maintenance à usage manuel.
**Ne jamais exécuter en production sans backup préalable.**

## Scripts disponibles

| Script | Usage | Commande |
|--------|-------|---------|
| `clear_data.py` | Supprime toutes les données métier (hors utilisateurs) | `python scripts/clear_data.py` |
| `seed_sample_data.py` | Injecte des données de démonstration | `python scripts/seed_sample_data.py` |

## Prérequis

Lancer depuis la racine du projet avec l'environnement virtuel activé :
```bash
# Windows
venv\Scripts\activate
python scripts/<nom_script>.py

# Linux/Mac
source venv/bin/activate
python scripts/<nom_script>.py
```
