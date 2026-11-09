"""Compare a local Chinese neural cross-encoder on synthetic positive/negative pairs."""
import importlib.util
import json
import math
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('model_audit',ROOT/'scripts/evaluate-memory-e5.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
REPO='Xenova/bge-reranker-base'
REV='280bcc27a84e0b898c251e06fddb25171bd9b101'
DIRECTORY=ROOT/'services/life-core/data/embedding-models'/('bge-reranker-base-'+REV)


def main():
    manifest=module.download_model(REPO,REV,DIRECTORY)
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    from fastembed.common.model_description import ModelSource
    TextCrossEncoder.add_custom_model(REPO,sources=ModelSource(hf=REPO),model_file='onnx/model_quantized.onnx',license='mit')
    encoder=TextCrossEncoder(REPO,specific_model_path=str(DIRECTORY),local_files_only=True,threads=2)
    audit=json.loads((ROOT/'evidence/memory-load-20261109/score-audit.json').read_text(encoding='utf-8'))
    cases=module.LIFE+module.WORK+module.STUDY
    rows=[]
    for index,row in enumerate(audit['rows']):
        # All 100 authorized documents participate in vector scoring. This
        # independent experiment examines its 8 closest meanings, never a text filter.
        candidates=list(row['top'])
        started=time.perf_counter()
        scores=list(encoder.rerank(row['query'],[r['text'] for r in candidates],batch_size=8))
        ranked=sorted([dict(**item,logit=round(score,5),confidence=round(1/(1+math.exp(-max(-50,min(50,score)))),5))
                       for item,score in zip(candidates,scores)],key=lambda item:-item['logit'])
        gold=next((i for i,item in enumerate(ranked,1) if item['index']==row['gold_index']),None)
        gold_score=next((item['confidence'] for item in ranked if item['index']==row['gold_index']),None)
        rows.append(dict(query=row['query'],positive=row['positive'],gold_index=row['gold_index'],rank=gold,
                         gold_score=gold_score,elapsed_ms=round((time.perf_counter()-started)*1000,2),top=ranked))
        if (index+1)%20==0:
            print('RERANKED',index+1,len(audit['rows']),flush=True)
    sweep=[]
    for threshold in (0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8):
        sweep.append(dict(threshold=threshold,
            positive_top1=sum(r['rank']==1 and r['gold_score']>=threshold for r in rows if r['positive']),
            positive_top8=sum(r['rank'] is not None and r['gold_score']>=threshold for r in rows if r['positive']),
            negative_false_positive=sum(r['top'][0]['confidence']>=threshold for r in rows if not r['positive'])))
    report=dict(model=REPO,revision=REV,license='mit',artifacts=manifest,rows=rows,sweep=sweep)
    (ROOT/'evidence/memory-load-20261109/reranker-score-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(sweep,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    main()
