"""
BrainBrew Main Application
--------------------------
This is the heart of our Flask application. It contains:
1.  **Configuration**: Settings for the app (secret keys, upload folders).
2.  **Database Initialization**: Creates tables if they don't exist.
3.  **Routes**: The URL endpoints (like /login, /quiz) that users visit.
4.  **Logic**: The code that connects the database to the HTML templates.

Structure of this file:
- Imports
- App Configuration
- Global Storage (Battle Mode)
- Database Setup (init_db)
- Routes:
    - Authentication (Login/Register)
    - Dashboard & Profile
    - Quiz Engine (Solo Mode)
    - Battle Mode (Multiplayer)
    - Flashcards (Study Mode)
    - Admin Dashboard
    - Utilities (Helpers)
    - Error Handlers
- Main Execution
"""

# =========================================================
# 1. IMPORTS
# =========================================================
# Standard Python Libraries
import os               # For file paths and folder creation
import json             # For parsing JSON data (quiz results, AJAX)
import csv              # For reading CSV files (Bulk Upload)
import io               # For handling file streams in memory
import uuid             # For generating unique IDs (not heavily used but good to have)
import random           # For picking random questions
import string           # For generating battle codes (A-Z)
from datetime import datetime, date, timedelta # For timestamps and streak calculation

# Third-Party Libraries (Flask & Extensions)
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from werkzeug.security import generate_password_hash, check_password_hash # Secure password handling
from werkzeug.utils import secure_filename # Safe file uploads
from fpdf import FPDF   # For generating PDF certificates

# Local Imports
from database import get_db_connection # Our helper function from database.py

# =========================================================
# 2. CONFIGURATION
# =========================================================
app = Flask(__name__)

# Secret Key: Used by Flask to sign session cookies. Keep this safe in production!
app.secret_key = 'brainbrew_edu_key'

# Upload Folder: Where user profile pictures and question images are stored
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# =========================================================
# 3. GLOBAL STORAGE (IN-MEMORY)
# =========================================================
# We use a global dictionary to store active multiplayer battles.
# Since SQLite is disk-based, using RAM is faster for real-time lobby updates.
# Structure: { 'CODE123': { 'creator': '...', 'players': {...}, 'state': 'waiting' } }
active_battles = {} 

# =========================================================
# 4. DATABASE INITIALIZATION
# =========================================================
def init_db():
    """
    Checks if the database tables exist. If not, it creates them.
    This runs automatically when the app starts.
    """
    conn = get_db_connection()
    
    # 1. Users Table: Stores login info and stats
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, 
        email TEXT UNIQUE NOT NULL, 
        password TEXT NOT NULL,
        role TEXT DEFAULT 'student',        -- 'student' or 'admin'
        profile_pic TEXT DEFAULT 'default.png',
        streak INTEGER DEFAULT 0,           -- Consecutive days logged in
        last_login TEXT
    )''')
    
    # 2. Questions Table: The bank of all quiz questions
    conn.execute('''CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_text TEXT NOT NULL, 
        option_a TEXT NOT NULL, 
        option_b TEXT NOT NULL,
        option_c TEXT NOT NULL, 
        option_d TEXT NOT NULL, 
        correct_option TEXT NOT NULL,       -- Stores 'A', 'B', 'C', or 'D'
        category TEXT DEFAULT 'General', 
        difficulty TEXT DEFAULT 'Medium',
        image_file TEXT, 
        explanation TEXT
    )''')
    
    # 3. Results Table: History of quizzes taken
    conn.execute('''CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, 
        score INTEGER, 
        total_questions INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        details TEXT,                       -- JSON string containing full review (Q&A)
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    
    # 4. Challenges Table: Stores Battle Mode history (for persistence)
    conn.execute('''CREATE TABLE IF NOT EXISTS challenges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL, 
        creator_id INTEGER, 
        question_ids TEXT NOT NULL          -- Comma-separated IDs: "1,5,12,4"
    )''')
    
    # 5. Flashcard Progress: Tracks which cards are Mastered/Learning
    conn.execute('''CREATE TABLE IF NOT EXISTS flashcard_progress (
        user_id INTEGER, 
        question_id INTEGER, 
        status TEXT,                        -- 'mastered', 'learning', 'hard', 'again'
        PRIMARY KEY(user_id, question_id)
    )''')
    
    # 6. Reports Table: User-submitted error reports for questions
    conn.execute('''CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER, 
        user_id INTEGER, 
        reason TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(question_id) REFERENCES questions(id)
    )''')
    
    # 7. Bookmarks Table: Questions saved by users
    conn.execute('''CREATE TABLE IF NOT EXISTS bookmarks (
        user_id INTEGER, 
        question_id INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(user_id, question_id),
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(question_id) REFERENCES questions(id)
    )''')
    
    # Create Default Admin Account if it doesn't exist
    admin = conn.execute('SELECT * FROM users WHERE role = "admin"').fetchone()
    if not admin:
        pw = generate_password_hash('admin123', method='pbkdf2:sha256')
        conn.execute('INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)',
                     ('System Admin', 'admin@brainbrew.com', pw, 'admin'))
        print("[OK] Admin Account Created (Email: admin@brainbrew.com, Pass: admin123)")
        
    conn.commit()
    conn.close()
    print("[OK] Database Ready!")

# =========================================================
# 5. AUTHENTICATION ROUTES
# =========================================================
@app.route('/')
def index():
    """
    Landing Page.
    - If logged in -> Redirect to Dashboard.
    - If not logged in -> Show Login Page.
    """
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    """
    Handles the Login Form submission.
    """
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (request.form['email'],)).fetchone()
    
    # Validate User and Password Hash
    if user and check_password_hash(user['password'], request.form['password']):
        # --- Streak Logic ---
        today = date.today().isoformat()
        last_login = user['last_login']
        new_streak = user['streak']

        if last_login != today:
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            if last_login == yesterday:
                new_streak += 1 # Continue streak
            else:
                new_streak = 1  # Reset streak
            
            conn.execute('UPDATE users SET last_login = ?, streak = ? WHERE id = ?', (today, new_streak, user['id']))
            conn.commit()

        # Store User Info in Session (Cookies)
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

@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    Handles User Registration.
    """
    if request.method == 'POST':
        try:
            # Hash the password for security
            hashed_pw = generate_password_hash(request.form['password'], method='pbkdf2:sha256')
            conn = get_db_connection()
            today = date.today().isoformat()
            
            # Insert new user
            conn.execute('INSERT INTO users (name, email, password, streak, last_login) VALUES (?, ?, ?, ?, ?)',
                         (request.form['name'], request.form['email'], hashed_pw, 1, today))
            conn.commit()
            conn.close()
            return redirect(url_for('index'))
        except: 
            flash('Email already taken!')
    return render_template('register.html')

@app.route('/logout')
def logout():
    """
    Logs the user out by clearing the session.
    """
    session.clear()
    return redirect(url_for('index'))

# =========================================================
# 6. DASHBOARD & PROFILE
# =========================================================
@app.route('/dashboard')
def dashboard():
    """
    Student Dashboard. Shows stats, recent activity, and unit mastery.
    """
    if 'user_id' not in session: return redirect(url_for('index'))
    if session.get('role') == 'admin': return redirect(url_for('admin_dashboard'))

    conn = get_db_connection()
    user_id = session['user_id']
    
    # Fetch Basic Stats
    total_score = conn.execute('SELECT SUM(score) FROM results WHERE user_id = ?', (user_id,)).fetchone()[0]
    quizzes_taken = conn.execute('SELECT COUNT(*) FROM results WHERE user_id = ?', (user_id,)).fetchone()[0]
    categories = conn.execute('SELECT DISTINCT category FROM questions').fetchall()
    
    # Fetch Recent 5 Results
    recent_results = conn.execute('''
        SELECT id, score, total_questions, timestamp as date, details 
        FROM results 
        WHERE user_id = ? 
        ORDER BY timestamp DESC LIMIT 5
    ''', (user_id,)).fetchall()

    # --- Unit-Wise Analysis (Calculates % Mastery per Category) ---
    unit_stats = {}
    all_results = conn.execute('SELECT details FROM results WHERE user_id = ? ORDER BY timestamp DESC LIMIT 50', (user_id,)).fetchall()
    
    category_totals = {}
    category_correct = {}
    
    for row in all_results:
        if row['details']:
            try:
                data = json.loads(row['details'])
                if 'review' in data:
                    for item in data['review']:
                        cat = item.get('category', 'General')
                        if cat not in category_totals:
                            category_totals[cat] = 0
                            category_correct[cat] = 0
                        category_totals[cat] += 1
                        if item.get('is_correct'):
                            category_correct[cat] += 1
            except: pass
                        
    for cat in category_totals:
        if category_totals[cat] > 0:
            unit_stats[cat] = int((category_correct[cat] / category_totals[cat]) * 100)
    
    conn.close()

    return render_template('dashboard.html', 
                           total_score=total_score, 
                           quizzes_taken=quizzes_taken, 
                           categories=categories, 
                           recent_results=recent_results,
                           unit_stats=unit_stats)

@app.route('/profile')
def profile():
    """
    User Profile Page. Shows badges and full history graph.
    """
    if 'user_id' not in session: return redirect(url_for('index'))
    
    conn = get_db_connection()
    history = conn.execute('SELECT * FROM results WHERE user_id = ? ORDER BY timestamp ASC', (session['user_id'],)).fetchall()
    conn.close()
    
    # --- Badge Logic ---
    badges = []
    total_quizzes = len(history)
    high_score = max([r['score'] for r in history]) if history else 0
    
    if total_quizzes >= 1: badges.append({'name': 'Rookie', 'icon': 'fa-seedling', 'color': 'success'})
    if total_quizzes >= 10: badges.append({'name': 'Veteran', 'icon': 'fa-shield-alt', 'color': 'primary'})
    if high_score >= 10: badges.append({'name': 'Genius', 'icon': 'fa-brain', 'color': 'warning'})
    
    # Prepare Data for Chart.js
    dates = [row['timestamp'][:10] for row in history]
    scores = [row['score'] for row in history]
    
    return render_template('profile.html', history=history, dates=json.dumps(dates), scores=json.dumps(scores), badges=badges)

@app.route('/leaderboard')
def leaderboard():
    """
    Global Leaderboard. Ranks users by Total XP (Sum of Scores).
    """
    if 'user_id' not in session: return redirect(url_for('index'))
    conn = get_db_connection()
    leaders = conn.execute('''
        SELECT u.name, u.email as username, u.profile_pic, u.streak, SUM(r.score) as total_xp 
        FROM users u 
        JOIN results r ON u.id = r.user_id 
        GROUP BY u.id 
        ORDER BY total_xp DESC LIMIT 50
    ''').fetchall()
    conn.close()
    return render_template('leaderboard.html', leaders=leaders)

@app.route('/bookmarks')
def view_bookmarks():
    """
    Shows questions the user has bookmarked.
    """
    if 'user_id' not in session: return redirect(url_for('index'))
    conn = get_db_connection()
    questions = conn.execute('''
        SELECT q.*, b.timestamp as saved_at 
        FROM questions q 
        JOIN bookmarks b ON q.id = b.question_id 
        WHERE b.user_id = ? 
        ORDER BY b.timestamp DESC
    ''', (session['user_id'],)).fetchall()
    conn.close()
    return render_template('bookmarks.html', questions=questions)

# =========================================================
# 7. QUIZ ENGINE (SOLO MODE)
# =========================================================
@app.route('/quiz_setup')
def quiz_setup():
    """
    Page where users choose category, difficulty, and question count.
    """
    if 'user_id' not in session: return redirect(url_for('index'))
    conn = get_db_connection()
    cats = conn.execute('SELECT DISTINCT category FROM questions').fetchall()
    total = conn.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
    conn.close()
    return render_template('quiz_setup.html', max_q=total, categories=cats)

@app.route('/start_quiz', methods=['POST'])
def start_quiz():
    """
    Generates a quiz based on user selection.
    """
    if 'user_id' not in session: return redirect(url_for('index'))
    
    # Get filters from form
    category = request.form.get('category')
    difficulty = request.form.get('difficulty')
    try:
        num_questions = int(request.form.get('num_questions', 5))
        time_limit = int(request.form.get('time_limit', 300))
    except ValueError:
        num_questions = 5
        time_limit = 300

    conn = get_db_connection()
    query = "SELECT * FROM questions WHERE 1=1"
    params = []

    if category and category != 'All':
        query += " AND category = ?"
        params.append(category)

    if difficulty and difficulty != 'Random':
        query += " AND difficulty = ?"
        params.append(difficulty)

    # Randomly select questions
    query += f" ORDER BY RANDOM() LIMIT {num_questions}"
    questions = conn.execute(query, params).fetchall()
    
    # Get bookmarks to show correct icon state
    user_bookmarks = set()
    bm_rows = conn.execute('SELECT question_id FROM bookmarks WHERE user_id = ?', (session['user_id'],)).fetchall()
    for r in bm_rows: user_bookmarks.add(r['question_id'])
    
    conn.close()

    return render_template('quiz.html', 
                           questions=questions, 
                           title=f"{category} ({difficulty})", 
                           time_limit=time_limit,
                           user_bookmarks=user_bookmarks)

@app.route('/submit_quiz', methods=['POST'])
def submit_quiz():
    """
    Handles Quiz Submission. Calculates score and saves result.
    """
    if 'user_id' not in session: return redirect(url_for('index'))
    
    conn = get_db_connection()
    user_answers = request.form.to_dict()
    
    # Check if this is a battle
    battle_id = user_answers.pop('battle_id', None) 
    
    # Get Question IDs
    q_ids = [int(k) for k in user_answers.keys() if k.isdigit()]
    questions = []
    if q_ids:
        placeholders = ','.join('?' for _ in q_ids)
        questions = conn.execute(f'SELECT * FROM questions WHERE id IN ({placeholders})', q_ids).fetchall()
        
    score = 0
    review_data = []
    
    for q in questions:
        raw_user = user_answers.get(str(q['id']))
        raw_correct = q['correct_option']
        
        # Normalize for comparison
        u_val = str(raw_user).strip().lower() if raw_user else ""
        c_val = str(raw_correct).strip().lower() if raw_correct else ""
        
        is_correct = False
        if u_val == c_val: 
            is_correct = True
        elif c_val in ['a', 'b', 'c', 'd']:
            # Handle case where user sends text instead of option letter
            correct_option_text = q[f'option_{c_val}'].strip().lower()
            if u_val == correct_option_text: is_correct = True

        if is_correct: score += 1
        
        # Get full text of correct answer for display
        correct_text_full = ""
        if raw_correct in ['A', 'B', 'C', 'D']:
            correct_text_full = q[f'option_{raw_correct.lower()}']
        else:
            correct_text_full = raw_correct

        review_data.append({
            'question_id': q['id'],
            'question': q['question_text'],
            'user_ans': raw_user,
            'correct_ans': raw_correct,
            'correct_text': correct_text_full,
            'is_correct': is_correct,
            'category': q['category'],
            'explanation': q['explanation']
        })

    # Update Flashcard Progress (Spaced Repetition)
    tutor_qids = session.get('tutor_qids')
    if session.get('tutor_mode') and tutor_qids and set(q_ids) == set(tutor_qids):
        for item in review_data:
            qid = item.get('question_id')
            if qid is None: continue
            status = 'mastered' if item.get('is_correct') else 'again'
            conn.execute(
                'INSERT OR REPLACE INTO flashcard_progress (user_id, question_id, status) VALUES (?, ?, ?)',
                (session['user_id'], qid, status)
            )
        session.pop('tutor_mode', None)
        session.pop('tutor_qids', None)
        
    # Save Result to DB
    feedback_text = "Battle Mode Match" if battle_id else "Standard Practice"
    details_json = json.dumps({'review': review_data, 'feedback': feedback_text})
    conn.execute('INSERT INTO results (user_id, score, total_questions, details) VALUES (?, ?, ?, ?)', 
                 (session['user_id'], score, len(questions), details_json))
    conn.commit()
    last_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.close()

    # --- BATTLE LOGIC UPDATE ---
    if battle_id and battle_id in active_battles:
        if session['user_id'] in active_battles[battle_id]['players']:
            player_entry = active_battles[battle_id]['players'][session['user_id']]
            player_entry['score'] = score
            player_entry['finished'] = True 
            player_entry['finish_time'] = datetime.now()
            player_entry['review'] = review_data 

        return redirect(url_for('battle_result', battle_id=battle_id))

    return redirect(url_for('view_result', result_id=last_id))

@app.route('/history/<int:result_id>')
def view_result(result_id):
    """
    View details of a past quiz (Score, Review of Answers).
    """
    if 'user_id' not in session: return redirect(url_for('index'))
    conn = get_db_connection()
    result = conn.execute('SELECT * FROM results WHERE id = ?', (result_id,)).fetchone()
    conn.close()
    
    if result and result['details']:
        data = json.loads(result['details'])
        percentage = 0
        if result['total_questions'] > 0:
            percentage = (result['score'] / result['total_questions']) * 100
            
        return render_template('result_history.html', 
                               score=result['score'], 
                               total=result['total_questions'], 
                               review=data['review'], 
                               feedback=data.get('feedback', 'Quiz Completed'), 
                               percentage=percentage, 
                               result_id=result_id)
    return "Analysis unavailable."

@app.route('/retry_mistakes')
def retry_mistakes():
    """
    Creates a custom quiz using only questions the user answered incorrectly in the past.
    """
    if 'user_id' not in session: return redirect(url_for('index'))
    conn = get_db_connection()
    results = conn.execute('SELECT details FROM results WHERE user_id = ?', (session['user_id'],)).fetchall()
    
    wrong_ids = set()
    for row in results:
        if row['details']:
            data = json.loads(row['details'])
            for item in data['review']:
                if not item['is_correct']:
                    # Find question ID (sometimes we only have text, so we lookup)
                    if 'question_id' in item:
                        wrong_ids.add(item['question_id'])
                    else:
                        q = conn.execute('SELECT id FROM questions WHERE question_text = ?', (item['question'],)).fetchone()
                        if q: wrong_ids.add(q['id'])
                        
    if not wrong_ids:
        conn.close()
        flash("You have no past mistakes to fix! 🌟")
        return redirect(url_for('quiz_setup'))
        
    placeholders = ','.join('?' for _ in wrong_ids)
    # Limit to 10 questions to not overwhelm
    questions = conn.execute(f'SELECT * FROM questions WHERE id IN ({placeholders}) LIMIT 10', list(wrong_ids)).fetchall()
    
    user_bookmarks = set()
    bm_rows = conn.execute('SELECT question_id FROM bookmarks WHERE user_id = ?', (session['user_id'],)).fetchall()
    for r in bm_rows: user_bookmarks.add(r['question_id'])
    
    conn.close()
    return render_template('quiz.html', questions=questions, title="Mistake Repair Session", user_bookmarks=user_bookmarks)

# =========================================================
# 8. BATTLE MODE (MULTIPLAYER)
# =========================================================
@app.route('/battle/setup')
def battle_setup():
    """
    Shows the 'Create Battle' page.
    """
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    categories = conn.execute('SELECT DISTINCT category FROM questions').fetchall()
    conn.close()
    return render_template('create_battle.html', categories=categories)

@app.route('/create_battle', methods=['GET', 'POST'])
def create_battle():
    """
    Creates a new battle room in the global `active_battles` dictionary.
    """
    if 'user_id' not in session: return redirect(url_for('login'))
    if request.method == 'GET': return redirect(url_for('battle_setup'))

    category = request.form.get('category')
    try:
        num_questions = int(request.form.get('num_questions', 5))
        time_limit = int(request.form.get('time_limit', 180))
    except ValueError:
        num_questions = 5
        time_limit = 180
    
    # Generate 6-char random code (e.g., "XY9A2B")
    battle_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    # Initialize Battle State
    active_battles[battle_id] = {
        'creator': session['name'],
        'creator_id': session['user_id'],
        'category': category,
        'num_questions': num_questions,
        'time_limit': time_limit,
        'players': {
            session['user_id']: {
                'score': 0, 
                'name': session['name'], 
                'avatar': session.get('profile_pic', 'default.png')
            }
        },
        'state': 'waiting',
        'created_at': datetime.now()
    }
    return redirect(url_for('battle_lobby', battle_id=battle_id))

@app.route('/battle/join_manual', methods=['POST'])
def join_battle_manual():
    """
    Handles joining via the input box (entering the code manually).
    """
    code = request.form.get('battle_code')
    if not code:
        flash("Please enter a valid room code!", "warning")
        return redirect(url_for('battle_setup'))
    
    clean_code = code.upper().replace(' ', '').strip()
    return redirect(url_for('join_battle_link', battle_id=clean_code))

@app.route('/battle/join/<battle_id>')
def join_battle_link(battle_id):
    """
    Handles joining via a direct link.
    """
    if 'user_id' not in session: return redirect(url_for('login'))
    battle_id = battle_id.upper() 

    if battle_id not in active_battles:
        flash("Battle Invalid or Expired", "danger")
        return redirect(url_for('battle_setup'))
        
    battle = active_battles[battle_id]
    
    # Add player to the battle if not already there
    if session['user_id'] not in battle['players']:
        battle['players'][session['user_id']] = {
            'score': 0, 
            'name': session['name'], 
            'avatar': session.get('profile_pic', 'default.png')
        }
    return redirect(url_for('battle_lobby', battle_id=battle_id))

@app.route('/battle/lobby/<battle_id>')
def battle_lobby(battle_id):
    """
    Waiting Room. Shows who is connected.
    """
    if battle_id not in active_battles:
        flash("Battle not found or expired!", "danger")
        return redirect(url_for('battle_setup'))
    
    battle_data = active_battles[battle_id]
    
    # If battle already started, redirect to the quiz
    if battle_data['state'] == 'started':
        return redirect(url_for('join_battle', code_val=battle_id))

    return render_template('battle_lobby.html', battle=battle_data, battle_id=battle_id)

@app.route('/battle/start/<battle_id>')
def start_battle_action(battle_id):
    """
    Host clicks 'Start'. Selects questions and saves them to DB.
    """
    if battle_id not in active_battles: return "Battle not found"
    battle_data = active_battles[battle_id]
    
    if battle_data['creator_id'] != session['user_id']:
        return redirect(url_for('battle_lobby', battle_id=battle_id))

    conn = get_db_connection()
    
    # Select Questions
    if battle_data['category'] != 'All':
        q_rows = conn.execute(f"SELECT id FROM questions WHERE category='{battle_data['category']}' ORDER BY RANDOM() LIMIT {battle_data['num_questions']}").fetchall()
    else:
        q_rows = conn.execute(f"SELECT id FROM questions ORDER BY RANDOM() LIMIT {battle_data['num_questions']}").fetchall()
        
    q_ids_str = ",".join([str(r['id']) for r in q_rows])
    
    # Save 'Challenge' to DB so late joiners get the same questions
    try: 
        conn.execute('INSERT INTO challenges (code, creator_id, question_ids) VALUES (?, ?, ?)', 
                     (battle_id, session['user_id'], q_ids_str))
        conn.commit()
    except: pass # Ignore if already exists
        
    conn.close()
    
    battle_data['state'] = 'started'
    battle_data['start_time'] = datetime.now()
    return redirect(url_for('join_battle', code_val=battle_id))

@app.route('/battle/<code_val>')
def join_battle(code_val):
    """
    The actual Battle Quiz Interface.
    """
    if 'user_id' not in session: return redirect(url_for('index'))
    conn = get_db_connection()
    battle = conn.execute('SELECT * FROM challenges WHERE code = ?', (code_val,)).fetchone()
    
    if not battle: return redirect(url_for('dashboard'))
    
    q_ids = battle['question_ids'].split(',')
    placeholders = ','.join('?' * len(q_ids))
    questions = conn.execute(f'SELECT * FROM questions WHERE id IN ({placeholders})', q_ids).fetchall()
    
    user_bookmarks = set()
    bm_rows = conn.execute('SELECT question_id FROM bookmarks WHERE user_id = ?', (session['user_id'],)).fetchall()
    for r in bm_rows: user_bookmarks.add(r['question_id'])
    
    conn.close()
    
    time_limit = active_battles.get(code_val, {}).get('time_limit', 60)
    
    return render_template('quiz.html', 
                           questions=questions, 
                           title=f"Battle: {code_val}", 
                           battle_id=code_val, 
                           time_limit=time_limit,
                           user_bookmarks=user_bookmarks)

@app.route('/battle/result/<battle_id>')
def battle_result(battle_id):
    """
    Live Battle Result Board. Refreshes automatically via JS.
    """
    if battle_id not in active_battles: return redirect(url_for('dashboard'))
    battle = active_battles[battle_id]
    
    # If host triggered rematch, redirect to lobby
    if battle['state'] == 'waiting':
        return redirect(url_for('battle_lobby', battle_id=battle_id))

    players = battle['players']
    all_finished = all(p.get('finished') for p in players.values())
    
    winner_id = None
    time_diff = None
    score_tied = False

    if all_finished:
        # Sort by Score (Desc), then Time Taken (Asc)
        def get_sort_key(item):
            p_data = item[1]
            s = p_data.get('score', 0)
            t = 999999
            if p_data.get('finish_time') and battle.get('start_time'):
                t = (p_data['finish_time'] - battle['start_time']).total_seconds()
            return (-s, t)

        sorted_players = sorted(players.items(), key=get_sort_key)
        winner_id = sorted_players[0][0]

        if len(sorted_players) > 1:
            p1 = sorted_players[0][1]
            p2 = sorted_players[1][1]
            if p1['score'] == p2['score']:
                score_tied = True
            if p1.get('finish_time') and p2.get('finish_time') and battle.get('start_time'):
                t1 = (p1['finish_time'] - battle['start_time']).total_seconds()
                t2 = (p2['finish_time'] - battle['start_time']).total_seconds()
                time_diff = abs(t2 - t1)

    return render_template('battle_result.html', 
                           battle=battle, 
                           players=players, 
                           all_finished=all_finished, 
                           winner_id=winner_id, 
                           current_user=session['user_id'],
                           time_diff=time_diff,
                           score_tied=score_tied,
                           battle_id=battle_id)

@app.route('/battle/rematch/<battle_id>')
def rematch_battle(battle_id):
    """
    Allows the host to restart the battle with the same players.
    """
    if 'user_id' not in session: return redirect(url_for('login'))
    if battle_id not in active_battles: return redirect(url_for('dashboard'))
    
    battle = active_battles[battle_id]
    
    if battle['creator_id'] != session['user_id']:
        flash("Only the Host can start a rematch.", "warning")
        return redirect(url_for('battle_result', battle_id=battle_id))

    # Remove old question set from DB so we generate new ones
    conn = get_db_connection()
    conn.execute('DELETE FROM challenges WHERE code = ?', (battle_id,))
    conn.commit()
    conn.close()

    # Reset State
    battle['state'] = 'waiting' 
    for pid in battle['players']:
        player = battle['players'][pid]
        player['score'] = 0
        player['finished'] = False
        if 'review' in player: del player['review']

    return redirect(url_for('battle_lobby', battle_id=battle_id))

# =========================================================
# 9. FLASHCARDS (STUDY MODE)
# =========================================================
@app.route('/flashcards')
def flashcard_setup():
    """
    Setup page for Flashcard Study.
    """
    if 'user_id' not in session: return redirect(url_for('index'))
    conn = get_db_connection()
    cats = conn.execute('SELECT DISTINCT category FROM questions').fetchall()
    mastered = conn.execute('SELECT COUNT(*) FROM flashcard_progress WHERE user_id = ? AND status = "mastered"', (session['user_id'],)).fetchone()[0]
    total_q = conn.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
    conn.close()
    return render_template('flashcard_setup.html', categories=cats, mastered=mastered, total=total_q)

@app.route('/study_mode', methods=['POST'])
def study_mode():
    """
    Logic for Spaced Repetition Flashcards.
    Prioritizes cards marked 'again' or 'hard'.
    """
    if 'user_id' not in session: return redirect(url_for('index'))
    category = request.form.get('category')
    mode = (request.form.get('mode') or 'smart').strip().lower()
    try:
        session_size = int(request.form.get('session_size', 20))
    except ValueError: session_size = 20

    # Clamp size
    if session_size < 5: session_size = 5
    if session_size > 50: session_size = 50

    conn = get_db_connection()
    cards = []
    selected_ids = set()
    params = [session['user_id']]
    cat_filter = ""
    if category != 'All':
        cat_filter = " AND q.category = ?"
        params.append(category)

    # 1. Fetch cards that need review (status != mastered)
    if mode != 'new':
        review_rows = conn.execute(
            f'''SELECT q.*
                FROM questions q
                JOIN flashcard_progress fp ON fp.question_id = q.id
                WHERE fp.user_id = ? AND fp.status != "mastered"{cat_filter}
                ORDER BY CASE fp.status
                    WHEN "again" THEN 1
                    WHEN "hard" THEN 2
                    WHEN "learning" THEN 3
                    ELSE 4
                END, RANDOM()
                LIMIT ?''',
            (*params, session_size)
        ).fetchall()
        for r in review_rows:
            cards.append(list(r))
            selected_ids.add(r['id'])

    # 2. Fill remainder with new cards (unseen)
    remaining = session_size - len(cards)
    if remaining > 0:
        unseen_params = [session['user_id']]
        unseen_cat_filter = ""
        if category != 'All':
            unseen_cat_filter = " AND q.category = ?"
            unseen_params.append(category)

        exclude_clause = ""
        exclude_params = []
        if selected_ids:
            placeholders = ','.join('?' for _ in selected_ids)
            exclude_clause = f" AND q.id NOT IN ({placeholders})"
            exclude_params = list(selected_ids)

        unseen_rows = conn.execute(
            f'''SELECT q.*
                FROM questions q
                WHERE q.id NOT IN (
                    SELECT question_id FROM flashcard_progress WHERE user_id = ?
                ){unseen_cat_filter}{exclude_clause}
                ORDER BY RANDOM()
                LIMIT ?''',
            (*unseen_params, *exclude_params, remaining)
        ).fetchall()
        for r in unseen_rows:
            cards.append(list(r))

    user_bookmarks = set()
    bm_rows = conn.execute('SELECT question_id FROM bookmarks WHERE user_id = ?', (session['user_id'],)).fetchall()
    for r in bm_rows: user_bookmarks.add(r['question_id'])

    conn.close()
    if not cards:
        flash("You've mastered all cards in this category! 🎉")
        return redirect(url_for('flashcard_setup'))
    return render_template('study_mode.html', cards=cards, user_bookmarks=list(user_bookmarks))

@app.route('/mark_card', methods=['POST'])
def mark_card():
    """
    API: Saves the user's confidence level for a flashcard (Again/Hard/Good/Easy).
    """
    if 'user_id' not in session: return jsonify({'status': 'error'})
    data = request.json
    conn = get_db_connection()
    conn.execute('INSERT OR REPLACE INTO flashcard_progress (user_id, question_id, status) VALUES (?, ?, ?)',
                 (session['user_id'], data.get('question_id'), data.get('status')))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/tutor_mode', methods=['POST'])
def tutor_mode():
    """
    Turns weak flashcards into a Multiple Choice Quiz for reinforcement.
    """
    if 'user_id' not in session: return redirect(url_for('index'))
    category = request.form.get('category')
    try:
        session_size = int(request.form.get('session_size', 15))
    except ValueError: session_size = 15

    if session_size < 5: session_size = 5
    if session_size > 30: session_size = 30

    conn = get_db_connection()

    params = [session['user_id']]
    cat_filter = ""
    if category and category != 'All':
        cat_filter = " AND q.category = ?"
        params.append(category)

    # Prioritize cards marked 'again', 'hard', 'learning'
    priority_rows = conn.execute(
        f'''SELECT q.id
            FROM questions q
            JOIN flashcard_progress fp ON fp.question_id = q.id
            WHERE fp.user_id = ? AND fp.status IN ("again", "hard", "learning") {cat_filter}
            ORDER BY CASE fp.status
                WHEN "again" THEN 1
                WHEN "hard" THEN 2
                WHEN "learning" THEN 3
                ELSE 4
            END, RANDOM()
            LIMIT ?''',
        (*params, session_size)
    ).fetchall()

    ids = []
    seen = set()
    for r in priority_rows:
        ids.append(r['id'])
        seen.add(r['id'])

    # Fill rest with random questions if needed
    remaining = session_size - len(ids)
    if remaining > 0:
        fill_params = [session['user_id']]
        fill_cat_filter = ""
        if category and category != 'All':
            fill_cat_filter = " AND q.category = ?"
            fill_params.append(category)

        exclude_clause = ""
        exclude_params = []
        if ids:
            placeholders = ','.join('?' for _ in ids)
            exclude_clause = f" AND q.id NOT IN ({placeholders})"
            exclude_params = list(ids)

        fill_rows = conn.execute(
            f'''SELECT q.id FROM questions q WHERE q.id NOT IN (
                    SELECT question_id FROM flashcard_progress WHERE user_id = ? AND status = "mastered"
                ){fill_cat_filter}{exclude_clause} ORDER BY RANDOM() LIMIT ?''',
            (*fill_params, *exclude_params, remaining)
        ).fetchall()
        for r in fill_rows:
            if r['id'] not in seen:
                ids.append(r['id'])
                seen.add(r['id'])

    questions = []
    if ids:
        placeholders = ','.join('?' for _ in ids)
        questions = conn.execute(f'SELECT * FROM questions WHERE id IN ({placeholders})', ids).fetchall()

    user_bookmarks = set()
    bm_rows = conn.execute('SELECT question_id FROM bookmarks WHERE user_id = ?', (session['user_id'],)).fetchall()
    for r in bm_rows: user_bookmarks.add(r['question_id'])

    conn.close()

    if not questions:
        flash("Not enough questions found for this deck.", 'warning')
        return redirect(url_for('flashcard_setup'))

    session['tutor_mode'] = True
    session['tutor_qids'] = ids

    title = "Tutor Mode"
    if category and category != 'All': title = f"Tutor Mode: {category}"

    return render_template('quiz.html', questions=questions, title=title, time_limit=0, user_bookmarks=user_bookmarks, tutor_mode=True)

# =========================================================
# 10. ADMIN DASHBOARD & MANAGEMENT
# =========================================================
@app.route('/admin', methods=['GET', 'POST'])
def admin_dashboard():
    """
    Admin Control Panel. Add questions, view stats, manage reports.
    """
    if session.get('role') != 'admin': return redirect(url_for('index'))
    conn = get_db_connection()
    
    # Handle 'Add Question' Form
    if request.method == 'POST':
        image = request.files.get('image')
        img_filename = None
        
        if image and image.filename != '':
            img_filename = secure_filename(image.filename)
            save_path = os.path.join(app.root_path, 'static', 'uploads', img_filename)
            image.save(save_path)
            
        conn.execute('''INSERT INTO questions 
            (question_text, option_a, option_b, option_c, option_d, correct_option, category, difficulty, image_file, explanation) 
            VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (request.form['question'], request.form['option_a'], request.form['option_b'], 
             request.form['option_c'], request.form['option_d'], request.form['correct'],
             request.form['category'], request.form['difficulty'], img_filename, 
             request.form.get('explanation', 'No explanation provided.')))
        conn.commit()
        flash('Question Added!')

    # Gather Stats
    total_users = conn.execute('SELECT COUNT(*) FROM users WHERE role != "admin"').fetchone()[0]
    total_quizzes = conn.execute('SELECT COUNT(*) FROM results').fetchone()[0]
    avg_score_data = conn.execute('SELECT AVG(CAST(score AS FLOAT) / total_questions) FROM results').fetchone()[0]
    avg_score = round(avg_score_data * 100, 1) if avg_score_data else 0
    
    # Fetch Reports
    reports = conn.execute('''
        SELECT r.id, q.question_text, u.name as reporter, r.reason, r.timestamp, q.id as qid,
               q.option_a, q.option_b, q.option_c, q.option_d, q.correct_option, q.category, q.difficulty, q.explanation
        FROM reports r 
        JOIN questions q ON r.question_id = q.id 
        JOIN users u ON r.user_id = u.id 
        ORDER BY r.timestamp DESC
    ''').fetchall()

    activity = conn.execute('SELECT u.name, r.score, r.total_questions, r.timestamp FROM results r JOIN users u ON r.user_id = u.id ORDER BY r.timestamp DESC LIMIT 5').fetchall()
    all_questions = conn.execute('SELECT * FROM questions').fetchall()
    all_users = conn.execute('SELECT * FROM users WHERE role != "admin"').fetchall()
    conn.close()
    
    return render_template('admin_dashboard.html', questions=all_questions, stats={'users': total_users, 'quizzes': total_quizzes, 'avg': avg_score}, activity=activity, reports=reports, users=all_users)

@app.route('/upload_csv', methods=['POST'])
def upload_csv():
    """
    Parses a CSV file and adds multiple questions at once.
    """
    if session.get('role') != 'admin': return redirect(url_for('index'))
    file = request.files['file']
    if not file: return "No file"
    
    try:
        file_content = file.stream.read().decode("utf-8-sig")
        stream = io.StringIO(file_content, newline=None)
        
        # Auto-detect format (Excel vs standard CSV)
        try:
            dialect = csv.Sniffer().sniff(file_content[:2048])
        except:
            dialect = 'excel'
            
        stream.seek(0)
        csv_input = csv.DictReader(stream, dialect=dialect)
        fieldnames = [f.strip().lower() for f in csv_input.fieldnames] if csv_input.fieldnames else []
        
        # Helper to find column names
        def get_col(keywords):
            for f in fieldnames:
                for k in keywords:
                    if k in f: return f
            return None

        # Map typical headers to our columns
        col_q = get_col(['question', 'q_text', 'problem', 'stimulus'])
        col_a = get_col(['option_a', 'opt_a', 'choice_a', ' a ']) or 'a'
        col_b = get_col(['option_b', 'opt_b', 'choice_b', ' b ']) or 'b'
        col_c = get_col(['option_c', 'opt_c', 'choice_c', ' c ']) or 'c'
        col_d = get_col(['option_d', 'opt_d', 'choice_d', ' d ']) or 'd'
        col_ans = get_col(['correct', 'answer', 'ans', 'solution'])
        col_cat = get_col(['category', 'topic', 'subject'])
        col_diff = get_col(['difficulty', 'level'])
        col_exp = get_col(['explanation', 'reason', 'rationale'])

        conn = get_db_connection()
        count = 0
        
        for row in csv_input:
            clean_row = {k.strip().lower(): v for k, v in row.items() if k}
            q_text = clean_row.get(col_q) if col_q else None
            
            if not q_text or not q_text.strip(): continue

            conn.execute('''INSERT INTO questions (
                question_text, option_a, option_b, option_c, option_d, 
                correct_option, category, difficulty, explanation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
            (
                q_text.strip(),
                clean_row.get(col_a, '').strip(),
                clean_row.get(col_b, '').strip(),
                clean_row.get(col_c, '').strip(),
                clean_row.get(col_d, '').strip(),
                clean_row.get(col_ans, '').strip(),
                clean_row.get(col_cat, 'General').strip(),
                clean_row.get(col_diff, 'Medium').strip(),
                clean_row.get(col_exp, 'No explanation provided.').strip()
            ))
            count += 1
            
        conn.commit()
        conn.close()
        
        if count == 0:
            flash(f'Warning: 0 questions added. Detected headers: {fieldnames}. Check your CSV!', 'warning')
        else:
            flash(f'Success! Uploaded {count} questions.', 'success')
            
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        
    return redirect(url_for('admin_dashboard'))

@app.route('/edit_question/<int:qid>', methods=['POST'])
def edit_question(qid):
    """
    Updates an existing question.
    """
    if session.get('role') != 'admin': return redirect(url_for('index'))
    conn = get_db_connection()
    conn.execute('''UPDATE questions SET 
                    question_text=?, option_a=?, option_b=?, option_c=?, option_d=?, 
                    correct_option=?, category=?, difficulty=?, explanation=?
                    WHERE id=?''',
                 (request.form['question'], request.form['option_a'], request.form['option_b'], 
                  request.form['option_c'], request.form['option_d'], request.form['correct'],
                  request.form['category'], request.form['difficulty'], 
                  request.form.get('explanation', ''), qid))
    
    # If this came from a report, delete the report
    if request.form.get('report_id'):
        conn.execute('DELETE FROM reports WHERE id = ?', (request.form['report_id'],))
    
    conn.commit()
    conn.close()
    flash('Question Updated & Report Resolved!')
    return redirect(url_for('admin_dashboard'))

@app.route('/delete_question/<int:qid>', methods=['POST'])
def delete_question(qid):
    if session.get('role') != 'admin': return redirect(url_for('index'))
    conn = get_db_connection()
    conn.execute('DELETE FROM questions WHERE id = ?', (qid,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if session.get('role') != 'admin': return redirect(url_for('index'))
    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.execute('DELETE FROM results WHERE user_id = ?', (user_id,))
    conn.execute('DELETE FROM reports WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    flash('User deleted successfully.')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reset_mastery', methods=['POST'])
def reset_mastery():
    """
    Resets all progress for everyone (Danger Zone).
    """
    if session.get('role') != 'admin': return redirect(url_for('index'))
    conn = get_db_connection()
    conn.execute('DELETE FROM flashcard_progress')
    conn.execute('DELETE FROM results')
    conn.execute('UPDATE users SET streak = 0, last_login = NULL')
    conn.commit()
    conn.close()
    flash('All user mastery and progress has been reset!', 'warning')
    return redirect(url_for('admin_dashboard'))

@app.route('/report_question/<int:qid>', methods=['POST'])
def report_question(qid):
    """
    Allows users to report errors in questions.
    """
    if 'user_id' not in session: return jsonify({'status': 'error'})
    if request.is_json:
        reason = request.json.get('reason', "User reported error")
    else:
        reason = "User reported error"
        
    conn = get_db_connection()
    conn.execute('INSERT INTO reports (question_id, user_id, reason) VALUES (?, ?, ?)', 
                 (qid, session['user_id'], reason))
    conn.commit()
    conn.close()
    return jsonify({'status': 'reported'})

@app.route('/delete_report/<int:rid>', methods=['POST'])
def delete_report(rid):
    if session.get('role') != 'admin': return redirect(url_for('index'))
    conn = get_db_connection()
    conn.execute('DELETE FROM reports WHERE id = ?', (rid,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))

# =========================================================
# 11. UTILITIES & API
# =========================================================
@app.route('/toggle_bookmark', methods=['POST'])
def toggle_bookmark():
    if 'user_id' not in session: return jsonify({'status': 'error'})
    data = request.json
    qid = data.get('question_id')
    conn = get_db_connection()
    exists = conn.execute('SELECT 1 FROM bookmarks WHERE user_id = ? AND question_id = ?', (session['user_id'], qid)).fetchone()
    if exists:
        conn.execute('DELETE FROM bookmarks WHERE user_id = ? AND question_id = ?', (session['user_id'], qid))
        action = 'removed'
    else:
        conn.execute('INSERT INTO bookmarks (user_id, question_id) VALUES (?, ?)', (session['user_id'], qid))
        action = 'added'
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'action': action})

@app.route('/api/get_count')
def get_question_count():
    category = request.args.get('category', 'All')
    difficulty = request.args.get('difficulty', 'All')
    conn = get_db_connection()
    query = "SELECT COUNT(*) FROM questions WHERE 1=1"
    params = []
    if category != 'All': query += " AND category = ?"; params.append(category)
    if difficulty != 'All': query += " AND difficulty = ?"; params.append(difficulty)
    count = conn.execute(query, params).fetchone()[0]
    conn.close()
    return jsonify({'count': count})

@app.route('/api/check_question_count', methods=['POST'])
def check_question_count():
    data = request.get_json()
    category = data.get('category')
    difficulty = data.get('difficulty')
    conn = get_db_connection()
    query = "SELECT COUNT(*) FROM questions WHERE 1=1"
    params = []
    if category and category != 'All': query += " AND category = ?"; params.append(category)
    if difficulty and difficulty != 'Random': query += " AND difficulty = ?"; params.append(difficulty)
    count = conn.execute(query, params).fetchone()[0]
    conn.close()
    return jsonify({'count': count})

@app.route('/update_name', methods=['POST'])
def update_name():
    if 'user_id' not in session: return redirect(url_for('index'))
    new_name = request.form.get('name')
    if new_name:
        conn = get_db_connection()
        conn.execute('UPDATE users SET name = ? WHERE id = ?', (new_name, session['user_id']))
        conn.commit()
        conn.close()
        session['name'] = new_name
        flash('Name updated successfully!')
    return redirect(url_for('profile'))

@app.route('/upload_profile_pic', methods=['POST'])
def upload_profile_pic():
    if 'user_id' not in session: return redirect(url_for('index'))
    if 'file' not in request.files: return redirect(url_for('profile'))
    file = request.files['file']``
    if file.filename == '': return redirect(url_for('profile'))
    if file:
        filename = secure_filename(file.filename)
        unique_name = f"user_{session['user_id']}_{filename}"
        save_folder = os.path.join(app.root_path, 'static', 'uploads')
        if not os.path.exists(save_folder): os.makedirs(save_folder)
        file.save(os.path.join(save_folder, unique_name))
        conn = get_db_connection()
        conn.execute('UPDATE users SET profile_pic = ? WHERE id = ?', (unique_name, session['user_id']))
        conn.commit()
        conn.close()
        session['profile_pic'] = unique_name
        flash('Profile Picture Updated! 📸')
    return redirect(url_for('profile'))

@app.route('/certificate/<int:result_id>')
def download_certificate(result_id):
    """
    Generates a PDF certificate if the user scored > 75%.
    """
    if 'user_id' not in session: return redirect(url_for('index'))
    conn = get_db_connection()
    result = conn.execute('SELECT * FROM results WHERE id = ?', (result_id,)).fetchone()
    conn.close()
    
    percentage = (result['score'] / result['total_questions']) * 100
    if percentage < 75: 
        flash("Keep training! You need 75% to earn a certificate.")
        return redirect(url_for('dashboard'))

    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_fill_color(250, 248, 240) 
    pdf.rect(0, 0, 297, 210, 'F')
    pdf.set_line_width(2)
    pdf.set_draw_color(218, 165, 32)
    pdf.rect(10, 10, 277, 190)
    
    pdf.set_y(40)
    pdf.set_font("Times", 'B', 48)
    pdf.cell(0, 20, "CERTIFICATE", ln=True, align='C')
    pdf.set_font("Times", 'B', 24)
    pdf.set_text_color(218, 165, 32)
    pdf.cell(0, 15, "OF ACHIEVEMENT", ln=True, align='C')
    
    pdf.ln(10)
    pdf.set_font("Arial", 'I', 14)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 10, "This prestigious award is presented to", ln=True, align='C')
    
    pdf.ln(5)
    pdf.set_font("Times", 'B', 42)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 25, session['name'].upper(), ln=True, align='C')
    
    pdf.ln(10)
    pdf.set_font("Arial", '', 12)
    pdf.set_text_color(50, 50, 50)
    pdf.multi_cell(0, 8, f"For successfully demonstrating mastery in the BrainBrew Assessment,\nachieving an outstanding score of {percentage:.1f}% on {date.today().strftime('%B %d, %Y')}.", align='C')
    
    pdf.set_y(155)
    sig_path = os.path.join(app.config['UPLOAD_FOLDER'], 'signature.png')
    if not os.path.exists(sig_path): sig_path = os.path.join('static', 'signature.png')

    if os.path.exists(sig_path): pdf.image(sig_path, x=50, y=145, w=40)
    else:
        pdf.set_font("Times", 'I', 14)
        pdf.text(55, 160, "Authorized Signature") 
        
    pdf.line(40, 165, 100, 165)
    pdf.text(55, 172, "Founder & CEO")
    
    response = io.BytesIO(pdf.output())
    return send_file(response, mimetype='application/pdf', as_attachment=True, download_name=f'BrainBrew_Certificate_{session["name"]}.pdf')

@app.template_filter('avatar')
def avatar_filter(filename, name='User'):
    """
    Template filter to show profile picture or a generated fallback.
    Usage: {{ user.profile_pic | avatar(user.name) }}
    """
    fallback = f"https://ui-avatars.com/api/?name={name}&background=6366f1&color=fff&size=128&bold=true"
    if not filename or filename == 'None' or filename == 'default.png':
        return fallback
    try:
        file_path = os.path.join(app.root_path, 'static', 'uploads', filename)
        if not os.path.exists(file_path):
            return fallback
    except:
        return fallback
    return url_for('static', filename='uploads/' + filename)

# =========================================================
# 12. ERROR HANDLERS
# =========================================================
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template('500.html'), 500

# =========================================================
# 13. MAIN EXECUTION
# =========================================================
if __name__ == '__main__':
    # Ensure database exists
    if not os.path.exists('quiz.db'):
        init_db()
        
    # Ensure upload folder exists
    if not os.path.exists('static/uploads'):
        os.makedirs('static/uploads')
        
    # Run the app in Debug Mode (Auto-reload on changes)
    app.run(debug=True)
