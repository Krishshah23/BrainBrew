import json
from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from database import get_db_connection
from services import log_audit, update_mistakes_for_submission
from state import active_battles

quiz_bp = Blueprint('quiz', __name__)


def _normalize_category_selection(categories, legacy_category=None):
    selected = []
    for value in categories or []:
        raw = (value or '').strip()
        if raw:
            selected.append(raw)
    legacy_raw = (legacy_category or '').strip()
    if legacy_raw:
        selected.append(legacy_raw)

    deduped = []
    seen = set()
    for cat in selected:
        key = cat.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cat)

    if not deduped or any(c.lower() == 'all' for c in deduped):
        return []
    return deduped


def _apply_category_filter(query, params, categories):
    if not categories:
        return query, params
    placeholders = ','.join('?' for _ in categories)
    query += f' AND category IN ({placeholders})'
    params.extend(categories)
    return query, params


@quiz_bp.route('/toggle_bookmark', methods=['POST'])
def toggle_bookmark():
    if 'user_id' not in session:
        return jsonify({'status': 'error'})
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


@quiz_bp.route('/bookmarks')
def view_bookmarks():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    conn = get_db_connection()
    questions = conn.execute(
        '''
        SELECT q.*, b.timestamp as saved_at
        FROM questions q
        JOIN bookmarks b ON q.id = b.question_id
        WHERE b.user_id = ?
        ORDER BY b.timestamp DESC
    ''',
        (session['user_id'],),
    ).fetchall()
    conn.close()
    return render_template('bookmarks.html', questions=questions)


@quiz_bp.route('/flashcards')
def flashcard_setup():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    conn = get_db_connection()
    cats = conn.execute('SELECT DISTINCT category FROM questions').fetchall()
    mastered = conn.execute(
        'SELECT COUNT(*) FROM flashcard_progress WHERE user_id = ? AND status = "mastered"',
        (session['user_id'],),
    ).fetchone()[0]
    total_q = conn.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
    conn.close()
    return render_template('flashcard_setup.html', categories=cats, mastered=mastered, total=total_q)


@quiz_bp.route('/study_mode', methods=['POST'])
def study_mode():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    category = request.form.get('category')
    mode = (request.form.get('mode') or 'smart').strip().lower()
    try:
        session_size = int(request.form.get('session_size', 20))
    except ValueError:
        session_size = 20

    if session_size < 5:
        session_size = 5
    if session_size > 50:
        session_size = 50

    conn = get_db_connection()
    cards = []
    selected_ids = set()
    params = [session['user_id']]
    cat_filter = ""
    if category != 'All':
        cat_filter = " AND q.category = ?"
        params.append(category)

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
            (*params, session_size),
        ).fetchall()
        for r in review_rows:
            cards.append(list(r))
            selected_ids.add(r['id'])

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
            (*unseen_params, *exclude_params, remaining),
        ).fetchall()
        for r in unseen_rows:
            cards.append(list(r))

    user_bookmarks = set()
    bm_rows = conn.execute('SELECT question_id FROM bookmarks WHERE user_id = ?', (session['user_id'],)).fetchall()
    for r in bm_rows:
        user_bookmarks.add(r['question_id'])

    conn.close()
    if not cards:
        flash("You've mastered all cards in this category! 🎉")
        return redirect(url_for('flashcard_setup'))
    return render_template('study_mode.html', cards=cards, user_bookmarks=list(user_bookmarks))


@quiz_bp.route('/mark_card', methods=['POST'])
def mark_card():
    if 'user_id' not in session:
        return jsonify({'status': 'error'})
    data = request.json
    conn = get_db_connection()
    conn.execute(
        'INSERT OR REPLACE INTO flashcard_progress (user_id, question_id, status) VALUES (?, ?, ?)',
        (session['user_id'], data.get('question_id'), data.get('status')),
    )
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})


@quiz_bp.route('/tutor_mode', methods=['POST'])
def tutor_mode():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    category = request.form.get('category')
    try:
        session_size = int(request.form.get('session_size', 15))
    except ValueError:
        session_size = 15

    if session_size < 5:
        session_size = 5
    if session_size > 30:
        session_size = 30

    conn = get_db_connection()
    params = [session['user_id']]
    cat_filter = ""
    if category and category != 'All':
        cat_filter = " AND q.category = ?"
        params.append(category)

    ids = []
    seen = set()
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
        (*params, session_size),
    ).fetchall()

    for r in priority_rows:
        qid = r['id']
        if qid not in seen:
            ids.append(qid)
            seen.add(qid)

    remaining = session_size - len(ids)
    if remaining > 0:
        unseen_params = [session['user_id']]
        unseen_cat_filter = ""
        if category and category != 'All':
            unseen_cat_filter = " AND q.category = ?"
            unseen_params.append(category)
        exclude_clause = ""
        exclude_params = []
        if ids:
            placeholders = ','.join('?' for _ in ids)
            exclude_clause = f" AND q.id NOT IN ({placeholders})"
            exclude_params = list(ids)

        unseen_rows = conn.execute(
            f'''SELECT q.id
                FROM questions q
                WHERE q.id NOT IN (
                    SELECT question_id FROM flashcard_progress WHERE user_id = ?
                ){unseen_cat_filter}{exclude_clause}
                ORDER BY RANDOM()
                LIMIT ?''',
            (*unseen_params, *exclude_params, remaining),
        ).fetchall()
        for r in unseen_rows:
            qid = r['id']
            if qid not in seen:
                ids.append(qid)
                seen.add(qid)

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
            f'''SELECT q.id
                FROM questions q
                WHERE q.id NOT IN (
                    SELECT question_id FROM flashcard_progress WHERE user_id = ? AND status = "mastered"
                ){fill_cat_filter}{exclude_clause}
                ORDER BY RANDOM()
                LIMIT ?''',
            (*fill_params, *exclude_params, remaining),
        ).fetchall()
        for r in fill_rows:
            qid = r['id']
            if qid not in seen:
                ids.append(qid)
                seen.add(qid)

    questions = []
    if ids:
        placeholders = ','.join('?' for _ in ids)
        questions = conn.execute(f'SELECT * FROM questions WHERE id IN ({placeholders})', ids).fetchall()

    user_bookmarks = set()
    bm_rows = conn.execute('SELECT question_id FROM bookmarks WHERE user_id = ?', (session['user_id'],)).fetchall()
    for r in bm_rows:
        user_bookmarks.add(r['question_id'])
    conn.close()

    if not questions:
        flash("Not enough questions found for this deck.", 'warning')
        return redirect(url_for('flashcard_setup'))
    session['tutor_mode'] = True
    session['tutor_qids'] = ids
    title = "Tutor Mode"
    if category and category != 'All':
        title = f"Tutor Mode: {category}"
    return render_template('quiz.html', questions=questions, title=title, time_limit=0, user_bookmarks=user_bookmarks, tutor_mode=True)


@quiz_bp.route('/report_question/<int:qid>', methods=['POST'])
def report_question(qid):
    if 'user_id' not in session:
        return jsonify({'status': 'error'})
    reason = request.json.get('reason', "User reported error") if request.is_json else "User reported error"
    conn = get_db_connection()
    conn.execute('INSERT INTO reports (question_id, user_id, reason) VALUES (?, ?, ?)', (qid, session['user_id'], reason))
    conn.commit()
    conn.close()
    return jsonify({'status': 'reported'})


@quiz_bp.route('/api/get_count')
def get_question_count():
    categories = _normalize_category_selection(
        request.args.getlist('categories'),
        legacy_category=request.args.get('category', 'All'),
    )
    difficulty = request.args.get('difficulty', 'All')
    conn = get_db_connection()
    query = "SELECT COUNT(*) FROM questions WHERE 1=1"
    params = []
    query, params = _apply_category_filter(query, params, categories)
    if difficulty and difficulty not in ('All', 'Random'):
        query += " AND difficulty = ?"
        params.append(difficulty)
    count = conn.execute(query, params).fetchone()[0]
    conn.close()
    return jsonify({'count': count})


@quiz_bp.route('/start_quiz', methods=['POST'])
def start_quiz():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    categories = _normalize_category_selection(
        request.form.getlist('categories'),
        legacy_category=request.form.get('category'),
    )
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
    query, params = _apply_category_filter(query, params, categories)
    if difficulty and difficulty not in ('All', 'Random'):
        query += " AND difficulty = ?"
        params.append(difficulty)
    query += f" ORDER BY RANDOM() LIMIT {num_questions}"
    questions = conn.execute(query, params).fetchall()

    user_bookmarks = set()
    bm_rows = conn.execute('SELECT question_id FROM bookmarks WHERE user_id = ?', (session['user_id'],)).fetchall()
    for r in bm_rows:
        user_bookmarks.add(r['question_id'])
    conn.close()
    category_label = "All Topics" if not categories else ", ".join(categories)
    difficulty_label = "Random" if not difficulty or difficulty in ('All', 'Random') else difficulty
    return render_template(
        'quiz.html',
        questions=questions,
        title=f"{category_label} ({difficulty_label})",
        time_limit=time_limit,
        user_bookmarks=user_bookmarks,
    )


@quiz_bp.route('/api/check_question_count', methods=['POST'])
def check_question_count():
    data = request.get_json()
    categories_raw = data.get('categories', [])
    if not isinstance(categories_raw, list):
        categories_raw = [categories_raw] if categories_raw else []
    categories = _normalize_category_selection(categories_raw, legacy_category=data.get('category'))
    difficulty = data.get('difficulty')
    conn = get_db_connection()
    query = "SELECT COUNT(*) FROM questions WHERE 1=1"
    params = []
    query, params = _apply_category_filter(query, params, categories)
    if difficulty and difficulty not in ('All', 'Random'):
        query += " AND difficulty = ?"
        params.append(difficulty)
    count = conn.execute(query, params).fetchone()[0]
    conn.close()
    return jsonify({'count': count})


@quiz_bp.route('/submit_quiz', methods=['POST'])
def submit_quiz():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    conn = get_db_connection()
    user_answers = request.form.to_dict()
    user_answers.pop('_csrf_token', None)
    battle_id = user_answers.pop('battle_id', None)
    q_ids = [int(k) for k in user_answers.keys() if str(k).isdigit()]
    questions = []
    if q_ids:
        placeholders = ','.join('?' for _ in q_ids)
        questions = conn.execute(f'SELECT * FROM questions WHERE id IN ({placeholders})', q_ids).fetchall()

    score = 0
    review_data = []
    for q in questions:
        raw_user = user_answers.get(str(q['id']))
        raw_correct = q['correct_option']
        u_val = str(raw_user).strip().lower() if raw_user else ""
        c_val = str(raw_correct).strip().lower() if raw_correct else ""
        is_correct = False
        if u_val == c_val:
            is_correct = True
        elif c_val in ['a', 'b', 'c', 'd']:
            correct_option_text = q[f'option_{c_val}'].strip().lower()
            if u_val == correct_option_text:
                is_correct = True
        if is_correct:
            score += 1
        correct_text_full = q[f'option_{raw_correct.lower()}'] if raw_correct in ['A', 'B', 'C', 'D'] else raw_correct
        review_data.append(
            {
                'question_id': q['id'],
                'question': q['question_text'],
                'user_ans': raw_user,
                'correct_ans': raw_correct,
                'correct_text': correct_text_full,
                'is_correct': is_correct,
                'category': q['category'],
                'explanation': q['explanation'],
            }
        )

    tutor_qids = session.get('tutor_qids')
    if session.get('tutor_mode') and tutor_qids and set(q_ids) == set(tutor_qids):
        for item in review_data:
            qid = item.get('question_id')
            if qid is None:
                continue
            status = 'mastered' if item.get('is_correct') else 'again'
            conn.execute(
                'INSERT OR REPLACE INTO flashcard_progress (user_id, question_id, status) VALUES (?, ?, ?)',
                (session['user_id'], qid, status),
            )
        session.pop('tutor_mode', None)
        session.pop('tutor_qids', None)

    feedback_text = "Battle Mode Match" if battle_id else "Standard Practice"
    details_json = json.dumps({'review': review_data, 'feedback': feedback_text})
    result_cursor = conn.execute(
        'INSERT INTO results (user_id, score, total_questions, details) VALUES (?, ?, ?, ?)',
        (session['user_id'], score, len(questions), details_json),
    )
    result_id = result_cursor.lastrowid
    conn.execute('UPDATE users SET xp_total = COALESCE(xp_total, 0) + ? WHERE id = ?', (score, session['user_id']))
    update_mistakes_for_submission(conn, session['user_id'], review_data)
    log_audit(conn, session.get('user_id'), 'quiz.submitted', json.dumps({'score': score, 'total_questions': len(questions), 'battle_id': battle_id}))
    conn.commit()
    conn.close()

    if battle_id and battle_id in active_battles:
        if session['user_id'] in active_battles[battle_id]['players']:
            player_entry = active_battles[battle_id]['players'][session['user_id']]
            player_entry['score'] = score
            player_entry['finished'] = True
            player_entry['finish_time'] = datetime.now()
            player_entry['review'] = review_data
        return redirect(url_for('battle_result', battle_id=battle_id))
    return redirect(url_for('view_result', result_id=result_id))
