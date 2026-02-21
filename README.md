BrainBrew – Full Stack Quiz & Battle Platform (3rd Semester Project)

BrainBrew is a full-stack quiz and competitive learning platform built using Flask, SQLite, HTML, CSS, and JavaScript as part of my 3rd semester college project.

Unlike a typical academic project, this system was deployed live and tested with real users.

🔗 Live Deployment: Hosted on PythonAnywhere
🔗 GitHub Repository: https://github.com/Krishshah23/BrainBrew

🚀 Project Highlights

260+ real users

1000+ quiz attempts within 48 hours of launch

Live multiplayer battle sessions

Adaptive learning system

Admin command center

This project helped me move beyond theoretical implementation into handling real-world usage scenarios.

🧠 System Architecture

The system follows a structured Flask backend architecture:

User → Flask Routes → SQLite Database
Battle Mode → In-memory Dictionary + Persistent Challenge Storage

Core Backend Concepts Used:

Session-based authentication

Role-based access control (Admin / Student)

Relational database schema

JSON-based API responses for dynamic UI updates

In-memory state management for multiplayer battles

⚙️ Key Features
🔐 Authentication System

Secure password hashing (Werkzeug)

Session management

Daily login streak tracking

Role-based authorization

📝 Dynamic Quiz Engine

Category & difficulty filtering

Randomized question selection

Timer-based quizzes

Automatic scoring logic

JSON-based detailed result storage

Per-category performance analytics

🔁 Repair Station (Mistake Mode)

Detects previously incorrect questions

Dynamically builds retry sessions

Helps improve weak areas

📚 Flashcard Learning System

Smart Mode (blend of new + review)

Tutor Mode (prioritizes weak questions)

Mastery tracking stored per user

⚔️ Multiplayer Battle Mode

6-character room code generation

Live lobby system

Host-controlled battle start

Score + completion time-based winner logic

Real-time in-memory state tracking

Persistent question set storage for rejoin handling

🏆 Leaderboard System

XP-based ranking

Aggregated performance tracking

Streak integration

📊 Performance Dashboard

Category-wise mastery tracking

Skill trajectory graph

Historical quiz reports

Achievement badges

🛠 Admin Command Center

Question CRUD operations

Bulk CSV upload with flexible header detection

Question reporting & moderation

User management

Mastery reset tools

📄 Certificate Generation

Dynamic PDF certificate generation

Unlock condition (75%+ score)

🗄 Database Schema

The platform uses a relational SQLite schema including:

users

questions

results

flashcard_progress

bookmarks

reports

challenges

Foreign key relationships ensure structured data consistency.

🛠 Tech Stack

Backend:

Python

Flask

SQLite

Frontend:

HTML

CSS

JavaScript

Other:

FPDF (PDF generation)
JSON APIs

PythonAnywhere (Deployment)

💡 What I Learned

Designing relational databases for real-world usage

Managing application state using sessions and in-memory structures

Implementing adaptive learning logic

Handling real users in a deployed environment

Structuring backend routes in Flask

▶️ How to Run Locally
git clone https://github.com/Krishshah23/BrainBrew.git
cd BrainBrew
pip install -r requirements.txt
python app.py
📌 Live Version

The project is hosted and accessible via https://kreesh.pythonanywhere.com/
