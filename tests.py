import unittest
from app import create_app, db
from app.config import Config
from app.models import Utilisateur, Client, Propriete, Transaction, Commission
from datetime import datetime, date

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

class CientoImmobilierTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_user_password_hashing(self):
        user = Utilisateur(
            nom='Dupont',
            prenom='Jean',
            email='jean.dupont@ciento.immo',
            role='Agent immobilier'
        )
        user.set_password('superpassword123')
        self.assertTrue(user.check_password('superpassword123'))
        self.assertFalse(user.check_password('wrongpassword'))

    def test_client_creation(self):
        client = Client(
            code_client='CLI-2026-0001',
            nom='MARTIN',
            prenom='Thomas',
            telephone='+33612345678',
            email='thomas.martin@outlook.com'
        )
        db.session.add(client)
        db.session.commit()
        
        queried = Client.query.filter_by(code_client='CLI-2026-0001').first()
        self.assertIsNotNone(queried)
        self.assertEqual(queried.nom, 'MARTIN')
        self.assertEqual(queried.prenom, 'Thomas')

    def test_property_creation(self):
        prop = Propriete(
            reference_bien='BIEN-2026-0001',
            titre='Appartement T2 Marais',
            type_bien='Appartement',
            type_operation='Vente',
            prix=250000,
            ville='Paris',
            statut='Disponible'
        )
        db.session.add(prop)
        db.session.commit()
        
        queried = Propriete.query.filter_by(reference_bien='BIEN-2026-0001').first()
        self.assertIsNotNone(queried)
        self.assertEqual(queried.prix, 250000)
        self.assertEqual(queried.statut, 'Disponible')

    def test_transaction_and_commission(self):
        agent = Utilisateur(
            nom='Dubois',
            prenom='Paul',
            email='paul.dubois@ciento.immo',
            role='Agent immobilier'
        )
        agent.set_password('agentpass')
        client = Client(code_client='CLI-01', nom='MARTIN', prenom='Thomas')
        prop = Propriete(
            reference_bien='BIEN-01',
            titre='Appartement T2',
            type_bien='Appartement',
            type_operation='Vente',
            prix=100000,
            ville='Paris'
        )
        
        db.session.add_all([agent, client, prop])
        db.session.commit()
        
        tx = Transaction(
            reference_transaction='TX-01',
            client_id=client.id,
            propriete_id=prop.id,
            agent_id=agent.id,
            type_transaction='Vente',
            montant=100000,
            date_transaction=date.today(),
            statut='En cours'
        )
        db.session.add(tx)
        db.session.commit()
        
        # Calcul de commission
        pct = 5.0
        mt_commission = float(tx.montant) * (pct / 100)
        commission = Commission(
            transaction_id=tx.id,
            agent_id=agent.id,
            pourcentage=pct,
            montant=mt_commission,
            date_calcul=date.today()
        )
        db.session.add(commission)
        db.session.commit()
        
        queried_commission = Commission.query.filter_by(transaction_id=tx.id).first()
        self.assertIsNotNone(queried_commission)
        self.assertEqual(float(queried_commission.montant), 5000.0)
        self.assertEqual(float(queried_commission.pourcentage), 5.0)

if __name__ == '__main__':
    unittest.main()
