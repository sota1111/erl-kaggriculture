"""Diagnostics that need a live episode.  Run when the Controller re-enables
simulation:  .venv/bin/python code/m_diag.py [seeds]

Wraps main.py's agent so that every turn is recorded, then reports the things
the design depends on and that no static check can settle:

  * did we ever lose a plant to weeds or an animal to starvation (both
    unrecoverable -- the whole priority scheme exists to make this zero)
  * how many harvested units were discarded at the 100-slot shed cap
  * realised $/unit per product, against the analytic model in code/a_plan.py
  * how many hands we actually hired and how many of their actions were moves
  * worst single-turn wall time over 720 turns
  * the same numbers in self-play, where the opponent sells into our book
"""
import sys, time, collections, statistics
sys.path.insert(0, "tools")
import engine

CAND = sys.argv[1] if len(sys.argv) > 1 else "main.py"
SEEDS = [int(x) for x in sys.argv[2:]] or list(range(1, 13))
PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"]


class Probe(object):
    def __init__(self, fn):
        self.fn = fn
        self.reset()

    def reset(self):
        self.worst = 0.0
        self.turns = 0
        self.moves = 0
        self.acts = 0
        self.hands = []
        self.weeds_seen = 0
        self.prev_plants = None
        self.prev_animals = None
        self.lost_plants = 0
        self.lost_animals = 0
        self.sold = collections.Counter()
        self.revenue = collections.Counter()
        self.prev_money = None
        self.shed_peak = 0

    def __call__(self, obs):
        t = time.perf_counter()
        a = self.fn(obs)
        self.worst = max(self.worst, time.perf_counter() - t)
        self.turns += 1
        me = obs["farms"][obs["player"]]
        self.hands.append(len(me["hands"]))
        priv = obs.get("private") or {}
        self.shed_peak = max(self.shed_peak, sum((priv.get("shed") or {}).values()))
        n_plant = n_animal = n_weed = 0
        for row in me["tiles"]:
            for tile in row:
                if isinstance(tile, dict):
                    k = tile.get("kind")
                    if k == "PLANT":
                        n_plant += 1
                    elif k == "WEED":
                        n_weed += 1
                    elif tile.get("animal"):
                        n_animal += 1
        if obs.get("hour") == 0:
            if self.prev_plants is not None:
                # a weed that appeared where a plant was is a watering failure;
                # random weed spawns only happen on empty tiles
                self.lost_plants += max(0, n_weed - self.weeds_seen)
            if self.prev_animals is not None and n_animal < self.prev_animals:
                self.lost_animals += self.prev_animals - n_animal
            self.prev_plants, self.prev_animals = n_plant, n_animal
            self.weeds_seen = n_weed
        for o in a.get("market", []):
            if o and o[0] == "SELL":
                price = (obs.get("market") or {}).get("prices", {}).get(o[1], 0)
                self.sold[o[1]] += o[2]
                self.revenue[o[1]] += price * o[2]
        self.acts += 1 + len(a.get("hands", []))
        for u in [a.get("farmer", ["PASS"])] + list(a.get("hands", [])):
            if u and u[0] in ("NORTH", "SOUTH", "EAST", "WEST"):
                self.moves += 1
        return a

    def report(self, tag, bank):
        print(f"\n--- {tag}  bank {bank:,.0f} ---")
        print(f"  lost to weeds {self.lost_plants}   animals escaped {self.lost_animals}"
              f"   shed peak {self.shed_peak}/100")
        print(f"  hands: mean {statistics.mean(self.hands):.1f} max {max(self.hands)}"
              f"   moves {self.moves}/{self.acts} actions ({self.moves/max(1,self.acts):.0%})")
        print(f"  worst turn {self.worst*1000:.1f} ms")
        print("  " + "  ".join(f"{p[:4]}:{self.sold[p]}@${self.revenue[p]/max(1,self.sold[p]):.0f}"
                               for p in PRODUCTS if self.sold[p]))


def main():
    agent_fn = engine.load_agent(CAND)
    starter = engine.builtin("starter")
    banks = []
    for seed in SEEDS:
        for seat in (0, 1):
            p = Probe(agent_fn)
            a, b = (engine.play(p, starter, seed) if seat == 0
                    else engine.play(starter, p, seed))
            mine = a if seat == 0 else b
            banks.append(mine)
            p.report(f"seed {seed} seat {seat} vs starter", mine)
    print(f"\nvs starter: mean bank {statistics.mean(banks):,.0f}  min {min(banks):,.0f}")

    self_banks = []
    for seed in SEEDS:
        p, q = Probe(agent_fn), Probe(engine.load_agent(CAND))
        a, b = engine.play(p, q, seed)
        self_banks += [a, b]
        p.report(f"seed {seed} self-play seat 0", a)
    print(f"\nself-play: mean bank {statistics.mean(self_banks):,.0f}  "
          f"min {min(self_banks):,.0f}")
    print("\nCompare the realised $/unit above with code/a_plan.py --rival 1.0: "
          "if the premium goods come in far under model, the reserve prices in "
          "main.py RESERVE are set too low for a market with a second seller.")


if __name__ == "__main__":
    main()
