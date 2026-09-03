"""ローカル採点(弱い相手に対する所持金)が、強い相手同士の勝敗を予測するかを測る。"""
import itertools, importlib.util, sys, json
from concurrent.futures import ProcessPoolExecutor

AGENTS = ["moon198","gpt_champion","soil_remembers_rain","moon_counts_melons",
          "kaitofukami_v17_market_ranker","pilkwang_economic_control","roman_hamburger_anchor"]
SEEDS = [7,42,101,202,303,404,505,777,1234,2026,5555,9001]

def _load(name):
    p=f"agents/{name}.py"
    s=importlib.util.spec_from_file_location(f"ag_{name}",p)
    m=importlib.util.module_from_spec(s); sys.modules[f"ag_{name}"]=m; s.loader.exec_module(m)
    return m.agent

def game(task):
    a,b,seed = task
    from kaggle_environments import make
    A = _load(a) if a not in ("starter","random","pass") else a
    B = _load(b) if b not in ("starter","random","pass") else b
    e = make("kaggriculture", configuration={"seed":seed}, debug=False)
    e.run([A,B])
    r=[s.reward for s in e.steps[-1]]
    return a,b,seed,r[0],r[1]

if __name__=="__main__":
    tasks=[]
    for ag in AGENTS:                       # (a) 弱い相手に対する所持金
        for sd in SEEDS: tasks.append((ag,"starter",sd))
    for x,y in itertools.combinations(AGENTS,2):   # (b) 強い相手同士の総当たり(両席)
        for sd in SEEDS:
            tasks.append((x,y,sd)); tasks.append((y,x,sd))
    print(f"episodes: {len(tasks)}", flush=True)
    with ProcessPoolExecutor(max_workers=24) as ex:
        rows=list(ex.map(game, tasks, chunksize=4))
    json.dump(rows, open("exp_local_signal.json","w"))
    print("done", flush=True)
