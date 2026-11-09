"""Pinned larger Chinese dense encoder experiment; synthetic-only and offline inference."""
import importlib.util
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('model_audit',ROOT/'scripts/evaluate-memory-e5.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
REPO='Xenova/bge-large-zh-v1.5'
REV='a48549b3259a6165364f226599cd91f39923d5d5'
DIRECTORY=ROOT/'services/life-core/data/embedding-models'/('bge-large-zh-'+REV)
MODEL='BAAI/bge-large-zh-v1.5-pinned-q8'


def main():
    manifest=module.download_model(REPO,REV,DIRECTORY)
    import numpy as np
    from fastembed import TextEmbedding
    from fastembed.common.model_description import PoolingType,ModelSource
    TextEmbedding.add_custom_model(MODEL,pooling=PoolingType.CLS,normalization=True,
        sources=ModelSource(hf=REPO),dim=1024,model_file='onnx/model_quantized.onnx',license='mit')
    # The upstream tokenizer uses a sentinel > Python's platform integer range.
    # Preserve downloaded artifacts; derive a separate verified 512-token runtime copy.
    import os
    import shutil
    prepared=DIRECTORY/'context-512'
    prepared.mkdir(exist_ok=True)
    for filename in module.FILES:
        target=prepared/filename
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():
            if filename.endswith('.onnx'):
                os.link(DIRECTORY/filename,target)
            else:
                shutil.copy2(DIRECTORY/filename,target)
    config=json.loads((DIRECTORY/'tokenizer_config.json').read_text(encoding='utf-8'))
    config['model_max_length']=512
    (prepared/'tokenizer_config.json').write_text(json.dumps(config,ensure_ascii=False),encoding='utf-8')
    encoder=TextEmbedding(MODEL,specific_model_path=str(prepared),local_files_only=True,threads=2)
    cases=module.LIFE+module.WORK+module.STUDY
    docs=np.asarray(list(encoder.embed([row[0] for row in cases],batch_size=8)))
    questions=[row[1] for row in cases]+module.NEGATIVES
    vectors=np.asarray(list(encoder.embed(questions,batch_size=8)))
    rows=[]
    for index,(query,scored) in enumerate(zip(questions,vectors@docs.T)):
        order=np.argsort(-scored)
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
    report=dict(model=MODEL,source=REPO,revision=REV,license='mit',artifacts=manifest,
        positive_count=100,negative_count=len(module.NEGATIVES),sweep=sweep,rows=rows)
    (ROOT/'evidence/memory-load-20261109/bge-large-score-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(sweep,ensure_ascii=False,indent=2),flush=True)
    print('NON_FIRST_GOLD',[(r['gold_index'],r['gold_rank'],r['gold_score']) for r in rows if r['positive'] and r['gold_rank']!=1],flush=True)

if __name__=='__main__':
    main()
