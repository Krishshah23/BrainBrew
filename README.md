BrainBrew 🚀

Production-deployed Full-Stack Quiz & Multiplayer Battle Platform

🔗 Live: https://kreesh.pythonanywhere.com/

🔗 GitHub: https://github.com/Krishshah23/BrainBrew

📊 Impact

260+ real users

1000+ quiz attempts within 48 hours

Live multiplayer battle sessions

Adaptive learning & mastery tracking

Built and tested in a real-user environment — not just a classroom submission.

🧠 What Makes This Project Strong

Session-based authentication & role-based access control

Adaptive learning engine (weak-area detection + retry sessions)

Real-time multiplayer battle logic using in-memory state

Persistent relational database schema with foreign key integrity

JSON-based APIs powering dynamic frontend updates

This section tells recruiters: “This guy understands backend systems.”

⚙️ Core Features
🔐 Authentication

Secure password hashing (Werkzeug)

Role-based authorization (Admin / Student)

Daily login streak system

📝 Dynamic Quiz Engine

<img width="1063" height="470" alt="image" src="https://github.com/user-attachments/assets/11b80344-9366-480d-bcbf-6f04fbc3315e" />


Randomized question generation

Difficulty & category filtering

Timer-based quizzes

Auto scoring + detailed JSON result storage

⚔️ Multiplayer Battle Mode 

<img width="1913" height="978" alt="image" src="https://github.com/user-attachments/assets/959ad172-b1cc-4c79-88d5-05162a09067e" />


6-character room code system

Host-controlled match start

Score + completion-time-based winner logic

In-memory state management + persistent storage

📊 Analytics & Dashboard

<img width="1918" height="977" alt="image" src="https://github.com/user-attachments/assets/dd0b78e2-ab03-46a6-832b-6822b2c06587" />


 
Category-wise mastery tracking

XP-based leaderboard

Skill progression reports

Achievement badges

🛠 Admin Panel

<img width="1914" height="977" alt="image" src="https://github.com/user-attachments/assets/d7754cfd-3393-423e-8d48-553556dc3165" />



Full CRUD for questions

Bulk CSV upload

Reporting & moderation tools

🗄 Database Design

Relational SQLite schema including:

users

questions

results

flashcard_progress

bookmarks

challenges

Foreign key constraints ensure structured and consistent data.

🛠 Tech Stack

Backend: Python, Flask, SQLite
Frontend: HTML, CSS, JavaScript
Deployment: PythonAnywhere
Other: JSON APIs, FPDF

▶️ Run Locally
git clone https://github.com/Krishshah23/BrainBrew.git
cd BrainBrew
pip install -r requirements.txt
python app.py
