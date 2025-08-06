from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import sqlite3
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'd3b07384d113edec49eaa6238ad5ff00c1f169fbe280f1f2d61af4a07e951d33')
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

def get_db():
    """Устанавливает соединение с базой данных"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Конфигурация базы данных
DB_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "school.db")
# Инициализация базы данных
def init_db():
    """Инициализирует базу данных и создает таблицы"""
    print(f"Инициализация базы данных по пути: {DB_PATH}")
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Проверяем существование таблиц
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            # Создаем таблицы, если они не существуют
            cursor.executescript("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    is_teacher BOOLEAN DEFAULT 0
                );

                CREATE TABLE students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    level TEXT,
                    start_date TEXT,
                    goal TEXT,
                    teacher_id INTEGER,
                    FOREIGN KEY (teacher_id) REFERENCES users(id)
                );

                CREATE TABLE lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    understanding INTEGER DEFAULT 0,
                    participation INTEGER DEFAULT 0,
                    homework TEXT,
                    FOREIGN KEY (student_id) REFERENCES students(id)
                );

                CREATE TABLE monthly_awards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    year INTEGER NOT NULL,
                    month INTEGER NOT NULL,
                    award INTEGER,
                    FOREIGN KEY (student_id) REFERENCES students(id),
                    UNIQUE(student_id, year, month)
                );
            """)
            conn.commit()
            print("Таблицы успешно созданы")
        else:
            print("Таблицы уже существуют")
    except sqlite3.Error as e:
        print(f"Ошибка при инициализации базы данных: {e}")
        raise
    finally:
        conn.close()

# Создание первого учителя
def create_first_teacher():
    """Создает учетную запись администратора по умолчанию"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE is_teacher = 1")
        if not cursor.fetchone():
            hashed_password = generate_password_hash("admin123")
            cursor.execute(
                "INSERT INTO users (username, password, is_teacher) VALUES (?, ?, 1)",
                ("admin", hashed_password)
            )
            conn.commit()
            print("Создан учитель по умолчанию: admin/admin123")
    except sqlite3.Error as e:
        print(f"Ошибка при создании учителя: {e}")
        raise
    finally:
        conn.close()

@app.before_first_request
def initialize():
    """Инициализация перед первым запросом"""
    init_db()
    create_first_teacher()

# Декораторы для проверки прав
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите для доступа к этой странице', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_teacher'):
            flash('Эта функция доступна только учителям', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# Маршруты аутентификации
@app.route('/')
def index():
    """Перенаправляет на вход, даже если пользователь был авторизован ранее"""
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Страница входа"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect("school.db")
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['is_teacher'] = bool(user[3])
            flash('Вы успешно вошли в систему', 'success')
            return redirect(url_for('home'))
        else:
            flash('Неверный логин или пароль', 'error')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        is_teacher = 1 if request.form.get('is_teacher') else 0

        if len(username) < 3:
            flash('Логин должен содержать минимум 3 символа', 'error')
        elif len(password) < 6:
            flash('Пароль должен содержать минимум 6 символов', 'error')
        elif password != confirm_password:
            flash('Пароли не совпадают', 'error')
        else:
            hashed_password = generate_password_hash(password)

            try:
                conn = sqlite3.connect("school.db")
                cursor = conn.cursor()
                cursor.execute('INSERT INTO users (username, password, is_teacher) VALUES (?, ?, ?)',
                               (username, hashed_password, is_teacher))
                conn.commit()
                conn.close()
                flash('Регистрация успешна! Теперь войдите', 'success')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('Пользователь с таким именем уже существует', 'error')

    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы успешно вышли из системы', 'success')
    return redirect(url_for('login'))

# Основные маршруты
@app.route("/home")
@login_required
def home():
    """Страница 'Мои ученики'"""
    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()

    if session.get('is_teacher'):
        cursor.execute("SELECT * FROM students WHERE teacher_id = ?", (session['user_id'],))
    else:
        cursor.execute("SELECT * FROM students LIMIT 0")

    students = cursor.fetchall()
    conn.close()
    return render_template("index.html", students=students)

@app.route("/student/<int:student_id>")
@login_required
def student(student_id):
    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()

    if session.get('is_teacher'):
        cursor.execute("SELECT * FROM students WHERE id = ? AND teacher_id = ?",
                       (student_id, session['user_id']))
    else:
        cursor.execute("SELECT * FROM students WHERE id = ?", (student_id,))

    student = cursor.fetchone()

    if not student:
        conn.close()
        flash("Ученик не найден или у вас нет прав доступа", "error")
        return redirect(url_for("home"))

    if session.get('is_teacher'):
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
               COALESCE(NULLIF(homework, ''), '0') as homework
        FROM lessons 
        WHERE student_id = ? 
        ORDER BY id ASC
        LIMIT 8
    """, (student_id,))
    lessons = cursor.fetchall()

    cursor.execute("SELECT year, month, award FROM monthly_awards WHERE student_id = ?", (student_id,))
    awards = {(year, month): award for year, month, award in cursor.fetchall()}

    conn.close()

    return render_template("student.html",
                           student=student,
                           lessons=lessons,
                           awards=awards,
                           current_date=datetime.now(),
                           relativedelta=relativedelta)

@app.route("/add_student", methods=["POST"])
@login_required
@teacher_required
def add_student():
    name = request.form.get("name", "").strip()
    level = request.form.get("level", "").strip()
    start_date = request.form.get("start_date", "").strip()
    goal = request.form.get("goal", "").strip()

    errors = []
    if not name:
        errors.append("Имя ученика обязательно")
    elif len(name) > 50:
        errors.append("Имя слишком длинное (макс. 50 символов)")

    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(url_for("home"))

    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO students (name, level, start_date, goal, teacher_id) VALUES (?, ?, ?, ?, ?)",
            (name, level if level else None,
             start_date if start_date else None,
             goal if goal else None,
             session['user_id'])
        )
        conn.commit()
        flash("Ученик добавлен!", "success")
    except sqlite3.IntegrityError:
        flash("Ученик с таким именем уже существует", "error")
    except Exception as e:
        flash(f"Ошибка при добавлении ученика: {str(e)}", "error")
    finally:
        conn.close()

    return redirect(url_for("home"))

# Остальные маршруты
@app.route("/set_coins/<int:lesson_id>/<string:coin_type>", methods=["POST"])
@login_required
def set_coins(lesson_id, coin_type):
    if coin_type not in ['understanding', 'participation', 'homework']:
        return jsonify({'status': 'error', 'message': 'Invalid coin type'}), 400

    coins = int(request.form.get('coins', 0))
    student_id = request.form.get('student_id')

    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()
    try:
        if coin_type == 'homework':
            cursor.execute(
                "UPDATE lessons SET homework = ? WHERE id = ?",
                (str(coins), lesson_id))
        else:
            cursor.execute(
                f"UPDATE lessons SET {coin_type} = ? WHERE id = ?",
                (coins, lesson_id))
        conn.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()

@app.route("/update_homework/<int:lesson_id>", methods=["POST"])
@login_required
def update_homework(lesson_id):
    homework = request.form.get("homework", "")
    student_id = request.form.get("student_id")

    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE lessons SET homework = ? WHERE id = ?",
            (homework, lesson_id))
        conn.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()

@app.route("/student/<int:student_id>/awards")
@login_required
def student_awards(student_id):
    current_date = datetime.now()
    selected_month = request.args.get('month', current_date.month, type=int)
    selected_year = request.args.get('year', current_date.year, type=int)

    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students WHERE id = ?", (student_id,))
    student = cursor.fetchone()

    cursor.execute("SELECT year, month, award FROM monthly_awards WHERE student_id = ?", (student_id,))
    awards = {(year, month): award for year, month, award in cursor.fetchall()}
    conn.close()

    months = []
    for i in range(-3, 3):
        date = datetime(selected_year, selected_month, 1) + relativedelta(months=i)
        months.append({
            'year': date.year,
            'month': date.month,
            'name': date.strftime('%B'),
            'is_current': (date.year == current_date.year and date.month == current_date.month),
            'award': awards.get((date.year, date.month))
        })

    return render_template("awards.html",
                         student=student,
                         months=months,
                         current_date=current_date,
                         selected_month=selected_month,
                         selected_year=selected_year)

@app.route("/update_award", methods=["POST"])
@login_required
def update_award():
    student_id = request.form.get("student_id")
    year = int(request.form.get("year"))
    month = int(request.form.get("month"))
    award = int(request.form.get("award"))

    conn = sqlite3.connect("school.db")
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO monthly_awards 
            (student_id, year, month, award) 
            VALUES (?, ?, ?, ?)
        """, (student_id, year, month, award))
        conn.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    # Проверяем и инициализируем БД перед запуском
    if not os.path.exists(DB_PATH):
        init_db()
        create_first_teacher()
    app.run(host="0.0.0.0", port=port)