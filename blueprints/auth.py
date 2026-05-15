from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db_connection

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))
    return render_template('login.html')


@auth_bp.route('/login', methods=['POST'])
def login():
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (request.form['email'],)).fetchone()

    if user and check_password_hash(user['password'], request.form['password']):
        today = date.today().isoformat()
        last_login = user['last_login']
        new_streak = user['streak']

        if last_login != today:
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            if last_login == yesterday:
                new_streak += 1
            else:
                new_streak = 1
            conn.execute('UPDATE users SET last_login = ?, streak = ? WHERE id = ?', (today, new_streak, user['id']))
            conn.commit()

        session['user_id'] = user['id']
        session['role'] = user['role']
        session['name'] = user['name']
        session['profile_pic'] = user['profile_pic']
        session['streak'] = new_streak
        conn.close()
        return redirect(url_for('dashboard'))

    conn.close()
    flash('Invalid Credentials')
    return redirect(url_for('index'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            hashed_pw = generate_password_hash(request.form['password'], method='pbkdf2:sha256')
            conn = get_db_connection()
            today = date.today().isoformat()
            conn.execute(
                'INSERT INTO users (name, email, password, streak, last_login) VALUES (?, ?, ?, ?, ?)',
                (request.form['name'], request.form['email'], hashed_pw, 1, today),
            )
            conn.commit()
            conn.close()
            return redirect(url_for('index'))
        except Exception:
            flash('Email taken')
    return render_template('register.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))
