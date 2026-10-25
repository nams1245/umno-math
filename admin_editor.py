
"""Browser-only content management for the mathematics website.
Set ADMIN_EMAIL in Render environment to your existing registered login email.
"""
import os
from functools import wraps
from datetime import datetime, timezone
from flask import Blueprint, request, redirect, url_for, flash, abort, render_template, Response
from flask_login import current_user, login_required
from app import db, Question, Attempt, Favorite, Assignment, number_of

admin = Blueprint('cms', __name__)

class ManagedTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam = db.Column(db.String(4), nullable=False)
    number = db.Column(db.Integer, nullable=False)
    topic = db.Column(db.String(130), nullable=False)
    statement = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False, default='')
    solution = db.Column(db.Text, nullable=False, default='')
    published = db.Column(db.Boolean, nullable=False, default=False)
    image_data = db.Column(db.LargeBinary, nullable=True)
    image_type = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class LegacyArchive(db.Model):
    __tablename__ = 'legacy_archive'
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False, unique=True, index=True)
    archived_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


def archived_ids():
    return {row[0] for row in db.session.query(LegacyArchive.question_id).all()}


def active_questions(questions):
    hidden = archived_ids()
    return [q for q in questions if q.id not in hidden]


def is_owner():
    configured = os.environ.get('ADMIN_EMAIL','').strip().casefold()
    return bool(configured and current_user.is_authenticated and current_user.email.casefold() == configured)


def owner_only(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if not is_owner(): abort(403)
        return fn(*args, **kwargs)
    return wrapped

@admin.app_context_processor
def owner_context():
    return {'cms_owner': is_owner()}

@admin.get('/admin/tasks')
@owner_only
def dashboard():
    exam = request.args.get('exam', '')
    status = request.args.get('status', '')
    term = request.args.get('q', '').strip()[:100].casefold()
    qs = ManagedTask.query
    if exam in ('oge','ege'): qs = qs.filter_by(exam=exam)
    if status == 'published': qs = qs.filter_by(published=True)
    if status == 'draft': qs = qs.filter_by(published=False)
    rows = qs.order_by(ManagedTask.id.desc()).all()
    if term: rows = [t for t in rows if term in (t.statement+' '+t.topic+' '+str(t.number)).casefold()]
    return render_template('cms_dashboard.html', rows=rows, exam=exam, status=status, q=term)

@admin.route('/admin/tasks/new',methods=['GET','POST'])
@owner_only
def create():
    return edit_form(None)

@admin.route('/admin/tasks/<int:task_id>/edit',methods=['GET','POST'])
@owner_only
def edit(task_id):
    task = db.get_or_404(ManagedTask,task_id)
    return edit_form(task)

def edit_form(task):
    if request.method=='POST':
        exam = request.form.get('exam','')
        try: number=int(request.form.get('number','0'))
        except ValueError: number=0
        topic = request.form.get('topic','').strip()[:130]
        statement = request.form.get('statement','').strip()[:15000]
        answer = request.form.get('answer','').strip()[:1500]
        solution = request.form.get('solution','').strip()[:30000]
        published = request.form.get('published')=='yes'
        limit = 25 if exam=='oge' else 19
        if exam not in ('oge','ege') or number < 1 or number>limit or not statement or not topic:
            flash('Заполни предмет, номер, тему и условие.','error')
            return render_template('cms_form.html',task=task),400
        # Use image headers rather than trusting extensions or supplied MIME type.
        upload=request.files.get('picture')
        image_bytes=None; image_type=None
        if upload and upload.filename:
            image_bytes=upload.stream.read(2*1024*1024+1)
            if len(image_bytes)>2*1024*1024:
                flash('Рисунок не должен превышать 2 МБ.','error')
                return render_template('cms_form.html',task=task),400
            if image_bytes.startswith(b'\x89PNG\r\n\x1a\n'):image_type='image/png'
            elif image_bytes[:3]==b'\xff\xd8\xff':image_type='image/jpeg'
            elif image_bytes[:4]==b'RIFF' and image_bytes[8:12]==b'WEBP':image_type='image/webp'
            else:
                flash('Можно загрузить только PNG, JPG или WebP.','error')
                return render_template('cms_form.html',task=task),400
        if task is None:
            task=ManagedTask()
            db.session.add(task)
        task.exam=exam; task.number=number; task.topic=topic
        task.statement=statement; task.answer=answer; task.solution=solution
        task.published=published
        if request.form.get('remove_picture')=='yes':
            task.image_data=None; task.image_type=None
        if image_type:
            task.image_data=image_bytes; task.image_type=image_type
        db.session.commit()
        flash('Задание сохранено в базе Neon и '+('опубликовано.' if published else 'оставлено в черновиках.'),'success')
        return redirect(url_for('cms.dashboard'))
    return render_template('cms_form.html',task=task)

@admin.post('/admin/tasks/<int:task_id>/toggle')
@owner_only
def toggle(task_id):
    task=db.get_or_404(ManagedTask,task_id)
    task.published=not task.published
    db.session.commit()
    flash('Статус публикации изменён.','success')
    return redirect(url_for('cms.dashboard'))

@admin.get('/tasks')
def catalog():
    exam=request.args.get('exam','oge')
    if exam not in ('oge','ege'):exam='oge'
    rows=ManagedTask.query.filter_by(exam=exam,published=True).order_by(ManagedTask.number,ManagedTask.id.desc()).all()
    return render_template('cms_catalog.html',rows=rows,exam=exam)

@admin.get('/tasks/<int:task_id>')
def detail(task_id):
    task=db.get_or_404(ManagedTask,task_id)
    if not task.published and not is_owner():abort(404)
    return render_template('cms_task.html',task=task)

@admin.get('/tasks/<int:task_id>/picture')
def picture(task_id):
    task=db.get_or_404(ManagedTask,task_id)
    if (not task.published and not is_owner()) or not task.image_data:abort(404)
    response=Response(task.image_data,mimetype=task.image_type)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Cache-Control']='public, max-age=300' if task.published else 'private, no-store'
    return response

def register_cms(app):
    app.config['MAX_CONTENT_LENGTH']=3*1024*1024
    app.register_blueprint(admin)


@admin.post('/admin/tasks/<int:task_id>/delete')
@owner_only
def delete_managed(task_id):
    task = db.get_or_404(ManagedTask, task_id)
    if request.form.get('confirm') != 'DELETE': abort(400)
    db.session.delete(task)
    db.session.commit()
    flash('Авторское задание удалено.','success')
    return redirect(url_for('cms.dashboard'))


@admin.post('/admin/tasks/bulk')
@owner_only
def bulk_managed():
    action=request.form.get('action')
    if action not in ('publish','draft','delete'): abort(400)
    raw=request.form.getlist('ids')[:200]
    ids=[]
    for item in raw:
        try: ids.append(int(item))
        except (ValueError,TypeError): continue
    items=ManagedTask.query.filter(ManagedTask.id.in_(ids)).all() if ids else []
    if action=='delete' and request.form.get('confirm')!='DELETE': abort(400)
    for task in items:
        if action=='delete': db.session.delete(task)
        else: task.published=(action=='publish')
    db.session.commit()
    flash(f'Обработано заданий: {len(items)}.','success')
    return redirect(url_for('cms.dashboard'))


@admin.get('/admin/legacy')
@owner_only
def legacy_list():
    exam=request.args.get('exam','oge')
    if exam not in ('oge','ege'): exam='oge'
    term=request.args.get('q','').strip()[:100].casefold()
    show_archived=request.args.get('status')=='archived'
    hidden=archived_ids()
    rows=Question.query.filter_by(exam=exam,subject='math').order_by(Question.id.desc()).all()
    rows=[q for q in rows if (q.id in hidden)==show_archived and (not term or term in (q.body+' '+q.topic+' '+str(q.id)).casefold())]
    return render_template('cms_legacy.html',rows=rows,exam=exam,status='archived' if show_archived else 'active',q=term,number_of=number_of)


@admin.post('/admin/legacy/<int:qid>/archive')
@owner_only
def archive_legacy(qid):
    task=db.get_or_404(Question,qid)
    if task.subject!='math': abort(404)
    if request.form.get('confirm')!='ARCHIVE':abort(400)
    if not LegacyArchive.query.filter_by(question_id=qid).first():
        db.session.add(LegacyArchive(question_id=qid))
        db.session.commit()
    flash('Задание скрыто из каталога. История решений сохранена.','success')
    return redirect(url_for('cms.legacy_list',exam=task.exam))


@admin.post('/admin/legacy/<int:qid>/restore')
@owner_only
def restore_legacy(qid):
    task=db.get_or_404(Question,qid)
    row=LegacyArchive.query.filter_by(question_id=qid).first()
    if row:
        db.session.delete(row)
        db.session.commit()
    flash('Задание восстановлено.','success')
    return redirect(url_for('cms.legacy_list',exam=task.exam,status='archived'))


@admin.route('/admin/legacy/<int:qid>/edit',methods=['GET','POST'])
@owner_only
def edit_legacy(qid):
    task=db.get_or_404(Question,qid)
    if task.subject!='math':abort(404)
    if request.method=='POST':
        # Preserve the body: legacy numbering and manual-answer tables use it as key.
        task.explanation=request.form.get('explanation','').strip()[:20000]
        task.theory=request.form.get('theory','').strip()[:20000]
        if task.options:
            try: correct=int(request.form.get('correct_index','-1'))
            except ValueError: correct=-1
            if correct < 0 or correct >= len(task.options): abort(400)
            task.correct_index=correct
        db.session.commit()
        flash('Разбор и ответ обновлены.','success')
        return redirect(url_for('cms.legacy_list',exam=task.exam))
    return render_template('cms_legacy_edit.html',task=task,number=number_of(task))
