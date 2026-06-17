from flask import Blueprint, render_template, abort
from flask_login import login_required, current_user
from app.models import Propriete, Client, Transaction, JournalActivite, Visite
from datetime import datetime, date
from sqlalchemy import extract, func
from app import db

dashboard = Blueprint('dashboard', __name__)

@dashboard.route('/')
@login_required
def index():
    # Statistiques Globales
    total_properties = Propriete.query.count()
    available_properties = Propriete.query.filter_by(statut='Disponible').count()
    total_clients = Client.query.count()
    
    # Mois en cours
    today = date.today()
    current_year = today.year
    current_month = today.month
    
    # Ventes du mois (Finalisées)
    sales_this_month = Transaction.query.filter(
        Transaction.type_transaction == 'Vente',
        Transaction.statut == 'Finalisée',
        extract('year', Transaction.date_transaction) == current_year,
        extract('month', Transaction.date_transaction) == current_month
    ).count()

    # Locations en cours (Finalisées)
    active_rentals = Transaction.query.filter(
        Transaction.type_transaction == 'Location',
        Transaction.statut == 'Finalisée'
    ).count()
    
    # Dernières transactions saisies
    recent_transactions = Transaction.query.order_by(Transaction.id.desc()).limit(5).all()
    
    # Dernières visites planifiées/effectuées
    recent_visits = Visite.query.order_by(Visite.date_visite.desc()).limit(5).all()
    
    # Répartition des biens par type pour un éventuel graphique
    properties_by_type = db.session.query(
        Propriete.type_bien, func.count(Propriete.id)
    ).group_by(Propriete.type_bien).all()
    
    type_labels = [p[0] for p in properties_by_type]
    type_counts = [p[1] for p in properties_by_type]

    return render_template(
        'dashboard/index.html',
        total_properties=total_properties,
        available_properties=available_properties,
        total_clients=total_clients,
        sales_this_month=sales_this_month,
        active_rentals=active_rentals,
        recent_transactions=recent_transactions,
        recent_visits=recent_visits,
        type_labels=type_labels,
        type_counts=type_counts
    )

@dashboard.route('/activities')
@login_required
def activities():
    # Seuls l'administrateur et le directeur ont accès au journal d'activités
    if current_user.role not in ['Administrateur', 'Directeur']:
        abort(403)
        
    logs = JournalActivite.query.order_by(JournalActivite.date_action.desc()).limit(100).all()
    return render_template('dashboard/activities.html', logs=logs)
