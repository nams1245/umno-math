"""Lightweight practice ЕГЭ mock exam, no user data stored or DB migrations."""
from flask import Blueprint, render_template, request
from ege_advanced import TASKS, same_answer

bp=Blueprint('ege_mock',__name__)
# Deterministic and reproducible selection: 13 short answers and 7 extended (draft 2027).
NUMBERS=list(range(1,21))
def tasks_for_variant(v):
    return [sorted((t for t in TASKS if t['num']==n),key=lambda x:x['key'])[(v-1)%len([t for t in TASKS if t['num']==n])] for n in NUMBERS]

@bp.route('/ege/mock',methods=['GET','POST'])
def home():
    v=request.values.get('variant',type=int) or 1
    if v not in (1,2,3):v=1
    tasks=tasks_for_variant(v)
    results=None
    if request.method=='POST':
        results=[]
        for t in tasks:
            answer=request.form.get('answer_'+str(t['num']),'').strip()[:3000]
            is_correct=(same_answer(answer,t['answer']) if t['answer'] is not None else None)
            results.append({'task':t,'given':answer,'correct':is_correct})
    return render_template('ege_mock.html',tasks=tasks,variant=v,results=results)

def register_ege_mock(app):
    app.register_blueprint(bp)
