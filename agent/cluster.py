"""Deterministic opportunity clustering and historical index helpers."""
from __future__ import annotations
import json, re
from pathlib import Path
from collections import defaultdict

STOPWORDS={"the","and","for","with","from","that","this","need","looking","help","china","rule","based","demand"}

def _norm(text:str)->str:
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9 ]+"," ",(text or "").lower())).strip()

def tokens_for_key(title:str,pain_point:str)->list[str]:
    toks=[t for t in (_norm(title)+" "+_norm(pain_point)).split() if len(t)>2 and t not in STOPWORDS]
    return sorted(dict.fromkeys(toks))

def opportunity_key(opportunity:dict)->str:
    toks=tokens_for_key(opportunity.get("title",""), opportunity.get("pain_point",""))
    return "|".join(toks[:8]) or "unknown"

def cluster_opportunities(opportunities:list[dict])->list[dict]:
    groups=defaultdict(list)
    for opp in opportunities:
        groups[opportunity_key(opp)].append(dict(opp))
    merged=[]
    for _, items in groups.items():
        rep=max(items,key=lambda o: float(o.get('weighted_score',o.get('opportunity_score',0)) or 0))
        urls=[]; quotes=[]; sources=set()
        for it in items:
            urls.extend(it.get('evidence_urls',[]) or [])
            quotes.extend(it.get('evidence_quotes',[]) or [])
            if it.get('source'): sources.add(it['source'])
        rep['evidence_urls']=sorted(dict.fromkeys(str(u) for u in urls if u))
        rep['evidence_quotes']=list(dict.fromkeys(str(q) for q in quotes if q))
        rep['source_count']=max(1,len(sources))
        rep['evidence_count']=len(rep['evidence_urls'])+len(rep['evidence_quotes'])
        rep['cluster_size']=len(items)
        merged.append(rep)
    merged.sort(key=lambda o: float(o.get('weighted_score',o.get('opportunity_score',0)) or 0), reverse=True)
    return merged

def load_history(path:str|Path)->dict[str,int]:
    p=Path(path)
    if not p.exists(): return {}
    out={}
    for line in p.read_text(encoding='utf-8').splitlines():
        if not line.strip(): continue
        row=json.loads(line)
        out[str(row.get('key',''))]=int(row.get('count',1))
    return out

def mark_history(opportunities:list[dict], history:dict[str,int])->list[dict]:
    for opp in opportunities:
        key=opportunity_key(opp)
        cnt=history.get(key,0)
        opp['history_key']=key
        opp['history_status']='new' if cnt==0 else ('repeated' if cnt==1 else 'recurring')
    return opportunities

def update_history_index(opportunities:list[dict], path:str|Path)->None:
    hist=load_history(path)
    for opp in opportunities:
        key=opp.get('history_key') or opportunity_key(opp)
        hist[key]=hist.get(key,0)+1
    p=Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps({'key':k,'count':v}, ensure_ascii=False, sort_keys=True) for k,v in sorted(hist.items()))+"\n", encoding='utf-8')
