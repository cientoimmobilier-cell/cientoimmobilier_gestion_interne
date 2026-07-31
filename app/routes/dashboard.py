import logging
import traceback
from flask import Blueprint, render_template, abort, flash, request
from flask_login import login_required, current_user
from app.models import Propriete, Client, Transaction, JournalActivite, Visite, BienAirbnb, ReservationAirbnb, Utilisateur
from app.utils.helpers import role_required
from datetime import datetime, date
from sqlalchemy import extract, func as sa_func, select
from app import db

logger = logging.getLogger(__name__)

dashboard = Blueprint('dashboard', __name__)

@dashboard.route('/')
@login_required
def index():
    try:
        # Statistiques Globales
        total_properties = db.session.execute(select(sa_func.count(Propriete.id))).scalar()
        available_properties = db.session.execute(select(sa_func.count(Propriete.id)).where(Propriete.statut == 'Disponible')).scalar()
        total_clients = db.session.execute(select(sa_func.count(Client.id))).scalar()
        
        # Mois en cours
        today = date.today()
        current_year = today.year
        current_month = today.month
        
        # Ventes du mois (Finalisées)
        sales_this_month = db.session.execute(select(sa_func.count(Transaction.id)).where(
            Transaction.type_transaction == 'Vente',
            Transaction.statut == 'Finalisée',
            extract('year', Transaction.date_transaction) == current_year,
            extract('month', Transaction.date_transaction) == current_month
        )).scalar()

        # Locations en cours (Finalisées)
        active_rentals = db.session.execute(select(sa_func.count(Transaction.id)).where(
            Transaction.type_transaction == 'Location',
            Transaction.statut == 'Finalisée'
        )).scalar()
        
        # Dernières transactions saisies
        recent_transactions = db.session.execute(select(Transaction).order_by(Transaction.id.desc()).limit(5)).scalars().all()
        
        # Dernières visites planifiées/effectuées
        recent_visits = db.session.execute(select(Visite).order_by(Visite.date_visite.desc()).limit(5)).scalars().all()
        
        # Répartition des biens par type pour un éventuel graphique
        properties_by_type = db.session.execute(
            select(Propriete.type_bien, sa_func.count(Propriete.id)).group_by(Propriete.type_bien)
        ).all()
        
        type_labels = [p[0] for p in properties_by_type]
        type_counts = [p[1] for p in properties_by_type]

        # Nouvelles statistiques (AirBNB et Agents)
        total_airbnb = db.session.execute(select(sa_func.count(BienAirbnb.id))).scalar()
        agents_actifs = db.session.execute(select(sa_func.count(Utilisateur.id)).where(Utilisateur.role == 'Agent immobilier', Utilisateur.actif == True)).scalar()
        reservations_airbnb_mois = db.session.execute(select(sa_func.count(ReservationAirbnb.id)).where(
            ReservationAirbnb.statut.in_(['Confirmée', 'Terminée']),
            extract('year', ReservationAirbnb.date_arrivee) == current_year,
            extract('month', ReservationAirbnb.date_arrivee) == current_month
        )).scalar()

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
            type_counts=type_counts,
            total_airbnb=total_airbnb,
            agents_actifs=agents_actifs,
            reservations_airbnb_mois=reservations_airbnb_mois
        )
    except Exception as e:
        logger.error(f"[DASHBOARD] Erreur chargement tableau de bord user_id={current_user.id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors du chargement du tableau de bord.", "danger")
        return render_template('dashboard/index.html',
            total_properties=0, available_properties=0, total_clients=0,
            sales_this_month=0, active_rentals=0,
            recent_transactions=[], recent_visits=[],
            type_labels=[], type_counts=[],
            total_airbnb=0, agents_actifs=0, reservations_airbnb_mois=0
        )

@dashboard.route('/activities')
@login_required
@role_required('Administrateur', 'Directeur')
def activities():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        search = request.args.get('search', '').strip()
        sort = request.args.get('sort', 'date_action')
        order = request.args.get('order', 'desc')

        stmt = select(JournalActivite)

        if search:
            search_term = f'%{search}%'
            stmt = stmt.where(
                db.or_(JournalActivite.action.ilike(search_term), JournalActivite.table_concernee.ilike(search_term))
            )

        sort_column = getattr(JournalActivite, sort, JournalActivite.date_action)
        try:
            stmt = stmt.order_by(sort_column.asc() if order == 'asc' else sort_column.desc())
        except:
            stmt = stmt.order_by(JournalActivite.date_action.desc())

        pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
        return render_template('dashboard/activities.html', logs=pagination.items, pagination=pagination, sort=sort, order=order)
    except Exception as e:
        logger.error(f"[DASHBOARD] Erreur chargement activités: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors du chargement du journal d'activités.", "danger")
        return render_template('dashboard/activities.html', pagination=None, logs=[])


@dashboard.route('/a-propos')
@login_required
def about():
    return render_template('dashboard/about.html')
