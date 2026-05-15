import importlib
import json
from urllib.parse import urlparse


def _set_logged_in_session(client, user_id, role='student', name='Tester'):
    token = 'test-csrf-token'
    with client.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['role'] = role
        sess['name'] = name
        sess['profile_pic'] = 'default.png'
        sess['_csrf_token'] = token
    return token


def _seed_user(conn, name, email, role='student', xp_total=0):
    conn.execute(
        'INSERT INTO users (name, email, password, role, streak, last_login, xp_total) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (name, email, 'hashed', role, 0, None, xp_total),
    )
    conn.commit()
    return conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()['id']


def _bootstrap_app(monkeypatch, tmp_path):
    monkeypatch.setenv('QUIZ_DB_PATH', str(tmp_path / 'test_quiz.db'))
    monkeypatch.setenv('SECRET_KEY', 'test-secret')
    import app as app_module
    importlib.reload(app_module)
    app_module.init_db()
    app_module.app.config['TESTING'] = True
    return app_module


def test_retry_mistakes_redirects_when_empty(monkeypatch, tmp_path):
    app_module = _bootstrap_app(monkeypatch, tmp_path)
    conn = app_module.get_db_connection()
    user_id = _seed_user(conn, 'Student A', 'a@example.com')
    conn.close()

    with app_module.app.test_client() as client:
        _set_logged_in_session(client, user_id)
        resp = client.get('/retry_mistakes')
        assert resp.status_code == 302
        assert '/repair_station' in resp.headers['Location']


def test_submit_quiz_updates_xp_and_mistakes(monkeypatch, tmp_path):
    app_module = _bootstrap_app(monkeypatch, tmp_path)
    conn = app_module.get_db_connection()
    user_id = _seed_user(conn, 'Student B', 'b@example.com')
    conn.execute(
        '''
        INSERT INTO questions (question_text, option_a, option_b, option_c, option_d, correct_option, category, difficulty, explanation)
        VALUES
        ('Q1', 'A1', 'B1', 'C1', 'D1', 'A', 'Math', 'Easy', 'exp'),
        ('Q2', 'A2', 'B2', 'C2', 'D2', 'A', 'Science', 'Easy', 'exp')
        '''
    )
    conn.commit()
    ids = conn.execute('SELECT id FROM questions ORDER BY id').fetchall()
    q1 = ids[0]['id']
    q2 = ids[1]['id']
    conn.close()

    with app_module.app.test_client() as client:
        token = _set_logged_in_session(client, user_id)
        resp = client.post('/submit_quiz', data={
            '_csrf_token': token,
            str(q1): 'B',
            str(q2): 'A',
        })
        assert resp.status_code == 302
        assert '/history/' in resp.headers['Location']

    conn = app_module.get_db_connection()
    xp_total = conn.execute('SELECT xp_total FROM users WHERE id = ?', (user_id,)).fetchone()['xp_total']
    pending_mistakes = conn.execute(
        'SELECT COUNT(*) AS c FROM mistakes WHERE user_id = ? AND fixed_at IS NULL',
        (user_id,),
    ).fetchone()['c']
    conn.close()
    assert xp_total == 1
    assert pending_mistakes == 1


def test_submit_quiz_redirect_targets_result_row(monkeypatch, tmp_path):
    app_module = _bootstrap_app(monkeypatch, tmp_path)
    conn = app_module.get_db_connection()
    user_id = _seed_user(conn, 'Student B2', 'b2@example.com')
    conn.execute(
        '''
        INSERT INTO questions (question_text, option_a, option_b, option_c, option_d, correct_option, category, difficulty, explanation)
        VALUES
        ('Q1', 'A1', 'B1', 'C1', 'D1', 'A', 'Math', 'Easy', 'exp')
        '''
    )
    conn.commit()
    q1 = conn.execute('SELECT id FROM questions ORDER BY id').fetchone()['id']
    conn.close()

    with app_module.app.test_client() as client:
        token = _set_logged_in_session(client, user_id)
        resp = client.post('/submit_quiz', data={
            '_csrf_token': token,
            str(q1): 'A',
        })
        assert resp.status_code == 302
        history_path = urlparse(resp.headers['Location']).path
        assert history_path.startswith('/history/')
        result_id = int(history_path.rsplit('/', 1)[-1])

    conn = app_module.get_db_connection()
    result_row = conn.execute(
        'SELECT id, user_id FROM results WHERE id = ?',
        (result_id,),
    ).fetchone()
    conn.close()
    assert result_row is not None
    assert result_row['user_id'] == user_id


def test_reset_mastery_preserves_results_and_xp(monkeypatch, tmp_path):
    app_module = _bootstrap_app(monkeypatch, tmp_path)
    conn = app_module.get_db_connection()
    admin_id = conn.execute('SELECT id FROM users WHERE role = "admin"').fetchone()['id']
    user_id = _seed_user(conn, 'Student C', 'c@example.com', xp_total=10)
    conn.execute(
        'INSERT INTO results (user_id, score, total_questions, details) VALUES (?, ?, ?, ?)',
        (user_id, 10, 10, json.dumps({'review': [{'question_id': 1, 'is_correct': False}]})),
    )
    conn.execute(
        'INSERT INTO flashcard_progress (user_id, question_id, status) VALUES (?, ?, ?)',
        (user_id, 1, 'again'),
    )
    conn.execute(
        'INSERT INTO mistakes (user_id, question_id, fixed_at) VALUES (?, ?, NULL)',
        (user_id, 1),
    )
    conn.commit()
    conn.close()

    with app_module.app.test_client() as client:
        token = _set_logged_in_session(client, admin_id, role='admin', name='Admin')
        resp = client.post('/admin/reset_mastery', data={'_csrf_token': token})
        assert resp.status_code == 302
        assert '/admin' in resp.headers['Location']

    conn = app_module.get_db_connection()
    details = conn.execute('SELECT details FROM results WHERE user_id = ?', (user_id,)).fetchone()['details']
    xp = conn.execute('SELECT xp_total FROM users WHERE id = ?', (user_id,)).fetchone()['xp_total']
    flashcards = conn.execute('SELECT COUNT(*) AS c FROM flashcard_progress WHERE user_id = ?', (user_id,)).fetchone()['c']
    mistakes = conn.execute('SELECT COUNT(*) AS c FROM mistakes WHERE user_id = ?', (user_id,)).fetchone()['c']
    conn.close()
    assert details is None
    assert xp == 10
    assert flashcards == 0
    assert mistakes == 0


def test_csrf_protection_blocks_missing_token(monkeypatch, tmp_path):
    app_module = _bootstrap_app(monkeypatch, tmp_path)
    conn = app_module.get_db_connection()
    user_id = _seed_user(conn, 'Student D', 'd@example.com')
    conn.close()

    with app_module.app.test_client() as client:
        _set_logged_in_session(client, user_id)
        resp = client.post('/update_name', data={'name': 'New Name'})
        assert resp.status_code == 400


def test_view_result_handles_missing_details(monkeypatch, tmp_path):
    app_module = _bootstrap_app(monkeypatch, tmp_path)
    conn = app_module.get_db_connection()
    user_id = _seed_user(conn, 'Student E', 'e@example.com')
    conn.execute(
        'INSERT INTO results (user_id, score, total_questions, details) VALUES (?, ?, ?, ?)',
        (user_id, 6, 10, None),
    )
    conn.commit()
    result_id = conn.execute('SELECT id FROM results WHERE user_id = ? ORDER BY id DESC', (user_id,)).fetchone()['id']
    conn.close()

    with app_module.app.test_client() as client:
        _set_logged_in_session(client, user_id)
        resp = client.get(f'/history/{result_id}')
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'Question-level breakdown is unavailable for this older result.' in body


def test_get_count_supports_multiple_categories(monkeypatch, tmp_path):
    app_module = _bootstrap_app(monkeypatch, tmp_path)
    conn = app_module.get_db_connection()
    user_id = _seed_user(conn, 'Student F', 'f@example.com')
    conn.execute(
        '''
        INSERT INTO questions (question_text, option_a, option_b, option_c, option_d, correct_option, category, difficulty, explanation)
        VALUES
        ('Q1', 'A1', 'B1', 'C1', 'D1', 'A', 'A', 'Easy', 'exp'),
        ('Q2', 'A2', 'B2', 'C2', 'D2', 'A', 'B', 'Easy', 'exp'),
        ('Q3', 'A3', 'B3', 'C3', 'D3', 'A', 'C', 'Hard', 'exp')
        '''
    )
    conn.commit()
    conn.close()

    with app_module.app.test_client() as client:
        _set_logged_in_session(client, user_id)
        resp = client.get('/api/get_count?categories=B&categories=C&difficulty=All')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] == 2
