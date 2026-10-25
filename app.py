import os, secrets, json, urllib.request, random
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
if os.environ.get('RENDER') and not os.environ.get('SECRET_KEY'):
    raise RuntimeError('На сервере требуется переменная окружения SECRET_KEY.')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(BASE, 'umno.db')).replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('COOKIE_SECURE') == '1'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(90), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(12), nullable=False, default='student')
    grade = db.Column(db.Integer, nullable=False, default=9)

    def verify(self, value):
        return check_password_hash(self.password_hash, value)


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(40), nullable=False)
    exam = db.Column(db.String(10), nullable=False)
    topic = db.Column(db.String(100), nullable=False)
    body = db.Column(db.Text, nullable=False)
    options = db.Column(db.JSON, nullable=False)
    correct_index = db.Column(db.Integer, nullable=False)
    explanation = db.Column(db.Text, nullable=False)
    theory = db.Column(db.Text, nullable=False)


class Attempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    answer_index = db.Column(db.Integer, nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)


class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'question_id', name='uq_favorite_user_question'),)


class ExtendedAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    response = db.Column(db.Text, nullable=False)
    self_score = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    invite_code = db.Column(db.String(12), unique=True, nullable=False)


class Membership(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('group_id', 'student_id'),)


class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('group_id', 'question_id'),)


class MockExam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    exam = db.Column(db.String(10), nullable=False)
    question_ids = db.Column(db.JSON, nullable=False)
    responses = db.Column(db.JSON, nullable=True)
    started_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    finished_at = db.Column(db.DateTime, nullable=True)
    score = db.Column(db.Integer, nullable=True)


CATALOG = {
    'oge': [(i, topic) for i, topic in enumerate([
        'Практические задачи', 'Практические задачи', 'Практические задачи', 'Практические задачи', 'Практические задачи',
        'Вычисления', 'Числа на прямой', 'Алгебраические выражения', 'Уравнения', 'Вероятность',
        'Графики функций', 'Расчёты по формулам', 'Неравенства', 'Последовательности', 'Геометрия',
        'Геометрия', 'Геометрия', 'Геометрия', 'Геометрические утверждения', 'Уравнения и неравенства',
        'Текстовые задачи', 'Графики и анализ', 'Геометрия', 'Геометрия', 'Геометрия'
    ], 1)],
    'ege': [(i, topic) for i, topic in enumerate([
        'Планиметрия', 'Векторы', 'Стереометрия', 'Вероятность', 'Вероятность', 'Уравнения',
        'Вычисления', 'Производная', 'Прикладные задачи', 'Текстовые задачи', 'Графики функций',
        'Экстремумы', 'Уравнения', 'Стереометрия', 'Неравенства', 'Планиметрия',
        'Финансовые задачи', 'Параметры', 'Теория чисел'
    ], 1)]
}
EXAM_MINUTES = {'oge': 235, 'ege': 235}
SUBJECTS = {'math': ('📐', 'Математика')}


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@app.before_request
def csrf_guard():
    if request.method == 'POST' and not secrets.compare_digest(str(session.get('csrf', '')), str(request.form.get('csrf', 'not-supplied'))):
        abort(400, 'Недействительный токен формы. Обновите страницу.')


@app.context_processor
def context():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(32)
    return {'csrf': session['csrf'], 'subjects': SUBJECTS}


def teacher_only(fn):
    @wraps(fn)
    @login_required
    def inner(*a, **kw):
        if current_user.role != 'teacher':
            abort(403)
        return fn(*a, **kw)
    return inner


def student_only(fn):
    @wraps(fn)
    @login_required
    def inner(*a, **kw):
        if current_user.role != 'student':
            abort(403)
        return fn(*a, **kw)
    return inner


def user_exam():
    if current_user.is_authenticated and current_user.role == 'student':
        return 'oge' if current_user.grade == 9 else 'ege'
    return session.get('guest_exam', 'oge')


def chosen_exam():
    exam_type = request.args.get('exam') or request.form.get('exam')
    if exam_type in ('oge', 'ege'):
        if not current_user.is_authenticated:
            session['guest_exam'] = exam_type
        return exam_type
    return user_exam()


def number_of(q):
    for exam, num, _, body, *_ in NUMBERED_SAMPLES + MANUAL_SAMPLES:
        if exam == q.exam and body == q.body:
            return num
    legacy = {
        'oge': {'Линейные уравнения': 9, 'Дроби': 6, 'Проценты': 2, 'Степени': 8, 'Геометрия': 15, 'Вероятность': 10},
        'ege': {'Показательные уравнения': 13, 'Логарифмы': 7, 'Тригонометрия': 6, 'Производная': 8, 'Вероятность': 5, 'Планиметрия': 1},
    }
    return legacy.get(q.exam, {}).get(q.topic)


@app.context_processor
def catalog_helpers():
    return {'number_of': number_of, 'catalog': CATALOG, 'user_exam': user_exam}


def visible_questions(rows):
    from admin_editor import active_questions
    return active_questions(rows)


def is_archived(qid):
    from admin_editor import LegacyArchive
    return db.session.query(LegacyArchive.id).filter_by(question_id=qid).first() is not None


@app.route('/')
def home():
    if not current_user.is_authenticated:
        return render_template('landing.html')
    if current_user.role == 'teacher':
        return redirect(url_for('teacher'))
    attempts = Attempt.query.filter_by(user_id=current_user.id).all()
    completed = sum(a.is_correct for a in attempts)
    assigned = db.session.query(Question).join(Assignment, Assignment.question_id == Question.id).join(Membership, Membership.group_id == Assignment.group_id).filter(
        Membership.student_id == current_user.id, Question.exam == user_exam(), Question.subject == 'math'
    ).all()
    assigned = visible_questions(assigned)
    return render_template('home.html', count=len(attempts), correct=completed, accuracy=round(100 * completed / len(attempts)) if attempts else 0, assigned=assigned)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        role = request.form.get('role')
        try:
            grade = int(request.form.get('grade', '9'))
        except ValueError:
            grade = 0
        if not 2 <= len(name) <= 90 or len(email) > 180 or '@' not in email or len(password) < 8 or role not in ('student', 'teacher') or grade not in (9, 10, 11):
            flash('Проверьте поля. Пароль должен содержать минимум 8 символов.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('Эта почта уже зарегистрирована.', 'error')
        else:
            user = User(name=name, email=email, password_hash=generate_password_hash(password), role=role, grade=grade)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for('home'))
    return render_template('auth.html', register=True)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and user.verify(request.form.get('password', '')):
            login_user(user)
            return redirect(url_for('home'))
        flash('Неверная почта или пароль.', 'error')
    return render_template('auth.html', register=False)


@app.post('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/subjects')
def subjects_page():
    return render_template('subjects.html', exam_type=chosen_exam())


@app.route('/subject/<subject>')
def subject_page(subject):
    if subject != 'math':
        abort(404)
    exam_type = chosen_exam()
    questions = visible_questions(Question.query.filter_by(subject=subject, exam=exam_type).order_by(Question.id).all())
    selected = request.args.get('number', type=int)
    if selected and selected not in dict(CATALOG[exam_type]):
        abort(404)
    if selected:
        questions = [q for q in questions if number_of(q) == selected]
    categories = sorted({q.topic for q in questions})
    topic = request.args.get('topic', '').strip()[:100]
    if topic:
        questions = [q for q in questions if q.topic == topic]
    return render_template('subject.html', subject=subject, questions=questions, selected=selected, exam_type=exam_type, topic=topic, categories=categories)


@app.route('/constructor', methods=['GET', 'POST'])
def constructor():
    """Author-built practice sets. No registration is required."""
    exam_type = chosen_exam()
    available = visible_questions(Question.query.filter_by(subject='math', exam=exam_type).order_by(Question.id).all())
    by_number = {}
    for q in available:
        num = number_of(q)
        if num:
            by_number.setdefault(num, []).append(q)
    selected = session.get('custom_set', {})
    if request.method == 'POST':
        requested = []
        for raw in request.form.getlist('numbers'):
            try:
                num = int(raw)
            except ValueError:
                continue
            if num in by_number and num not in requested:
                requested.append(num)
        if not requested:
            flash('Выбери хотя бы один номер задания.', 'error')
        else:
            try:
                count = min(5, max(1, int(request.form.get('per_number', '1'))))
            except ValueError:
                count = 1
            rng = random.SystemRandom()
            ids = []
            for num in requested:
                ids.extend(q.id for q in rng.sample(by_number[num], min(count, len(by_number[num]))))
            rng.shuffle(ids)
            # Limit size of session cookie; server database holds task content.
            ids = ids[:35]
            session['custom_set'] = {'exam': exam_type, 'ids': ids}
            return redirect(url_for('custom_variant'))
    counts = {n: len(by_number.get(n, [])) for n, _ in CATALOG[exam_type]}
    return render_template('constructor.html', exam_type=exam_type, counts=counts)


@app.route('/my-variant', methods=['GET', 'POST'])
def custom_variant():
    data = session.get('custom_set') or {}
    ids = data.get('ids', [])
    if not ids:
        return redirect(url_for('constructor'))
    questions = visible_questions(Question.query.filter(Question.id.in_(ids)).all())
    lookup = {q.id: q for q in questions}
    ordered = [lookup[qid] for qid in ids if qid in lookup]
    results = None
    if request.method == 'POST':
        results = []
        for q in ordered:
            raw = request.form.get(f'q_{q.id}', '').strip()
            manual = MANUAL_LOOKUP.get(q.body)
            if manual:
                correct = same_answer(raw, manual[0]) if raw else False
                expected = manual[0]
                index = -1
            else:
                try:
                    index = int(raw)
                except (ValueError, TypeError):
                    index = -1
                correct = index == q.correct_index
                expected = q.options[q.correct_index]
            results.append((q, raw, correct, expected))
            if raw and current_user.is_authenticated and current_user.role == 'student':
                db.session.add(Attempt(user_id=current_user.id, question_id=q.id, answer_index=index, is_correct=correct))
        if current_user.is_authenticated and current_user.role == 'student':
            db.session.commit()
    return render_template('custom_variant.html', questions=ordered, exam_type=data.get('exam', 'oge'),
                           results=results, diagrams=DIAGRAMS, manual_lookup=MANUAL_LOOKUP)


@app.route('/question/<int:qid>', methods=['GET', 'POST'])
def question(qid):
    q = db.get_or_404(Question, qid)
    if is_archived(q.id): abort(404)
    if q.subject != 'math':
        abort(404)
    manual = MANUAL_LOOKUP.get(q.body)
    result = None
    if request.method == 'POST':
        answer_index = -1
        if manual is not None:
            written = request.form.get('written_answer', '').strip()[:70]
            if written:
                result = same_answer(written, manual[0])
            else:
                flash('Введите ответ.', 'error')
        else:
            try:
                answer_index = int(request.form.get('answer', '-1'))
            except (ValueError, TypeError):
                pass
            if 0 <= answer_index < len(q.options):
                result = answer_index == q.correct_index
            else:
                flash('Выберите ответ.', 'error')
        if result is not None and current_user.is_authenticated and current_user.role == 'student':
            db.session.add(Attempt(user_id=current_user.id, question_id=q.id,
                                   answer_index=answer_index, is_correct=result))
            db.session.commit()
    is_favorite = bool(current_user.is_authenticated and Favorite.query.filter_by(user_id=current_user.id, question_id=q.id).first())
    return render_template('question.html', q=q, result=result, manual=manual,
                           diagram=DIAGRAMS.get(q.body), is_favorite=is_favorite,
                           difficulty=difficulty_of(q))


@app.post('/favorite/<int:qid>')
@student_only
def toggle_favorite(qid):
    q = db.get_or_404(Question, qid)
    existing = Favorite.query.filter_by(user_id=current_user.id, question_id=q.id).first()
    if existing:
        db.session.delete(existing)
        flash('Убрано из избранного.', 'info')
    else:
        db.session.add(Favorite(user_id=current_user.id, question_id=q.id))
        flash('Добавлено в избранное.', 'success')
    db.session.commit()
    return redirect(url_for('question', qid=q.id))


@app.route('/favorites')
@student_only
def favorites():
    rows = db.session.query(Question).join(Favorite, Favorite.question_id == Question.id).filter(
        Favorite.user_id == current_user.id, Question.subject == 'math').order_by(Favorite.id.desc()).all()
    rows = visible_questions(rows)
    return render_template('favorites.html', questions=rows)


def difficulty_of(q):
    number = number_of(q) or 0
    if q.exam == 'oge':
        return 'Сложный' if number >= 20 else ('Средний' if number >= 13 else 'Базовый')
    return 'Сложный' if number >= 13 else ('Средний' if number >= 8 else 'Базовый')


@app.route('/search')
def search_questions():
    exam_type = chosen_exam()
    phrase = request.args.get('q', '').strip()[:120]
    difficulty = request.args.get('difficulty', '')
    qs = visible_questions(Question.query.filter_by(subject='math', exam=exam_type).all())
    if phrase:
        qs = [q for q in qs if phrase.casefold() in (q.body+' '+q.topic+' '+str(number_of(q))).casefold()]
    if difficulty in ('Базовый', 'Средний', 'Сложный'):
        qs = [q for q in qs if difficulty_of(q) == difficulty]
    return render_template('search.html', questions=qs[:120], total=len(qs), phrase=phrase,
                           difficulty=difficulty, exam_type=exam_type, difficulty_of=difficulty_of)


@app.route('/extended/<int:qid>', methods=['GET', 'POST'])
def extended(qid):
    q = db.get_or_404(Question, qid)
    if q.exam != 'ege' or (number_of(q) or 0) < 13:
        abort(404)
    response = None
    if request.method == 'POST':
        response = request.form.get('solution', '').strip()[:6000]
        if not response:
            flash('Введите развёрнутое решение.', 'error')
            response = None
        elif current_user.is_authenticated and current_user.role == 'student':
            db.session.add(ExtendedAnswer(user_id=current_user.id, question_id=q.id, response=response))
            db.session.commit()
    return render_template('extended.html', q=q, response=response, diagram=DIAGRAMS.get(q.body), number=number_of(q))


@app.post('/extended/<int:qid>/score')
@student_only
def extended_score(qid):
    entry = ExtendedAnswer.query.filter_by(user_id=current_user.id, question_id=qid).order_by(ExtendedAnswer.id.desc()).first()
    if entry:
        try:
            score = int(request.form.get('score', ''))
        except (ValueError, TypeError):
            score = -1
        if 0 <= score <= 3:
            entry.self_score = score
            db.session.commit()
            flash('Самооценка сохранена.', 'success')
    return redirect(url_for('extended', qid=qid))


@app.route('/theory')
def theory():
    exam_type = chosen_exam()
    questions = visible_questions(Question.query.filter_by(subject='math', exam=exam_type).order_by(Question.id).all())
    return render_template('theory.html', questions=questions, exam_type=exam_type)


@app.route('/progress')
@student_only
def progress():
    rows = db.session.query(Attempt, Question).join(Question, Question.id == Attempt.question_id).filter(Attempt.user_id == current_user.id).order_by(Attempt.created_at.desc()).all()
    by_topic = {}
    for a, q in rows:
        stat = by_topic.setdefault(q.topic, [0, 0])
        stat[0] += 1
        stat[1] += int(a.is_correct)
    topic_stats = sorted([(k, v[0], v[1], round(v[1] * 100 / v[0])) for k, v in by_topic.items()], key=lambda x: (x[3], -x[1]))
    runs = MockExam.query.filter_by(user_id=current_user.id).filter(MockExam.finished_at.isnot(None)).order_by(MockExam.finished_at.desc()).limit(10).all()
    return render_template('progress.html', rows=rows, count=len(rows), correct=sum(a.is_correct for a, _ in rows), topic_stats=topic_stats, runs=runs)


@app.route('/assistant', methods=['GET', 'POST'])
@login_required
def assistant():
    response = None
    if request.method == 'POST':
        topic = request.form.get('topic', '').strip()[:400]
        if os.environ.get('OPENAI_API_KEY') and request.form.get('use_ai') == '1':
            try:
                payload = json.dumps({
                    'model': os.environ.get('OPENAI_MODEL', 'gpt-4.1-mini'),
                    'instructions': (
                        'Ты русскоязычный преподаватель математики для школьников 9–11 классов. '
                        'Помогай разобраться пошагово, не выдавай выдуманные факты. '
                        'Готовь только к ОГЭ и профильному ЕГЭ; никогда не проси персональные данные. '
                        'Ответ — до 1000 символов.'
                    ),
                    'input': topic,
                    'max_output_tokens': 500,
                }, ensure_ascii=False).encode('utf-8')
                req = urllib.request.Request(
                    'https://api.openai.com/v1/responses',
                    data=payload,
                    headers={
                        'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'],
                        'Content-Type': 'application/json',
                    },
                    method='POST',
                )
                with urllib.request.urlopen(req, timeout=18) as r:
                    data = json.loads(r.read())
                response = ' '.join(
                    chunk.get('text', '')
                    for item in data.get('output', [])
                    for chunk in item.get('content', [])
                    if chunk.get('type') == 'output_text'
                ).strip()
                if not response:
                    response = 'Ответ не получен. Попробуй сформулировать вопрос иначе.'
            except Exception:
                response = 'Сервис ИИ временно недоступен. Попробуй локальную подсказку без ИИ.'
        else:
            keyword = topic.lower()
            matching = [
                q for q in visible_questions(Question.query.filter_by(subject='math', exam=user_exam()).all())
                if any(w in (q.topic + ' ' + q.body).lower() for w in keyword.split() if len(w) >= 4)
            ]
            if matching:
                q = matching[0]
                response = f'Похоже, поможет тема «{q.topic}». {q.theory} Пример: {q.explanation}'
            else:
                response = 'Попробуй назвать конкретную тему: например, «дроби», «уравнения» или «геометрия». Я покажу подсказку из нашей базы знаний.'
    return render_template('assistant.html', response=response, ai_available=bool(os.environ.get('OPENAI_API_KEY')))


@app.route('/join', methods=['POST'])
@student_only
def join():
    code = request.form.get('code', '').strip().upper()
    group = Group.query.filter_by(invite_code=code).first()
    if not group:
        flash('Группа с таким кодом не найдена.', 'error')
    elif Membership.query.filter_by(student_id=current_user.id, group_id=group.id).first():
        flash('Вы уже в этой группе.', 'info')
    else:
        db.session.add(Membership(student_id=current_user.id, group_id=group.id))
        db.session.commit()
        flash('Вы присоединились к группе!', 'success')
    return redirect(url_for('home'))


@app.route('/teacher', methods=['GET', 'POST'])
@teacher_only
def teacher():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()[:100]
        if not name:
            flash('Введите название группы.', 'error')
        else:
            code = secrets.token_hex(4).upper()
            db.session.add(Group(name=name, teacher_id=current_user.id, invite_code=code))
            db.session.commit()
            flash('Группа создана.', 'success')
        return redirect(url_for('teacher'))
    groups = Group.query.filter_by(teacher_id=current_user.id).all()
    return render_template('teacher.html', groups=groups)


@app.route('/teacher/group/<int:gid>', methods=['GET', 'POST'])
@teacher_only
def teacher_group(gid):
    group = db.get_or_404(Group, gid)
    if group.teacher_id != current_user.id:
        abort(403)
    if request.method == 'POST':
        try:
            qid = int(request.form.get('question_id', '0'))
        except ValueError:
            qid = 0
        if (q := db.session.get(Question, qid)) and q.subject == 'math' and not Assignment.query.filter_by(group_id=gid, question_id=qid).first():
            db.session.add(Assignment(group_id=gid, question_id=qid))
            db.session.commit()
            flash('Задание назначено.', 'success')
        return redirect(url_for('teacher_group', gid=gid))
    members = db.session.query(User).join(Membership, Membership.student_id == User.id).filter(Membership.group_id == gid).all()
    assignments = db.session.query(Question).join(Assignment, Assignment.question_id == Question.id).filter(Assignment.group_id == gid).all()
    questions = visible_questions(Question.query.filter_by(subject='math').all())
    stats = {u.id: (lambda a: (len(a), sum(x.is_correct for x in a)))(Attempt.query.filter_by(user_id=u.id).all()) for u in members}
    return render_template('teacher_group.html', group=group, members=members, assignments=assignments, questions=questions, stats=stats)


@app.route('/exam', methods=['GET', 'POST'])
@student_only
def exam():
    exam_type = user_exam()
    if request.method == 'POST':
        all_q = visible_questions(Question.query.filter_by(subject='math', exam=exam_type).all())
        picked = {}
        for q in all_q:
            n = number_of(q)
            if n and n not in picked:
                picked[n] = q.id
        ids = [picked[n] for n in sorted(picked)]
        if not ids:
            flash('Заданий пока нет.', 'error')
            return redirect(url_for('subjects_page'))
        run = MockExam(user_id=current_user.id, exam=exam_type, question_ids=ids)
        db.session.add(run)
        db.session.commit()
        return redirect(url_for('exam_run', run_id=run.id))
    past = MockExam.query.filter_by(user_id=current_user.id).order_by(MockExam.started_at.desc()).limit(10).all()
    available = len({number_of(q) for q in visible_questions(Question.query.filter_by(subject='math', exam=exam_type).all()) if number_of(q)})
    return render_template('exam.html', past=past, available=available, minutes=EXAM_MINUTES[exam_type])


@app.route('/exam/<int:run_id>', methods=['GET', 'POST'])
@student_only
def exam_run(run_id):
    run = db.get_or_404(MockExam, run_id)
    if run.user_id != current_user.id:
        abort(403)
    qs = Question.query.filter(Question.id.in_(run.question_ids)).all()
    ordered = {q.id: q for q in qs}
    qs = [ordered[qid] for qid in run.question_ids if qid in ordered]
    if request.method == 'POST':
        if run.finished_at is not None:
            return redirect(url_for('exam_run', run_id=run.id))
        answers = {}
        score = 0
        for q in qs:
            raw = request.form.get(f'q_{q.id}', '').strip()[:70]
            manual = MANUAL_LOOKUP.get(q.body)
            if manual:
                correct = bool(raw) and same_answer(raw, manual[0])
                answers[str(q.id)] = raw
                answer_index = -1
            else:
                try:
                    answer_index = int(raw)
                except (TypeError, ValueError):
                    answer_index = -1
                if not 0 <= answer_index < len(q.options):
                    answer_index = -1
                answers[str(q.id)] = answer_index
                correct = answer_index == q.correct_index
            score += int(correct)
            if raw and current_user.role == 'student':
                db.session.add(Attempt(user_id=current_user.id, question_id=q.id,
                                       answer_index=answer_index, is_correct=correct))
        run.responses = answers
        run.score = score
        run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()
        return redirect(url_for('exam_run', run_id=run.id))
    seconds_left = max(0, EXAM_MINUTES[run.exam] * 60 - int((datetime.now(timezone.utc).replace(tzinfo=None) - run.started_at).total_seconds()))
    return render_template('exam_run.html', run=run, qs=qs, seconds_left=seconds_left, manual_lookup=MANUAL_LOOKUP, diagrams=DIAGRAMS, same_answer=same_answer)


@app.route('/mistakes')
@student_only
def mistakes():
    attempts = Attempt.query.filter_by(user_id=current_user.id).order_by(Attempt.created_at.desc()).all()
    newest = {}
    for a in attempts:
        newest.setdefault(a.question_id, a)
    wrong_ids = [qid for qid, a in newest.items() if not a.is_correct]
    qs = Question.query.filter(Question.id.in_(wrong_ids)).all() if wrong_ids else []
    return render_template('mistakes.html', qs=qs)


SEED = [
    ('oge', 'Линейные уравнения', 'Реши уравнение: 3x + 7 = 22', ['3', '5', '7', '9'], 1, 'Вычитаем 7: 3x = 15. Делим на 3: x = 5.', 'Чтобы решить линейное уравнение, перенеси числа в одну часть, а неизвестные — в другую.'),
    ('oge', 'Дроби', 'Вычисли: 1/2 + 1/4', ['1/6', '2/6', '3/4', '1'], 2, '1/2 = 2/4, поэтому 2/4 + 1/4 = 3/4.', 'Для сложения дробей приведи их к общему знаменателю.'),
    ('oge', 'Проценты', 'Найди 20% от 250.', ['25', '40', '50', '75'], 2, '250 × 0,2 = 50.', 'Чтобы найти процент от числа, умножь число на процент, записанный десятичной дробью.'),
    ('oge', 'Степени', 'Найди значение 2³ × 2².', ['16', '24', '32', '64'], 2, '2³ × 2² = 2⁵ = 32.', 'При умножении степеней с одинаковыми основаниями показатели складывают.'),
    ('oge', 'Геометрия', 'Катеты прямоугольного треугольника равны 3 и 4. Найди гипотенузу.', ['5', '6', '7', '12'], 0, 'По теореме Пифагора c² = 3² + 4² = 25, значит c = 5.', 'В прямоугольном треугольнике квадрат гипотенузы равен сумме квадратов катетов.'),
    ('oge', 'Вероятность', 'В коробке 3 красных и 2 синих шара. Какова вероятность вытащить синий шар?', ['1/5', '2/5', '3/5', '1/2'], 1, 'Всего 5 шаров, благоприятных исходов 2, поэтому вероятность 2/5.', 'Для равновозможных исходов вероятность равна отношению благоприятных исходов ко всем исходам.'),
    ('ege', 'Показательные уравнения', 'Реши уравнение: 2ˣ = 16.', ['2', '3', '4', '8'], 2, '16 = 2⁴, следовательно x = 4.', 'При одинаковых основаниях больше 0 и не равных 1 показатели равны.'),
    ('ege', 'Логарифмы', 'Вычисли log₂(32).', ['4', '5', '6', '8'], 1, '2⁵ = 32, значит log₂(32) = 5.', 'Логарифм по основанию a от числа b — показатель степени, в которую надо возвести a для получения b.'),
    ('ege', 'Тригонометрия', 'Вычисли sin(π/6).', ['0', '1/2', '√2/2', '1'], 1, 'sin(π/6) = sin(30°) = 1/2.', 'Значения тригонометрических функций основных углов полезно знать наизусть.'),
    ('ege', 'Производная', 'Найди производную функции f(x) = x³.', ['x²', '2x', '3x²', '3x'], 2, 'По правилу (xⁿ)′ = nxⁿ⁻¹ получаем 3x².', 'Производная степенной функции xⁿ равна nxⁿ⁻¹.'),
    ('ege', 'Вероятность', 'Монету подбрасывают дважды. Какова вероятность двух орлов?', ['1/2', '1/3', '1/4', '1/8'], 2, 'Исходов 4: ОО, ОР, РО, РР. Благоприятный один, значит 1/4.', 'При независимых событиях вероятности перемножаются.'),
    ('ege', 'Планиметрия', 'Площадь круга радиуса 3 равна:', ['3π', '6π', '9π', '12π'], 2, 'S = πr² = π × 9 = 9π.', 'Площадь круга вычисляется по формуле S = πr².'),
]


NUMBERED_SAMPLES = [
    ('oge', 1, 'Практическая задача', 'Стоимость 3 одинаковых тетрадей — 90 рублей. Сколько стоит одна?', ['20', '30', '40', '90'], 1, '90 : 3 = 30.', 'Стоимость одной вещи равна общей цене, делённой на количество.'),
    ('oge', 1, 'Практическая задача', 'За 4 шоколадки заплатили 160 рублей. Сколько стоит одна шоколадка?', ['20', '30', '40', '50'], 2, '160 : 4 = 40.', 'Чтобы найти цену одной вещи, раздели общую стоимость на количество товаров.'),
    ('oge', 2, 'Практическая задача', 'Скидка 10% на товар стоимостью 800 рублей. Сколько рублей составит скидка?', ['8', '40', '80', '120'], 2, '10% от 800 — это 800 × 0,1 = 80.', 'Процент от числа находят умножением числа на десятичную дробь.'),
    ('oge', 2, 'Практическая задача', 'Билет стоил 500 рублей и подорожал на 20%. Сколько стал стоить билет?', ['520', '560', '600', '620'], 2, '20% от 500 — 100 рублей, значит новая цена 600.', 'После увеличения на p% число умножают на 1 + p/100.'),
    ('oge', 3, 'Практическая задача', 'На покупку 6 ручек потратили 240 рублей. Сколько рублей стоят 2 такие ручки?', ['40', '60', '80', '120'], 2, 'Одна ручка стоит 240 : 6 = 40 рублей, две — 80 рублей.', 'Сначала найди цену одной единицы, затем умножь на нужное количество.'),
    ('oge', 3, 'Практическая задача', 'Автобус ехал 3 часа со скоростью 60 км/ч. Какой путь он прошёл?', ['120', '150', '180', '200'], 2, 's = v × t = 60 × 3 = 180.', 'Путь равен произведению скорости на время.'),
    ('oge', 4, 'Практическая задача', 'В классе 12 девочек и 8 мальчиков. Какую часть класса составляют мальчики?', ['2/3', '2/5', '3/5', '4/5'], 1, 'Всего 20 учеников, мальчиков 8. Доля = 8/20 = 2/5.', 'Доля части равна отношению количества этой части ко всему количеству.'),
    ('oge', 4, 'Практическая задача', 'Из 25 вопросов Маша решила 20. Какую часть вопросов она решила?', ['1/5', '4/5', '5/4', '20/25'], 1, '20 из 25 — это 20/25 = 4/5.', 'Сокращай дробь, если это возможно.'),
    ('oge', 5, 'Практическая задача', 'Поезд отправился в 14:35 и ехал 2 часа 20 минут. Во сколько он прибыл?', ['16:45', '16:55', '17:05', '17:15'], 1, '14:35 + 2 часа = 16:35, ещё 20 минут = 16:55.', 'При работе со временем удобно прибавлять отдельно часы и минуты.'),
    ('oge', 5, 'Практическая задача', 'Урок начался в 9:10 и длился 45 минут. Во сколько он закончился?', ['9:45', '9:50', '9:55', '10:05'], 2, '9:10 + 45 минут = 9:55.', 'Суммируй минуты аккуратно, переходя через целый час при необходимости.'),
    ('oge', 6, 'Вычисления', 'Вычисли: 2,4 + 0,6.', ['2,8', '3', '3,2', '24,6'], 1, '2,4 + 0,6 = 3.', 'Десятичные дроби складывают поразрядно.'),
    ('oge', 6, 'Вычисления', 'Вычисли: 7,2 : 0,9.', ['6', '7', '8', '9'], 2, '7,2 : 0,9 = 8.', 'Можно умножить делимое и делитель на 10 и разделить 72 на 9.'),
    ('oge', 7, 'Числа на прямой', 'Какое из чисел больше: −2 или −5?', ['−5', '−2', 'Равны', 'Нельзя сравнить'], 1, '−2 находится правее −5 на числовой прямой.', 'Чем правее число на оси, тем оно больше.'),
    ('oge', 7, 'Числа на прямой', 'Какое число расположено между 1,2 и 1,4?', ['1,1', '1,25', '1,45', '2'], 1, '1,25 больше 1,2 и меньше 1,4.', 'Чтобы сравнить десятичные дроби, смотри на их разряды.'),
    ('oge', 8, 'Алгебраические выражения', 'Упрости: 2a + 3a.', ['5a', '6a', '5a²', 'a'], 0, 'Складываем коэффициенты: 2a + 3a = 5a.', 'Подобные слагаемые имеют одинаковую буквенную часть.'),
    ('oge', 8, 'Алгебраические выражения', 'Упрости: 4x − x + 2x.', ['5x', '6x', '7x', '8x'], 0, '4x − x + 2x = 5x.', 'Сначала складывай коэффициенты при одинаковой переменной.'),
    ('oge', 9, 'Уравнения', 'Реши уравнение: 5x = 35.', ['5', '6', '7', '8'], 2, 'x = 35 : 5 = 7.', 'Чтобы решить уравнение вида ax = b, раздели обе части на a.'),
    ('oge', 9, 'Уравнения', 'Реши уравнение: x − 12 = 8.', ['4', '20', '−4', '96'], 1, 'К обеим частям прибавим 12: x = 20.', 'Если из x вычли число, прибавь это число обратно.'),
    ('oge', 10, 'Вероятность', 'В мешке 5 белых и 5 чёрных шаров. Какова вероятность достать белый шар?', ['1/10', '1/5', '1/2', '5/2'], 2, 'Белых 5 из 10, значит вероятность 5/10 = 1/2.', 'Вероятность = благоприятные исходы / все исходы.'),
    ('oge', 10, 'Вероятность', 'Кубик бросают один раз. Какова вероятность выпадения числа 6?', ['1/3', '1/6', '1/2', '1/12'], 1, 'У правильного кубика 6 равновозможных исходов, благоприятный один.', 'Для симметричного кубика все грани равновероятны.'),
    ('oge', 11, 'Функции', 'Какое значение y у функции y = 2x + 1 при x = 3?', ['5', '6', '7', '8'], 2, '2 × 3 + 1 = 7.', 'Подставь значение x в формулу функции.'),
    ('oge', 11, 'Функции', 'Найди значение функции y = x² при x = −4.', ['−16', '8', '16', '−8'], 2, '(−4)² = 16.', 'Квадрат отрицательного числа положителен.'),
    ('oge', 12, 'Формулы', 'Найди путь при скорости 60 км/ч за 2 часа.', ['30 км', '60 км', '120 км', '180 км'], 2, 's = v × t = 60 × 2 = 120 км.', 'Путь равен произведению скорости на время.'),
    ('oge', 12, 'Формулы', 'Найди периметр прямоугольника со сторонами 3 см и 5 см.', ['8 см', '10 см', '15 см', '16 см'], 3, 'P = 2(a + b) = 2(3 + 5) = 16.', 'Периметр прямоугольника равен удвоенной сумме длины и ширины.'),
    ('oge', 13, 'Неравенства', 'Реши неравенство: x + 2 > 5.', ['x > 3', 'x < 3', 'x > 7', 'x < 7'], 0, 'Вычти 2 из обеих частей: x > 3.', 'При прибавлении или вычитании одного и того же числа знак неравенства сохраняется.'),
    ('oge', 13, 'Неравенства', 'Реши неравенство: 3x < 12.', ['x < 4', 'x > 4', 'x < 9', 'x > 9'], 0, 'Делим обе части на 3: x < 4.', 'При делении на положительное число знак неравенства не меняется.'),
    ('oge', 14, 'Прогрессии', 'Найди четвёртый член последовательности 2, 5, 8, ...', ['9', '10', '11', '12'], 2, 'Разность 3, четвёртый член 8 + 3 = 11.', 'В арифметической прогрессии каждый следующий член увеличивается на одно и то же число.'),
    ('oge', 14, 'Прогрессии', 'Найди следующий член последовательности 15, 12, 9, ...', ['3', '5', '6', '7'], 2, 'Разность равна −3, значит следующий член 9 − 3 = 6.', 'Арифметическая прогрессия может как возрастать, так и убывать.'),
    ('oge', 15, 'Геометрия', 'Катеты прямоугольного треугольника равны 6 и 8. Найди гипотенузу.', ['10', '12', '14', '16'], 0, 'c = √(6² + 8²) = √100 = 10.', 'Используй теорему Пифагора.'),
    ('oge', 15, 'Геометрия', 'У равнобедренного треугольника боковые стороны по 5, основание 6. Каков периметр?', ['10', '11', '16', '21'], 2, 'Периметр равен сумме всех сторон: 5 + 5 + 6 = 16.', 'Периметр — это сумма длин всех сторон фигуры.'),
    ('oge', 16, 'Окружность', 'Чему равен диаметр окружности с радиусом 7?', ['3,5', '7', '14', '49'], 2, 'Диаметр равен двум радиусам: 2 × 7 = 14.', 'Формула диаметра: d = 2r.'),
    ('oge', 16, 'Окружность', 'Радиус окружности равен 4. Чему равна длина диаметра?', ['2', '4', '6', '8'], 3, 'Диаметр — это два радиуса: 2 × 4 = 8.', 'Диаметр проходит через центр окружности.'),
    ('oge', 17, 'Площадь', 'Найди площадь прямоугольника со сторонами 4 и 6.', ['10', '20', '24', '48'], 2, 'S = 4 × 6 = 24.', 'Площадь прямоугольника равна произведению его сторон.'),
    ('oge', 17, 'Площадь', 'Площадь квадрата со стороной 5 равна:', ['10', '20', '25', '50'], 2, 'S = a² = 25.', 'Площадь квадрата равна квадрату его стороны.'),
    ('oge', 18, 'Геометрия', 'Сумма углов треугольника равна:', ['90°', '180°', '270°', '360°'], 1, 'Сумма внутренних углов любого треугольника равна 180°.', 'Это одно из основных свойств треугольника.'),
    ('oge', 18, 'Геометрия', 'Один угол треугольника 70°, другой 50°. Чему равен третий угол?', ['50°', '60°', '70°', '80°'], 1, '180° − 70° − 50° = 60°.', 'Сумма углов треугольника равна 180°.'),
    ('oge', 19, 'Геометрические утверждения', 'Верно ли: диагонали прямоугольника равны?', ['Да', 'Нет', 'Только у квадрата', 'Неизвестно'], 0, 'Да, диагонали любого прямоугольника равны.', 'Это одно из свойств прямоугольника.'),
    ('oge', 19, 'Геометрические утверждения', 'Верно ли: у ромба все стороны равны?', ['Да', 'Нет', 'Только две стороны', 'Только при остром угле'], 0, 'По определению ромба все его стороны равны.', 'Ромб — это параллелограмм с равными сторонами.'),
    ('oge', 20, 'Уравнения и неравенства', 'Реши: x² = 9. Сколько действительных корней?', ['0', '1', '2', '3'], 2, 'Корни: −3 и 3. Всего два.', 'Уравнение x² = a при a > 0 имеет два действительных корня.'),
    ('oge', 20, 'Уравнения и неравенства', 'Какое из чисел является корнем уравнения x² − 4 = 0?', ['1', '2', '3', '4'], 1, 'x² = 4, значит x = ±2. Среди вариантов есть 2.', 'Перенеси свободный член и найди квадратный корень.'),
    ('oge', 21, 'Текстовые задачи', 'Поезд проехал 150 км за 3 часа. Найди среднюю скорость.', ['30', '40', '50', '60'], 2, '150 / 3 = 50 км/ч.', 'Средняя скорость равна отношению пути ко времени.'),
    ('oge', 21, 'Текстовые задачи', 'За 5 одинаковых блокнотов заплатили 350 рублей. Сколько стоит один блокнот?', ['60', '65', '70', '75'], 2, '350 : 5 = 70.', 'Чтобы найти стоимость единицы товара, раздели общую сумму на количество.'),
    ('oge', 22, 'Графики функций', 'Какой график у функции y = x²?', ['Прямая', 'Парабола', 'Окружность', 'Гипербола'], 1, 'График y = x² — парабола.', 'Квадратичная функция задаёт параболу.'),
    ('oge', 22, 'Графики функций', 'Какой график у функции y = kx + b?', ['Парабола', 'Окружность', 'Прямая', 'Гипербола'], 2, 'Функция вида y = kx + b линейная, её график — прямая.', 'Линейные функции изображаются прямыми.'),
    ('oge', 23, 'Геометрия', 'Найди третий угол треугольника, если два равны 40° и 60°.', ['60°', '70°', '80°', '100°'], 2, '180 − 40 − 60 = 80°.', 'Сумма углов треугольника равна 180°.'),
    ('oge', 23, 'Геометрия', 'В равнобедренном треугольнике угол при вершине равен 40°. Чему равен каждый угол при основании?', ['40°', '60°', '70°', '80°'], 2, 'Оставшиеся 140° делятся поровну: по 70°.', 'В равнобедренном треугольнике углы при основании равны.'),
    ('oge', 24, 'Геометрия', 'Равны ли вертикальные углы?', ['Да', 'Нет', 'Только острые', 'Только тупые'], 0, 'Да, вертикальные углы равны.', 'Вертикальные углы образуются при пересечении двух прямых.'),
    ('oge', 24, 'Геометрия', 'Смежные углы в сумме дают:', ['90°', '120°', '180°', '360°'], 2, 'Смежные углы образуют развернутый угол, равный 180°.', 'Это базовое свойство смежных углов.'),
    ('oge', 25, 'Геометрия', 'В квадрате диагональ равна 2√2. Найди сторону.', ['1', '2', '√2', '4'], 1, 'a√2 = 2√2, значит a = 2.', 'Диагональ квадрата выражается формулой d = a√2.'),
    ('oge', 25, 'Геометрия', 'Сторона квадрата равна 6. Чему равна его диагональ?', ['6', '6√2', '12', '12√2'], 1, 'd = a√2 = 6√2.', 'У квадрата диагональ в √2 раза больше стороны.'),

    ('ege', 1, 'Планиметрия', 'Площадь прямоугольного треугольника с катетами 6 и 8 равна:', ['14', '24', '48', '56'], 1, 'S = 6 × 8 / 2 = 24.', 'Площадь прямоугольного треугольника равна половине произведения катетов.'),
    ('ege', 1, 'Планиметрия', 'У трапеции основания 4 и 10, высота 3. Найди площадь.', ['18', '21', '24', '42'], 1, 'S = (4 + 10) / 2 × 3 = 21.', 'Площадь трапеции: полусумма оснований, умноженная на высоту.'),
    ('ege', 2, 'Векторы', 'Даны векторы (1; 2) и (3; 4). Найди их сумму.', ['(2; 2)', '(4; 6)', '(3; 8)', '(1; 4)'], 1, 'Складываем координаты: (1 + 3; 2 + 4) = (4; 6).', 'У суммы векторов соответствующие координаты складываются.'),
    ('ege', 2, 'Векторы', 'Чему равен вектор (5; −1) − (2; 3)?', ['(3; −4)', '(7; 2)', '(3; 4)', '(−3; 4)'], 0, 'Вычитаем координаты: (5 − 2; −1 − 3) = (3; −4).', 'Разность векторов находят покоординатно.'),
    ('ege', 3, 'Стереометрия', 'Объём куба с ребром 3 равен:', ['9', '18', '27', '36'], 2, 'V = a³ = 27.', 'Объём куба равен кубу длины его ребра.'),
    ('ege', 3, 'Стереометрия', 'Площадь полной поверхности куба с ребром 2 равна:', ['8', '16', '24', '32'], 2, '6 граней по 2² = 4, значит 6 × 4 = 24.', 'Площадь полной поверхности куба равна 6a².'),
    ('ege', 4, 'Вероятность', 'Вероятность попадания в цель равна 0,7. Какова вероятность промаха?', ['0,1', '0,2', '0,3', '0,7'], 2, 'Вероятность противоположного события: 1 − 0,7 = 0,3.', 'Сумма вероятностей противоположных событий равна 1.'),
    ('ege', 4, 'Вероятность', 'Из колоды с 4 картами: туз, король, дама, валет. Какова вероятность вынуть даму?', ['1/2', '1/3', '1/4', '1/5'], 2, 'Благоприятный исход один из четырёх.', 'При равновозможных исходах вероятность — отношение благоприятных исходов ко всем.'),
    ('ege', 5, 'Вероятность', 'Монету подбрасывают дважды. Какова вероятность, что орёл выпадет хотя бы один раз?', ['1/4', '1/2', '3/4', '1'], 2, 'Не выпадет орёл только в случае РР: вероятность 1/4. Значит хотя бы один орёл: 1 − 1/4 = 3/4.', 'Удобно использовать вероятность противоположного события.'),
    ('ege', 5, 'Вероятность', 'В коробке 2 красных и 3 зелёных фишки. Какова вероятность достать зелёную?', ['2/5', '3/5', '1/2', '5/3'], 1, 'Зелёных 3 из 5, значит вероятность 3/5.', 'Вероятность не может быть больше 1.'),
    ('ege', 6, 'Уравнения', 'Реши: 3ˣ = 81.', ['2', '3', '4', '5'], 2, '81 = 3⁴, значит x = 4.', 'Если основания одинаковы, то равны и показатели.'),
    ('ege', 6, 'Уравнения', 'Реши: log₂x = 3.', ['3', '5', '8', '9'], 2, 'Если log₂x = 3, то x = 2³ = 8.', 'Логарифмическое уравнение можно переписать в показательной форме.'),
    ('ege', 7, 'Вычисления', 'Вычисли √144.', ['10', '11', '12', '14'], 2, '12² = 144, значит арифметический корень равен 12.', 'Арифметический квадратный корень — неотрицательное число.'),
    ('ege', 7, 'Вычисления', 'Вычисли: 2⁵ / 2².', ['4', '6', '8', '16'], 2, '2⁵ / 2² = 2³ = 8.', 'При делении степеней с одинаковыми основаниями показатели вычитают.'),
    ('ege', 8, 'Производная', 'Найди производную функции y = x³.', ['x²', '2x', '3x²', '3x'], 2, 'По правилу (xⁿ)′ = nxⁿ⁻¹ получаем 3x².', 'Степенная функция дифференцируется по формуле nxⁿ⁻¹.'),
    ('ege', 8, 'Производная', 'Найди производную функции y = 5x².', ['5x', '10x', '25x', '2x'], 1, 'Коэффициент сохраняется: (5x²)′ = 10x.', 'Постоянный множитель выносится за знак производной.'),
    ('ege', 9, 'Прикладные задачи', 'Мощность равна 100 Вт. Сколько энергии за 2 секунды?', ['50 Дж', '100 Дж', '200 Дж', '400 Дж'], 2, 'E = P × t = 100 × 2 = 200 Дж.', 'Энергия равна произведению мощности на время.'),
    ('ege', 9, 'Прикладные задачи', 'Автомобиль расходует 8 л на 100 км. Сколько литров потребуется на 250 км?', ['16', '18', '20', '24'], 2, '250 км — это 2,5 раза по 100 км. Расход 8 × 2,5 = 20 л.', 'Используй пропорцию.'),
    ('ege', 10, 'Текстовые задачи', 'Путь 240 км пройден за 4 часа. Найди скорость.', ['40', '50', '60', '80'], 2, 'v = 240 / 4 = 60 км/ч.', 'Скорость равна отношению пути ко времени.'),
    ('ege', 10, 'Текстовые задачи', 'Один рабочий выполняет заказ за 6 дней. Сколько заказов он выполнит за 18 дней?', ['2', '3', '4', '6'], 1, '18 : 6 = 3 заказа.', 'Если производительность постоянна, количество работы пропорционально времени.'),
    ('ege', 11, 'Графики функций', 'Какой график имеет функция y = 1/x?', ['Прямая', 'Парабола', 'Гипербола', 'Окружность'], 2, 'y = 1/x — гипербола.', 'График обратной пропорциональности — гипербола.'),
    ('ege', 11, 'Графики функций', 'Какой график имеет функция y = x²?', ['Гипербола', 'Парабола', 'Прямая', 'Ломаная'], 1, 'График квадратичной функции — парабола.', 'Квадратичная функция задаётся формулой y = ax² + bx + c.'),
    ('ege', 12, 'Экстремумы', 'В какой точке функция y = (x − 2)² имеет минимум?', ['0', '1', '2', '4'], 2, 'Квадрат неотрицателен и обращается в ноль при x = 2.', 'Минимум квадрата выражения достигается, когда выражение равно нулю.'),
    ('ege', 12, 'Экстремумы', 'Наибольшее значение функции y = −(x − 1)² + 4 равно:', ['1', '2', '4', '5'], 2, 'Вершина параболы находится в точке x = 1, значение y = 4.', 'Если коэффициент перед x² отрицателен, ветви параболы направлены вниз.'),
    ('ege', 13, 'Уравнения', 'Реши уравнение: x² − 5x + 6 = 0. Сколько у него корней?', ['0', '1', '2', '3'], 2, '(x − 2)(x − 3) = 0, значит два корня.', 'Квадратное уравнение можно разложить на множители.'),
    ('ege', 13, 'Уравнения', 'Какой из чисел является корнем уравнения x² − 9 = 0?', ['1', '2', '3', '4'], 2, 'x² = 9, значит x = ±3. Среди вариантов есть 3.', 'После переноса можно извлечь квадратный корень.'),
    ('ege', 14, 'Стереометрия', 'Сколько граней имеет куб?', ['4', '6', '8', '12'], 1, 'У куба 6 квадратных граней.', 'Куб — правильный многогранник с шестью гранями.'),
    ('ege', 14, 'Стереометрия', 'Сколько рёбер у прямоугольного параллелепипеда?', ['8', '10', '12', '16'], 2, 'У прямоугольного параллелепипеда 12 рёбер.', 'Свойства параллелепипеда нужно помнить наизусть.'),
    ('ege', 15, 'Неравенства', 'Реши: 2ˣ > 8.', ['x > 2', 'x > 3', 'x < 3', 'x < 2'], 1, '8 = 2³; функция 2ˣ возрастает, значит x > 3.', 'Если основание больше 1, показательная функция возрастает.'),
    ('ege', 15, 'Неравенства', 'Реши неравенство: x² < 16. Какой промежуток подходит?', ['x > 4', '−4 < x < 4', 'x < −4', 'x ≤ 4'], 1, 'Число x должно лежать между −4 и 4.', 'Для неравенства x² < a² ответ: −a < x < a.'),
    ('ege', 16, 'Планиметрия', 'Площадь треугольника с основанием 10 и высотой 4 равна:', ['14', '20', '40', '80'], 1, 'S = 10 × 4 / 2 = 20.', 'Площадь треугольника равна половине произведения основания на высоту.'),
    ('ege', 16, 'Планиметрия', 'Длина окружности радиуса 5 равна:', ['5π', '10π', '20π', '25π'], 1, 'L = 2πr = 10π.', 'Длина окружности вычисляется по формуле 2πr.'),
    ('ege', 17, 'Финансовые задачи', 'Вклад 1000 ₽ увеличился за год на 10%. Сколько стало?', ['1010', '1050', '1100', '1200'], 2, '1000 × 1,1 = 1100 ₽.', 'Рост на 10% соответствует умножению на 1,1.'),
    ('ege', 17, 'Финансовые задачи', 'Цена товара 2000 ₽. После скидки 15% сколько он стоит?', ['1700', '1750', '1800', '1850'], 0, '2000 × 0,85 = 1700 ₽.', 'После скидки на p% число умножают на 1 − p/100.'),
    ('ege', 18, 'Параметры', 'При каком a уравнение x + a = 0 имеет корень x = 3?', ['−3', '0', '3', '6'], 0, '3 + a = 0, следовательно a = −3.', 'Подставь данный корень в уравнение и найди параметр.'),
    ('ege', 18, 'Параметры', 'При каком a значение выражения x + a при x = 5 равно 9?', ['2', '3', '4', '5'], 2, '5 + a = 9, значит a = 4.', 'Параметр находят как неизвестное число из обычного уравнения.'),
    ('ege', 19, 'Теория чисел', 'Сколько положительных делителей у числа 6?', ['2', '3', '4', '6'], 2, 'Делители: 1, 2, 3, 6. Их четыре.', 'Положительные делители делят число без остатка.'),
    ('ege', 19, 'Теория чисел', 'Какое из чисел является простым?', ['21', '25', '29', '33'], 2, '29 делится только на 1 и на 29.', 'Простое число имеет ровно два положительных делителя.'),
]



# Авторские задачи с ручным вводом. Не копии сторонних банков.
MANUAL_SAMPLES = []

def add_manual(exam, number, topic, body, answer, explanation, theory, diagram=None):
    MANUAL_SAMPLES.append((exam, number, topic, body, str(answer), explanation, theory, diagram))

# Три дополнительных варианта для каждого номера — без повторения прежних условий.
for n, topic in CATALOG['oge']:
    for k in range(1, 4):
        if n <= 5:
            count = n + k + 2
            price = (n + k + 3) * 10
            total = count * price
            add_manual('oge', n, 'Практические задачи', f'Задание №{n}. За {count} одинаковых блокнотов заплатили {total} рублей. Сколько стоит один блокнот?', price, f'{total} : {count} = {price} рублей.', 'Чтобы найти цену одного товара, раздели стоимость на количество.')
        elif n <= 8:
            a = n + k
            b = (k + 2) * 3
            add_manual('oge', n, topic, f'Задание №{n}. Вычисли: {a} × {b} − {a}.', a * (b - 1), f'{a} × {b} − {a} = {a * b} − {a} = {a * (b - 1)}.', 'Сначала умножение, затем вычитание.')
        elif n <= 14:
            root = n + k
            offset = k * 4
            add_manual('oge', n, topic, f'Задание №{n}. Найди x из уравнения {k + 2}x + {offset} = {(k + 2) * root + offset}.', root, f'Вычитаем {offset} и делим на {k+2}. Получаем x = {root}.', 'Одинаковые действия с двумя частями уравнения сохраняют равенство.')
        elif n <= 19:
            a, b = n - 10 + k, k + 3
            add_manual('oge', n, 'Геометрия', f'Задание №{n}. Прямоугольник имеет стороны {a} см и {b} см. Найди его площадь (в см²).', a * b, f'Площадь S = {a} × {b} = {a * b} см².', 'Площадь прямоугольника равна произведению длин сторон.', 'rectangle')
        elif n <= 22:
            root = n + k - 15
            add_manual('oge', n, topic, f'Задание №{n}. Найди положительный корень уравнения x² = {root * root}.', root, f'Положительный корень: √{root*root} = {root}.', 'Если x² = a², то x = ±a, при a > 0.')
        else:
            angle1 = 30 + k * 5
            angle2 = 45 + k * 5
            angle3 = 180-angle1-angle2
            add_manual('oge', n, 'Геометрия', f'Задание №{n}. В треугольнике ABC угол A равен {angle1}°, угол B — {angle2}°. Найди угол C (в градусах).', angle3, f'180 − {angle1} − {angle2} = {angle3}°.', 'Сумма углов треугольника равна 180°.', 'triangle')

for n, topic in CATALOG['ege']:
    for k in range(1, 4):
        if n in (1, 3, 14, 16):
            a = n + k + 1
            b = k + 3
            add_manual('ege', n, topic, f'Задание №{n}. Прямоугольный треугольник имеет катеты {a} и {b}. Найди площадь.', a*b/2 if a*b%2 else a*b//2, f'S = {a} × {b} / 2 = {a*b/2:g}.', 'Площадь прямоугольного треугольника равна половине произведения катетов.', 'right_triangle')
        elif n in (4, 5):
            good = k+1
            all_ = (k+1)*5
            add_manual('ege', n, 'Вероятность', f'Задание №{n}. В непрозрачном мешке {good} синих и {all_-good} белых фишек. Найди вероятность вытянуть синюю фишку (десятичной дробью).', '0,2', f'P = {good}/{all_} = 0,2.', 'Вероятность равна отношению благоприятных исходов ко всем равновозможным.')
        elif n in (6, 7, 13, 15):
            a = k+2
            power = k+2
            add_manual('ege', n, 'Уравнения и логарифмы', f'Задание №{n}. Реши: log_{a}(x) = {power}. Найди x.', a**power, f'По определению логарифма x = {a}^{power} = {a**power}.', 'Если logₐ(x) = b, то x = aᵇ, при a > 0 и a ≠ 1.')
        elif n in (8, 12):
            x=k+2
            add_manual('ege', n, 'Производная', f'Задание №{n}. Найди значение производной f(x) = {k+2}x² при x = {x}.', 2*(k+2)*x, f"f′(x) = {2*(k+2)}x, f′({x}) = {2*(k+2)*x}.", 'Производная ax² равна 2ax.')
        elif n == 18:
            x=k+2
            add_manual('ege', n, 'Параметры', f'Задание №18. При каком значении a уравнение {x}x + a = {x*x + 7} имеет корень x = {x}?', 7, f'Подставляем x = {x}: {x*x} + a = {x*x + 7}, поэтому a = 7.', 'Чтобы найти параметр, подставь заданный корень в уравнение.')
        elif n == 19:
            a = 2*(k+3)
            add_manual('ege', n, 'Теория чисел', f'Задание №19. Найди наибольший общий делитель чисел {a} и {a*3}.', a, f'Число {a*3} делится на {a}, поэтому НОД равен {a}.', 'Наибольший общий делитель двух чисел делит их оба.')
        else:
            a = n+k+2
            b = k+3
            add_manual('ege', n, topic, f'Задание №{n}. Найди значение выражения {a}² − {b}².', a*a-b*b, f'{a}² − {b}² = {a*a} − {b*b} = {a*a-b*b}.', 'Разность квадратов a² − b² = (a − b)(a + b).')

# Специализированные задания для тренировки ключевых тем профильного ЕГЭ.
for k in range(2, 11):
    add_manual('ege', 7, 'Логарифмы', f'Вычисли log₂({2**k}).', k, f'2^{k} = {2**k}, значит логарифм равен {k}.', 'Логарифм — показатель степени.')
    add_manual('ege', 8, 'Производная', f'Найди значение производной функции f(x) = {k}x³ при x = 1.', 3*k, f'f′(x) = {3*k}x², поэтому f′(1) = {3*k}.', 'Для степенной функции применяется правило (xⁿ)′ = nxⁿ⁻¹.')
    add_manual('ege', 18, 'Параметры', f'Найди a, если точка (2; {2*k+3}) лежит на прямой y = ax + 3.', k, f'{2*k+3} = 2a + 3, значит a = {k}.', 'Подставь координаты точки в уравнение прямой.')
    add_manual('ege', 14, 'Стереометрия', f'Объём куба с ребром {k} равен:', k**3, f'V = {k}³ = {k**3}.', 'Объём куба равен a³.', 'cube')

# Дополнительные авторские тренировки ОГЭ: условие, ответ, подробное решение.
# Номера используются как разделы тренажёра, а не как копия КИМ.
OGE_NEW_PRACTICE = [
(1,'Практические задачи','В магазине пачка из 5 тетрадей стоит 175 рублей. Сколько стоят 8 таких тетрадей?',280,'Цена одной тетради: 175 : 5 = 35 рублей. Восемь тетрадей стоят 35 × 8 = 280 рублей.','Задачи на стоимость решай через цену одной единицы.'),
(2,'Проценты','Кроссовки стоили 2400 рублей. На распродаже цена снизилась на 15%. Какова новая цена?',2040,'Размер скидки: 2400 × 0,15 = 360. Новая цена: 2400 − 360 = 2040 рублей.','После скидки 15% остаётся 85% исходной цены.'),
(3,'Практические задачи','На плане масштаб 1:200. Длина комнаты на плане 3,5 см. Найди её реальную длину в метрах.',7,'В реальности длина 3,5 × 200 = 700 см, или 7 метров.','В масштабе 1:n один сантиметр на плане соответствует n сантиметрам в действительности.'),
(4,'Практические задачи','На поездку нужно 42 литра топлива. Сколько полных канистр вместимостью 8 литров требуется минимум?',6,'42 : 8 = 5,25. Пяти канистр не хватит, поэтому нужно 6.','В задачах на количество целых ёмкостей результат иногда нужно округлить вверх.'),
(5,'Практические задачи','Маша вышла из дома в 08:45 и шла 1 час 35 минут. Введи время прибытия в формате ЧЧ:ММ.','10:20','08:45 + 1 час = 09:45. Ещё 35 минут дают 10:20.','При прибавлении времени учитывай переход через час.'),
(6,'Вычисления','Вычисли: 3/4 − 1/8. Ответ запиши десятичной дробью.','0,625','3/4 = 6/8, 6/8 − 1/8 = 5/8 = 0,625.','Для вычитания дробей приведи их к общему знаменателю.'),
(7,'Числа на прямой','Найди расстояние на числовой прямой между числами −3,2 и 4,1.','7,3','Расстояние равно |4,1 − (−3,2)| = |7,3| = 7,3.','Расстояние между двумя числами равно модулю их разности.'),
(8,'Алгебраические выражения','При a = −2 вычисли значение выражения (a − 3)² − a².',21,'(−2 − 3)² − (−2)² = 25 − 4 = 21.','Подставляй отрицательные числа в скобках.'),
(9,'Уравнения','Реши уравнение: 7(x − 2) = 3x + 10. Найди x.',6,'7x − 14 = 3x + 10; 4x = 24; x = 6.','Раскрой скобки, собери x в одной части.'),
(10,'Вероятность','В коробке лежат 4 красных, 5 синих и 3 зелёных карандаша. Найди вероятность достать зелёный карандаш. Ответ запиши десятичной дробью.','0,25','Всего 12 карандашей, зелёных 3. P = 3/12 = 1/4 = 0,25.','Вероятность равна отношению количества благоприятных исходов к количеству всех равновозможных.'),
(11,'Графики функций','Линейная функция y = −2x + 7. При каком x значение y равно 1?',3,'1 = −2x + 7; −2x = −6; x = 3.','Подставь заданное значение функции и реши уравнение.'),
(12,'Расчёты по формулам','Площадь треугольника равна 30 см², основание 12 см. Найди высоту к этому основанию.',5,'S = ah/2. Тогда h = 2S/a = 60/12 = 5 см.','Из формулы S = ah/2 вырази высоту.'),
(13,'Неравенства','Найди наименьшее целое x, удовлетворяющее неравенству 3x − 5 > 7.',5,'3x > 12, значит x > 4. Наименьшее целое число, большее 4, равно 5.','После решения неравенства учти, требуется ли целое число.'),
(14,'Последовательности','В арифметической прогрессии первый член равен 7, разность равна −2. Найди шестой член.',-3,'a₆ = a₁ + 5d = 7 + 5 × (−2) = −3.','Формула n-го члена арифметической прогрессии: aₙ = a₁ + (n−1)d.'),
(15,'Геометрия','Катеты прямоугольного треугольника равны 9 см и 12 см. Найди гипотенузу.',15,'c² = 9² + 12² = 81 + 144 = 225, поэтому c = 15.','Теорема Пифагора: квадрат гипотенузы равен сумме квадратов катетов.'),
(16,'Окружность','Хорда окружности находится на расстоянии 3 см от центра. Радиус окружности 5 см. Найди длину хорды.',8,'Половина хорды, радиус и расстояние до центра образуют прямоугольный треугольник: половина хорды = √(25 − 9) = 4. Вся хорда равна 8.','Перпендикуляр из центра к хорде делит её пополам.'),
(17,'Площадь','Площадь ромба равна 48 см². Одна диагональ 12 см. Найди другую диагональ.',8,'S = d₁d₂/2, поэтому d₂ = 2 × 48 / 12 = 8 см.','Площадь ромба равна половине произведения его диагоналей.'),
(18,'Геометрия','В равнобедренном треугольнике угол при вершине равен 38°. Найди угол при основании.',71,'Остальные два угла равны, их сумма 180° − 38° = 142°. Каждый равен 142°/2 = 71°.','Углы при основании равнобедренного треугольника равны.'),
(19,'Геометрические утверждения','Сколько осей симметрии у квадрата?',4,'Две оси проходят через середины противоположных сторон и две — через противоположные вершины. Всего четыре.','Ось симметрии делит фигуру на зеркально равные части.'),
(20,'Уравнения и неравенства','Реши уравнение x² − 10x + 21 = 0. Запиши больший корень.',7,'(x − 3)(x − 7) = 0, корни 3 и 7. Больший корень — 7.','Квадратный трёхчлен иногда удобно разложить на множители.'),
(21,'Текстовые задачи','Один мастер выполняет заказ за 6 часов, второй — за 3 часа. За сколько часов они выполнят заказ вместе?',2,'Их совместная производительность: 1/6 + 1/3 = 1/2 заказа в час. Время = 1 : (1/2) = 2 часа.','Скорости выполнения работы складываются.'),
(22,'Графики и анализ','Парабола y = (x − 4)² − 9. В какой точке по оси x находится её вершина?',4,'Вершина функции вида y = (x − a)² + b имеет абсциссу a. Здесь a = 4.','Канонический вид квадратной функции помогает определить вершину параболы.'),
(23,'Геометрия','В треугольнике два угла равны 47° и 68°. Найди третий угол.',65,'180° − 47° − 68° = 65°.','Сумма внутренних углов треугольника равна 180°.'),
(24,'Геометрия','Из вершины прямого угла проведён луч, который образует с одной стороной угол 27°. Найди угол с другой стороной.',63,'Прямой угол равен 90°, второй угол равен 90° − 27° = 63°.','Составляющие прямой угол углы в сумме дают 90°.'),
(25,'Геометрия','У прямоугольника стороны 5 см и 12 см. Найди длину диагонали.',13,'По теореме Пифагора d² = 5² + 12² = 169, поэтому d = 13.','Диагональ прямоугольника — гипотенуза прямоугольного треугольника.'),
]
for number, topic, body, answer, explanation, theory in OGE_NEW_PRACTICE:
    add_manual('oge', number, topic, body, answer, explanation, theory)

# Собственные задачи экзаменационного уровня: часть 2 ОГЭ, номера 20–25.
# Полное решение требуется даже там, где есть числовой ответ.
OGE_PART2 = [
 (20, 'Алгебра · уравнения', 'Решите уравнение (x² − 9)/(x − 3) = 8. Укажите все допустимые корни.', '5',
  'Область допустимых значений: x ≠ 3. При x ≠ 3 дробь сокращается до x + 3. Получаем x + 3 = 8, откуда x = 5. Проверка ОДЗ: 5 ≠ 3. Ответ: 5.',
  '2 балла — найден корень и проверено ОДЗ; 1 балл — верный метод, но вычислительная неточность; 0 — существенная ошибка.'),
 (20, 'Алгебра · системы', 'Решите систему: x + y = 7; x² + y² = 25. Запишите обе пары (x; y).', '(3;4), (4;3)',
  'Из (x + y)² = x² + 2xy + y² получаем 49 = 25 + 2xy, поэтому xy = 12. Числа x и y — корни t² − 7t + 12 = 0, то есть 3 и 4. Ответ: (3; 4) и (4; 3).',
  '2 балла — обе пары и обоснование; 1 — правильный метод с одной вычислительной ошибкой; 0 — неверная система решений.'),
 (21, 'Текстовые задачи · движение', 'Два велосипедиста одновременно выехали навстречу друг другу из пунктов на расстоянии 90 км. Скорость первого на 6 км/ч больше скорости второго. Через 2 часа они встретились. Найдите скорости обоих.', '25,5 км/ч и 19,5 км/ч',
  'Пусть скорость второго v км/ч, тогда первого v + 6. За 2 часа вместе они проехали 90 км: 2v + 2(v + 6) = 90. Отсюда 4v = 78, v = 19,5. Первый ехал 25,5 км/ч. Проверка: (19,5 + 25,5) × 2 = 90.',
  '2 балла — верно составлено уравнение, найдены обе скорости и сделана проверка; 1 — верный план с арифметической ошибкой.'),
 (21, 'Текстовые задачи · смеси', 'Смешали 4 кг 20%-го раствора соли и 6 кг 35%-го раствора. Сколько процентов соли содержит смесь?', '29%',
  'Масса соли в первом растворе: 4 × 0,20 = 0,8 кг, во втором: 6 × 0,35 = 2,1 кг. Всего соли 2,9 кг, масса смеси 10 кг. Концентрация 2,9/10 × 100% = 29%.',
  '2 балла — найдены массы вещества и итоговая концентрация; 1 — верный способ с небольшой вычислительной неточностью.'),
 (22, 'Функции · построение графика', 'Постройте график y = (x² − 4)/(x − 2). Укажите точку, исключённую из графика. Сколько общих точек с графиком имеет прямая y = 4?', 'исключена (2;4), пересечений 0',
  'ОДЗ: x ≠ 2. При x ≠ 2 имеем y = x + 2. График — прямая y = x + 2 с выколотой точкой (2; 4). Прямая y = 4 пересекала бы её лишь при x = 2, но точка исключена. Общих точек нет.',
  '2 балла — верная прямая, выколотая точка и вывод об отсутствии пересечения; 1 — корректный график при ошибке в выводе.'),
 (22, 'Функции · парабола', 'Постройте график y = x² − 6x + 5. Найдите все значения x, при которых y = 0, и координаты вершины.', 'корни 1 и 5; вершина (3;−4)',
  'y = (x − 3)² − 4. Вершина (3; −4), ветви направлены вверх, ось симметрии x = 3. Нули: (x − 1)(x − 5) = 0, значит x = 1 и x = 5. Для построения отметьте вершину и пересечения с осями.',
  '2 балла — верный график, вершина и оба корня; 1 — график построен верно, но ошибочно указаны отдельные значения.'),
 (23, 'Геометрия · подобие', 'В треугольнике ABC точки M и N лежат на AB и AC, причём MN ∥ BC. Известно AM = 6, MB = 4, AN = 9. Найдите NC.', '6',
  'AB = 6 + 4 = 10. Так как MN ∥ BC, треугольники AMN и ABC подобны. AM/AB = AN/AC, то есть 6/10 = 9/AC. Отсюда AC = 15 и NC = AC − AN = 6.',
  '2 балла — доказано подобие, составлена пропорция и получен ответ; 1 — верный ход с арифметической неточностью.'),
 (23, 'Геометрия · вписанные углы', 'В окружности хорды AB и CD пересекаются в точке P. Известно PA = 3, PB = 8, PC = 4. Найдите PD.', '6',
  'По теореме о пересекающихся хордах PA × PB = PC × PD. Значит 3 × 8 = 4 × PD, откуда PD = 6.',
  '2 балла — корректно применена теорема о хордах; 1 — верная идея с вычислительной ошибкой.'),
 (24, 'Геометрия · доказательство', 'В равнобедренном треугольнике ABC (AB = AC) медиана AD проведена к основанию BC. Докажите, что AD — также высота.', 'требуется доказательство',
  'Так как AD — медиана, BD = DC. Также AB = AC по условию, а AD — общая сторона. Следовательно, треугольники ABD и ACD равны по трём сторонам. Поэтому ∠ADB = ∠ADC. Эти углы смежные, значит каждый равен 90°. Следовательно, AD ⟂ BC.',
  '2 балла — полное доказательство через равенство треугольников и смежные углы; 1 — верная идея с недостающим обоснованием.'),
 (24, 'Геометрия · параллелограмм', 'Докажите, что диагонали параллелограмма делят друг друга пополам.', 'требуется доказательство',
  'Пусть диагонали AC и BD пересекаются в O. В параллелограмме AB ∥ CD и AB = CD. Из параллельности следует ∠ABO = ∠CDO и ∠BAO = ∠DCO (накрест лежащие). Треугольники ABO и CDO равны по стороне и двум прилежащим углам. Значит AO = OC и BO = OD.',
  '2 балла — обоснованы равенство треугольников и обе пары отрезков; 1 — ход доказательства верен, но пропущено обоснование.'),
 (25, 'Геометрия · сложная задача', 'В прямоугольном треугольнике ABC с прямым углом C высота CH к гипотенузе AB делит её на отрезки AH = 9 и HB = 16. Найдите площадь треугольника ABC.', '150',
  'По свойству высоты к гипотенузе CH² = AH × HB = 9 × 16 = 144, CH = 12. Гипотенуза AB = 9 + 16 = 25. Площадь S = AB × CH / 2 = 25 × 12 / 2 = 150.',
  '2 балла — обоснованно применена теорема о высоте и вычислена площадь; 1 — верный ход с одной арифметической неточностью.'),
 (25, 'Геометрия · сложная задача', 'В трапеции ABCD основания AD = 18 и BC = 8 параллельны, а боковые стороны AB = CD = 13. Найдите площадь трапеции.', '156',
  'Трапеция равнобедренная. Проекции боковых сторон на большее основание равны (18 − 8)/2 = 5. Высота h = √(13² − 5²) = √144 = 12. Площадь S = (18 + 8)/2 × 12 = 156.',
  '2 балла — найдена высота по Пифагору и площадь по формуле трапеции; 1 — верный ход с вычислительной неточностью.'),
]
for number, topic, body, expected, explanation, rubric in OGE_PART2:
    add_manual('oge', number, topic, body, expected, explanation, rubric)

MANUAL_LOOKUP = {body: (answer, explanation) for _, _, _, body, answer, explanation, _, _ in MANUAL_SAMPLES}
DIAGRAMS = {body: diagram for _, _, _, body, _, _, _, diagram in MANUAL_SAMPLES if diagram}

def same_answer(raw, expected):
    raw = raw.strip().lower().replace(' ', '').replace(',', '.').replace('−', '-')
    expected = str(expected).strip().lower().replace(' ', '').replace(',', '.').replace('−', '-')
    try:
        return Decimal(raw) == Decimal(expected)
    except InvalidOperation:
        return raw == expected


@app.route('/oge/part2')
def oge_part2():
    return render_template('oge_part2.html', tasks=OGE_PART2, groups={n: [t for t in OGE_PART2 if t[0] == n] for n in range(20, 26)}, task_ids={q.body: q.id for q in Question.query.filter_by(subject='math', exam='oge').all() if any(t[2] == q.body for t in OGE_PART2)})


@app.route('/oge/part2/task/<int:qid>', methods=['GET', 'POST'])
def oge_part2_task(qid):
    q = db.get_or_404(Question, qid)
    entry = next((t for t in OGE_PART2 if t[2] == q.body and q.exam == 'oge'), None)
    if not entry:
        abort(404)
    show_solution = False
    submitted = ''
    if request.method == 'POST':
        submitted = request.form.get('solution', '').strip()[:6000]
        if not submitted:
            flash('Сначала запишите ход решения.', 'error')
        else:
            show_solution = True
            if current_user.is_authenticated and current_user.role == 'student':
                db.session.add(ExtendedAnswer(user_id=current_user.id, question_id=q.id, response=submitted))
                db.session.commit()
    return render_template('oge_part2_task.html', q=q, number=entry[0], rubric=entry[5],
                           submitted=submitted, show_solution=show_solution)


def init_database():
    with app.app_context():
        db.create_all()
        for exam, topic, body, options, answer, explanation, th in SEED:
            exists = Question.query.filter_by(subject='math', exam=exam, body=body).first()
            if not exists:
                db.session.add(Question(subject='math', exam=exam, topic=topic, body=body, options=options, correct_index=answer, explanation=explanation, theory=th))
        for exam, _, topic, body, options, answer, explanation, th in NUMBERED_SAMPLES:
            if not Question.query.filter_by(subject='math', exam=exam, body=body).first():
                db.session.add(Question(subject='math', exam=exam, topic=topic, body=body, options=options, correct_index=answer, explanation=explanation, theory=th))
        for exam, _, topic, body, answer, explanation, th, diagram in MANUAL_SAMPLES:
            if not Question.query.filter_by(subject='math', exam=exam, body=body).first():
                db.session.add(Question(subject='math', exam=exam, topic=topic, body=body, options=[], correct_index=0, explanation=explanation, theory=th))
        db.session.commit()


if __name__ == '__main__':
    init_database()
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1', host='127.0.0.1', port=int(os.environ.get('PORT', 5000)))
