import io
import json
import os
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, send_file, session, url_for
from fpdf import FPDF
from werkzeug.utils import secure_filename

from database import get_db_connection

user_bp = Blueprint('user', __name__)


@user_bp.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))

    conn = get_db_connection()
    user_id = session['user_id']

    total_score = conn.execute('SELECT COALESCE(xp_total, 0) FROM users WHERE id = ?', (user_id,)).fetchone()[0]
    quizzes_taken = conn.execute('SELECT COUNT(*) FROM results WHERE user_id = ?', (user_id,)).fetchone()[0]
    categories = conn.execute(
        '''
        SELECT category, COUNT(*) AS question_count
        FROM questions
        GROUP BY category
        ORDER BY category COLLATE NOCASE ASC
        '''
    ).fetchall()

    recent_results = conn.execute(
        '''
        SELECT id, score, total_questions, timestamp as date, details
        FROM results
        WHERE user_id = ?
        ORDER BY timestamp DESC LIMIT 5
    ''',
        (user_id,),
    ).fetchall()

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
            except Exception:
                pass
    for cat in category_totals:
        if category_totals[cat] > 0:
            unit_stats[cat] = int((category_correct[cat] / category_totals[cat]) * 100)
    conn.close()

    return render_template(
        'dashboard.html',
        total_score=total_score,
        quizzes_taken=quizzes_taken,
        categories=categories,
        recent_results=recent_results,
        unit_stats=unit_stats,
    )


@user_bp.route('/leaderboard')
def leaderboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    conn = get_db_connection()
    leaders = conn.execute(
        '''
        SELECT u.name, u.email as username, u.profile_pic, u.streak, COALESCE(u.xp_total, 0) as total_xp
        FROM users u
        WHERE u.role != "admin"
        ORDER BY total_xp DESC, u.name ASC
        LIMIT 50
    '''
    ).fetchall()
    conn.close()
    return render_template('leaderboard.html', leaders=leaders)


@user_bp.route('/update_name', methods=['POST'])
def update_name():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    new_name = request.form.get('name')
    if new_name:
        conn = get_db_connection()
        conn.execute('UPDATE users SET name = ? WHERE id = ?', (new_name, session['user_id']))
        conn.commit()
        conn.close()
        session['name'] = new_name
        flash('Name updated successfully!')
    return redirect(url_for('profile'))


@user_bp.route('/upload_profile_pic', methods=['POST'])
def upload_profile_pic():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    if 'file' not in request.files:
        flash('No file part')
        return redirect(url_for('profile'))

    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('profile'))

    if file:
        filename = secure_filename(file.filename)
        unique_name = f"user_{session['user_id']}_{filename}"
        save_folder = os.path.join(os.getcwd(), 'static', 'uploads')
        if not os.path.exists(save_folder):
            os.makedirs(save_folder)

        full_path = os.path.join(save_folder, unique_name)
        file.save(full_path)

        conn = get_db_connection()
        conn.execute('UPDATE users SET profile_pic = ? WHERE id = ?', (unique_name, session['user_id']))
        conn.commit()
        conn.close()

        session['profile_pic'] = unique_name
        flash('Profile Picture Updated!')

    return redirect(url_for('profile'))


@user_bp.route('/history/<int:result_id>')
def view_result(result_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    conn = get_db_connection()
    result = conn.execute(
        'SELECT * FROM results WHERE id = ? AND user_id = ?',
        (result_id, session['user_id']),
    ).fetchone()
    conn.close()
    if not result:
        return "Result not found.", 404

    review = []
    feedback = 'Quiz Completed'
    details_missing = True

    if result['details']:
        try:
            data = json.loads(result['details'])
            if isinstance(data, dict):
                review = data.get('review') if isinstance(data.get('review'), list) else []
                feedback = data.get('feedback', feedback)
                details_missing = False if review else True
        except (json.JSONDecodeError, TypeError):
            details_missing = True

    percentage = 0
    if result['total_questions'] > 0:
        percentage = (result['score'] / result['total_questions']) * 100

    if details_missing:
        feedback = (
            "Detailed question-by-question analysis is not available for this attempt. "
            "The score summary is still shown below."
        )

    return render_template(
        'result_history.html',
        score=result['score'],
        total=result['total_questions'],
        review=review,
        feedback=feedback,
        percentage=percentage,
        result_id=result_id,
        details_missing=details_missing,
    )


@user_bp.route('/certificate/<int:result_id>')
def download_certificate(result_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    conn = get_db_connection()
    result = conn.execute('SELECT * FROM results WHERE id = ?', (result_id,)).fetchone()
    conn.close()
    if not result:
        return "Result not found", 404

    percentage = (result['score'] / result['total_questions']) * 100 if result['total_questions'] > 0 else 0

    pdf = FPDF('L', 'mm', 'A4')
    pdf.add_page()
    pdf.set_auto_page_break(auto=False)
    pdf.set_fill_color(245, 240, 255)
    pdf.rect(0, 0, 297, 210, 'F')
    pdf.set_draw_color(106, 17, 203)
    pdf.set_line_width(3)
    pdf.rect(10, 10, 277, 190)
    pdf.set_font("Arial", "B", 36)
    pdf.set_text_color(106, 17, 203)
    pdf.cell(0, 40, "CERTIFICATE OF ACHIEVEMENT", ln=1, align='C')
    pdf.set_font("Arial", "", 18)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 10, "This is proudly presented to", ln=1, align='C')
    pdf.set_font("Arial", "B", 30)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 20, session['name'], ln=1, align='C')
    pdf.set_font("Arial", "", 14)
    pdf.multi_cell(
        0,
        8,
        f"For successfully demonstrating mastery in the BrainBrew Assessment,\nachieving an outstanding score of {percentage:.1f}% on {date.today().strftime('%B %d, %Y')}.",
        align='C',
    )
    pdf.set_font("Arial", "I", 12)
    pdf.set_text_color(100, 100, 100)
    pdf.set_y(170)
    pdf.cell(0, 10, "BrainBrew Learning Platform", ln=1, align='C')
    pdf.set_draw_color(0, 0, 0)
    pdf.line(40, 165, 100, 165)
    pdf.text(55, 172, "Founder & CEO")
    response = io.BytesIO(pdf.output())
    return send_file(
        response,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'BrainBrew_Certificate_{session["name"]}.pdf',
    )


@user_bp.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    conn = get_db_connection()
    history = conn.execute('SELECT * FROM results WHERE user_id = ? ORDER BY timestamp DESC', (session['user_id'],)).fetchall()
    conn.close()
    badges = []
    total_quizzes = len(history)
    high_score = max([r['score'] for r in history]) if history else 0
    if total_quizzes >= 1:
        badges.append({'name': 'Rookie', 'icon': 'fa-seedling', 'color': 'success'})
    if total_quizzes >= 10:
        badges.append({'name': 'Veteran', 'icon': 'fa-shield-alt', 'color': 'primary'})
    if high_score >= 10:
        badges.append({'name': 'Genius', 'icon': 'fa-brain', 'color': 'warning'})
    # Table is newest-first, but chart should remain chronological.
    chart_rows = list(reversed(history))
    dates = [row['timestamp'][:10] for row in chart_rows]
    scores = [row['score'] for row in chart_rows]
    return render_template('profile.html', history=history, dates=json.dumps(dates), scores=json.dumps(scores), badges=badges)
