import logging
import traceback
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from app.models import Utilisateur, Transaction, Visite, Commission, BienAirbnb
from app.utils.helpers import log_activity, role_required, sanitize_search
from app import db
from sqlalchemy import select, func as sa_func

logger = logging.getLogger(__name__)

agents = Blueprint('agents', __name__)

@agents.route('/')
@login_required
def list_agents():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'nom')
    order = request.args.get('order', 'asc')

    stmt = select(Utilisateur).where(Utilisateur.role == 'Agent immobilier')

    if search:
        safe_search = sanitize_search(search)
        search_term = f'%{safe_search}%'
        stmt = stmt.where(
            db.or_(Utilisateur.nom.ilike(search_term), Utilisateur.prenom.ilike(search_term), Utilisateur.email.ilike(search_term))
        )

    zone = request.args.get('zone', '').strip()
    if zone:
        stmt = stmt.where(Utilisateur.zone_affectation == zone)

    sort_column = getattr(Utilisateur, sort, Utilisateur.nom)
    try:
        stmt = stmt.order_by(sort_column.asc() if order == 'asc' else sort_column.desc())
    except:
        stmt = stmt.order_by(Utilisateur.nom.asc())

    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)

    zones = db.session.execute(select(Utilisateur.zone_affectation).where(
        Utilisateur.zone_affectation.isnot(None), Utilisateur.role == 'Agent immobilier'
    ).distinct()).scalars().all()
    zones = [z for z in zones if z]

    return render_template('agents/list.html', agents=pagination.items, pagination=pagination, zones=zones, sort=sort, order=order)

@agents.route('/details/<int:agent_id>')
@login_required
def view_agent(agent_id):
    agent = db.session.get(Utilisateur, agent_id)
    if agent is None:
        abort(404)
    
    # Vérifier que c'est bien un agent immobilier
    if agent.role != 'Agent immobilier':
        flash("Cet utilisateur n'est pas un agent immobilier.", "warning")
        return redirect(url_for('agents.list_agents'))
    
    # Statistiques de l'agent
    total_transactions = db.session.execute(select(sa_func.count(Transaction.id)).where(Transaction.agent_id == agent.id)).scalar()
    transactions_finalisees = db.session.execute(select(sa_func.count(Transaction.id)).where(Transaction.agent_id == agent.id, Transaction.statut == 'Finalisée')).scalar()
    total_visites = db.session.execute(select(sa_func.count(Visite.id)).where(Visite.agent_id == agent.id)).scalar()
    visites_effectuees = db.session.execute(select(sa_func.count(Visite.id)).where(Visite.agent_id == agent.id, Visite.statut == 'Effectuée')).scalar()
    
    # Commissions totales
    total_commissions = db.session.execute(select(sa_func.sum(Commission.montant)).where(Commission.agent_id == agent.id)).scalar() or 0
    
    # Biens AirBNB gérés
    biens_airbnb = db.session.execute(select(BienAirbnb).where(BienAirbnb.agent_id == agent.id)).scalars().all()
    
    # Dernières transactions
    dernieres_transactions = db.session.execute(select(Transaction).where(Transaction.agent_id == agent.id).order_by(Transaction.id.desc()).limit(5)).scalars().all()
    
    # Dernières visites
    dernieres_visites = db.session.execute(select(Visite).where(Visite.agent_id == agent.id).order_by(Visite.date_visite.desc()).limit(5)).scalars().all()
    
    return render_template('agents/view.html', agent=agent,
                         total_transactions=total_transactions,
                         transactions_finalisees=transactions_finalisees,
                         total_visites=total_visites,
                         visites_effectuees=visites_effectuees,
                         total_commissions=float(total_commissions),
                         biens_airbnb=biens_airbnb,
                         dernieres_transactions=dernieres_transactions,
                         dernieres_visites=dernieres_visites)

@agents.route('/affecter/<int:agent_id>', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def affecter_zone(agent_id):
    agent = db.session.get(Utilisateur, agent_id)
    if agent is None:
        abort(404)
    
    if agent.role != 'Agent immobilier':
        flash("Seuls les agents immobiliers peuvent être affectés à une zone.", "warning")
        return redirect(url_for('agents.list_agents'))
    
    nouvelle_zone = request.form.get('zone_affectation')
    agent.zone_affectation = nouvelle_zone
    
    try:
        log_activity(current_user.id, f"Affectation zone '{nouvelle_zone}' à {agent.prenom} {agent.nom}", "utilisateurs", agent.id)
        db.session.commit()
        flash(f"Zone d'affectation de {agent.prenom} {agent.nom} mise à jour : {nouvelle_zone or 'Aucune'}.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[AGENTS] Échec affectation zone agent_id={agent_id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de la mise à jour. Veuillez réessayer.", "danger")
    
    return redirect(url_for('agents.view_agent', agent_id=agent_id))

@agents.route('/add', methods=['GET', 'POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def add_agent():
    if request.method == 'POST':
        nom = request.form.get('nom')
        prenom = request.form.get('prenom')
        email = request.form.get('email')
        telephone = request.form.get('telephone')
        zone_affectation = request.form.get('zone_affectation')
        
        if db.session.execute(select(Utilisateur).where(Utilisateur.email == email)).scalars().first():
            flash('Cet email est déjà utilisé.', 'danger')
            return redirect(url_for('agents.add_agent'))
            
        password = request.form.get('password')
        if not password:
            flash('Le mot de passe est obligatoire.', 'danger')
            return redirect(url_for('agents.add_agent'))
        # ── Validation AVANT bcrypt ──────────────────────────────────────
        if len(password.strip()) < 8:
            flash('Le mot de passe doit contenir au moins 8 caractères.', 'danger')
            return redirect(url_for('agents.add_agent'))
        
        agent = Utilisateur(
            nom=nom,
            prenom=prenom,
            email=email,
            telephone=telephone,
            role='Agent immobilier',
            zone_affectation=zone_affectation,
            actif=True
        )
        agent.set_password(password)  # Hash uniquement après validation
        
        try:
            db.session.add(agent)
            db.session.flush()
            log_activity(current_user.id, 'Création', 'utilisateurs', agent.id)
            db.session.commit()
            flash('Agent externe créé avec succès.', 'success')
            return redirect(url_for('agents.list_agents'))
        except Exception:
            db.session.rollback()
            logger.error(f"[AGENTS] Échec création agent par user_id={current_user.id}")
            logger.error(traceback.format_exc())
            flash('Erreur lors de la création de l\'agent. Veuillez réessayer.', 'danger')
            return redirect(url_for('agents.add_agent'))
        
    return render_template('agents/form.html', action="add")

@agents.route('/edit/<int:agent_id>', methods=['GET', 'POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def edit_agent(agent_id):
    agent = db.session.get(Utilisateur, agent_id)
    if agent is None:
        abort(404)
    
    if agent.role != 'Agent immobilier':
        flash("Cet utilisateur n'est pas un agent immobilier.", "warning")
        return redirect(url_for('agents.list_agents'))
        
    if request.method == 'POST':
        agent.nom = request.form.get('nom')
        agent.prenom = request.form.get('prenom')
        
        new_email = request.form.get('email')
        if new_email != agent.email and db.session.execute(select(Utilisateur).where(Utilisateur.email == new_email)).scalars().first():
            flash('Cet email est déjà utilisé.', 'danger')
            return redirect(url_for('agents.edit_agent', agent_id=agent.id))
            
        agent.email = new_email
        agent.telephone = request.form.get('telephone')
        agent.zone_affectation = request.form.get('zone_affectation')
        
        try:
            log_activity(current_user.id, 'Modification', 'utilisateurs', agent.id)
            db.session.commit()
            flash('Agent externe modifié avec succès.', 'success')
            return redirect(url_for('agents.list_agents'))
        except Exception:
            db.session.rollback()
            logger.error(f"[AGENTS] Échec modification agent_id={agent_id} par user_id={current_user.id}")
            logger.error(traceback.format_exc())
            flash('Erreur lors de la modification de l\'agent. Veuillez réessayer.', 'danger')
        
    return render_template('agents/form.html', action="edit", agent=agent)

@agents.route('/toggle/<int:agent_id>', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def toggle_agent(agent_id):
    agent = db.session.get(Utilisateur, agent_id)
    if agent is None:
        abort(404)
    
    if agent.role != 'Agent immobilier':
        flash("Cet utilisateur n'est pas un agent.", "warning")
        return redirect(url_for('agents.list_agents'))
        
    agent.actif = not agent.actif
    try:
        statut = "activé" if agent.actif else "désactivé"
        log_activity(current_user.id, f'Changement statut ({statut})', 'utilisateurs', agent.id)
        db.session.commit()
        flash(f'L\'agent a été {statut} avec succès.', 'success')
    except Exception:
        db.session.rollback()
        logger.error(f"[AGENTS] Échec toggle statut agent_id={agent_id} par user_id={current_user.id}")
        logger.error(traceback.format_exc())
        flash('Erreur lors du changement de statut. Veuillez réessayer.', 'danger')
    return redirect(url_for('agents.list_agents'))
