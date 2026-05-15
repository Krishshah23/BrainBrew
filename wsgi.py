import os

from app import app, init_db


os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
if not os.path.exists(os.environ.get('QUIZ_DB_PATH', 'quiz.db')):
    init_db()
