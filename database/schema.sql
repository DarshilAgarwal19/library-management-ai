PRAGMA foreign_keys = ON;

CREATE TABLE Users (
    user_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name      TEXT NOT NULL,
    username       TEXT NOT NULL UNIQUE,
    email          TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('student', 'librarian', 'admin')) DEFAULT 'student',
    created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE Books (
    book_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title             TEXT NOT NULL,
    author            TEXT NOT NULL,
    category          TEXT NOT NULL,
    isbn              TEXT UNIQUE,
    call_number       TEXT,
    total_copies      INTEGER NOT NULL DEFAULT 1 CHECK (total_copies >= 0),
    available_copies  INTEGER NOT NULL DEFAULT 1 CHECK (available_copies >= 0),
    added_date        DATETIME DEFAULT CURRENT_TIMESTAMP,
    popularity_score  INTEGER DEFAULT 0
);

CREATE TABLE Borrowing (
    borrow_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    book_id       INTEGER NOT NULL,
    issue_date    DATETIME DEFAULT CURRENT_TIMESTAMP,
    due_date      DATETIME NOT NULL,
    return_date   DATETIME,
    status        TEXT NOT NULL CHECK (status IN ('issued', 'returned', 'overdue')) DEFAULT 'issued',
    fine_amount   REAL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES Books(book_id) ON DELETE CASCADE
);

CREATE TABLE Recommendations (
    recommendation_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id            INTEGER NOT NULL,
    book_id            INTEGER NOT NULL,
    score              REAL NOT NULL DEFAULT 0,
    reason             TEXT,
    algorithm_used     TEXT CHECK (algorithm_used IN ('content_based', 'collaborative', 'popularity', 'hybrid')) DEFAULT 'hybrid',
    generated_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    was_clicked        BOOLEAN DEFAULT 0,
    was_issued         BOOLEAN DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES Books(book_id) ON DELETE CASCADE
);

CREATE TABLE Notifications (
    notification_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER,
    book_id          INTEGER,
    type             TEXT NOT NULL CHECK (type IN ('due_soon', 'overdue', 'new_arrival', 'general')),
    message          TEXT NOT NULL,
    is_read          BOOLEAN DEFAULT 0,
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (book_id) REFERENCES Books(book_id) ON DELETE CASCADE
);

CREATE INDEX idx_books_category ON Books(category);
CREATE INDEX idx_books_author ON Books(author);
CREATE INDEX idx_borrowing_user ON Borrowing(user_id);
CREATE INDEX idx_borrowing_status ON Borrowing(status);
CREATE INDEX idx_recommendations_user ON Recommendations(user_id);
CREATE INDEX idx_notifications_user ON Notifications(user_id);