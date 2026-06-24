from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app.models import Utilisateur, Transaction, Visite, Commission, BienAirbnb
from app.utils.helpers import log_activity, role_required
from app import db
from sqlalchemy import func
import string
import secrets

def generate_random_password(length=12):
    characters = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(characters) for i in range(length))

agents = Blueprint('agents', __name__)

@agents.route('/')
@login_required
def list_agents():
    search = request.args.get('search', '')
    zone_filter = request.args.get('zone', '')
    
    query = Utilisateur.query.filter_by(role='Agent immobilier')
    
    if search:
        query = query.filter(
            (Utilisateur.nom.ilike(f'%{search}%')) |
            (Utilisateur.prenom.ilike(f'%{search}%')) |
            (Utilisateur.email.ilike(f'%{search}%'))
        )
    if zone_filter:
        query = query.filter(Utilisateur.zone_affectation.ilike(f'%{zone_filter}%'))
    
    agents_list = query.order_by(Utilisateur.nom.asc()).all()
    
    # Récupérer les zones uniques pour le filtre
    zones = db.session.query(Utilisateur.zone_affectation).filter(
        Utilisateur.role == 'Agent immobilier',
        Utilisateur.zone_affectation.isnot(None),
        Utilisateur.zone_affectation != ''
    ).distinct().all()
    zones = [z[0] for z in zones if z[0]]
    
    return render_template('agents/list.html', agents=agents_list, search=search, 
                         zone=zone_filter, zones=zones)

@agents.route('/details/<int:agent_id>')
@login_required
def view_agent(agent_id):
    agent = Utilisateur.query.get_or_404(agent_id)
    
    # Vérifier que c'est bien un agent immobilier
    if agent.role != 'Agent immobilier':
        flash("Cet utilisateur n'est pas un agent immobilier.", "warning")
        return redirect(url_for('agents.list_agents'))
    
    # Statistiques de l'agent
    total_transactions = Transaction.query.filter_by(agent_id=agent.id).count()
    transactions_finalisees = Transaction.query.filter_by(agent_id=agent.id, statut='Finalisée').count()
    total_visites = Visite.query.filter_by(agent_id=agent.id).count()
    visites_effectuees = Visite.query.filter_by(agent_id=agent.id, statut='Effectuée').count()
    
    # Commissions totales
    total_commissions = db.session.query(func.sum(Commission.montant)).filter_by(agent_id=agent.id).scalar() or 0
    
    # Biens AirBNB gérés
    biens_airbnb = BienAirbnb.query.filter_by(agent_id=agent.id).all()
    
    # Dernières transactions
    dernieres_transactions = Transaction.query.filter_by(agent_id=agent.id).order_by(Transaction.id.desc()).limit(5).all()
    
    # Dernières visites
    dernieres_visites = Visite.query.filter_by(agent_id=agent.id).order_by(Visite.date_visite.desc()).limit(5).all()
    
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
    agent = Utilisateur.query.get_or_404(agent_id)
    
    if agent.role != 'Agent immobilier':
        flash("Seuls les agents immobiliers peuvent être affectés à une zone.", "warning")
        return redirect(url_for('agents.list_agents'))
    
    nouvelle_zone = request.form.get('zone_affectation')
    agent.zone_affectation = nouvelle_zone
    
    try:
        db.session.commit()
        log_activity(current_user.id, f"Affectation zone '{nouvelle_zone}' à {agent.prenom} {agent.nom}", "utilisateurs", agent.id)
        flash(f"Zone d'affectation de {agent.prenom} {agent.nom} mise à jour : {nouvelle_zone or 'Aucune'}.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erreur: {e}", "danger")
    
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
        
        if Utilisateur.query.filter_by(email=email).first():
            flash('Cet email est déjà utilisé.', 'danger')
            return redirect(url_for('agents.add_agent'))
            
        password = generate_random_password()
        
        agent = Utilisateur(
            nom=nom,
            prenom=prenom,
            email=email,
            telephone=telephone,
            role='Agent immobilier',
            zone_affectation=zone_affectation,
            actif=True
        )
        agent.set_password(password)
        
        db.session.add(agent)
        db.session.commit()
        
        log_activity(current_user.id, 'Création', 'utilisateurs', agent.id)
        flash('Agent externe créé avec succès.', 'success')
        return redirect(url_for('agents.list_agents'))
        
    return render_template('agents/form.html', action="add")

@agents.route('/edit/<int:agent_id>', methods=['GET', 'POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def edit_agent(agent_id):
    agent = Utilisateur.query.get_or_404(agent_id)
    
    if agent.role != 'Agent immobilier':
        flash("Cet utilisateur n'est pas un agent immobilier.", "warning")
        return redirect(url_for('agents.list_agents'))
        
    if request.method == 'POST':
        agent.nom = request.form.get('nom')
        agent.prenom = request.form.get('prenom')
        
        new_email = request.form.get('email')
        if new_email != agent.email and Utilisateur.query.filter_by(email=new_email).first():
            flash('Cet email est déjà utilisé.', 'danger')
            return redirect(url_for('agents.edit_agent', agent_id=agent.id))
            
        agent.email = new_email
        agent.telephone = request.form.get('telephone')
        agent.zone_affectation = request.form.get('zone_affectation')
        
        db.session.commit()
        log_activity(current_user.id, 'Modification', 'utilisateurs', agent.id)
        flash('Agent externe modifié avec succès.', 'success')
        return redirect(url_for('agents.list_agents'))
        
    return render_template('agents/form.html', action="edit", agent=agent)

@agents.route('/toggle/<int:agent_id>', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def toggle_agent(agent_id):
    agent = Utilisateur.query.get_or_404(agent_id)
    
    if agent.role != 'Agent immobilier':
        flash("Cet utilisateur n'est pas un agent.", "warning")
        return redirect(url_for('agents.list_agents'))
        
    agent.actif = not agent.actif
    db.session.commit()
    
    statut = "activé" if agent.actif else "désactivé"
    log_activity(current_user.id, f'Changement statut ({statut})', 'utilisateurs', agent.id)
    flash(f'L\'agent a été {statut} avec succès.', 'success')
    return redirect(url_for('agents.list_agents'))
