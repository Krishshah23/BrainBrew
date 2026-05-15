"""Service layer helpers for XP, mistakes, leaderboard, and audit logging."""

from datetime import date


def log_audit(conn, actor_user_id, action, details=None):
    conn.execute(
        'INSERT INTO audit_log (actor_user_id, action, details) VALUES (?, ?, ?)',
        (actor_user_id, action, details),
    )


def sync_all_user_xp(conn):
    conn.execute(
        '''
        UPDATE users
        SET xp_total = COALESCE((
            SELECT SUM(score)
            FROM results r
            WHERE r.user_id = users.id
        ), 0)
        '''
    )


def rebuild_user_mistakes(conn, user_id):
    conn.execute('DELETE FROM mistakes WHERE user_id = ?', (user_id,))
    rows = conn.execute(
        'SELECT details FROM results WHERE user_id = ? ORDER BY timestamp ASC',
        (user_id,),
    ).fetchall()

    today = date.today().isoformat()
    for row in rows:
        raw = row['details']
        if not raw:
            continue
        try:
            import json
            data = json.loads(raw)
        except Exception:
            continue
        for item in data.get('review', []):
            qid = item.get('question_id')
            if not qid:
                continue
            if item.get('is_correct'):
                conn.execute(
                    '''
                    INSERT INTO mistakes (user_id, question_id, fixed_at, fixed_date)
                    VALUES (?, ?, CURRENT_TIMESTAMP, ?)
                    ON CONFLICT(user_id, question_id) DO UPDATE SET
                        fixed_at = CURRENT_TIMESTAMP,
                        fixed_date = excluded.fixed_date,
                        updated_at = CURRENT_TIMESTAMP
                    ''',
                    (user_id, qid, today),
                )
            else:
                conn.execute(
                    '''
                    INSERT INTO mistakes (user_id, question_id, first_seen, last_seen, fixed_at, fixed_date)
                    VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL, NULL)
                    ON CONFLICT(user_id, question_id) DO UPDATE SET
                        last_seen = CURRENT_TIMESTAMP,
                        fixed_at = NULL,
                        fixed_date = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    ''',
                    (user_id, qid),
                )


def update_mistakes_for_submission(conn, user_id, review_data):
    today = date.today().isoformat()
    for item in review_data:
        qid = item.get('question_id')
        if qid is None:
            continue
        if item.get('is_correct'):
            conn.execute(
                '''
                INSERT INTO mistakes (user_id, question_id, fixed_at, fixed_date)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(user_id, question_id) DO UPDATE SET
                    fixed_at = CURRENT_TIMESTAMP,
                    fixed_date = excluded.fixed_date,
                    updated_at = CURRENT_TIMESTAMP
                ''',
                (user_id, qid, today),
            )
        else:
            conn.execute(
                '''
                INSERT INTO mistakes (user_id, question_id, first_seen, last_seen, fixed_at, fixed_date)
                VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL, NULL)
                ON CONFLICT(user_id, question_id) DO UPDATE SET
                    last_seen = CURRENT_TIMESTAMP,
                    fixed_at = NULL,
                    fixed_date = NULL,
                    updated_at = CURRENT_TIMESTAMP
                ''',
                (user_id, qid),
            )


def get_repair_station_questions(conn, user_id, category='All', limit=10):
    params = [user_id]
    cat_clause = ''
    if category and category != 'All':
        cat_clause = ' AND q.category = ?'
        params.append(category)

    rows = conn.execute(
        f'''
        SELECT q.*
        FROM mistakes m
        JOIN questions q ON q.id = m.question_id
        WHERE m.user_id = ? AND m.fixed_at IS NULL{cat_clause}
        ORDER BY m.last_seen DESC
        LIMIT ?
        ''',
        (*params, limit),
    ).fetchall()
    return rows


def get_repair_station_stats(conn, user_id):
    pending = conn.execute(
        'SELECT COUNT(*) FROM mistakes WHERE user_id = ? AND fixed_at IS NULL',
        (user_id,),
    ).fetchone()[0]
    fixed_today = conn.execute(
        'SELECT COUNT(*) FROM mistakes WHERE user_id = ? AND fixed_date = ?',
        (user_id, date.today().isoformat()),
    ).fetchone()[0]
    categories = conn.execute(
        '''
        SELECT q.category, COUNT(*) AS cnt
        FROM mistakes m
        JOIN questions q ON q.id = m.question_id
        WHERE m.user_id = ? AND m.fixed_at IS NULL
        GROUP BY q.category
        ORDER BY cnt DESC, q.category ASC
        ''',
        (user_id,),
    ).fetchall()
    return pending, fixed_today, categories
