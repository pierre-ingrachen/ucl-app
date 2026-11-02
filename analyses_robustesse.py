"""Analyses de robustesse du modele D (sur experiences_probas.pkl, genere par experiences_modele.py) :
1) stabilite de la regle "victoire exterieure" selon l ecart exige et la saison, avec IC95 ;
2) persistance du ROI par (ligue, issue) ; 3) regles positives dans les 4 saisons de test.
Usage : .venv/bin/python analyses_robustesse.py"""
import sys,pickle,warnings; sys.path.insert(0,'.'); warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import experiences_modele as X, entrainer_modele_d as D, evaluation_paris as ev
d=D.charger_avec_ratings(); P=pickle.load(open("experiences_probas.pkl","rb"))
T4=[2024,2025,2026,2027]
def ens(cfgs):
    out={}
    for T in T4:
        pos=P[cfgs[0]][T][0]; out[T]=(pos,np.mean([P[c][T][1] for c in cfgs],axis=0))
    return out
groups={"mlp_ens":[c for c in P if c[0]=="mlp" and c[1]!="base"],
        "hgb_ens":[c for c in P if c[0]=="hgb" and c[1]!="base"],
        "tous_ens":[c for c in P if c[1]!="base"]}
def cand(folds,scen): return pd.concat([X.candidats(d,*folds[T],scen,T) for T in T4],ignore_index=True)
def boot(q,n=2000):
    rng=np.random.default_rng(0);idx=rng.integers(0,len(q),(n,len(q)));r=q.profit.to_numpy()[idx].sum(1)/q.mise.to_numpy()[idx].sum(1)
    return np.percentile(r,[2.5,97.5])
for gname,cfgs in groups.items():
    F=ens(cfgs)
    print("=====",gname,len(cfgs),"modeles")
    for scen in ("Bet365 cloture -5%","Bet365 cloture -10%"):
        c=cand(F,scen)
        print("--",scen,"| regle issue=2, plafond 8 : ROI% (n) par saison, selon ecart exige")
        for e in (0.10,0.15,0.20,0.25,0.30):
            row=[]
            for T in T4:
                q=X.appliquer(c[c.saison==T],(e,8.0,"2",0.0)); row.append(f"{100*X.roi(q):6.1f}({len(q):3d})")
            q=X.appliquer(c,(e,8.0,"2",0.0)); lo,hi=boot(q)
            print(f"  ecart>={e:.2f}: "+"  ".join(row)+f"  | total {100*X.roi(q):5.1f}% n={len(q)} IC[{100*lo:.0f};{100*hi:.0f}]")

# --- 2) et 3) ---
import sys,pickle,warnings; sys.path.insert(0,'.'); warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import experiences_modele as X, entrainer_modele_d as D
d=D.charger_avec_ratings(); P=pickle.load(open("experiences_probas.pkl","rb"))
# E1 : ROI aveugle par (ligue, issue) sur cote>4, Bet365 -5% : persistance entre saisons paires/impaires et dev/conf
rows=[]
for scen in ("Bet365 cloture -5%",):
    cs=D.cotes_scenario(d,scen); g=np.eye(3)[d.y.astype(int)]
    for k in range(3):
        c=cs[:,k]; m=np.isfinite(c)&(c>4)
        df=pd.DataFrame({"ligue":d.ligue[m].values,"saison":d.saison_fin[m].values,"issue":k,"mise":1/c[m],"profit":g[m,k]-1/c[m]})
        rows.append(df)
a=pd.concat(rows)
a["per"]=np.where(a.saison<=2024,"A(<=2023-24)",np.where(a.saison<=2026,"B(2024-26)","C"))
r=a.groupby(["ligue","issue","per"]).apply(lambda g: pd.Series({"n":len(g),"roi":g.profit.sum()/g.mise.sum()})).unstack("per")
r=r.dropna(); 
r["roi_A"]=r[("roi","A(<=2023-24)")];r["roi_B"]=r[("roi","B(2024-26)")];r["nA"]=r[("n","A(<=2023-24)")];r["nB"]=r[("n","B(2024-26)")]
r=r[(r.nA>=60)&(r.nB>=60)]
print("correlation du ROI aveugle (ligue,issue) entre periode A et B :",round(np.corrcoef(r.roi_A,r.roi_B)[0,1],3),"sur",len(r),"cellules")
pos=r[(r.roi_A>0)&(r.roi_B>0)]
print("cellules positives dans les 2 periodes :",len(pos)); print(pos[["nA","roi_A","nB","roi_B"]].round(3).to_string())
# par issue
print(a.groupby("issue").apply(lambda g: g.profit.sum()/g.mise.sum()).round(3).to_dict())
# E2 : regles robustes sur les 4 folds (tous_ens)
T4=[2024,2025,2026,2027]
cfgs=[c for c in P if c[1]!="base"]
F={T:(P[cfgs[0]][T][0],np.mean([P[c][T][1] for c in cfgs],axis=0)) for T in T4}
for scen in ("Bet365 cloture -5%","Bet365 cloture -10%"):
    c=pd.concat([X.candidats(d,*F[T],scen,T) for T in T4],ignore_index=True)
    ok=[];tot=0
    for regle in X.GRILLE:
        q=X.appliquer(c,regle); 
        if len(q)<150: continue
        tot+=1
        rs=[X.roi(q[q.saison==T]) for T in T4]; ns=[(q.saison==T).sum() for T in T4]
        if min(ns)>=15 and min(rs)>0: ok.append((regle,len(q),[round(100*r,1) for r in rs],round(100*X.roi(q),1)))
    print(scen,": regles (>=150 paris) positives dans les 4 saisons :",len(ok),"sur",tot)
    for o in ok[:10]: print("  ",o)
