import csv
import io
import json
import os

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from database import get_db_connection
from services import log_audit

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/admin', methods=['GET', 'POST'])
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    conn = get_db_connection()

    if request.method == 'POST':
        image = request.files.get('image')
        img_filename = None

        if image and image.filename != '':
            img_filename = secure_filename(image.filename)
            save_path = os.path.join(current_app.root_path, 'static', 'uploads', img_filename)
            image.save(save_path)

        conn.execute(
            '''INSERT INTO questions
            (question_text, option_a, option_b, option_c, option_d, correct_option, category, difficulty, image_file, explanation)
            VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (
                request.form['question'],
                request.form['option_a'],
                request.form['option_b'],
                request.form['option_c'],
                request.form['option_d'],
                request.form['correct'],
                request.form['category'],
                request.form['difficulty'],
                img_filename,
                request.form.get('explanation', 'No explanation provided.'),
            ),
        )
        conn.commit()
        flash('Question Added!')

    total_users = conn.execute('SELECT COUNT(*) FROM users WHERE role != "admin"').fetchone()[0]
    total_quizzes = conn.execute('SELECT COUNT(*) FROM results').fetchone()[0]
    avg_score_data = conn.execute('SELECT AVG(CAST(score AS FLOAT) / total_questions) FROM results').fetchone()[0]
    avg_score = round(avg_score_data * 100, 1) if avg_score_data else 0

    reports = conn.execute(
        '''
        SELECT r.id, q.question_text, u.name as reporter, r.reason, r.timestamp, q.id as qid,
               q.option_a, q.option_b, q.option_c, q.option_d, q.correct_option, q.category, q.difficulty, q.explanation
        FROM reports r
        JOIN questions q ON r.question_id = q.id
        JOIN users u ON r.user_id = u.id
        ORDER BY r.timestamp DESC
    '''
    ).fetchall()

    activity = conn.execute(
        'SELECT u.name, r.score, r.total_questions, r.timestamp FROM results r JOIN users u ON r.user_id = u.id ORDER BY r.timestamp DESC LIMIT 5'
    ).fetchall()
    all_questions = conn.execute('SELECT * FROM questions').fetchall()
    all_users = conn.execute('SELECT * FROM users WHERE role != "admin"').fetchall()
    conn.close()
    return render_template(
        'admin_dashboard.html',
        questions=all_questions,
        stats={'users': total_users, 'quizzes': total_quizzes, 'avg': avg_score},
        activity=activity,
        reports=reports,
        users=all_users,
    )


@admin_bp.route('/edit_question/<int:qid>', methods=['POST'])
def edit_question(qid):
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    conn = get_db_connection()
    conn.execute(
        '''UPDATE questions SET
                    question_text=?, option_a=?, option_b=?, option_c=?, option_d=?,
                    correct_option=?, category=?, difficulty=?, explanation=?
                    WHERE id=?''',
        (
            request.form['question'],
            request.form['option_a'],
            request.form['option_b'],
            request.form['option_c'],
            request.form['option_d'],
            request.form['correct'],
            request.form['category'],
            request.form['difficulty'],
            request.form.get('explanation', ''),
            qid,
        ),
    )

    if request.form.get('report_id'):
        conn.execute('DELETE FROM reports WHERE id = ?', (request.form['report_id'],))

    conn.commit()
    conn.close()
    flash('Question Updated & Report Resolved!')
    return redirect(url_for('admin_dashboard'))


@admin_bp.route('/delete_report/<int:rid>', methods=['POST'])
def delete_report(rid):
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    conn = get_db_connection()
    conn.execute('DELETE FROM reports WHERE id = ?', (rid,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))


@admin_bp.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    log_audit(conn, session.get('user_id'), 'admin.delete_user', json.dumps({'target_user_id': user_id}))
    conn.commit()
    conn.close()
    flash('User deleted successfully.')
    return redirect(url_for('admin_dashboard'))


@admin_bp.route('/admin/reset_mastery', methods=['POST'])
def reset_mastery():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    conn = get_db_connection()
    conn.execute('UPDATE results SET details = NULL')
    conn.execute('DELETE FROM flashcard_progress')
    conn.execute('DELETE FROM mistakes')
    log_audit(conn, session.get('user_id'), 'admin.reset_mastery', '{"scope":"all_users"}')
    conn.commit()
    conn.close()
    flash('All user mastery/progress has been reset. XP and leaderboard scores were preserved.', 'warning')
    return redirect(url_for('admin_dashboard'))


@admin_bp.route('/upload_csv', methods=['POST'])
def upload_csv():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    file = request.files['file']
    if not file:
        return "No file"

    try:
        file_content = file.stream.read().decode("utf-8-sig")
        stream = io.StringIO(file_content, newline=None)

        try:
            dialect = csv.Sniffer().sniff(file_content[:2048])
        except Exception:
            dialect = 'excel'

        stream.seek(0)
        csv_input = csv.DictReader(stream, dialect=dialect)

        fieldnames = [f.strip().lower() for f in csv_input.fieldnames] if csv_input.fieldnames else []

        def get_col(keywords):
            for f in fieldnames:
                for k in keywords:
                    if k in f:
                        return f
            return None

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

            if not q_text or not q_text.strip():
                continue

            conn.execute(
                '''INSERT INTO questions (
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
                    clean_row.get(col_exp, 'No explanation provided.').strip(),
                ),
            )
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


@admin_bp.route('/delete_question/<int:qid>', methods=['POST'])
def delete_question(qid):
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    conn = get_db_connection()
    conn.execute('DELETE FROM questions WHERE id = ?', (qid,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))
