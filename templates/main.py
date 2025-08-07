from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime
import sqlite3
import os

app = Flask(__name__, template_folder='templates')
app.secret_key = 'your-secret-key-here'


def init_db():
    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()

    # Создаем таблицы, если они не существуют
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            level TEXT,
            start_date TEXT,
            goal TEXT
        );

        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            topic TEXT NOT NULL,
            understanding INTEGER DEFAULT 0,
            participation INTEGER DEFAULT 0,
            homework TEXT,
            FOREIGN KEY (student_id) REFERENCES students (id)
        );

        CREATE TABLE IF NOT EXISTS monthly_trophies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            trophy INTEGER NOT NULL,
            FOREIGN KEY (student_id) REFERENCES students (id),
            UNIQUE(student_id, year, month)
        );
    """)
    conn.commit()
    conn.close()


def check_tables():
    try:
        with sqlite3.connect("school.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='monthly_trophies'")
            if not cursor.fetchone():
                init_db()  # Просто пересоздаем всю БД, если таблицы нет
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        raise


# Инициализация БД при первом запуске
if not os.path.exists('school.db'):
    init_db()

@app.route("/student/<int:student_id>")
def student(student_id):
    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM students WHERE id = ?", (student_id,))
    student = cursor.fetchone()

    if not student:
        conn.close()
        flash("Ученик не найден!", "error")
        return redirect(url_for("home"))

    # Создаем 8 уроков, если их нет
    cursor.execute("SELECT COUNT(*) FROM lessons WHERE student_id = ?", (student_id,))
    lesson_count = cursor.fetchone()[0]

    if lesson_count < 8:
        for i in range(lesson_count + 1, 9):
            cursor.execute(
                "INSERT INTO lessons (student_id, date, topic) VALUES (?, ?, ?)",
                (student_id, datetime.now().strftime("%Y-%m-%d"), f"Урок {i}")
            )
        conn.commit()

    cursor.execute("""
        SELECT id, student_id, date, topic, 
               COALESCE(understanding, 0) as understanding,
               COALESCE(participation, 0) as participation,
               homework
        FROM lessons 
        WHERE student_id = ? 
        ORDER BY id ASC
        LIMIT 8
    """, (student_id,))
    lessons = cursor.fetchall()

    # Получаем данные о кубках за все месяцы
    cursor.execute("""
        SELECT year, month, trophy 
        FROM monthly_trophies 
        WHERE student_id = ?
        ORDER BY year, month
    """, (student_id,))
    trophies = cursor.fetchall()

    # Создаем словарь для быстрого доступа к кубкам по году и месяцу
    trophies_dict = {(year, month): trophy for year, month, trophy in trophies}

    # Список всех месяцев для отображения
    months = [
        (1, "Январь"), (2, "Февраль"), (3, "Март"), (4, "Апрель"),
        (5, "Май"), (6, "Июнь"), (7, "Июль"), (8, "Август"),
        (9, "Сентябрь"), (10, "Октябрь"), (11, "Ноябрь"), (12, "Декабрь")
    ]

    current_year = datetime.now().year

    conn.close()
    return render_template("student.html",
                           student=student,
                           lessons=lessons,
                           months=months,
                           current_year=current_year,
                           trophies=trophies_dict)


@app.route("/update_trophy", methods=["POST"])
def update_trophy():
    student_id = request.form.get("student_id")
    year = int(request.form.get("year"))
    month = int(request.form.get("month"))
    trophy = int(request.form.get("trophy"))

    if trophy not in [1, 2, 3, 4]:
        return jsonify({'status': 'error', 'message': 'Invalid trophy value'}), 400

    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()
    try:
        # Используем INSERT OR REPLACE для обновления существующей записи
        cursor.execute("""
            INSERT OR REPLACE INTO monthly_trophies 
            (student_id, year, month, trophy) 
            VALUES (?, ?, ?, ?)
        """, (student_id, year, month, trophy))
        conn.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()

@app.route("/")
def home():
    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students")
    students = cursor.fetchall()
    conn.close()
    return render_template("index.html", students=students)  # Вот это ключевое изменение!


if __name__ == "__main__":
    check_tables()
    app.run(debug=True)