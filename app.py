"""
AI-Powered Library Management System
Flask + SQLite backend

Run with:  python app.py
First run automatically creates database/library.db from database/schema.sql
and seeds demo accounts + sample books.
"""

import os
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, g, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

# ----------------------------------------------------------------------
# App configuration
# ----------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = "replace-this-with-a-random-secret-key-in-production"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "library.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "database", "schema.sql")

FINE_PER_DAY = 5.0          # currency units per day overdue
LOAN_PERIOD_DAYS = 14       # default loan period
MAX_BOOKS_PER_STUDENT = 3   # active-loan cap for students

DATE_FMT = "%Y-%m-%d %H:%M:%S"


# ----------------------------------------------------------------------
# Database helpers
# ----------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create the database from schema.sql on first run and seed demo data."""
    os.makedirs(os.path.join(BASE_DIR, "database"), exist_ok=True)
    is_new = not os.path.exists(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    if is_new:
        with open(SCHEMA_PATH, "r") as f:
            conn.executescript(f.read())
        conn.commit()
        seed_demo_data(conn)

    conn.close()


def seed_demo_data(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM Users")
    if cur.fetchone()[0] > 0:
        return  # already seeded

    users = [
        ("Anita Sharma", "anita", "anita@library.edu", generate_password_hash("librarian123"), "librarian"),
        ("Rahul Verma", "rahul", "rahul@student.edu", generate_password_hash("student123"), "student"),
        ("Priya Singh", "priya", "priya@student.edu", generate_password_hash("student123"), "student"),
    ]
    cur.executemany(
        "INSERT INTO Users (full_name, username, email, password_hash, role) VALUES (?,?,?,?,?)",
        users,
    )

    books = [
        ("Introduction to Algorithms", "Thomas H. Cormen", "Computer Science", "9780262033848", "CS-005-COR", 4, 4, 18),
        ("Clean Code", "Robert C. Martin", "Computer Science", "9780132350884", "CS-006-MAR", 3, 3, 25),
        ("A Brief History of Time", "Stephen Hawking", "Science", "9780553380163", "SCI-001-HAW", 2, 2, 12),
        ("The Alchemist", "Paulo Coelho", "Fiction", "9780062315007", "FIC-002-COE", 5, 5, 30),
        ("Database System Concepts", "Abraham Silberschatz", "Computer Science", "9780073523323", "CS-007-SIL", 3, 3, 10),
        ("Sapiens: A Brief History of Humankind", "Yuval Noah Harari", "History", "9780062316097", "HIS-001-HAR", 3, 3, 22),
        ("The Pragmatic Programmer", "Andrew Hunt", "Computer Science", "9780201616224", "CS-008-HUN", 2, 2, 15),
        ("Atomic Habits", "James Clear", "Self-Help", "9780735211292", "SH-001-CLE", 4, 4, 28),
    ]
    cur.executemany(
        """INSERT INTO Books (title, author, category, isbn, call_number, total_copies, available_copies, popularity_score)
           VALUES (?,?,?,?,?,?,?,?)""",
        books,
    )
    conn.commit()


# ----------------------------------------------------------------------
# Auth helper
# ----------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


# ----------------------------------------------------------------------
# Routes: Auth
# ----------------------------------------------------------------------
@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM Users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["user_id"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]
            flash(f"Welcome back, {user['full_name']}!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ----------------------------------------------------------------------
# Routes: Dashboard
# ----------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    user_id = session["user_id"]
    role = session["role"]

    if role in ("librarian", "admin"):
        total_books = db.execute("SELECT COUNT(*) c FROM Books").fetchone()["c"]
        total_copies = db.execute("SELECT COALESCE(SUM(total_copies),0) c FROM Books").fetchone()["c"]
        available_copies = db.execute("SELECT COALESCE(SUM(available_copies),0) c FROM Books").fetchone()["c"]
        active_loans = db.execute(
            "SELECT COUNT(*) c FROM Borrowing WHERE status IN ('issued','overdue')"
        ).fetchone()["c"]
        overdue_loans = db.execute(
            """SELECT Borrowing.*, Users.full_name, Books.title FROM Borrowing
               JOIN Users ON Users.user_id = Borrowing.user_id
               JOIN Books ON Books.book_id = Borrowing.book_id
               WHERE Borrowing.status != 'returned' AND date(Borrowing.due_date) < date('now')
               ORDER BY Borrowing.due_date"""
        ).fetchall()
        recent_loans = db.execute(
            """SELECT Borrowing.*, Users.full_name, Books.title FROM Borrowing
               JOIN Users ON Users.user_id = Borrowing.user_id
               JOIN Books ON Books.book_id = Borrowing.book_id
               ORDER BY Borrowing.issue_date DESC LIMIT 8"""
        ).fetchall()
        return render_template(
            "dashboard.html", role=role, total_books=total_books, total_copies=total_copies,
            available_copies=available_copies, active_loans=active_loans,
            overdue_loans=overdue_loans, recent_loans=recent_loans,
        )
    else:
        my_loans = db.execute(
            """SELECT Borrowing.*, Books.title, Books.author FROM Borrowing
               JOIN Books ON Books.book_id = Borrowing.book_id
               WHERE Borrowing.user_id = ? AND Borrowing.status != 'returned'
               ORDER BY Borrowing.due_date""",
            (user_id,),
        ).fetchall()
        notifications = db.execute(
            """SELECT * FROM Notifications WHERE user_id = ? OR user_id IS NULL
               ORDER BY created_at DESC LIMIT 5""",
            (user_id,),
        ).fetchall()
        return render_template("dashboard.html", role=role, my_loans=my_loans, notifications=notifications)


# ----------------------------------------------------------------------
# Routes: Search
# ----------------------------------------------------------------------
@app.route("/search")
@login_required
def search():
    db = get_db()
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()

    sql = "SELECT * FROM Books WHERE 1=1"
    params = []
    if query:
        sql += " AND (title LIKE ? OR author LIKE ? OR isbn LIKE ?)"
        like = f"%{query}%"
        params += [like, like, like]
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY title"

    books = db.execute(sql, params).fetchall()
    categories = db.execute("SELECT DISTINCT category FROM Books ORDER BY category").fetchall()
    return render_template(
        "search.html", books=books, categories=categories, query=query, selected_category=category
    )


# ----------------------------------------------------------------------
# Routes: Issue
# ----------------------------------------------------------------------
@app.route("/issue", methods=["GET", "POST"])
@login_required
def issue():
    db = get_db()
    role = session["role"]

    if request.method == "POST":
        book_id = request.form.get("book_id")
        user_id = request.form.get("user_id") if role in ("librarian", "admin") else session["user_id"]

        book = db.execute("SELECT * FROM Books WHERE book_id = ?", (book_id,)).fetchone()
        if not book:
            flash("Book not found.", "danger")
            return redirect(url_for("issue"))
        if book["available_copies"] <= 0:
            flash("No copies currently available for this book.", "danger")
            return redirect(url_for("issue"))

        active_count = db.execute(
            "SELECT COUNT(*) c FROM Borrowing WHERE user_id = ? AND status != 'returned'", (user_id,)
        ).fetchone()["c"]
        if role == "student" and active_count >= MAX_BOOKS_PER_STUDENT:
            flash(f"Borrowing limit reached ({MAX_BOOKS_PER_STUDENT} books).", "warning")
            return redirect(url_for("issue"))

        issue_dt = datetime.now()
        due_dt = issue_dt + timedelta(days=LOAN_PERIOD_DAYS)

        db.execute(
            """INSERT INTO Borrowing (user_id, book_id, issue_date, due_date, status)
               VALUES (?, ?, ?, ?, 'issued')""",
            (user_id, book_id, issue_dt.strftime(DATE_FMT), due_dt.strftime(DATE_FMT)),
        )
        db.execute(
            "UPDATE Books SET available_copies = available_copies - 1, popularity_score = popularity_score + 1 WHERE book_id = ?",
            (book_id,),
        )
        db.commit()
        flash(f"\"{book['title']}\" issued successfully. Due back on {due_dt.strftime('%Y-%m-%d')}.", "success")
        return redirect(url_for("dashboard"))

    available_books = db.execute("SELECT * FROM Books WHERE available_copies > 0 ORDER BY title").fetchall()
    students = []
    if role in ("librarian", "admin"):
        students = db.execute("SELECT * FROM Users WHERE role = 'student' ORDER BY full_name").fetchall()
    return render_template("issue.html", books=available_books, students=students, role=role)


# ----------------------------------------------------------------------
# Routes: Return
# ----------------------------------------------------------------------
@app.route("/return", methods=["GET", "POST"])
@login_required
def return_book():
    db = get_db()
    role = session["role"]
    user_id = session["user_id"]

    if request.method == "POST":
        borrow_id = request.form.get("borrow_id")
        record = db.execute("SELECT * FROM Borrowing WHERE borrow_id = ?", (borrow_id,)).fetchone()

        if not record:
            flash("Borrowing record not found.", "danger")
            return redirect(url_for("return_book"))
        if role == "student" and record["user_id"] != user_id:
            flash("You can only return your own books.", "danger")
            return redirect(url_for("return_book"))

        return_dt = datetime.now()
        due_dt = datetime.strptime(record["due_date"], DATE_FMT)

        fine = 0.0
        if return_dt > due_dt:
            days_late = (return_dt - due_dt).days + 1
            fine = round(days_late * FINE_PER_DAY, 2)

        db.execute(
            "UPDATE Borrowing SET return_date = ?, status = 'returned', fine_amount = ? WHERE borrow_id = ?",
            (return_dt.strftime(DATE_FMT), fine, borrow_id),
        )
        db.execute(
            "UPDATE Books SET available_copies = available_copies + 1 WHERE book_id = ?", (record["book_id"],)
        )
        db.commit()

        if fine > 0:
            flash(f"Book returned. Overdue fine: {fine}", "warning")
        else:
            flash("Book returned successfully. No fine due.", "success")
        return redirect(url_for("dashboard"))

    if role in ("librarian", "admin"):
        active_loans = db.execute(
            """SELECT Borrowing.*, Users.full_name, Books.title FROM Borrowing
               JOIN Users ON Users.user_id = Borrowing.user_id
               JOIN Books ON Books.book_id = Borrowing.book_id
               WHERE Borrowing.status != 'returned' ORDER BY Borrowing.due_date"""
        ).fetchall()
    else:
        active_loans = db.execute(
            """SELECT Borrowing.*, Books.title FROM Borrowing
               JOIN Books ON Books.book_id = Borrowing.book_id
               WHERE Borrowing.user_id = ? AND Borrowing.status != 'returned'
               ORDER BY Borrowing.due_date""",
            (user_id,),
        ).fetchall()
    return render_template("return.html", loans=active_loans, role=role)


# ----------------------------------------------------------------------
# Routes: Recommendation Engine
# ----------------------------------------------------------------------
@app.route("/recommend")
@login_required
def recommend():
    db = get_db()
    recommendations = generate_recommendations(db, session["user_id"])
    return render_template("recommend.html", recommendations=recommendations)


def generate_recommendations(db, user_id, top_n=6):
    """
    Hybrid recommendation logic:
      1. Content-based   - weight by category/author overlap with this user's history
      2. Collaborative    - boost books borrowed by 'peers' (users who share borrowed titles)
      3. Popularity       - cold-start fallback when the user has no history yet
    """
    history = db.execute(
        """SELECT Borrowing.book_id, Books.category, Books.author FROM Borrowing
           JOIN Books ON Books.book_id = Borrowing.book_id
           WHERE Borrowing.user_id = ?""",
        (user_id,),
    ).fetchall()
    borrowed_ids = {row["book_id"] for row in history}
    all_books = db.execute("SELECT * FROM Books").fetchall()

    if not history:
        ranked = sorted(all_books, key=lambda b: b["popularity_score"], reverse=True)
        return [{**dict(b), "score": b["popularity_score"], "reason": "Popular across the library"} for b in ranked[:top_n]]

    category_count, author_count = {}, {}
    for row in history:
        category_count[row["category"]] = category_count.get(row["category"], 0) + 1
        author_count[row["author"]] = author_count.get(row["author"], 0) + 1

    placeholders = ",".join("?" * len(borrowed_ids))
    peer_rows = db.execute(
        f"SELECT DISTINCT user_id FROM Borrowing WHERE book_id IN ({placeholders}) AND user_id != ?",
        (*borrowed_ids, user_id),
    ).fetchall()
    peer_ids = [r["user_id"] for r in peer_rows]

    co_borrow_count = {}
    if peer_ids:
        peer_placeholders = ",".join("?" * len(peer_ids))
        peer_history = db.execute(
            f"SELECT book_id FROM Borrowing WHERE user_id IN ({peer_placeholders})", peer_ids
        ).fetchall()
        for row in peer_history:
            if row["book_id"] not in borrowed_ids:
                co_borrow_count[row["book_id"]] = co_borrow_count.get(row["book_id"], 0) + 1

    scored = []
    for b in all_books:
        if b["book_id"] in borrowed_ids:
            continue
        score = 0.0
        score += category_count.get(b["category"], 0) * 3
        score += author_count.get(b["author"], 0) * 4
        score += co_borrow_count.get(b["book_id"], 0) * 5
        score += b["popularity_score"] * 0.5

        if co_borrow_count.get(b["book_id"]):
            reason = "Readers with similar taste also borrowed this"
        elif category_count.get(b["category"]):
            reason = f"Matches your interest in {b['category']}"
        elif author_count.get(b["author"]):
            reason = f"By {b['author']}, an author you've read"
        else:
            reason = "Trending in the library"

        scored.append({**dict(b), "score": round(score, 2), "reason": reason})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


# ----------------------------------------------------------------------
# Routes: Library Assistant (chat widget on the dashboard)
# ----------------------------------------------------------------------
@app.route("/assistant", methods=["POST"])
@login_required
def assistant():
    db = get_db()
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()

    if not message:
        return jsonify({"reply": 'Please type a question — e.g. "What have I borrowed?"'})

    reply = get_assistant_reply(db, session["user_id"], session["role"], message)
    return jsonify({"reply": reply})


def get_assistant_reply(db, user_id, role, message):
    """
    Lightweight rule-based assistant: matches keywords in the user's message
    to an intent, then answers using live data from Books / Borrowing.
    No external AI service is required — this runs entirely on local data.
    """
    msg = message.lower()

    # ---- Librarian / admin only intents ----
    if role in ("librarian", "admin"):
        if any(k in msg for k in ["overdue", "late book"]):
            rows = db.execute(
                """SELECT Books.title, Users.full_name, Borrowing.due_date FROM Borrowing
                   JOIN Books ON Books.book_id = Borrowing.book_id
                   JOIN Users ON Users.user_id = Borrowing.user_id
                   WHERE Borrowing.status != 'returned' AND date(Borrowing.due_date) < date('now')
                   ORDER BY Borrowing.due_date"""
            ).fetchall()
            if not rows:
                return "No books are currently overdue. The library is all caught up! 🎉"
            lines = [f'• "{r["title"]}" — borrowed by {r["full_name"]}, was due {r["due_date"][:10]}' for r in rows[:8]]
            return "Here are the current overdue books:\n" + "\n".join(lines)

        if any(k in msg for k in ["popular", "trend", "most borrowed"]):
            rows = db.execute(
                "SELECT title, popularity_score FROM Books ORDER BY popularity_score DESC LIMIT 5"
            ).fetchall()
            lines = [f'• "{r["title"]}" — {r["popularity_score"]} borrows' for r in rows]
            return "Most popular books right now:\n" + "\n".join(lines)

        if any(k in msg for k in ["who has", "currently issued", "active loan", "issued books"]):
            rows = db.execute(
                """SELECT Books.title, Users.full_name, Borrowing.due_date FROM Borrowing
                   JOIN Books ON Books.book_id = Borrowing.book_id
                   JOIN Users ON Users.user_id = Borrowing.user_id
                   WHERE Borrowing.status != 'returned' ORDER BY Borrowing.due_date LIMIT 10"""
            ).fetchall()
            if not rows:
                return "There are no active loans right now."
            lines = [f'• "{r["title"]}" — {r["full_name"]}, due {r["due_date"][:10]}' for r in rows]
            return "Currently issued books:\n" + "\n".join(lines)

        if any(k in msg for k in ["stat", "total", "how many books", "inventory"]):
            total_books = db.execute("SELECT COUNT(*) c FROM Books").fetchone()["c"]
            available = db.execute("SELECT COALESCE(SUM(available_copies),0) c FROM Books").fetchone()["c"]
            active = db.execute("SELECT COUNT(*) c FROM Borrowing WHERE status != 'returned'").fetchone()["c"]
            return f"The library has {total_books} titles, {available} copies currently available, and {active} active loans."

    # ---- Shared intents (students + librarians) ----
    if any(k in msg for k in ["recommend", "suggest", "what should i read", "good book"]):
        recs = generate_recommendations(db, user_id, top_n=3)
        if not recs:
            return "I don't have enough data yet to recommend something — try borrowing a book first!"
        lines = [f'• "{r["title"]}" by {r["author"]} — {r["reason"]}' for r in recs]
        return "Here's what I'd recommend for you:\n" + "\n".join(lines)

    if any(k in msg for k in ["my book", "currently borrowed", "what do i have", "borrowed book", "checked out"]):
        rows = db.execute(
            """SELECT Books.title, Borrowing.due_date, Borrowing.status FROM Borrowing
               JOIN Books ON Books.book_id = Borrowing.book_id
               WHERE Borrowing.user_id = ? AND Borrowing.status != 'returned'
               ORDER BY Borrowing.due_date""",
            (user_id,),
        ).fetchall()
        if not rows:
            return "You don't have any books checked out right now."
        lines = [f'• "{r["title"]}" — due {r["due_date"][:10]} ({r["status"]})' for r in rows]
        return "Here's what you currently have:\n" + "\n".join(lines)

    if any(k in msg for k in ["history", "returned", "past book", "record"]):
        rows = db.execute(
            """SELECT Books.title, Borrowing.return_date, Borrowing.fine_amount FROM Borrowing
               JOIN Books ON Books.book_id = Borrowing.book_id
               WHERE Borrowing.user_id = ? AND Borrowing.status = 'returned'
               ORDER BY Borrowing.return_date DESC LIMIT 8""",
            (user_id,),
        ).fetchall()
        if not rows:
            return "You don't have any returned books in your history yet."
        lines = []
        for r in rows:
            line = f'• "{r["title"]}" — returned {r["return_date"][:10]}'
            if r["fine_amount"]:
                line += f", fine: {r['fine_amount']}"
            lines.append(line)
        return "Here's your return history:\n" + "\n".join(lines)

    if any(k in msg for k in ["fine", "owe", "penalty"]):
        row = db.execute("SELECT COALESCE(SUM(fine_amount),0) c FROM Borrowing WHERE user_id = ?", (user_id,)).fetchone()
        return f"Your total recorded fines are {row['c']}."

    if any(k in msg for k in ["hello", "hi", "hey"]):
        return "Hello! I can tell you about your borrowed books, return history, due dates, fines, or recommend a book. What would you like to know?"

    return (
        "I can help with: book recommendations, your currently borrowed books, your return history, "
        'due dates, and fines. Try asking something like "recommend a book" or "what have I borrowed".'
    )


# ----------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)