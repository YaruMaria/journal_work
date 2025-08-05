from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime
import sqlite3
import os
from flask import Flask, render_template
app = Flask(__name__)


app.secret_key = 'your_secret_key_here'


# Инициализация базы данных
def init_db():
    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()

    # Удаляем существующие таблицы (для пересоздания)
    cursor.execute("DROP TABLE IF EXISTS students")
    cursor.execute("DROP TABLE IF EXISTS lessons")
    cursor.execute("DROP TABLE IF EXISTS lesson_items")

    # Создаем новые таблицы с актуальной структурой
    cursor.execute("""
        CREATE TABLE students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            level TEXT,
            start_date TEXT,
            goal TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            topic TEXT NOT NULL,
            max_score INTEGER,
            is_finished INTEGER DEFAULT 0,
            total_earned INTEGER DEFAULT 0,
            total_max INTEGER DEFAULT 0,
            percentage REAL DEFAULT 0,
            homework TEXT,
            comment TEXT,
            finished_at TEXT,
            FOREIGN KEY (student_id) REFERENCES students (id)
        )
    """)
    cursor.execute("""
        CREATE TABLE lesson_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            score_earned INTEGER DEFAULT 0,
            max_score INTEGER DEFAULT 10,
            notes TEXT,
            FOREIGN KEY (lesson_id) REFERENCES lessons (id)
        )
    """)
    conn.commit()
    conn.close()


init_db()


def migrate_db():
    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()

    try:
        # Проверяем существование столбца
        cursor.execute("PRAGMA table_info(lessons)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'comment' not in columns:
            cursor.execute("ALTER TABLE lessons ADD COLUMN comment TEXT")

        if 'finished_at' not in columns:
            cursor.execute("ALTER TABLE lessons ADD COLUMN finished_at TEXT")

        conn.commit()
        print("Миграция базы данных успешно завершена")
    except Exception as e:
        print(f"Ошибка миграции: {str(e)}")
        conn.rollback()
    finally:
        conn.close()


# Вызовите эту функцию перед init_db() или в начале работы приложения
migrate_db()

# Главная страница
@app.route("/")
def home():
    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students")
    students = cursor.fetchall()
    conn.close()
    return render_template("index.html", students=students)


# Страница ученика
@app.route("/student/<int:student_id>")
def student(student_id):
    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()

    # Получаем данные ученика
    cursor.execute("SELECT * FROM students WHERE id = ?", (student_id,))
    student = cursor.fetchone()

    if not student:
        conn.close()
        flash("Ученик не найден!", "error")
        return redirect(url_for("home"))

    # Получаем активный (незавершенный) урок
    cursor.execute("""
        SELECT * FROM lessons 
        WHERE student_id = ? AND is_finished = 0
        ORDER BY date DESC 
        LIMIT 1
    """, (student_id,))
    active_lesson = cursor.fetchone()

    lesson_items = []
    if active_lesson:
        cursor.execute("SELECT * FROM lesson_items WHERE lesson_id = ?", (active_lesson[0],))
        lesson_items = cursor.fetchall()

    # Получаем завершенные уроки
    cursor.execute("""
        SELECT * FROM lessons 
        WHERE student_id = ? AND is_finished = 1
        ORDER BY date DESC
    """, (student_id,))
    finished_lessons = cursor.fetchall()

    conn.close()

    return render_template(
        "student.html",
        student=student,
        active_lesson=active_lesson,
        lesson_items=lesson_items,
        finished_lessons=finished_lessons
    )


# Добавление ученика
@app.route("/add_student", methods=["POST"])
def add_student():
    name = request.form["name"]
    level = request.form["level"]
    start_date = request.form["start_date"]
    goal = request.form["goal"]

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


# Добавление урока
@app.route("/add_lesson/<int:student_id>", methods=["POST"])
def add_lesson(student_id):
    topic = request.form["topic"]
    max_score = request.form["max_score"]
    date = datetime.now().strftime("%d.%m.%Y")

    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO lessons (student_id, date, topic, max_score) VALUES (?, ?, ?, ?)",
            (student_id, date, topic, max_score)
        )
        conn.commit()
        flash("Урок начат!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Ошибка при добавлении урока: {str(e)}", "error")
    finally:
        conn.close()

    return redirect(url_for("student", student_id=student_id))


# Добавление пункта урока
@app.route("/add_lesson_item/<int:lesson_id>", methods=["POST"])
def add_lesson_item(lesson_id):
    item_name = request.form["item_name"]
    max_score = request.form.get("item_max_score", 10)
    student_id = request.form["student_id"]

    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO lesson_items (lesson_id, item_name, max_score) VALUES (?, ?, ?)",
            (lesson_id, item_name, max_score)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        flash(f"Ошибка при добавлении пункта урока: {str(e)}", "error")
    finally:
        conn.close()

    return redirect(url_for("student", student_id=student_id))


# Обновление пункта урока
@app.route("/update_lesson_item/<int:item_id>", methods=["POST"])
def update_lesson_item(item_id):
    data = request.json
    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()

    try:
        if data['field'] == 'score':
            cursor.execute(
                "UPDATE lesson_items SET score_earned = ? WHERE id = ?",
                (data['value'], item_id)
            )
        else:
            cursor.execute(
                "UPDATE lesson_items SET notes = ? WHERE id = ?",
                (data['value'], item_id)
            )
        conn.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()


# Завершение урока
@app.route("/finish_lesson/<int:lesson_id>", methods=["POST"])
def finish_lesson(lesson_id):
    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()

    try:
        # Получаем student_id для редиректа
        cursor.execute("SELECT student_id FROM lessons WHERE id = ?", (lesson_id,))
        lesson_data = cursor.fetchone()
        if not lesson_data:
            flash("Урок не найден!", "error")
            return redirect(url_for("home"))

        student_id = lesson_data[0]
        homework = request.form.get("homework", "")

        # Считаем общие баллы
        cursor.execute("""
            SELECT 
                SUM(score_earned) as earned,
                SUM(max_score) as max,
                GROUP_CONCAT(CASE WHEN score_earned < max_score/2 THEN item_name ELSE NULL END) as problems
            FROM lesson_items 
            WHERE lesson_id = ?
        """, (lesson_id,))
        result = cursor.fetchone()

        total_earned = result[0] or 0
        total_max = result[1] or 1  # избегаем деления на 0
        problem_items = result[2] or ""

        # Рассчитываем процент
        percentage = round((total_earned / total_max) * 100, 1)

        # Формируем автоматический комментарий
        comment = "Хорошая работа!"
        if problem_items:
            comment = f"Слабые места: {problem_items}"
        if percentage < 50:
            comment = "Требуется дополнительная проработка материала"

        # Обновляем урок
        cursor.execute("""
            UPDATE lessons 
            SET 
                is_finished = 1,
                total_earned = ?,
                total_max = ?,
                percentage = ?,
                homework = ?,
                comment = ?,
                finished_at = datetime('now')
            WHERE id = ?
        """, (total_earned, total_max, percentage, homework, comment, lesson_id))

        conn.commit()
        flash(f"Урок завершен! Результат: {percentage}%", "success")

    except Exception as e:
        conn.rollback()
        flash(f"Ошибка при завершении урока: {str(e)}", "error")
        return redirect(url_for("home"))

    finally:
        conn.close()

    return redirect(url_for("student", student_id=student_id))


# Новый маршрут для просмотра деталей урока
@app.route("/lesson_details/<int:lesson_id>")
def lesson_details(lesson_id):
    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()

    try:
        # Получаем основную информацию об уроке
        cursor.execute("""
            SELECT 
                l.id, l.student_id, l.date, l.topic, l.max_score,
                l.is_finished, l.total_earned, l.total_max, 
                l.percentage, l.homework, l.comment, l.finished_at,
                s.name
            FROM lessons l
            JOIN students s ON l.student_id = s.id
            WHERE l.id = ?
        """, (lesson_id,))
        lesson = cursor.fetchone()

        if not lesson:
            flash("Урок не найден!", "error")
            return redirect(url_for("home"))

        # Преобразуем в словарь для удобства
        lesson_dict = {
            'id': lesson[0],
            'student_id': lesson[1],
            'date': lesson[2],
            'topic': lesson[3],
            'max_score': lesson[4],
            'is_finished': lesson[5],
            'total_earned': lesson[6],
            'total_max': lesson[7],
            'percentage': float(lesson[8]) if lesson[8] else 0.0,
            'homework': lesson[9],
            'comment': lesson[10],
            'finished_at': lesson[11],
            'student_name': lesson[12]
        }

        # Получаем пункты урока
        cursor.execute("""
            SELECT id, lesson_id, item_name, score_earned, max_score, notes
            FROM lesson_items 
            WHERE lesson_id = ?
            ORDER BY id
        """, (lesson_id,))
        items = [{
            'id': item[0],
            'lesson_id': item[1],
            'item_name': item[2],
            'score_earned': item[3],
            'max_score': item[4],
            'notes': item[5]
        } for item in cursor.fetchall()]

        return render_template(
            "lesson_details.html",
            lesson=lesson_dict,
            items=items
        )

    except Exception as e:
        flash(f"Ошибка при загрузке деталей урока: {str(e)}", "error")
        return redirect(url_for("home"))

    finally:
        conn.close()
@app.route('/')
def home():
    return render_template('index.html')

if __name__ == "__main__":
    app.run(debug=True)