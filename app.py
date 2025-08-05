from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'


def init_db():
    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            level TEXT,
            start_date TEXT,
            goal TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            topic TEXT NOT NULL,
            understanding INTEGER DEFAULT 0,
            participation INTEGER DEFAULT 0,
            homework TEXT,
            FOREIGN KEY (student_id) REFERENCES students (id)
        )
    """)

    conn.commit()
    conn.close()


if not os.path.exists('school.db'):
    init_db()


@app.route("/")
def home():
    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students")
    students = cursor.fetchall()
    conn.close()
    return render_template("index.html", students=students)


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

    conn.close()
    return render_template("student.html", student=student, lessons=lessons)


@app.route("/student_old/<int:student_id>")
def student_old(student_id):
    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM students WHERE id = ?", (student_id,))
    student = cursor.fetchone()

    if not student:
        conn.close()
        flash("Ученик не найден!", "error")
        return redirect(url_for("home"))

    cursor.execute("""
        SELECT * FROM lessons 
        WHERE student_id = ? 
        ORDER BY date DESC
        LIMIT 1
    """, (student_id,))
    active_lesson = cursor.fetchone()

    conn.close()
    return render_template("student_old.html", student=student, active_lesson=active_lesson)


@app.route("/add_student", methods=["POST"])
def add_student():
    name = request.form["name"]
    level = request.form.get("level", "")
    start_date = request.form.get("start_date", "")
    goal = request.form.get("goal", "")

    if not name:
        flash("Имя ученика обязательно!", "error")
        return redirect(url_for("home"))

    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO students (name, level, start_date, goal) VALUES (?, ?, ?, ?)",
            (name, level, start_date, goal)
        )
        conn.commit()
        flash("Ученик добавлен!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Ошибка при добавлении ученика: {str(e)}", "error")
    finally:
        conn.close()

    return redirect(url_for("home"))


@app.route("/set_coins/<int:lesson_id>/<string:coin_type>", methods=["POST"])
def set_coins(lesson_id, coin_type):
    if coin_type not in ['understanding', 'participation']:
        return jsonify({'status': 'error', 'message': 'Invalid coin type'}), 400

    coins = int(request.form.get('coins', 0))
    student_id = request.form.get('student_id')

    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"UPDATE lessons SET {coin_type} = ? WHERE id = ?",
            (coins, lesson_id)
        )
        conn.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()


@app.route("/update_homework/<int:lesson_id>", methods=["POST"])
def update_homework(lesson_id):
    homework = request.form.get("homework", "")
    student_id = request.form.get("student_id")

    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE lessons SET homework = ? WHERE id = ?",
            (homework, lesson_id)
        )
        conn.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()


if __name__ == "__main__":
    app.run(debug=True)