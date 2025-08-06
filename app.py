from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import sqlite3
import os
from functools import wraps

# Инициализация приложения
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')  # Безопасный ключ из переменных окружения
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

# Конфигурация базы данных
DB_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "school.db")


def get_db():
    """Создает и возвращает соединение с базой данных"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Доступ к колонкам по имени
    return conn


def init_db():
    """Инициализация структуры базы данных"""
    print(f"Инициализация базы данных по пути: {DB_PATH}")
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Создание всех таблиц одним транзакцией
        cursor.executescript("""
            BEGIN;
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                is_teacher BOOLEAN DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                level TEXT,
                start_date TEXT,
                goal TEXT,
                teacher_id INTEGER,
                FOREIGN KEY (teacher_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                topic TEXT NOT NULL,
                understanding INTEGER DEFAULT 0,
                participation INTEGER DEFAULT 0,
                homework TEXT,
                FOREIGN KEY (student_id) REFERENCES students(id)
            );

            CREATE TABLE IF NOT EXISTS monthly_awards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                award INTEGER,
                FOREIGN KEY (student_id) REFERENCES students(id),
                UNIQUE(student_id, year, month)
            );
            COMMIT;
        """)
        print("Таблицы успешно созданы")
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Ошибка при создании таблиц: {e}")
        raise
    finally:
        conn.close()


def create_first_teacher():
    """Создание учетной записи администратора по умолчанию"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Проверяем, есть ли уже учитель
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
def initialize_app():
    """Инициализация приложения перед первым запросом"""
    if not os.path.exists(DB_PATH):
        init_db()
    create_first_teacher()


# Декораторы для контроля доступа
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_teacher'):
            flash('Доступно только для учителей', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)

    return decorated_function


# Маршруты аутентификации
@app.route('/')
def index():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id, username, password, is_teacher FROM users WHERE username = ?',
                (username,)
            )
            user = cursor.fetchone()
            conn.close()

            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['is_teacher'] = bool(user['is_teacher'])
                flash('Вход выполнен успешно', 'success')
                return redirect(url_for('home'))

            flash('Неверный логин или пароль', 'error')
        except sqlite3.Error as e:
            flash('Ошибка базы данных', 'error')
            print(f"Ошибка входа: {e}")

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        is_teacher = 1 if request.form.get('is_teacher') else 0

        # Валидация
        errors = []
        if len(username) < 3:
            errors.append('Логин должен содержать минимум 3 символа')
        if len(password) < 6:
            errors.append('Пароль должен содержать минимум 6 символов')
        if password != confirm_password:
            errors.append('Пароли не совпадают')

        if errors:
            for error in errors:
                flash(error, 'error')
        else:
            try:
                hashed_password = generate_password_hash(password)
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO users (username, password, is_teacher) VALUES (?, ?, ?)',
                    (username, hashed_password, is_teacher)
                )
                conn.commit()
                conn.close()
                flash('Регистрация успешна! Теперь войдите', 'success')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('Пользователь с таким именем уже существует', 'error')
            except sqlite3.Error as e:
                flash('Ошибка базы данных', 'error')
                print(f"Ошибка регистрации: {e}")

    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('login'))


# Основные маршруты приложения
@app.route("/home")
@login_required
def home():
    try:
        conn = get_db()
        cursor = conn.cursor()

        if session.get('is_teacher'):
            cursor.execute(
                "SELECT * FROM students WHERE teacher_id = ?",
                (session['user_id'],)
            )
        else:
            cursor.execute("SELECT * FROM students LIMIT 0")

        students = cursor.fetchall()
        conn.close()
        return render_template("index.html", students=students)
    except sqlite3.Error as e:
        flash('Ошибка загрузки данных', 'error')
        print(f"Ошибка загрузки студентов: {e}")
        return render_template("index.html", students=[])


# Остальные маршруты (student, add_student, set_coins, и т.д.) остаются аналогичными,
# но с использованием get_db() и обработкой ошибок

@app.route("/debug")
def debug():
    """Диагностический маршрут для проверки работы приложения"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Проверка таблиц
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row['name'] for row in cursor.fetchall()]

        # Проверка пользователей
        cursor.execute("SELECT COUNT(*) as count FROM users")
        users_count = cursor.fetchone()['count']

        # Проверка студентов
        cursor.execute("SELECT COUNT(*) as count FROM students")
        students_count = cursor.fetchone()['count']

        conn.close()

        return jsonify({
            "status": "success",
            "db_path": DB_PATH,
            "file_exists": os.path.exists(DB_PATH),
            "file_size": os.path.getsize(DB_PATH),
            "tables": tables,
            "users_count": users_count,
            "students_count": students_count,
            "session": dict(session)
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "db_path": DB_PATH,
            "file_exists": os.path.exists(DB_PATH)
        })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)