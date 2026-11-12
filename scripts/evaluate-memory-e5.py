"""Pinned public model experiment using synthetic text only. No service credentials."""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts')]
from memory_load_dataset import LIFE,WORK,STUDY
# Own evaluation code; downloaded files never provide Python modules.
import importlib.util
spec=importlib.util.spec_from_file_location('calibration',ROOT/'scripts/calibrate-memory-semantic.py')
calibration=importlib.util.module_from_spec(spec)
spec.loader.exec_module(calibration)
NEGATIVES=calibration.NEGATIVES
REPO='Xenova/multilingual-e5-small'
REV='761b726dd34fb83930e26aab4e9ac3899aa1fa78'
MODEL='intfloat/multilingual-e5-small-pinned-q8'
DIRECTORY=ROOT/'services/life-core/data/embedding-models'/('e5-small-'+REV)
FILES=['README.md','config.json','tokenizer.json','tokenizer_config.json','special_tokens_map.json','onnx/model_quantized.onnx']


def download_model(repo=REPO, revision=REV, directory=DIRECTORY):
    directory.mkdir(parents=True,exist_ok=True)
    manifest=[]
    with httpx.Client(timeout=60,follow_redirects=True) as client:
        metadata=client.get(f'https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true')
        metadata.raise_for_status()
        by_path={r['rfilename']:r for r in metadata.json()['siblings']}
        for name in FILES:
            path=directory/name
            expected=by_path[name]
            if not path.exists():
                path.parent.mkdir(parents=True,exist_ok=True)
                temporary=path.with_suffix(path.suffix+'.partial')
                with client.stream('GET',f'https://huggingface.co/{repo}/resolve/{revision}/{name}') as response:
                    response.raise_for_status()
                    with temporary.open('wb') as output:
                        for chunk in response.iter_bytes():
                            output.write(chunk)
                temporary.replace(path)
            data=path.read_bytes()
            digest=hashlib.sha256(data).hexdigest()
            if expected.get('lfs'):
                assert digest==expected['lfs']['sha256'], 'MODEL_HASH_MISMATCH'
            else:
                git_hash=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
                assert git_hash==expected['blobId'], 'MODEL_FILE_HASH_MISMATCH'
            manifest.append(dict(file=name,size=len(data),sha256=digest))
            print('MODEL_FILE_OK',name,len(data),flush=True)
    return manifest


def main():
    manifest = download_model()
    import numpy as np
    from fastembed import TextEmbedding
    from fastembed.common.model_description import PoolingType,ModelSource
    TextEmbedding.add_custom_model(MODEL,pooling=PoolingType.MEAN,normalization=True,
        sources=ModelSource(hf=REPO),dim=384,model_file='onnx/model_quantized.onnx',license='mit')
    encoder=TextEmbedding(model_name=MODEL,specific_model_path=str(DIRECTORY),local_files_only=True,threads=2)
    cases=LIFE+WORK+STUDY
    docs=np.asarray(list(encoder.embed(['passage: '+row[0] for row in cases],batch_size=16)))
    queries=[row[1] for row in cases]+NEGATIVES
    vectors=np.asarray(list(encoder.embed(['query: '+q for q in queries],batch_size=16)))
    rows=[]
    for index,(query,scored) in enumerate(zip(queries,vectors@docs.T)):
        order=np.argsort(-scored)
        rows.append(dict(query=query,positive=index<len(cases),gold_index=index if index<len(cases) else None,
            gold_score=round(float(scored[index]),5) if index<len(cases) else None,
            gold_rank=int(np.where(order==index)[0][0])+1 if index<len(cases) else None,
            top=[dict(index=int(i),score=round(float(scored[i]),5),text=cases[i][0]) for i in order[:8]]))
    sweep=[]
    for threshold in (0.7,0.72,0.74,0.76,0.78,0.8,0.82,0.84,0.86):
        sweep.append(dict(threshold=threshold,
            positive_top1=sum(r['gold_rank']==1 and r['gold_score']>=threshold for r in rows if r['positive']),
            positive_top8=sum(r['gold_rank']<=8 and r['gold_score']>=threshold for r in rows if r['positive']),
            negative_false_positive=sum(r['top'][0]['score']>=threshold for r in rows if not r['positive'])))
    report=dict(model=MODEL,source=REPO,revision=REV,license='mit',artifacts=manifest,
        positive_count=100,negative_count=len(NEGATIVES),sweep=sweep,rows=rows)
    (ROOT/'evidence/memory-load-20261109/e5-score-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(sweep,ensure_ascii=False,indent=2),flush=True)
    print('NON_FIRST_GOLD',[(r['gold_index'],r['gold_rank'],r['gold_score']) for r in rows if r['positive'] and r['gold_rank']!=1],flush=True)

if __name__=='__main__':
    main()
