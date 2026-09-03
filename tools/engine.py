"""Episode backend: kagsim when it validates, kaggle_environments otherwise.

kagsim is a bit-exact C++ port of the 1.32.7 engine (destbreso/kaggriculture-cppsim,
built on nikital7's port). It is ~19x faster than kaggle_environments for live Python
agents and ~4000x for fixed action streams. A fast simulator that has silently drifted
from the real engine is worse than a slow one, so every process self-checks before it
is trusted and degrades to slow rather than to wrong.
"""
from __future__ import annotations

_BACKEND = None


def _selfcheck_kagsim():
    import kagsim
    s = kagsim.Stream([])
    if kagsim.run_episode(s, s, seed=11) != (3000.0, 3000.0):
        raise RuntimeError("kagsim self-check failed on the idle episode")
    return kagsim


def backend() -> str:
    play(lambda o: {"farmer": ["PASS"], "hands": [], "market": []},
         lambda o: {"farmer": ["PASS"], "hands": [], "market": []}, 11)
    return _BACKEND


def play(agent_a, agent_b, seed: int):
    """Run one 720-turn episode between two callables. Returns (bank_a, bank_b)."""
    global _BACKEND
    if _BACKEND != "kaggle_environments":
        try:
            kagsim = _selfcheck_kagsim()
            g = kagsim.Game(int(seed))
            while not g.done:
                g.step(agent_a(g.observe(0)), agent_b(g.observe(1)))
            _BACKEND = "kagsim"
            return float(g.reward(0)), float(g.reward(1))
        except Exception:
            _BACKEND = "kaggle_environments"
    from kaggle_environments import make
    env = make("kaggriculture", configuration={"seed": int(seed)}, debug=False)
    env.run([agent_a, agent_b])
    a, b = env.steps[-1]
    return float(a.reward or 0), float(b.reward or 0)


def load_agent(path: str):
    """Load agent(obs) from a python file, isolated so module globals never leak."""
    import importlib.util, sys, hashlib
    name = "ag_" + hashlib.sha1(str(path).encode()).hexdigest()[:12]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod.agent


def builtin(name: str):
    """The environment's own agents: 'starter', 'random', 'pass'."""
    from kaggle_environments.envs.kaggriculture import kaggriculture as kg
    return getattr(kg, f"{name}_agent")
