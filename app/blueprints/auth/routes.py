from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
from app.extensions import db
from app.models import User

auth_bp = Blueprint('auth', __name__, template_folder='../../templates/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(_dashboard_for(current_user.role)))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()

        if user and user.is_active and check_password_hash(user.password_hash, password):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()

            if user.must_change_password:
                return redirect(url_for('auth.change_password'))

            flash('Logged in successfully.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for(_dashboard_for(user.role)))

        flash('Invalid email or password.', 'error')

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if not check_password_hash(current_user.password_hash, current_pw):
            flash('Current password is incorrect.', 'error')
        elif len(new_pw) < 6:
            flash('New password must be at least 6 characters.', 'error')
        elif new_pw != confirm_pw:
            flash('Passwords do not match.', 'error')
        else:
            current_user.password_hash = generate_password_hash(new_pw)
            current_user.must_change_password = False
            db.session.commit()
            flash('Password changed successfully.', 'success')
            return redirect(url_for(_dashboard_for(current_user.role)))

    return render_template('change_password.html')


def _dashboard_for(role):
    """Returns the endpoint name for a role's dashboard."""
    if role == 'admin':
        return 'admin.dashboard'
    elif role == 'faculty':
        return 'faculty.dashboard'
    else:
        return 'student.dashboard'
