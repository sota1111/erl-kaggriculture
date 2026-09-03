"""Kaggriculture agent — rule-based controller driven by the market price curve.

Strategy family: rule-based control (no search, no learning).  The season plan is
not a fixed opening book; every allocation decision (what to plant, what animal to
buy, what to sell) is scored against the *marginal* market price the goods will
actually fetch, computed from the shipped price function with our own production
pipeline already added to market inventory.  See agent_submission.json for the
measurements this is built on.

The two hard invariants — every plant watered, every animal fed — dominate every
priority; they are unrecoverable if broken.
"""

import math

# ---------------------------------------------------------------- game tables
# Copied from kaggle_environments 1.32.7 (kaggriculture.py) so the agent can
# price its own marginal unit without importing the environment.

TURNS_PER_DAY = 24
LAST_DAY = 29

CROPS = {
    "WHEAT":      {"seed": 10, "first": 2, "maxday": 4,  "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT":     {"seed": 20, "first": 2, "maxday": 3,  "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO":     {"seed": 50, "first": 8, "maxday": 8,  "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first": 10, "maxday": 10, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON":      {"seed": 80, "first": 10, "maxday": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}

ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP",    "first": 4, "interval": 1, "max_held": 4, "product": "EGG"},
    "COW":   {"cost": 400, "structure": "PASTURE", "first": 8, "interval": 2, "max_held": 6, "product": "MILK"},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "first": 6, "interval": 3, "max_held": 6, "product": "WOOL"},
}

PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"]

MARKET_PARAMS = {
    "WHEAT":      {"base":  25, "I0": 10000, "T": 400, "bf": "sqrt",   "bt": 0.80, "af": "log",    "at": 0.20},
    "CARROT":     {"base":  35, "I0": 10000, "T": 450, "bf": "hinge",  "bt": 1.00, "af": "sqrt",   "at": 0.70},
    "TOMATO":     {"base":  60, "I0": 10000, "T": 200, "bf": "hinge",  "bt": 0.40, "af": "sqrt",   "at": 0.60},
    "STRAWBERRY": {"base": 120, "I0": 10000, "T": 100, "bf": "sqrt",   "bt": 0.70, "af": "linear", "at": 1.60},
    "MELON":      {"base": 250, "I0": 10000, "T": 300, "bf": "log",    "bt": 0.20, "af": "sq",     "at": 3.60},
    "EGG":        {"base":  50, "I0": 10000, "T": 332, "bf": "hinge",  "bt": 0.40, "af": "log",    "at": 0.20},
    "MILK":       {"base": 160, "I0": 10000, "T": 122, "bf": "sqrt",   "bt": 0.60, "af": "linear", "at": 1.60},
    "WOOL":       {"base": 200, "I0": 10000, "T": 105, "bf": "log",    "bt": 0.20, "af": "sq",     "at": 3.20},
    "FERTILIZER": {"base": 100, "I0": 10000, "T": 200, "bf": "linear", "bt": 0.40, "af": "linear", "at": 0.40},
}

HINGE_GAIN = 8.0


def _shape(func, x, T):
    x = max(0.0, x)
    if func == "linear":
        return x
    if func == "sq":
        return x * x
    if func == "sqrt":
        return math.sqrt(x)
    if func == "log":
        return math.log(1.0 + x)
    if func == "log10":
        return math.log10(1.0 + x)
    if func == "hinge":
        if not T or T <= 0:
            return x
        u = x / T
        return u + HINGE_GAIN * max(0.0, u - 1.0) ** 2
    return x


def market_price(item, inventory):
    p = MARKET_PARAMS.get(item)
    if p is None:
        return 1
    base, I0, T = p["base"], p["I0"], p["T"]
    if inventory < I0:
        amp = p["bt"] * base / _shape(p["bf"], T, T)
        price = base + amp * _shape(p["bf"], I0 - inventory, T)
    else:
        amp = p["at"] * base / _shape(p["af"], T, T)
        price = base - amp * _shape(p["af"], inventory - I0, T)
    return max(1, int(round(price)))


# ------------------------------------------------------------------- policy
# Reserve prices: the marginal price below which a unit is worth more held than
# sold.  Chosen so that, at the town's expected season-long drain, the volume we
# can move stays inside the flat part of each curve (see agent_submission.json
# §price_curve / §town_demand).  Melon and fertilizer have (almost) no town
# demand, so their reserves are the real production caps.
RESERVE = {
    "WHEAT": 17, "CARROT": 24, "TOMATO": 38, "STRAWBERRY": 95, "MELON": 130,
    "EGG": 33, "MILK": 125, "WOOL": 150, "FERTILIZER": 35,
}

# tile-days a tile is occupied, and units harvested per cycle without / with
# fertilizer applied through the whole bonus window.
CROP_ECON = {
    "WHEAT":      {"cycle": 5,  "units": 4, "fert": 6, "plant_by": 24},
    "CARROT":     {"cycle": 4,  "units": 3, "fert": 4, "plant_by": 25},
    "TOMATO":     {"cycle": 12, "units": 4, "fert": 8, "plant_by": 17},
    "STRAWBERRY": {"cycle": 17, "units": 4, "fert": 8, "plant_by": 12},
    "MELON":      {"cycle": 11, "units": 6, "fert": 6, "plant_by": 19},
}

# Share of the crop-tile budget each crop may occupy, and a hard cap.  Set from
# code/a_mix.py: the caps are roughly where each product's own price curve stops
# paying, so the board ends up carrying every line at once rather than the single
# best one.  Which line actually wins in a given season is left to the live
# price via _crop_ranking.
CROP_SHARE = {"MELON": (0.16, 12), "STRAWBERRY": (0.26, 20),
              "TOMATO": (0.10, 8), "CARROT": (0.16, 14)}

# animals per unlocked tile, hard cap, last day worth buying
ANIMAL_PLAN = {"GOOSE": (0.20, 20, 20), "COW": (0.07, 7, 18), "SHEEP": (0.07, 7, 20)}

# Which shops eat what, and how much.  A shop instance consumes one of each
# product it demands every 4 turns (6/day), doubled when it is the shop's only
# product.  The town centre eats one of every non-fertilizer product per day.
SHOP_DEMAND = {
    "BAKERY": ("EGG", "WHEAT"),
    "PIZZA_SHOP": ("MILK", "TOMATO", "WHEAT"),
    "BRUNCH_SPOT": ("EGG", "WHEAT", "STRAWBERRY"),
    "YARN_STORE": ("WOOL",),
    "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"),
    "PET_CAFE": ("CARROT",),
    "SMOOTHIE_SHOP": ("STRAWBERRY", "MILK"),
    "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
}

# steady production per animal per day assuming it is fed and CAREd every day
ANIMAL_RATE = {"GOOSE": 2.0, "COW": 1.5, "SHEEP": 4.0 / 3.0}

# harvest an animal once holding this much, to stay under max_held
ANIMAL_PICK = {"GOOSE": 3, "COW": 4, "SHEEP": 3}

PASS = {"farmer": ["PASS"], "hands": [], "market": []}


def agent(obs):
    try:
        action = _decide(obs)
        if not isinstance(action, dict):
            return dict(PASS)
        farmer = action.get("farmer")
        hands = action.get("hands")
        market = action.get("market")
        return {
            "farmer": farmer if isinstance(farmer, list) and farmer else ["PASS"],
            "hands": hands if isinstance(hands, list) else [],
            "market": market[:10] if isinstance(market, list) else [],
        }
    except Exception:
        return {"farmer": ["PASS"], "hands": [], "market": []}


# --------------------------------------------------------------- observation

class _View(object):
    """Everything the policy needs, pulled out of obs with defaults."""

    def __init__(self, obs):
        self.player = int(obs.get("player", 0) or 0)
        farms = obs.get("farms") or [{}]
        if self.player >= len(farms):
            self.player = 0
        self.farm = farms[self.player] or {}
        self.tiles = self.farm.get("tiles") or [[None]]
        self.board = len(self.tiles)
        self.half = max(1, self.board // 2)
        self.day = int(obs.get("day", 0) or 0)
        self.hour = int(obs.get("hour", 0) or 0)
        self.step = int(obs.get("step", self.day * TURNS_PER_DAY + self.hour) or 0)
        self.money = float(self.farm.get("money", 0) or 0)

        private = obs.get("private") or {}
        self.shed = dict(private.get("shed") or {})
        self.seeds = dict(private.get("seeds") or {})
        raw_inv = private.get("inventories") or [{}]

        market = obs.get("market") or {}
        town = obs.get("town") or {}
        shops = town.get("unlocked_shops") or []
        self.shops = list(shops) if isinstance(shops, list) else []
        self.minv = dict(market.get("inventory") or {})
        for p in PRODUCTS:
            self.minv.setdefault(p, MARKET_PARAMS[p]["I0"])

        self.units = [tuple((self.farm.get("farmer") or [0, 0])[:2])]
        for h in (self.farm.get("hands") or []):
            self.units.append(tuple(h[:2]))
        self.inv = []
        for i in range(len(self.units)):
            self.inv.append(dict(raw_inv[i]) if i < len(raw_inv) and isinstance(raw_inv[i], dict) else {})
        self.hires_today = int(self.farm.get("hires_today", len(self.units) - 1) or 0)

        self.shed_total = sum(v for v in self.shed.values() if isinstance(v, (int, float)))
        self.carried = {}
        for inv in self.inv:
            for k, v in inv.items():
                self.carried[k] = self.carried.get(k, 0) + v

        # tile census
        self.owned = []
        self.plants = []      # (x, y, tile)
        self.animals = []     # (x, y, tile)
        self.empty_struct = []
        self.weeds = []
        self.empties = []
        for y in range(self.board):
            row = self.tiles[y] if isinstance(self.tiles[y], list) else []
            for x in range(len(row)):
                t = row[x]
                if t == "LOCKED":
                    continue
                self.owned.append((x, y))
                if t is None:
                    self.empties.append((x, y))
                elif isinstance(t, dict):
                    kind = t.get("kind")
                    if kind == "PLANT":
                        self.plants.append((x, y, t))
                    elif kind == "WEED":
                        self.weeds.append((x, y))
                    elif t.get("animal"):
                        self.animals.append((x, y, t))
                    elif kind in ("COOP", "PASTURE"):
                        self.empty_struct.append((x, y, t))
        self.owned_set = set(self.owned)

        self.live_crop = {}
        for _, _, t in self.plants:
            c = t.get("crop")
            self.live_crop[c] = self.live_crop.get(c, 0) + 1
        self.live_animal = {}
        for _, _, t in self.animals:
            a = t.get("animal")
            self.live_animal[a] = self.live_animal.get(a, 0) + 1
        self.n_animals = len(self.animals)
        self.days_left = max(0, LAST_DAY - self.day)

        self._pipe = {}
        self._eff = {}
        self.shed_tiles = [(self.half - 1, self.half - 1), (self.half, self.half - 1),
                           (self.half - 1, self.half), (self.half, self.half)]
        self.shed_tiles = [p for p in self.shed_tiles
                           if 0 <= p[0] < self.board and 0 <= p[1] < self.board]
        if not self.shed_tiles:
            self.shed_tiles = [(0, 0)]

    # ---- market pricing with our own pipeline priced in

    def pipeline(self, product, horizon=6):
        """Units of `product` we already own or will produce within `horizon`
        days.  Crops in the ground count their whole remaining cycle; animals
        count their production rate over the horizon."""
        key = (product, horizon)
        if key in self._pipe:
            return self._pipe[key]
        n = self.shed.get(product, 0) + self.carried.get(product, 0)
        if product in CROPS:
            per = CROP_ECON[product]["units"]
            for _, _, t in self.plants:
                if t.get("crop") == product:
                    n += max(t.get("yield_units", 0), per - 1)
        span = min(horizon, self.days_left)
        for kind, a in ANIMALS.items():
            # an animal in the shed is one PLACE away from producing; if it did
            # not count here we would buy the same herd again every turn
            owned = (self.live_animal.get(kind, 0) + self.shed.get(kind, 0)
                     + self.carried.get(kind, 0))
            if a["product"] == product:
                n += int(owned * ANIMAL_RATE[kind] * span)
            if product == "FERTILIZER":
                n += owned * span
        self._pipe[key] = n
        return n

    def drain_rate(self, product):
        """Units/day the town removes right now, read off the unlocked shop list."""
        n = 0 if product == "FERTILIZER" else 1
        for shop in self.shops:
            demand = SHOP_DEMAND.get(shop)
            if demand and product in demand:
                n += 6 * (2 if len(demand) == 1 else 1)
        return n

    def eff_price(self, product, horizon=6):
        """Marginal price of our next unit: our own pipeline pushed into the
        book, less what the town will have eaten by the time we get there.
        This is what makes the plan react to the shop draw -- wool is worth
        four times as much in a season that rolled a yarn store, and worth
        buying a third sheep for only in that season."""
        if (product, horizon) in self._eff:
            return self._eff[(product, horizon)]
        look = min(horizon, self.days_left + 1)
        inv = (self.minv.get(product, 10000) + self.pipeline(product, horizon)
               - look * self.drain_rate(product))
        self._eff[(product, horizon)] = market_price(product, inv)
        return self._eff[(product, horizon)]

    def spot(self, product):
        return market_price(product, self.minv.get(product, 10000))

    def in_animal_zone(self, x, y):
        """NE quadrant is reserved for coops and pastures (it is bought first)."""
        return x >= self.half and y < self.half


def _dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _step_toward(pos, tgt):
    if pos[0] < tgt[0]:
        return ["EAST"]
    if pos[0] > tgt[0]:
        return ["WEST"]
    if pos[1] < tgt[1]:
        return ["SOUTH"]
    if pos[1] > tgt[1]:
        return ["NORTH"]
    return None


# ------------------------------------------------------------------ planning

def _crop_ranking(v, fert_rich):
    """Crops worth planting right now, best first, with how many tiles each may take."""
    animal_tiles = 0
    for kind, (share, cap, _by) in ANIMAL_PLAN.items():
        animal_tiles += min(cap, int(share * len(v.owned)))
    crop_budget = max(1, len(v.owned) - animal_tiles)

    out = []
    for crop, cd in CROPS.items():
        econ = CROP_ECON[crop]
        if v.day > econ["plant_by"]:
            continue
        # cash-flow guard: while broke, only crops that turn over fast
        if v.money < 1500 and econ["cycle"] > 5:
            continue
        seed_cost = CROPS[crop]["seed"]
        if v.money < seed_cost:
            continue
        share = CROP_SHARE.get(crop)
        if share is None:
            cap = crop_budget
        else:
            cap = min(share[1], max(1, int(share[0] * crop_budget)))
        room = cap - v.live_crop.get(crop, 0)
        if room <= 0:
            continue
        units = econ["fert"] if fert_rich else econ["units"]
        price = v.eff_price(crop)
        score = (units * price - seed_cost) / float(econ["cycle"])
        if score <= 6:
            continue
        out.append((score, crop, room))
    out.sort(reverse=True)
    return out


def _animal_room(v, kind, limit):
    """How many more of `kind` the market can still absorb.

    An animal placed today sells its product for the rest of the season, so it
    is judged over that whole span, not over the six-day horizon used for crop
    rotation.  Milk and wool collapse after ~50-70 units into an undrained
    market, so this is what stops the herd at two sheep in a season with no
    yarn store and takes it to seven when the town rolled three."""
    a = ANIMALS[kind]
    prod = a["product"]
    producing = max(1, min(20, v.days_left - a["first"]))
    span = min(producing, v.days_left)
    base = (v.minv.get(prod, 10000) + v.pipeline(prod, producing)
            - min(producing, v.days_left + 1) * v.drain_rate(prod))
    floor = RESERVE[prod] * 0.9
    n = 0
    while n < limit:
        if market_price(prod, int(base + (n + 1) * ANIMAL_RATE[kind] * span)) < floor:
            break
        n += 1
    return n


def _animal_wanted(v):
    """{kind: how many more we want placed}, only while they still pay back."""
    want = {}
    for kind, (share, cap, buy_by) in ANIMAL_PLAN.items():
        a = ANIMALS[kind]
        if v.day > buy_by or v.days_left - a["first"] < 3 or v.money < a["cost"] + 200:
            continue
        target = min(cap, int(share * len(v.owned)))
        have = (v.live_animal.get(kind, 0) + v.shed.get(kind, 0) + v.carried.get(kind, 0))
        room = _animal_room(v, kind, min(cap, max(0, target - have)))
        if room > 0:
            want[kind] = room
    return want


def _reserve_price(v, item):
    r = float(RESERVE.get(item, 1))
    if v.day >= 26:
        r *= max(0.0, (LAST_DAY - v.day) / 4.0)
    press = (v.shed_total - 55) / 40.0
    if press > 0:
        r *= max(0.0, 1.0 - min(1.0, press))
    return max(1.0, r)


def _sell_quantity(v, item, have, reserve):
    if have <= 0:
        return 0
    if reserve <= 1:
        return have
    inv = v.minv.get(item, 10000)
    n = 0
    limit = min(have, 500)
    while n < limit:
        if market_price(item, inv + n + 2) < reserve:
            break
        n += 1
    return n


# ------------------------------------------------------------------- tasks

def _tile_tasks(v, fert_rich, struct_useful):
    """pos -> list of (priority, action, requirement) sorted best-first."""
    tasks = {}
    last = v.day >= LAST_DAY

    for (x, y, t) in v.plants:
        crop = t.get("crop")
        cd = CROPS.get(crop)
        if cd is None:
            continue
        econ = CROP_ECON[crop]
        age = v.day - int(t.get("planted_day", v.day))
        watered = bool(t.get("watered_today"))
        unwatered = int(t.get("consecutive_unwatered", 0) or 0)
        units = int(t.get("yield_units", 0) or 0)
        mls = int(t.get("max_lifespan_step", -1))
        decaying = mls >= 0 and v.step >= mls
        ready = age >= cd["first"] and units > 0
        acts = []

        if cd["ongoing"]:
            if ready and (units >= 3 or decaying or v.day >= LAST_DAY - 1):
                acts.append((74, ["HARVEST"], None))
        else:
            win_start = (cd["maxday"] + 1) // 2
            in_win = win_start <= age <= cd["maxday"]
            grown = units >= cd["max_yield"] or age >= cd["maxday"]
            endgame = v.day >= LAST_DAY - 1
            if ready and (grown or decaying or endgame) and (watered or not in_win):
                acts.append((77, ["HARVEST"], None))

        if not watered:
            if cd["ongoing"]:
                bonus = False
            else:
                win_start = (cd["maxday"] + 1) // 2
                bonus = win_start <= age <= cd["maxday"] and units < cd["max_yield"]
            if last:
                prio = 84 if (bonus and age >= cd["first"]) else 3
            elif unwatered >= 1:
                prio = 96          # turns into a weed tonight, unrecoverable
            elif bonus:
                prio = 82
            else:
                prio = 66
            acts.append((prio, ["WATER"], None))

        if int(t.get("fertilized_until_day", -1)) < v.day and not last:
            gain = False
            if cd["ongoing"]:
                gain = age >= cd["first"] - 1 and not decaying and v.days_left >= 1
                prio = 48
            else:
                win_start = (cd["maxday"] + 1) // 2
                gain = (win_start - 1 <= age <= cd["maxday"] - 1
                        and units < cd["max_yield"] and v.day + 1 <= LAST_DAY)
                prio = 46 if crop == "MELON" else (44 if crop == "WHEAT" else 30)
            if gain and (fert_rich or econ["fert"] - econ["units"] >= 2):
                acts.append((prio, ["FERTILIZE"], ("FERTILIZER", 1)))

        if acts:
            acts.sort(reverse=True)
            tasks[(x, y)] = acts

    for (x, y, t) in v.animals:
        kind = t.get("animal")
        a = ANIMALS.get(kind)
        if a is None:
            continue
        acts = []
        fed = bool(t.get("fed_today"))
        unfed = int(t.get("consecutive_unfed", 0) or 0)
        units = int(t.get("yield_units", 0) or 0)
        if units >= ANIMAL_PICK[kind] or (units > 0 and v.day >= LAST_DAY - 1):
            acts.append((75, ["HARVEST"], None))
        if not fed and v.day < LAST_DAY:
            acts.append((99 if unfed >= 1 else 76, ["FEED"], ("WHEAT", 1)))
        if t.get("fertilizer_available"):
            if v.eff_price("FERTILIZER") > 12 or v.shed.get("FERTILIZER", 0) < 30:
                acts.append((58, ["COLLECT_FERTILIZER"], None))
        if fed and not t.get("cared_today") and v.day <= LAST_DAY - 2:
            acts.append((62, ["CARE"], None))
        if acts:
            acts.sort(reverse=True)
            tasks[(x, y)] = acts

    for (x, y, t) in v.empty_struct:
        kind = t.get("kind")
        for name, a in ANIMALS.items():
            if a["structure"] != kind:
                continue
            if v.shed.get(name, 0) + v.carried.get(name, 0) > 0:
                tasks.setdefault((x, y), []).append((70, ["PLACE", name], (name, 1)))
        if (x, y) not in tasks and v.day <= 24 and not struct_useful.get(kind):
            tasks[(x, y)] = [(18, ["DIG"], None)]

    for (x, y) in v.weeds:
        if v.day <= LAST_DAY - 3:
            tasks[(x, y)] = [(38, ["DIG"], None)]

    return tasks


def _empty_tile_tasks(v, tasks, ranking, want_struct, homeless_struct):
    """Decide what each empty tile should become; respects seed stock.

    A fresh seed carries consecutive_unwatered = 1, so anything planted must be
    watered the same day or it is a weed by morning.  Nothing is planted late in
    the day for that reason."""
    if v.day >= LAST_DAY:
        return
    can_plant = v.hour <= 19
    seed_left = dict(v.seeds)
    # structures first: they are the reserved NE tiles
    struct_need = dict(want_struct)
    empties = sorted(v.empties, key=lambda p: (not v.in_animal_zone(p[0], p[1]),
                                               _dist(p, v.shed_tiles[0])))
    for (x, y) in empties:
        placed = False
        if struct_need and v.in_animal_zone(x, y):
            for kind in ("COOP", "PASTURE"):
                if struct_need.get(kind, 0) > 0:
                    tasks[(x, y)] = [(54, ["BUILD_" + kind], None)]
                    struct_need[kind] -= 1
                    placed = True
                    break
        if placed:
            continue
        if not can_plant:
            continue
        for score, crop, room in ranking:
            if room <= 0:
                continue
            if v.in_animal_zone(x, y) and CROP_ECON[crop]["cycle"] > 5:
                continue
            if seed_left.get(crop, 0) <= 0:
                continue
            seed_left[crop] -= 1
            tasks[(x, y)] = [(50, ["PLANT", crop], None)]
            break
    # An animal already paid for and sitting in the shed has to go somewhere,
    # so it may take crop land.  A merely *planned* animal may not -- building
    # speculative coops across the field is how the crop rotation dies.
    stuck = {k: min(n, homeless_struct.get(k, 0)) for k, n in struct_need.items()}
    if any(n > 0 for n in stuck.values()):
        for (x, y) in empties:
            if (x, y) in tasks:
                continue
            for kind in ("COOP", "PASTURE"):
                if stuck.get(kind, 0) > 0:
                    tasks[(x, y)] = [(54, ["BUILD_" + kind], None)]
                    stuck[kind] -= 1
                    break


# --------------------------------------------------------------- unit regions

def _serpentine(v):
    """Owned tiles in a walkable order.

    Quadrant by quadrant, boustrophedon, but each quadrant is walked *outward
    from its shed corner*.  Every unit respawns beside the shed each morning, so
    ordering the work outward from there is what keeps the morning commute short
    -- the early chunks, which the low-numbered units get, start under their feet.
    """
    order = []
    h = v.half
    b = v.board
    quads = [(range(h - 1, -1, -1), range(h - 1, -1, -1)),      # NW, from (h-1,h-1)
             (range(h - 1, -1, -1), range(h, b)),               # NE, from (h,h-1)
             (range(h, b), range(h - 1, -1, -1)),               # SW, from (h-1,h)
             (range(h, b), range(h, b))]                        # SE, from (h,h)
    for ys, xs in quads:
        base = list(xs)
        for i, y in enumerate(list(ys)):
            row = base if i % 2 == 0 else base[::-1]
            for x in row:
                if (x, y) in v.owned_set:
                    order.append((x, y))
    seen = set(order)
    for p in v.owned:
        if p not in seen:
            order.append(p)
    return order


def _tile_weight(v, pos):
    """Actions per day this tile costs, from what it *is*, not from what is
    still pending.  Weighting by pending work makes the region boundaries move
    as the work gets done, and units chase the boundary instead of the crop."""
    y, x = pos[1], pos[0]
    t = v.tiles[y][x] if y < len(v.tiles) and x < len(v.tiles[y]) else None
    if t is None:
        return 2.2                      # build / plant, then water it
    if not isinstance(t, dict):
        return 0.0
    kind = t.get("kind")
    if t.get("animal"):
        return 4.5                      # feed + care + fertilizer + share of harvest
    if kind == "PLANT":
        return 2.0                      # water + share of harvest / fertilize
    if kind == "WEED":
        return 1.2
    return 1.0


def _regions(order, weights, k):
    """Contiguous slices of the walk order, one per unit, of equal workload.
    Lists, not sets: tie-breaking between equally scored jobs then follows the
    walk order instead of set iteration order."""
    if k <= 1:
        return [list(order)]
    total = sum(weights) or 1.0
    cut = total / float(k)
    out, cur, acc = [], [], 0.0
    for i, pos in enumerate(order):
        cur.append(pos)
        acc += weights[i]
        if acc >= cut * (len(out) + 1) and len(out) < k - 1:
            out.append(cur)
            cur = []
    out.append(cur)
    while len(out) < k:
        out.append([])
    return out


# ------------------------------------------------------------------ decision

def _decide(obs):
    v = _View(obs)
    if not v.owned:
        return {"farmer": ["PASS"], "hands": [], "market": _market(v, 0, {})}

    fert_rich = (v.shed.get("FERTILIZER", 0) + v.carried.get("FERTILIZER", 0) >= 8
                 or v.eff_price("FERTILIZER") < 45)

    want_animals = _animal_wanted(v)
    # Structures needed = animals already sitting in the shed with nowhere to
    # live, plus animals we still intend to buy, less the empty structures we
    # already have.  Missing the first term strands bought animals in the shed.
    want_struct = {"COOP": 0, "PASTURE": 0}
    free_struct = {"COOP": 0, "PASTURE": 0}
    for _, _, t in v.empty_struct:
        k = t.get("kind")
        if k in free_struct:
            free_struct[k] += 1
    homeless_struct = {"COOP": 0, "PASTURE": 0}
    for kind, a in ANIMALS.items():
        homeless = v.shed.get(kind, 0) + v.carried.get(kind, 0)
        homeless_struct[a["structure"]] += homeless
        want_struct[a["structure"]] += homeless + want_animals.get(kind, 0)
    # An empty coop is only worth digging up if we want no more of its animal at
    # all -- otherwise we would demolish the pen we are about to stock.
    struct_useful = {k: n > 0 for k, n in want_struct.items()}
    for k in list(want_struct):
        want_struct[k] = max(0, want_struct[k] - free_struct[k])
        homeless_struct[k] = max(0, min(homeless_struct[k], want_struct[k]))

    ranking = _crop_ranking(v, fert_rich)
    tasks = _tile_tasks(v, fert_rich, struct_useful)
    _empty_tile_tasks(v, tasks, ranking, want_struct, homeless_struct)

    order = _serpentine(v)
    weights = [_tile_weight(v, p) for p in order]
    n_units = len(v.units)
    regions = _regions(order, weights, n_units)

    shed_avail = dict(v.shed)
    shed_room = max(0, 100 - v.shed_total)
    # an animal in the shed needs a courier: someone has to PICKUP it and walk
    # it to an empty structure, or it sits in storage all season
    courier_need = {}
    for name, a in ANIMALS.items():
        vacancies = sum(1 for _x, _y, t in v.empty_struct if t.get("kind") == a["structure"])
        carrying = sum(1 for inv in v.inv if inv.get(name, 0) > 0)
        courier_need[name] = max(0, min(v.shed.get(name, 0), vacancies) - carrying)
    plant_budget = dict(v.seeds)

    actions = [["PASS"] for _ in range(n_units)]
    claimed = set()

    # how much wheat each unit should be carrying for the animals near it
    animal_pos = set((x, y) for (x, y, _t) in v.animals)

    for i, pos in enumerate(v.units):
        inv = v.inv[i]
        region = regions[i] if i < len(regions) else []
        region_set = set(region)
        cands = []

        # -- supply run: wheat to feed with, fertilizer to apply
        my_animals = sum(1 for p in region if p in animal_pos)
        need_wheat = 0
        if my_animals and v.day < LAST_DAY:
            need_wheat = my_animals + 1 - inv.get("WHEAT", 0)
        if need_wheat > 0 and shed_avail.get("WHEAT", 0) > 0:
            tgt = min(v.shed_tiles, key=lambda s: _dist(pos, s))
            qty = min(need_wheat, shed_avail.get("WHEAT", 0))
            cands.append((90 - 1.4 * _dist(pos, tgt), tgt, ["PICKUP", "WHEAT", qty], "W", qty))
        for name in ANIMALS:
            if courier_need.get(name, 0) > 0 and shed_avail.get(name, 0) > 0:
                tgt = min(v.shed_tiles, key=lambda s: _dist(pos, s))
                cands.append((72 - 1.4 * _dist(pos, tgt), tgt,
                              ["PICKUP", name, 1], "A", name))
                break
        if (fert_rich and v.hour <= 10 and inv.get("FERTILIZER", 0) < 2
                and shed_avail.get("FERTILIZER", 0) > 0 and v.day < LAST_DAY):
            n_fert_jobs = sum(1 for p in region
                              if p in tasks and any(a[1][0] == "FERTILIZE" for a in tasks[p]))
            if n_fert_jobs:
                tgt = min(v.shed_tiles, key=lambda s: _dist(pos, s))
                qty = min(4, n_fert_jobs, shed_avail.get("FERTILIZER", 0))
                cands.append((52 - 1.4 * _dist(pos, tgt), tgt,
                              ["PICKUP", "FERTILIZER", qty], "F", qty))

        # -- drop harvested goods so the market orders can reach them
        carry = {k: n for k, n in inv.items() if k in PRODUCTS and n > 0}
        n_carry = sum(carry.values())
        keep_wheat = my_animals + 1 if (my_animals and v.day < LAST_DAY) else 0
        keep_fert = 2 if fert_rich and v.day < LAST_DAY else 0
        droppable = (n_carry - min(carry.get("WHEAT", 0), keep_wheat)
                     - min(carry.get("FERTILIZER", 0), keep_fert))
        spare = [(n, k) for k, n in carry.items() if k not in ("WHEAT", "FERTILIZER")]
        if keep_wheat and not spare:
            droppable = 0          # nothing but rations: the trip would undo itself
        if droppable >= 3 and shed_room > 4:
            tgt = min(v.shed_tiles, key=lambda s: _dist(pos, s))
            prio = 40 + 2.2 * droppable
            if v.day >= LAST_DAY and v.hour >= 4:
                prio = 120
            best_item = None
            if (keep_wheat or keep_fert) and spare:
                best_item = max(spare)[1]
            act = (["PLACE", best_item, carry[best_item]] if best_item
                   else ["DROP"])
            # capped below WATER-or-it-weeds (96) and FEED-or-it-escapes (99)
            cands.append((min(prio, 90) - 1.4 * _dist(pos, tgt), tgt, act, "D", 0))

        # -- tile work
        pool = region if region else v.owned
        for p in pool:
            if p in claimed:
                continue
            acts = tasks.get(p)
            if not acts:
                continue
            d = _dist(pos, p)
            for prio, act, req in acts:
                if req is not None and inv.get(req[0], 0) < req[1]:
                    continue
                if act[0] == "PLANT" and plant_budget.get(act[1], 0) <= 0:
                    continue
                cands.append((prio - 1.4 * d, p, act, "T", 0))
                break

        if not cands and region:
            for p in v.owned:
                if p in claimed or p in region_set:
                    continue
                acts = tasks.get(p)
                if not acts:
                    continue
                d = _dist(pos, p)
                for prio, act, req in acts:
                    if req is not None and inv.get(req[0], 0) < req[1]:
                        continue
                    if act[0] == "PLANT" and plant_budget.get(act[1], 0) <= 0:
                        continue
                    cands.append((prio - 1.8 * d, p, act, "T", 0))
                    break

        if not cands:
            continue

        cands.sort(key=lambda c: -c[0])
        _score, tgt, act, tag, qty = cands[0]
        if tuple(tgt) != tuple(pos):
            mv = _step_toward(pos, tgt)
            actions[i] = mv if mv else ["PASS"]
            if tag == "T":
                claimed.add(tgt)
            elif tag == "A":
                courier_need[qty] = max(0, courier_need.get(qty, 0) - 1)
            continue

        actions[i] = act
        if tag == "T":
            claimed.add(tgt)
            if act[0] == "PLANT":
                plant_budget[act[1]] = plant_budget.get(act[1], 0) - 1
            elif act[0] == "PLACE" and act[1] in ANIMALS:
                if shed_avail.get(act[1], 0) > 0:
                    shed_avail[act[1]] -= 1
        elif tag in ("W", "F"):
            shed_avail[act[1]] = max(0, shed_avail.get(act[1], 0) - qty)
        elif tag == "A":
            shed_avail[qty] = max(0, shed_avail.get(qty, 0) - 1)
            courier_need[qty] = max(0, courier_need.get(qty, 0) - 1)
        elif tag == "D":
            shed_room = max(0, shed_room - droppable)

    market = _market(v, len(v.units), plant_budget)
    return {"farmer": actions[0], "hands": actions[1:], "market": market}


# -------------------------------------------------------------------- market

def _hire_target(v, tasks_weight):
    units = int(math.ceil(tasks_weight / 19.0))
    if v.money < 400:
        cap = 4
    elif v.money < 1200:
        cap = 7
    elif v.money < 4000:
        cap = 10
    elif v.money < 9000:
        cap = 12
    elif v.money < 20000:
        cap = 13
    elif v.money < 35000:
        cap = 14
    else:
        cap = 15
    return max(1, min(units, cap))


def _market(v, n_units, plant_budget):
    """Market queue for this turn, at most 10 orders (extras are dropped in
    silence, so the order is the policy).

    Sells go first: they are what frees shed space and cash for everything
    underneath them, and a full shed makes BUY_PRODUCT and BUY_ANIMAL fail.
    """
    orders = []
    budget = v.money
    last = v.day >= LAST_DAY
    early = v.hour <= 3
    cap_hire = 4 if early else 0
    cap_seed = 2 if v.hour <= 6 else 1

    # Wheat the animals will eat.  Units draw their day's feed out of the shed
    # in the morning and carry it, so the shed only has to hold the whole herd's
    # ration at the top of the day -- reserving it all day long would eat 40 of
    # the 100 shed slots for nothing.
    if v.n_animals and not last:
        if v.hour <= 2:
            feed_need = v.n_animals + 4
        else:
            feed_need = max(3, v.n_animals + 4 - v.carried.get("WHEAT", 0))
    else:
        feed_need = 0

    # -- what is worth selling, dearest first
    sells = []
    for item in PRODUCTS:
        have = v.shed.get(item, 0)
        if have <= 0:
            continue
        if item == "WHEAT" and not last:
            have -= feed_need
            if have <= 0:
                continue
        n = _sell_quantity(v, item, have, _reserve_price(v, item))
        if n > 0:
            sells.append((v.spot(item) * n, item, n))
    sells.sort(reverse=True)

    freed = 0
    for _val, item, n in sells[:2]:
        orders.append(["SELL", item, n])
        budget += _val
        freed += n

    # -- wheat top-up.  An animal missed twice is gone and unrecoverable, so
    #    this outranks every discretionary purchase below it.
    if feed_need:
        short = feed_need - (v.shed.get("WHEAT", 0) + v.carried.get("WHEAT", 0))
        if short > 0:
            price = max(1, market_price("WHEAT", v.minv.get("WHEAT", 10000) - 1))
            room = max(0, 96 - (v.shed_total - freed))
            n = min(short, room, int(budget // price))
            if n > 0:
                orders.append(["BUY_PRODUCT", "WHEAT", n])
                budget -= n * price

    # -- labour.  fib(n) resets every day, so ten hands cost $143 for 230 extra
    #    actions; the binding constraint is land and market depth, not wages.
    if cap_hire and not last:
        weight = (2.0 * len(v.plants) + 4.5 * v.n_animals + 1.5 * len(v.weeds)
                  + 2.2 * min(len(v.empties), 6 + int(budget // 25)))
        target = _hire_target(v, weight)
        need = target - 1 - v.hires_today
        for _ in range(min(max(0, need), cap_hire)):
            if budget < 30:
                break
            orders.append(["HIRE"])
            budget -= 5

    for _val, item, n in sells[2:2 + (3 if early else 7)]:
        orders.append(["SELL", item, n])

    # -- seed for the tiles about to come free
    if not last and v.day <= 25:
        fert_rich = (v.shed.get("FERTILIZER", 0) >= 8 or v.eff_price("FERTILIZER") < 45)
        free = len(v.empties)
        bought = 0
        for _score, crop, room in _crop_ranking(v, fert_rich):
            if bought >= cap_seed or free <= 0:
                break
            want = min(room, free, 12) - v.seeds.get(crop, 0)
            cost = CROPS[crop]["seed"]
            n = min(want, int(max(0.0, budget - 150) // cost))
            if n > 0:
                orders.append(["BUY_SEED", crop, n])
                budget -= n * cost
                free -= n
                bought += 1

    # -- land.  A quadrant is 25 tiles; at the $25-100/tile-day the crop table
    #    supports it repays $1k-$4k inside a week.  Buy as soon as the purchase
    #    still leaves enough to put seed in the ground it just bought.
    nq = len(v.farm.get("unlocked_quadrants") or ["NW"]) - 1
    if 0 <= nq < 3 and v.day <= 23:
        price = [1000, 2000, 4000][nq]
        if budget >= price + 1400 and v.days_left >= 5:
            orders.append(["BUY_LAND"])
            budget -= price

    # -- animals last: the best tile-days in the game but the slowest payback,
    #    so they only get money the rest of the plan did not need.
    if not last:
        want = _animal_wanted(v)
        for kind in ("SHEEP", "COW", "GOOSE"):
            n_want = want.get(kind, 0)
            if n_want <= 0:
                continue
            keep = 700 + 25 * len(v.empties)
            n = min(n_want, 3, int(max(0.0, budget - keep) // ANIMALS[kind]["cost"]),
                    max(0, 96 - (v.shed_total - freed)))
            if n > 0:
                orders.append(["BUY_ANIMAL", kind, n])
                budget -= n * ANIMALS[kind]["cost"]
                break

    return orders[:10]
