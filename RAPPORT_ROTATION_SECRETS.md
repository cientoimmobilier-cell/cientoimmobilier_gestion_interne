# RAPPORT DE ROTATION DES SECRETS

**Date :** 03/08/2026
**Périmètre :** SECRET_KEY, DB_PASSWORD, identifiants OAuth Google, artefacts empaquetés.

## Contexte

L'audit de sécurité a établi que des secrets ont été exposés historiquement via
l'archive locale non chiffrée `backups/ciento_backup_20260730_135512.zip`
(contenait `.env` en clair : SECRET_KEY + DB_PASSWORD) et via des artefacts
empaquetés obsolètes (`dist/.env`, `build/`, `CIENTO-IMMOBILIER.exe`). Ces
secrets sont donc considérés comme **compromis** et doivent être rotés.

## Opérations effectuées

| # | Action | Statut |
|---|--------|--------|
| 1 | Vérification : `.env` absent de Git (suivi et historique) | ✅ déjà vérifié |
| 2 | Rotation de `SECRET_KEY` : nouvelle clé aléatoire 64 hex (SHA-256) générée, écrite dans `.env` | ✅ |
| 3 | Rotation de `DB_PASSWORD` : nouveau mot de passe aléatoire 24 chars généré, appliqué dans PostgreSQL (`ALTER USER postgres WITH PASSWORD …`) et écrit dans `.env` | ✅ |
| 4 | Ré-enveloppement des secrets en base (`cloud_backup_settings`) avec le **nouveau** SECRET_KEY : `google_client_id_wrapped`, `google_client_secret_wrapped`, `token_encrypted`, `encryption_passphrase_wrapped` — déchiffrés avec l'ancienne clé puis re-chiffrés avec la nouvelle, **sans perte de continuité** | ✅ |
| 5 | Suppression de `client_secret_821866264737-…apps.googleusercontent.com.json` (identifiants OAuth Google en clair, inutilisés par l'application qui lit la base) | ✅ |
| 6 | Suppression des artefacts empaquetés obsolètes contenant les anciens secrets : `dist/` (`dist/.env`, `CIENTO-IMMOBILIER.exe`) et `build/` | ✅ |
| 7 | Vérification : l'ancien SECRET_KEY n'apparaît plus dans le workspace (hors `venv/`, `.git/`) | ✅ |
| 8 | Vérification du `.spec` PyInstaller : `.env` et `uploads/` exclus de l'exécutable (`datas = [('assets','assets')]`, filtre `_is_upload_data`) | ✅ |

## Vérifications

- Connexion PostgreSQL avec le **nouveau** mot de passe : OK.
- Déchiffrement des secrets en base avec le **nouveau** SECRET_KEY : OK (roundtrip).
- `.env` : `SECRET_KEY` = 64 caractères hexadécimaux, `DB_PASSWORD` ≠ ancien.
- Le `.exe` devra être **reconstruit** (`build.bat`) avec le nouveau `.env` avant distribution.

## Actions restantes (à réaliser par l'équipe — non automatisables)

1. **Renouveler le client OAuth Google** dans la Google Cloud Console
   (API & Services → Identifiants → OAuth 2.0 Client IDs) :
   - régénérer le `client_secret` du client « CIENTO » ;
   - mettre à jour la base via l'interface
   (`Paramètres → Sauvegarde Cloud → Identifiants Google`) avec le nouveau
   `client_id` / `client_secret` (stockés chiffrés) ;
   - recréer l'autorisation (`Connexion Google`, flux OAuth + PKCE).
2. **Purge de l'historique Git** (obligatoire car le dépôt est sur GitHub) :
   `git filter-repo --path app/static/uploads --invert-paths --force` puis
   `git push --force --all` et `git push --force --tags`. Les documents et
   photos clients suivis dans les commits antérieurs restent dans l'historique
   tant que cette purge n'est pas faite.
3. **Vérifier la visibilité du dépôt GitHub** (privé/privé organisation) et
   considérer les documents exposés (contrat PDF, manuel DOCX, photos) comme
   potentiellement compromis.
4. Reconstruire et redistribuer l'exécutable après purge et rotation.
