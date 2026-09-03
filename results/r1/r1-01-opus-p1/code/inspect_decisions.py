"""Print the agent's decision on hand-built states. No episode is run.

This is a reading aid: it constructs the observation an opening / mid-game /
final-day board would produce and shows the resulting action, plus the internal
crop and animal valuations that drove it.
"""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("cand", str(ROOT / "main.py"))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

PRODUCTS = M.PRODUCTS
CROPS = M.CROPS


def blank(n=10, quads=("NW",)):
    def q(x, y):
        h = n // 2
        return ("N" if y < h else "S") + ("W" if x < h else "E")
    return [[None if q(x, y) in quads else "LOCKED" for x in range(n)] for y in range(n)]


def obs_for(day, hour, tiles, money, shed=None, seeds=None, hands=0,
            shops=(), minv=None, opp_tiles=None, player=0):
    n = len(tiles)
    quads = ["NW"]
    for qq in ("NE", "SW", "SE"):
        h = n // 2
        pos = {"NE": (h, 0), "SW": (0, h), "SE": (h, h)}[qq]
        if tiles[pos[1]][pos[0]] != "LOCKED":
            quads.append(qq)
    me = {"money": float(money), "tiles": tiles, "farmer": [4, 4],
          "hands": [[4, 4] for _ in range(hands)],
          "unlocked_quadrants": quads, "hires_today": hands}
    other = {"money": 3000.0, "tiles": opp_tiles or blank(n),
             "farmer": [4, 4], "hands": [], "unlocked_quadrants": ["NW"],
             "hires_today": 0}
    farms = [me, other] if player == 0 else [other, me]
    inv = minv or {p: 10000 for p in PRODUCTS}
    return {
        "player": player, "day": day, "hour": hour, "step": day * 24 + hour,
        "farms": farms,
        "market": {"inventory": inv,
                   "prices": {p: M.price_at(p, inv[p]) for p in PRODUCTS}},
        "town": {"unlocked_shops": list(shops)},
        "private": {"shed": dict(shed or {}), "seeds": dict(seeds or {}),
                    "inventories": [{} for _ in range(hands + 1)]},
    }


def show(tag, obs):
    act = M.agent(obs)
    ops = {}
    for a in [act["farmer"]] + act["hands"]:
        ops[a[0]] = ops.get(a[0], 0) + 1
    print(f"\n=== {tag} ===")
    print(f"  units: {dict(sorted(ops.items(), key=lambda kv: -kv[1]))}")
    print(f"  market: {act['market']}")


def crop_table(day, minv, shops, fert, mine=None, theirs=None, money=3000):
    mine = mine or {}
    theirs = theirs or {}
    days_left = M.SEASON_DAYS - day
    rows = []
    for c in CROPS:
        u, occ = M._expected_crop(c, day, fert)
        v = M.crop_tile_value(c, day, days_left, fert, mine.get(c, 0),
                              theirs.get(c, 0), minv[c], M.town_drain(c, day, shops),
                              money)
        rows.append((c, u, occ, v or 0.0))
    rows.sort(key=lambda r: -r[3])
    print(f"  crop value/tile-day (day {day}, fert={fert}, bank=${money}, "
          f"mine={mine or '-'}):")
    for c, u, occ, v in rows:
        print(f"    {c:<11} yield {u} over {occ}d -> {v:7.1f}")


def main():
    print("town drain over a full season (day 0, no shops yet):")
    for p in PRODUCTS:
        print(f"    {p:<11} {M.town_drain(p, 0, []):7.0f}")

    minv = {p: 10000 for p in PRODUCTS}
    crop_table(0, minv, [], False)
    crop_table(0, minv, [], False, mine={"MELON": 6}, money=1400)
    crop_table(0, minv, [], False, mine={"MELON": 6, "CARROT": 10}, money=600)
    crop_table(8, minv, ["BAKERY", "PET_CAFE"], True, money=20000)
    crop_table(8, minv, ["BAKERY", "PET_CAFE"], True, money=20000,
               mine={"MELON": 9, "STRAWBERRY": 20, "WHEAT": 20})
    crop_table(24, minv, ["BAKERY"] * 8, True, money=90000)

    show("day 0 h0, empty NW, $3000, no seeds",
         obs_for(0, 0, blank(), 3000))
    show("day 0 h3, empty NW, $3000, melon+carrot seeds, 3 hands",
         obs_for(0, 3, blank(), 1200, seeds={"MELON": 14, "CARROT": 12}, hands=3))

    # mid game: 100 tiles, mixed farm
    t = blank(10, ("NW", "NE", "SW", "SE"))
    for i in range(100):
        x, y = i % 10, i // 10
        if i < 30:
            t[y][x] = {"kind": "COOP", "animal": "GOOSE", "placed_day": 5,
                       "yield_units": 2, "fed_today": False, "consecutive_unfed": 0,
                       "cared_today": False, "fertilizer_available": True,
                       "pending_care_bonus": 1}
        elif i < 60:
            t[y][x] = {"kind": "PLANT", "crop": "WHEAT", "planted_day": 12,
                       "watered_today": False, "consecutive_unwatered": 1,
                       "yield_units": 3, "max_lifespan_step": 17 * 24,
                       "fertilized_until_day": 15}
        elif i < 80:
            t[y][x] = {"kind": "PLANT", "crop": "STRAWBERRY", "planted_day": 4,
                       "watered_today": False, "consecutive_unwatered": 0,
                       "yield_units": 2, "max_lifespan_step": -1,
                       "fertilized_until_day": 15}
    show("day 14 h0, 100 tiles, 30 geese + 30 wheat + 20 strawberry, 12 hands",
         obs_for(14, 0, t, 40000, shed={"WHEAT": 40, "EGG": 30, "STRAWBERRY": 8},
                 seeds={"WHEAT": 5}, hands=12, shops=["BAKERY", "PET_CAFE",
                 "FARMERS_MARKET", "YARN_STORE"]))
    show("day 14 h9, same board (mid-day)",
         obs_for(14, 9, t, 40000, shed={"WHEAT": 40, "EGG": 30, "STRAWBERRY": 8},
                 seeds={"WHEAT": 5}, hands=12, shops=["BAKERY", "PET_CAFE"]))
    show("day 29 h17, final-day liquidation, seat 1",
         obs_for(29, 17, t, 90000, shed={"EGG": 44, "WHEAT": 30, "STRAWBERRY": 12,
                 "FERTILIZER": 14}, hands=12, player=1))


if __name__ == "__main__":
    main()
