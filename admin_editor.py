
"""Browser-only content management for the mathematics website.
Set ADMIN_EMAIL in Render environment to your existing registered login email.
"""
import os
from functools import wraps
from datetime import datetime, timezone
from flask import Blueprint, request, redirect, url_for, flash, abort, render_template, Response
from flask_login import current_user, login_required
from app import db

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
    rows = ManagedTask.query.order_by(ManagedTask.created_at.desc(), ManagedTask.id.desc()).all()
    return render_template('cms_dashboard.html', rows=rows)

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
