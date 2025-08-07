from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import sqlite3
import os
from functools import wraps
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
app.config['WTF_CSRF_ENABLED'] = True  # Включаем CSRF защиту

# Инициализация CSRF защиты
csrf = CSRFProtect(app)

# Конфигурация базы данных
DB_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "school.db")


def get_db():
    """Устанавливает соединение с базой данных"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Инициализирует базу данных и создает таблицы"""
    print(f"Инициализация базы данных по пути: {DB_PATH}")
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Проверяем существование таблиц
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            # Создаем все таблицы с нуля
            cursor.executescript("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    is_teacher BOOLEAN DEFAULT 0,
                    is_parent BOOLEAN DEFAULT 0
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

                CREATE TABLE parent_child (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_id INTEGER NOT NULL,
                    student_id INTEGER NOT NULL,
                    FOREIGN KEY (parent_id) REFERENCES users(id),
                    FOREIGN KEY (student_id) REFERENCES students(id),
                    UNIQUE(parent_id, student_id)
                );
            """)
            conn.commit()
            print("Все таблицы успешно созданы")
        else:
            # Если таблицы уже существуют, добавляем недостающие колонки
            try:
                # Добавляем is_parent в users, если его нет
                cursor.execute("ALTER TABLE users ADD COLUMN is_parent BOOLEAN DEFAULT 0")
                print("Добавлен столбец is_parent в таблицу users")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e):
                    raise
                print("Столбец is_parent уже существует")

            # Создаем таблицу parent_child, если ее нет
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS parent_child (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_id INTEGER NOT NULL,
                    student_id INTEGER NOT NULL,
                    FOREIGN KEY (parent_id) REFERENCES users(id),
                    FOREIGN KEY (student_id) REFERENCES students(id),
                    UNIQUE(parent_id, student_id)
                )
            """)

            # Проверяем и добавляем другие таблицы, если их нет
            tables_to_check = ['students', 'lessons', 'monthly_awards']
            for table in tables_to_check:
                cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
                if not cursor.fetchone():
                    if table == 'students':
                        cursor.execute("""
                            CREATE TABLE students (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                name TEXT NOT NULL,
                                level TEXT,
                                start_date TEXT,
                                goal TEXT,
                                teacher_id INTEGER,
                                FOREIGN KEY (teacher_id) REFERENCES users(id)
                            )
                        """)
                    elif table == 'lessons':
                        cursor.execute("""
                            CREATE TABLE lessons (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                student_id INTEGER NOT NULL,
                                date TEXT NOT NULL,
                                topic TEXT NOT NULL,
                                understanding INTEGER DEFAULT 0,
                                participation INTEGER DEFAULT 0,
                                homework TEXT,
                                FOREIGN KEY (student_id) REFERENCES students(id)
                            )
                        """)
                    elif table == 'monthly_awards':
                        cursor.execute("""
                            CREATE TABLE monthly_awards (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                student_id INTEGER NOT NULL,
                                year INTEGER NOT NULL,
                                month INTEGER NOT NULL,
                                award INTEGER,
                                FOREIGN KEY (student_id) REFERENCES students(id),
                                UNIQUE(student_id, year, month)
                            )
                        """)
                    print(f"Таблица {table} создана")

            conn.commit()
            print("Проверка и обновление структуры базы данных завершены")

    except sqlite3.Error as e:
        print(f"Ошибка при инициализации базы данных: {e}")
        conn.rollback()
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

with app.app_context():
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
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT id, username, password, is_teacher, is_parent FROM users WHERE username = ?',
                    (username,)
                )
                user = cursor.fetchone()

            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['is_teacher'] = bool(user['is_teacher'])
                session['is_parent'] = bool(user['is_parent'])
                flash('Вы успешно вошли в систему', 'success')

                # Перенаправляем в зависимости от роли
                if user['is_parent']:
                    return redirect(url_for('parent_dashboard'))
                else:
                    return redirect(url_for('home'))

            flash('Неверный логин или пароль', 'error')
        except Exception as e:
            flash('Ошибка при входе в систему', 'error')
            print(f"Ошибка входа: {e}")

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            is_teacher = 1 if request.form.get('is_teacher') == 'on' else 0
            is_parent = 1 if request.form.get('is_parent') == 'on' else 0

            # Валидация
            errors = []
            if len(username) < 3:
                errors.append('Логин должен содержать минимум 3 символа')
            if len(password) < 6:
                errors.append('Пароль должен содержать минимум 6 символов')
            if password != confirm_password:
                errors.append('Пароли не совпадают')
            if is_teacher and is_parent:
                errors.append('Вы не можете быть одновременно учителем и родителем')

            if errors:
                for error in errors:
                    flash(error, 'error')
                return render_template('register.html', username=username)

            hashed_password = generate_password_hash(password)
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO users (username, password, is_teacher, is_parent) VALUES (?, ?, ?, ?)',
                    (username, hashed_password, is_teacher, is_parent)
                )
                conn.commit()

            flash('Регистрация успешна! Теперь войдите', 'success')
            return redirect(url_for('login'))

        except sqlite3.IntegrityError:
            flash('Пользователь с таким именем уже существует', 'error')
        except Exception as e:
            flash('Произошла ошибка при регистрации', 'error')
            print(f"Ошибка регистрации: {e}")

    return render_template('register.html')


@app.route('/search_student')
@login_required
def search_student():
    if not session.get('is_parent'):
        return redirect(url_for('home'))

    query = request.args.get('query', '').strip()
    if len(query) < 2:
        return render_template('search_child.html', students=[])

    conn = get_db()
    cursor = conn.cursor()

    # Ищем студентов по имени
    cursor.execute("""
        SELECT id, name, level, start_date 
        FROM students 
        WHERE name LIKE ? 
        LIMIT 10
    """, (f'%{query}%',))

    students = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # Для GET-запросов с параметром query возвращаем HTML с результатами
    if 'query' in request.args:
        return render_template('search_child.html', students=students)

    # Для AJAX-запросов возвращаем JSON
    return jsonify(students)


@app.route('/parent_dashboard')
@login_required
def parent_dashboard():
    if not session.get('is_parent'):
        return redirect(url_for('home'))

    return render_template('search_child.html')

@app.route("/home")
@login_required
def home():
    """Главная страница после входа"""
    if session.get('is_parent'):
        # Для родителей перенаправляем на поиск ребенка
        return redirect(url_for('parent_dashboard'))
    elif session.get('is_teacher'):
        # Для учителей показываем список учеников
        conn = sqlite3.connect("school.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM students WHERE teacher_id = ?", (session['user_id'],))
        students = cursor.fetchall()
        conn.close()
        return render_template("index.html", students=students)
    else:
        # Для других ролей (если будут добавлены)
        flash("У вас нет прав доступа", "error")
        return redirect(url_for('login'))
# Обновим home для родителей

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы успешно вышли из системы', 'success')
    return redirect(url_for('login'))

# Основные маршруты

@app.route('/debug/parent_child')
@login_required
@teacher_required
def debug_parent_child():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM parent_child")
    relations = cursor.fetchall()
    conn.close()
    return str(relations)

@app.route("/student/<int:student_id>")
@login_required
def student(student_id):
    print(f"Attempting to access student page for ID: {student_id}")  # Отладочное сообщение
    conn = get_db()
    cursor = conn.cursor()

    # Получаем данные ученика
    cursor.execute("""
        SELECT s.*, u.username as teacher_name 
        FROM students s
        LEFT JOIN users u ON s.teacher_id = u.id
        WHERE s.id = ?
    """, (student_id,))
    student = cursor.fetchone()

    if not student:
        conn.close()
        flash("Ученик не найден", "error")
        return redirect(url_for("home"))

    # Проверка прав доступа
    if session.get('is_parent'):
        # Для родителей проверяем связь в parent_child
        cursor.execute("""
            SELECT 1 FROM parent_child 
            WHERE parent_id = ? AND student_id = ?
        """, (session['user_id'], student_id))
        if not cursor.fetchone():
            conn.close()
            flash("У вас нет доступа к этому ученику", "error")
            return redirect(url_for("parent_dashboard"))
    elif session.get('is_teacher'):
        # Для учителей проверяем, что ученик привязан к нему
        if student['teacher_id'] != session['user_id']:
            conn.close()
            flash("У вас нет доступа к этому ученику", "error")
            return redirect(url_for("home"))
    else:
        # Для других ролей (если будут)
        conn.close()
        flash("У вас нет прав доступа", "error")
        return redirect(url_for("home"))

    # Если доступ разрешен, продолжаем обработку
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


@app.route('/link_child', methods=['POST'])
@login_required
@teacher_required
def link_child():
    parent_id = request.form.get('parent_id')
    student_id = request.form.get('student_id')

    try:
        conn = get_db()
        cursor = conn.cursor()

        # Проверяем, что пользователь действительно родитель
        cursor.execute("SELECT is_parent FROM users WHERE id = ?", (parent_id,))
        user = cursor.fetchone()
        if not user or not user['is_parent']:
            flash("Указанный пользователь не является родителем", "error")
            return redirect(url_for('admin'))

        # Проверяем существование студента
        cursor.execute("SELECT 1 FROM students WHERE id = ?", (student_id,))
        if not cursor.fetchone():
            flash("Ученик не найден", "error")
            return redirect(url_for('admin'))

        # Связываем родителя и ребенка
        cursor.execute("""
            INSERT OR IGNORE INTO parent_child (parent_id, student_id) 
            VALUES (?, ?)
        """, (parent_id, student_id))
        conn.commit()

        flash("Ребенок успешно привязан к родителю", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Ошибка при привязке ребенка: {str(e)}", "error")
    finally:
        conn.close()

    return redirect(url_for('admin'))


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
    app.run(host="0.0.0.0", port=port)