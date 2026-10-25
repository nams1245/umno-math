"""Independent OGE advanced practice, original examples; import from wsgi before init_database."""
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user
from app import db, session, secrets

advanced_bp = Blueprint('advanced_oge', __name__)

class AdvancedDraft(db.Model):
    __tablename__ = 'advanced_draft'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    task_key = db.Column(db.String(30), nullable=False)
    solution = db.Column(db.Text, nullable=False, default='')
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'task_key', name='uq_advanced_draft_user_task'),)

# (id, number, title, statement, solution, criteria, kind, difficulty)
TASKS = [
('20a',20,'Рациональное уравнение','Решите уравнение: (x² − 9)/(x − 3) = 8.', 'При x ≠ 3 имеем (x−3)(x+3)/(x−3)=x+3. Тогда x+3=8, x=5. Число 5 допустимо. Ответ: 5.', '2 балла: верное ОДЗ, преобразования и ответ. 1 балл: обоснованный верный ход с несущественной арифметической ошибкой.', 'algebra','сложный'),
('20b',20,'Система уравнений','Решите систему: x + y = 7; xy = 12. Запишите все упорядоченные пары (x; y).', 'Числа x и y — корни уравнения t²−7t+12=0. (t−3)(t−4)=0. Ответ: (3;4), (4;3).', '2 балла: обе пары и обоснованное решение. 1 балл: верная модель с одной неточностью.', 'algebra','сложный'),
('21a',21,'Движение навстречу','Из двух городов навстречу друг другу выехали автомобили. Расстояние 270 км; скорость первого на 15 км/ч больше скорости второго. Встретились через 2 часа. Найдите обе скорости.', 'Сумма скоростей 270/2=135. Пусть скорость второго v, первого v+15. 2v+15=135, v=60. Скорости: 75 и 60 км/ч.', '2 балла: правильная модель, уравнение, обе скорости с единицами. 1 балл: верная модель с вычислительным недочётом.', 'motion','сложный'),
('21b',21,'Совместная работа','Первый мастер выполняет заказ за 6 часов, второй — за 9. За сколько часов они выполнят заказ вместе?', 'Скорость первого 1/6 работы в час, второго 1/9. Вместе 1/6+1/9=5/18. Время 18/5=3,6 часа (3 ч 36 мин).', '2 балла: сложение производительностей и точный ответ. 1 балл: верное уравнение с вычислительной ошибкой.', 'motion','средний'),
('22a',22,'Парабола и прямая','Найдите все значения k, при которых прямая y=k пересекает параболу y=(x−2)²−1 ровно в одной точке.', 'Вершина параболы (2;−1), ветви вверх. Горизонтальная прямая касается параболы только при k=−1. При k>−1 точек две, при k<−1 точек нет.', '2 балла: верно объяснены все три случая и ответ k=−1. 1 балл: верный ответ с неполным обоснованием.', 'graph','сложный'),
('22b',22,'График с выколотой точкой','Функция y=(x²−4)/(x−2) задана при x ≠ 2. Постройте график и определите, при каком значении m прямая y=m имеет с ним ровно одну общую точку.', 'При x≠2 функция равна y=x+2: прямая с удалённой точкой (2;4). Любая горизонтальная прямая y=m пересекает её один раз, кроме m=4, когда единственная точка удалена. Ответ: все m≠4.', '2 балла: указана область определения, выколотая точка и ответ. 1 балл: верный график без полной аргументации.', 'graph','сложный'),
('23a',23,'Подобные треугольники','В треугольнике ABC отрезок DE параллелен BC, D лежит на AB, E — на AC. AD=6, DB=3, DE=8. Найдите BC.', 'AB=6+3=9. Треугольники ADE и ABC подобны, AD/AB=DE/BC=6/9. BC=8·9/6=12.', '2 балла: доказано подобие и получен ответ 12. 1 балл: указано подобие, но допущен небольшой счётный недочёт.', 'geometry','средний'),
('23b',23,'Хорды окружности','Хорды AB и CD окружности пересекаются в точке P. AP=4, PB=9, CP=6. Найдите PD.', 'По теореме о произведениях отрезков пересекающихся хорд AP·PB=CP·PD. 4·9=6·PD, PD=6.', '2 балла: корректно применена теорема и найден ответ. 1 балл: идея верна, но есть вычислительная ошибка.', 'geometry','сложный'),
('24a',24,'Доказательство о параллелограмме','Докажите, что диагонали параллелограмма точкой пересечения делятся пополам.', 'Пусть ABCD — параллелограмм, O — точка пересечения AC и BD. AB∥CD. Углы ABO и CDO равны как накрест лежащие; BAO и DCO — также. AB=CD как противоположные стороны параллелограмма. По стороне и двум прилежащим углам треугольники ABO и CDO равны. Следовательно AO=OC и BO=OD.', '2 балла: доказаны равенства обоих отрезков с опорой на признаки равенства. 1 балл: правильная идея, но пропущен обосновывающий шаг.', 'geometry','сложный'),
('24b',24,'Доказательство о ромбе','Докажите, что диагонали ромба перпендикулярны.', 'Пусть ABCD — ромб, O — пересечение диагоналей. В ромбе AB=BC и AD=DC, поэтому B и D равноудалены от A и C. Следовательно BD — серединный перпендикуляр к AC, то есть BD⊥AC.', '2 балла: ясное обоснование через равноудалённость или равные треугольники. 1 балл: правильная идея с пробелом.', 'geometry','сложный'),
('25a',25,'Высота прямоугольного треугольника','В прямоугольном треугольнике ABC высота CH к гипотенузе AB делит её на отрезки AH=9 и HB=16. Найдите CH и площадь ABC.', 'Высота к гипотенузе удовлетворяет CH²=AH·HB=9·16=144, значит CH=12. AB=25. Площадь S=AB·CH/2=25·12/2=150.', '2 балла: обоснована формула для высоты, найдены обе величины. 1 балл: верный подход с одной неточностью.', 'geometry','сложный'),
('25b',25,'Подобие и площадь','В треугольнике ABC точки D на AB и E на AC выбраны так, что DE∥BC, AD:AB=2:3. Площадь треугольника ADE равна 20. Найдите площадь ABC.', 'Треугольники ADE и ABC подобны с коэффициентом 2/3. Отношение площадей (2/3)²=4/9. Тогда S_ABC=20·9/4=45.', '2 балла: установлено подобие и квадрат коэффициента площадей. 1 балл: верная связь, но арифметическая ошибка.', 'geometry','сложный'),
]
LOOKUP = {t[0]: t for t in TASKS}

@advanced_bp.get('/oge/advanced')
def index():
    return render_template('oge_advanced_index.html', tasks=TASKS)

@advanced_bp.route('/oge/advanced/<key>', methods=['GET','POST'])
def task(key):
    entry=LOOKUP.get(key)
    if entry is None: abort(404)
    draft=None
    if current_user.is_authenticated and getattr(current_user,'role',None)=='student':
        draft=AdvancedDraft.query.filter_by(user_id=current_user.id, task_key=key).first()
    solution = draft.solution if draft else ''
    reveal = False
    if request.method=='POST':
        submitted=request.form.get('solution','')[:6000]
        action=request.form.get('action','save')
        if action not in ('save','check'): abort(400)
        if not submitted.strip():
            flash('Сначала запиши решение.', 'error')
        else:
            solution=submitted
            if draft is not None:
                draft.solution=solution; draft.updated_at=datetime.now(timezone.utc).replace(tzinfo=None)
                db.session.commit()
            elif current_user.is_authenticated and getattr(current_user,'role',None)=='student':
                db.session.add(AdvancedDraft(user_id=current_user.id, task_key=key, solution=solution))
                db.session.commit()
            if action=='check': reveal=True
            elif not current_user.is_authenticated: flash('Черновик в гостевом режиме не сохраняется. Для сохранения войди в аккаунт.', 'info')
            else: flash('Черновик сохранён.', 'success')
    return render_template('oge_advanced_task.html', entry=entry, solution=solution, reveal=reveal)

def register_advanced(app):
    app.register_blueprint(advanced_bp)
