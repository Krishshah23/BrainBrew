from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from database import get_db_connection
from services import get_repair_station_questions, get_repair_station_stats

repair_bp = Blueprint('repair', __name__)


@repair_bp.route('/repair_station')
def repair_station():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    category = request.args.get('category', 'All')
    conn = get_db_connection()
    pending_count, fixed_today, categories = get_repair_station_stats(conn, session['user_id'])
    preview_questions = get_repair_station_questions(conn, session['user_id'], category=category, limit=10)
    conn.close()
    return render_template(
        'repair_station.html',
        pending_count=pending_count,
        fixed_today=fixed_today,
        categories=categories,
        selected_category=category,
        preview_questions=preview_questions,
    )


@repair_bp.route('/retry_mistakes')
def retry_mistakes():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    category = request.args.get('category', 'All')
    conn = get_db_connection()
    questions = get_repair_station_questions(conn, session['user_id'], category=category, limit=10)
    if not questions:
        conn.close()
        flash("You have no past mistakes to fix yet.")
        return redirect(url_for('repair.repair_station'))

    user_bookmarks = set()
    bm_rows = conn.execute('SELECT question_id FROM bookmarks WHERE user_id = ?', (session['user_id'],)).fetchall()
    for r in bm_rows:
        user_bookmarks.add(r['question_id'])
    conn.close()
    title = "Mistake Repair Session" if category == 'All' else f"Mistake Repair: {category}"
    return render_template('quiz.html', questions=questions, title=title, user_bookmarks=user_bookmarks)
