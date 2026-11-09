"""Offline synthetic-only score audit; never opens application databases or secrets."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'services/life-core')]
from app.embedding import LocalEmbedding
from memory_load_dataset import LIFE, WORK, STUDY

NEGATIVES = [
    '我驾驶载人飞船登陆火星后做了哪些实验？', '我在南极冰盖下发现了哪一种新细菌？',
    '我率领的战斗机编队执行了什么空战任务？', '我参加奥运会拿到的金牌放在哪里？',
    '我在深海潜艇上发现了哪一艘古代沉船？', '我给国家议会提交了哪一份法律草案？',
    '我移植肾脏的手术用了几个小时？', '我获得诺贝尔物理学奖的研究成果是什么？',
    '我开办的钻石矿今年开采了多少克拉？', '我攀登珠穆朗玛峰时在哪个营地停留？',
    '我给北极科考船设计的核反应堆功率多大？', '我的私人直升飞机停在哪一座机场？',
    '我最近参加的海底火山考察发现了什么？', '我操作粒子加速器时获得了哪些碰撞数据？',
    '我收购的跨国银行有哪些海外分行？', '我训练赛马赢得了哪一项冠军？',
    '我在沙漠挖掘的古墓属于哪个王朝？', '我驾驶货轮经过苏伊士运河用了几天？',
    '我养的鳄鱼叫什么名字？', '我在太空站维修的太阳能阵列发生了什么故障？',
    '我写的交响乐首演由哪支乐团演奏？', '我负责的超导量子芯片有多少个量子比特？',
    '我收藏的陨石来自哪个星系？', '我设计的高速列车最高试验速度是多少？',
]

def main():
    import numpy as np
    cases = LIFE+WORK+STUDY
    model = LocalEmbedding(ROOT/'services/life-core/data/embedding-models')
    assert model.warmup() == 'ready'
    docs = np.asarray(model.embed([row[0] for row in cases]))
    questions = [row[1] for row in cases]+NEGATIVES
    queries = np.asarray(model.query_embed(questions))
    scores = queries @ docs.T
    rows = []
    for index,(query,scored) in enumerate(zip(questions,scores)):
        order = np.argsort(-scored)
        rows.append(dict(query=query,positive=index<len(cases),gold_index=index if index<len(cases) else None,
                         gold_score=round(float(scored[index]),5) if index<len(cases) else None,
                         gold_rank=int(np.where(order==index)[0][0])+1 if index<len(cases) else None,
                         top=[dict(index=int(i),score=round(float(scored[i]),5),text=cases[i][0]) for i in order[:8]]))
    sweep=[]
    for threshold in (0.35,0.38,0.4,0.42,0.44,0.46,0.48,0.5,0.52,0.54,0.56,0.58):
        sweep.append(dict(threshold=threshold,
            positive_top1=sum(r['gold_rank']==1 and r['gold_score']>=threshold for r in rows if r['positive']),
            positive_top8=sum(r['gold_rank']<=8 and r['gold_score']>=threshold for r in rows if r['positive']),
            negative_false_positive=sum(r['top'][0]['score']>=threshold for r in rows if not r['positive'])))
    report=dict(model=model.model_name,positive_count=100,negative_count=len(NEGATIVES),sweep=sweep,rows=rows)
    path=ROOT/'evidence/memory-load-20261109/score-audit.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(sweep,ensure_ascii=False,indent=2),flush=True)
    print('NON_FIRST_GOLD',[(r['gold_index'],r['gold_rank'],r['gold_score']) for r in rows if r['positive'] and r['gold_rank']!=1],flush=True)
    instruction = '为这个句子生成表示以用于检索相关文章：'
    instructed = np.asarray(model.query_embed([instruction+q for q in questions])) @ docs.T
    variants = []
    for index, (query, scored) in enumerate(zip(questions, instructed)):
        order = np.argsort(-scored)
        variants.append(dict(query=query,positive=index<len(cases),gold_index=index if index<len(cases) else None,
                             gold_score=round(float(scored[index]),5) if index<len(cases) else None,
                             gold_rank=int(np.where(order==index)[0][0])+1 if index<len(cases) else None,
                             top=[dict(index=int(i),score=round(float(scored[i]),5),text=cases[i][0]) for i in order[:8]]))
    prefixed_sweep = []
    for threshold in (0.4,0.42,0.44,0.46,0.48,0.5,0.52,0.54,0.56,0.58):
        prefixed_sweep.append(dict(threshold=threshold,
            positive_top1=sum(r['gold_rank']==1 and r['gold_score']>=threshold for r in variants if r['positive']),
            positive_top8=sum(r['gold_rank']<=8 and r['gold_score']>=threshold for r in variants if r['positive']),
            negative_false_positive=sum(r['top'][0]['score']>=threshold for r in variants if not r['positive'])))
    report.update(query_instruction=instruction,instructed_sweep=prefixed_sweep,instructed_rows=variants)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('INSTRUCTED',json.dumps(prefixed_sweep,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    main()
