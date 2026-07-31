"""
Migration script: synchronise la base de donnees existante avec les nouveaux modeles.
Cree les colonnes et tables manquantes sans perdre les donnees existantes.
"""
import logging
from sqlalchemy import inspect, text
from app import create_app, db

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

app = create_app()

COLUMNS_TO_ADD = {
    'clients': [
        {'name': 'numero_identite', 'definition': 'VARCHAR(50)'},
        {'name': 'type_piece', 'definition': 'VARCHAR(30)'},
    ],
    'contrats': [
        {'name': 'montant_loyer', 'definition': 'NUMERIC(15, 2)'},
        {'name': 'depot_garantie', 'definition': 'NUMERIC(15, 2)'},
        {'name': 'mode_paiement', 'definition': 'VARCHAR(50)'},
        {'name': 'frequence', 'definition': 'VARCHAR(30)'},
        {'name': 'statut', 'definition': 'VARCHAR(30) DEFAULT \'Actif\''},
    ],
}


def migrate():
    with app.app_context():
        inspector = inspect(db.engine)
        existing_tables = set(inspector.get_table_names())
        logger.info(f'Tables existantes: {len(existing_tables)}')

        missing_columns = []
        for table, columns in COLUMNS_TO_ADD.items():
            if table not in existing_tables:
                logger.info(f'  Table {table} n existe pas (sera creee par create_all)')
                continue
            existing_cols = {c['name'] for c in inspector.get_columns(table)}
            for col in columns:
                if col['name'] not in existing_cols:
                    missing_columns.append((table, col))
                    logger.info(f'  Colonne manquante: {table}.{col["name"]}')

        if missing_columns:
            logger.info(f'\nAjout de {len(missing_columns)} colonne(s) manquante(s)...')
            with db.engine.connect() as conn:
                for table, col in missing_columns:
                    sql = f'ALTER TABLE {table} ADD COLUMN {col["name"]} {col["definition"]}'
                    logger.info(f'  SQL: {sql}')
                    conn.execute(text(sql))
                conn.commit()
            logger.info('Colonnes ajoutees avec succes.')
        else:
            logger.info('Aucune colonne manquante.')

        logger.info('\nCreation des nouvelles tables...')
        db.create_all()
        logger.info('Tables creees ou deja existantes.')

        final_tables = set(inspector.get_table_names())
        new_tables = final_tables - existing_tables
        if new_tables:
            logger.info(f'Nouvelles tables creees: {", ".join(sorted(new_tables))}')
        else:
            logger.info('Aucune nouvelle table necessaire.')

        logger.info('\nCreation des index manquants (synchronisation des modeles)...')
        with db.engine.connect() as conn:
            created = 0
            for table_name, table in db.metadata.tables.items():
                if table_name not in final_tables:
                    continue
                existing_indexes = {ix['name'] for ix in inspector.get_indexes(table_name)}
                for index in table.indexes:
                    index_name = index.name
                    if index_name in existing_indexes:
                        continue
                    columns = ', '.join(c.name for c in index.columns)
                    if not columns:
                        continue
                    sql = (
                        f'CREATE INDEX IF NOT EXISTS {index_name} '
                        f'ON {table_name} ({columns})'
                    )
                    conn.execute(text(sql))
                    logger.info(f'  Index cree: {index_name} ON {table_name} ({columns})')
                    created += 1
            conn.commit()
        if created:
            logger.info(f'{created} index cree(s) avec succes.')
        else:
            logger.info('Aucun index manquant.')

        logger.info('\nMigration terminee avec succes.')


if __name__ == '__main__':
    migrate()
