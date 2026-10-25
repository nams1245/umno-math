"""Training 25-task OGE test; 19 one-point MCQs and 6 written tasks.
Not an official OGE scoring implementation. Import before db.create_all().
"""
from datetime import datetime, timedelta, timezone
import random
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from app import db, Question, number_of
from oge_advanced import LOOKUP

mock25_bp = Blueprint('mock25', __name__, url_prefix='/oge/mock25')
DURATION_MINUTES = 235

class OgePracticeRun(db.Model):
    __tablename__ = 'oge_practice_run'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    question_ids = db.Column(db.JSON, nullable=False)
    advanced_keys = db.Column(db.JSON, nullable=False)
    answers = db.Column(db.JSON, nullable=False, default=dict)
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)
    first_score = db.Column(db.Integer, nullable=True)


def _get_run(run_id):
    run = db.session.get(OgePracticeRun, run_id)
    if run is None: abort(404)
    if run.user_id != current_user.id: abort(403)
    return run


def _elapsed(run):
    return max(0, int((datetime.utcnow()-run.started_at).total_seconds()))


@mock25_bp.get('/')
@login_required
def home():
    if getattr(current_user, 'role', None) != 'student': abort(403)
    recent = OgePracticeRun.query.filter_by(user_id=current_user.id).order_by(OgePracticeRun.id.desc()).limit(12).all()
    return render_template('oge_mock25_home.html', recent=recent, duration=DURATION_MINUTES)


@mock25_bp.post('/start')
@login_required
def start():
    if getattr(current_user, 'role', None) != 'student': abort(403)
    # This practice format chooses ONLY questions with genuine options and valid correct_index.
    from admin_editor import active_questions
    pool = [q for q in active_questions(Question.query.filter_by(subject='math', exam='oge').all())
            if isinstance(q.options, list) and len(q.options) >= 2 and
            isinstance(q.correct_index, int) and 0 <= q.correct_index < len(q.options)]
    if len(pool) < 19:
        flash('В банке пока недостаточно тестовых заданий для пробника.', 'error')
        return redirect(url_for('mock25.home'))
    variant = request.form.get("variant", "random")
    if variant not in ("random", "1", "2", "3"):
        abort(400)
    rng = random.SystemRandom() if variant == "random" else random.Random(20261025 + int(variant) * 7919)
    pool = sorted(pool, key=lambda q: q.id)
    # Приоритет: по одному заданию на каждый номер 1–19, когда банк позволяет.
    by_number = {n: [] for n in range(1,20)}
    for question in pool:
        number = number_of(question)
        if number in by_number:
            by_number[number].append(question)
    if all(by_number.values()):
        picked = [rng.choice(by_number[n]) for n in range(1,20)]
    else:
        # Если какого-то номера нет, выдаём обычную учебную подборку,
        # не выдавая её за официальный вариант.
        picked = rng.sample(pool, 19)
    keys = []
    for n in range(20,26):
        options = [t[0] for t in LOOKUP.values() if t[1] == n]
        if not options: abort(503)
        options.sort()
        keys.append(rng.choice(options))
    run=OgePracticeRun(user_id=current_user.id, question_ids=[q.id for q in picked], advanced_keys=keys, answers={})
    db.session.add(run); db.session.commit()
    return redirect(url_for('mock25.take',run_id=run.id))


@mock25_bp.route('/<int:run_id>', methods=['GET','POST'])
@login_required
def take(run_id):
    run = _get_run(run_id)
    if run.finished_at is not None:
        return redirect(url_for('mock25.result',run_id=run_id))
    expired = _elapsed(run) >= DURATION_MINUTES*60
    if request.method == 'POST':
        saved = dict(run.answers or {})
        for i in range(1,20):
            v = request.form.get(f'q{i}')
            if v is not None and len(v)<=10: saved[str(i)] = v
        for i in range(20,26):
            v = request.form.get(f'q{i}')
            if v is not None: saved[str(i)] = v[:6000]
        run.answers = saved
        if request.form.get('action')=='finish' or expired:
            run.finished_at = datetime.utcnow()
            questions = {q.id:q for q in Question.query.filter(Question.id.in_(run.question_ids)).all()}
            run.first_score = sum(1 for i,qid in enumerate(run.question_ids,1)
                if qid in questions and saved.get(str(i))==str(questions[qid].correct_index))
        db.session.commit()
        if run.finished_at:
            return redirect(url_for('mock25.result', run_id=run.id))
        flash('Ответы сохранены.', 'success')
        return redirect(url_for('mock25.take', run_id=run.id))
    if expired:
        run.finished_at = datetime.utcnow()
        questions = {q.id:q for q in Question.query.filter(Question.id.in_(run.question_ids)).all()}
        run.first_score = sum(1 for i,qid in enumerate(run.question_ids,1)
            if qid in questions and (run.answers or {}).get(str(i))==str(questions[qid].correct_index))
        db.session.commit()
        return redirect(url_for('mock25.result', run_id=run.id))
    questions={q.id:q for q in Question.query.filter(Question.id.in_(run.question_ids)).all()}
    if len(questions)!=19: abort(503)
    first=[questions[qid] for qid in run.question_ids]
    second=[LOOKUP[k] for k in run.advanced_keys]
    remaining = DURATION_MINUTES*60 - _elapsed(run)
    return render_template('oge_mock25_take.html',run=run,first=first,second=second,remaining=remaining,answers=run.answers or {})


@mock25_bp.get('/<int:run_id>/result')
@login_required
def result(run_id):
    run = _get_run(run_id)
    if not run.finished_at: return redirect(url_for('mock25.take',run_id=run_id))
    qs={q.id:q for q in Question.query.filter(Question.id.in_(run.question_ids)).all()}
    first = [qs.get(i) for i in run.question_ids]
    second = [LOOKUP.get(k) for k in run.advanced_keys]
    breakdown = []
    for index, q in enumerate(first, 1):
        if q is None:
            continue
        breakdown.append({'position': index, 'topic': number_of(q),
            'correct': (run.answers or {}).get(str(index)) == str(q.correct_index),
            'answered': str(index) in (run.answers or {})})
    return render_template('oge_mock25_result.html',run=run,first=first,second=second,answers=run.answers or {},breakdown=breakdown)


def register_mock25(app):
    app.register_blueprint(mock25_bp)
