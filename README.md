# 🧠 BrainBrew: Gamified Quiz Platform

Welcome to **BrainBrew**, a modern, gamified educational platform built with Python (Flask) and SQLite. This project is designed to make learning fun through competitive "Battle Modes," spaced-repetition flashcards, and achievement-based rewards.

---

## 🚀 Key Features

- **Gamified Quiz Engine**: Dynamic timers, lifelines (if enabled), and instant feedback.
- **Battle Mode (Multiplayer)**: Real-time competitive lobbies with 6-character room codes.
- **Flashcard Study**: Anki-style spaced repetition (Again, Hard, Good, Mastered).
- **Admin Dashboard**: Bulk CSV uploads, question management, and user reporting.
- **Achievement System**: Earn badges (Rookie, Veteran, Genius) and download PDF certificates for high scores.
- **Modern UI**: Dark-mode "Glassmorphism" theme using Bootstrap 5 and custom CSS.

---

## 🛠️ Technical Stack

- **Backend**: Python 3, Flask (Web Framework)
- **Database**: SQLite (Native relational storage)
- **Frontend**: HTML5, Jinja2 Templates, Bootstrap 5, Vanilla JavaScript
- **Security**: Password hashing via `werkzeug.security`
- **Utilities**: `fpdf` (PDF Generation), `csv` (Bulk Uploads), `json` (Result Parsing)

---

## 📂 Project Structure (For Beginners)

- `app.py`: The heart of the application. Handles all routes (pages) and business logic.
- `database.py`: Contains all SQL queries and database connection logic.
- `templates/`: Contains HTML files using Jinja2 syntax for dynamic data injection.
- `static/`: Stores CSS, JavaScript, and user-uploaded files (like profile pictures).
- `quiz.db`: The SQLite database file where all users and questions are stored.
- `requirements.txt`: List of Python libraries needed to run the project.

---

## 🚦 Getting Started

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Initialize Database**:
    The app will automatically create `quiz.db` and the necessary tables on its first run via `database.py`.

3.  **Run the App**:
    ```bash
    python app.py
    ```
    Visit `http://127.0.0.1:5000` in your browser.

---

## 🧑‍💻 Beginner's Guide to the Code

Each file in this project has been heavily commented to help you understand how it works:
- **Routes**: Look in `app.py` for `@app.route` decorators—these define the URLs (like `/login` or `/quiz`).
- **Logic**: Search for "Key Features for Beginners" in the HTML files to understand the UI logic.
- **Data**: Check `database.py` to see how we talk to SQLite using standard SQL commands.

---

## 🏆 Development History
This project was built over 30 days, evolving from a simple quiz app to a full multiplayer platform with streak tracking, battle lobbies, and automated certificate generation.

**Happy Learning!** 🚀
