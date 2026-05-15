import random
import string
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from database import get_db_connection
from state import active_battles

battle_bp = Blueprint('battle', __name__)


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


@battle_bp.route('/battle/setup')
def battle_setup():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    categories = conn.execute('SELECT DISTINCT category FROM questions').fetchall()
    conn.close()
    return render_template('create_battle.html', categories=categories)


@battle_bp.route('/create_battle', methods=['GET', 'POST'])
def create_battle():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'GET':
        return redirect(url_for('battle_setup'))

    categories = _normalize_category_selection(
        request.form.getlist('categories'),
        legacy_category=request.form.get('category'),
    )
    try:
        num_questions = int(request.form.get('num_questions', 5))
        time_limit = int(request.form.get('time_limit', 180))
    except ValueError:
        num_questions = 5
        time_limit = 180

    battle_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    active_battles[battle_id] = {
        'creator': session['name'],
        'creator_id': session['user_id'],
        'category': 'All' if not categories else ', '.join(categories),
        'categories': categories,
        'num_questions': num_questions,
        'time_limit': time_limit,
        'players': {
            session['user_id']: {'score': 0, 'name': session['name'], 'avatar': session.get('profile_pic', 'default.png')}
        },
        'state': 'waiting',
        'created_at': datetime.now(),
    }
    return redirect(url_for('battle_lobby', battle_id=battle_id))


@battle_bp.route('/battle/join_manual', methods=['POST'])
def join_battle_manual():
    code = request.form.get('battle_code')
    if not code:
        flash("Please enter a valid room code!", "warning")
        return redirect(url_for('battle_setup'))
    clean_code = code.upper().replace(' ', '').strip()
    return redirect(url_for('join_battle_link', battle_id=clean_code))


@battle_bp.route('/battle/join/<battle_id>')
def join_battle_link(battle_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    battle_id = battle_id.upper()
    if battle_id not in active_battles:
        flash("Battle Invalid or Expired", "danger")
        return redirect(url_for('battle_setup'))
    battle = active_battles[battle_id]
    if session['user_id'] not in battle['players']:
        battle['players'][session['user_id']] = {
            'score': 0,
            'name': session['name'],
            'avatar': session.get('profile_pic', 'default.png'),
        }
    return redirect(url_for('battle_lobby', battle_id=battle_id))


@battle_bp.route('/battle/lobby/<battle_id>')
def battle_lobby(battle_id):
    if battle_id not in active_battles:
        flash("Battle not found or expired!", "danger")
        return redirect(url_for('battle_setup'))
    battle_data = active_battles[battle_id]
    if battle_data['state'] == 'started':
        return redirect(url_for('join_battle', code_val=battle_id))
    return render_template('battle_lobby.html', battle=battle_data, battle_id=battle_id)


@battle_bp.route('/battle/start/<battle_id>')
def start_battle_action(battle_id):
    if battle_id not in active_battles:
        return "Battle not found"
    battle_data = active_battles[battle_id]
    if battle_data['creator_id'] != session['user_id']:
        return redirect(url_for('battle_lobby', battle_id=battle_id))

    conn = get_db_connection()
    categories = battle_data.get('categories', [])
    if categories:
        placeholders = ','.join('?' for _ in categories)
        q_rows = conn.execute(
            f'SELECT id FROM questions WHERE category IN ({placeholders}) ORDER BY RANDOM() LIMIT ?',
            (*categories, battle_data['num_questions']),
        ).fetchall()
    else:
        q_rows = conn.execute(
            'SELECT id FROM questions ORDER BY RANDOM() LIMIT ?',
            (battle_data['num_questions'],),
        ).fetchall()
    q_ids_str = ",".join([str(r['id']) for r in q_rows])

    try:
        conn.execute('INSERT INTO challenges (code, creator_id, question_ids) VALUES (?, ?, ?)', (battle_id, session['user_id'], q_ids_str))
        conn.commit()
    except Exception:
        pass
    conn.close()
    battle_data['state'] = 'started'
    battle_data['start_time'] = datetime.now()
    return redirect(url_for('join_battle', code_val=battle_id))


@battle_bp.route('/battle/<code_val>')
def join_battle(code_val):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    conn = get_db_connection()
    battle = conn.execute('SELECT * FROM challenges WHERE code = ?', (code_val,)).fetchone()
    if not battle:
        return redirect(url_for('dashboard'))

    q_ids = battle['question_ids'].split(',')
    placeholders = ','.join('?' * len(q_ids))
    questions = conn.execute(f'SELECT * FROM questions WHERE id IN ({placeholders})', q_ids).fetchall()
    user_bookmarks = set()
    bm_rows = conn.execute('SELECT question_id FROM bookmarks WHERE user_id = ?', (session['user_id'],)).fetchall()
    for r in bm_rows:
        user_bookmarks.add(r['question_id'])
    conn.close()

    time_limit = active_battles.get(code_val, {}).get('time_limit', 60)
    return render_template(
        'quiz.html',
        questions=questions,
        title=f"Battle: {code_val}",
        battle_id=code_val,
        time_limit=time_limit,
        user_bookmarks=user_bookmarks,
    )


@battle_bp.route('/battle/rematch/<battle_id>')
def rematch_battle(battle_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if battle_id not in active_battles:
        return redirect(url_for('dashboard'))

    battle = active_battles[battle_id]
    if battle['creator_id'] != session['user_id']:
        flash("Only the Host can start a rematch.", "warning")
        return redirect(url_for('battle_result', battle_id=battle_id))

    conn = get_db_connection()
    conn.execute('DELETE FROM challenges WHERE code = ?', (battle_id,))
    conn.commit()
    conn.close()
    battle['state'] = 'waiting'
    for pid in battle['players']:
        player = battle['players'][pid]
        player['score'] = 0
        player['finished'] = False
        if 'review' in player:
            del player['review']
    return redirect(url_for('battle_lobby', battle_id=battle_id))


@battle_bp.route('/battle/result/<battle_id>')
def battle_result(battle_id):
    if battle_id not in active_battles:
        return redirect(url_for('dashboard'))
    battle = active_battles[battle_id]
    if battle['state'] == 'waiting':
        return redirect(url_for('battle_lobby', battle_id=battle_id))

    players = battle['players']
    all_finished = all(p.get('finished') for p in players.values())
    winner_id = None
    time_diff = None
    score_tied = False

    if all_finished:
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

    return render_template(
        'battle_result.html',
        battle=battle,
        players=players,
        all_finished=all_finished,
        winner_id=winner_id,
        current_user=session['user_id'],
        time_diff=time_diff,
        score_tied=score_tied,
        battle_id=battle_id,
    )
