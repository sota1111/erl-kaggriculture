"""Kaggriculture agent — rule-based economic controller.

Strategy family: rule-based control. No search, no learned weights, no RNG.

Three layers, recomputed from scratch every turn (the agent is stateless, so a
mid-episode reload or a second episode in the same process cannot corrupt it):

  1. Survey     — read my farm, the opponent's farm, the market and the town.
  2. Task pool  — every worthwhile unit-action becomes a scored task on a tile.
  3. Allocation — greedy assignment of farmer + hands to tasks by score minus
                  walking distance; then a price-aware market order queue.

The economics it encodes are in ECONOMIC NOTES at the bottom of this file.
"""

import math

# ---------------------------------------------------------------------------
# Environment constants (mirrored from kaggriculture.py 1.32.7; do not import).
# ---------------------------------------------------------------------------

TURNS_PER_DAY = 24
SEASON_DAYS = 30
LAST_DAY = SEASON_DAYS - 1          # day 29: no end-of-day refresh ever runs
SHED_CAP = 100
MAX_ORDERS = 10
PRICE_FLOOR = 1
HINGE_GAIN = 8.0
I0 = 10000

CROPS = {
    "WHEAT":      {"seed": 10,  "first": 2,  "maxday": 4,  "interval": 0, "maxy": 6, "ongoing": False},
    "CARROT":     {"seed": 20,  "first": 2,  "maxday": 3,  "interval": 0, "maxy": 4, "ongoing": False},
    "TOMATO":     {"seed": 50,  "first": 8,  "maxday": 8,  "interval": 1, "maxy": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first": 10, "maxday": 10, "interval": 2, "maxy": 4, "ongoing": True},
    "MELON":      {"seed": 80,  "first": 10, "maxday": 12, "interval": 0, "maxy": 6, "ongoing": False},
}

ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP",    "first": 4, "interval": 1, "max_held": 4, "product": "EGG"},
    "COW":   {"cost": 400, "structure": "PASTURE", "first": 8, "interval": 2, "max_held": 6, "product": "MILK"},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "first": 6, "interval": 3, "max_held": 6, "product": "WOOL"},
}

PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"]

MARKET_PARAMS = {
    "WHEAT":      {"base":  25, "T": 400, "bf": "sqrt",   "bt": 0.80, "af": "log",    "at": 0.20},
    "CARROT":     {"base":  35, "T": 450, "bf": "hinge",  "bt": 1.00, "af": "sqrt",   "at": 0.70},
    "TOMATO":     {"base":  60, "T": 200, "bf": "hinge",  "bt": 0.40, "af": "sqrt",   "at": 0.60},
    "STRAWBERRY": {"base": 120, "T": 100, "bf": "sqrt",   "bt": 0.70, "af": "linear", "at": 1.60},
    "MELON":      {"base": 250, "T": 300, "bf": "log",    "bt": 0.20, "af": "sq",     "at": 3.60},
    "EGG":        {"base":  50, "T": 332, "bf": "hinge",  "bt": 0.40, "af": "log",    "at": 0.20},
    "MILK":       {"base": 160, "T": 122, "bf": "sqrt",   "bt": 0.60, "af": "linear", "at": 1.60},
    "WOOL":       {"base": 200, "T": 105, "bf": "log",    "bt": 0.20, "af": "sq",     "at": 3.20},
    "FERTILIZER": {"base": 100, "T": 200, "bf": "linear", "bt": 0.40, "af": "linear", "at": 0.40},
}

BASE = {k: v["base"] for k, v in MARKET_PARAMS.items()}

SHOPS = {
    "BAKERY":         ["EGG", "WHEAT"],
    "PIZZA_SHOP":     ["MILK", "TOMATO", "WHEAT"],
    "BRUNCH_SPOT":    ["EGG", "WHEAT", "STRAWBERRY"],
    "YARN_STORE":     ["WOOL"],
    "ICE_CREAM_SHOP": ["STRAWBERRY", "MILK", "WHEAT"],
    "PET_CAFE":       ["CARROT"],
    "SMOOTHIE_SHOP":  ["STRAWBERRY", "MILK"],
    "FARMERS_MARKET": ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY"],
}
SHOP_UNLOCK_INTERVAL = 3
MAX_SHOP_INSTANCES = 8
SHOP_TICKS_PER_DAY = 6          # turnsPerDay 24 / townShopSellInterval 4

# Expected daily draw of one shop instance that has not unlocked yet, per
# product: shops are drawn uniformly with replacement from the eight below.
EXP_SHOP_DAILY = {}
for _item in PRODUCTS:
    _acc = 0.0
    for _name, _prods in SHOPS.items():
        if _item in _prods:
            _acc += SHOP_TICKS_PER_DAY * (2 if len(_prods) == 1 else 1)
    EXP_SHOP_DAILY[_item] = _acc / float(len(SHOPS))

# One-time crops: the age we harvest at, and the units we get there.
HARVEST_AGE = {"WHEAT": 4, "CARROT": 3, "MELON": 10}
YIELD_FERT  = {"WHEAT": 6, "CARROT": 4, "MELON": 6}
YIELD_PLAIN = {"WHEAT": 4, "CARROT": 3, "MELON": 6}

# Fertilizer earns nothing on melon (water alone already reaches the cap of 6
# by the time first_yield_day allows a harvest), so melon is never fertilized.
FERT_VALUE = {"STRAWBERRY": 70.0, "TOMATO": 58.0, "WHEAT": 30.0, "CARROT": 20.0, "MELON": -1.0}

# Sell below this fraction of base only in a trickle (or when the shed is full).
SELL_FLOOR_FRAC = {
    "WHEAT": 0.72, "CARROT": 0.60, "TOMATO": 0.58, "STRAWBERRY": 0.50,
    "MELON": 0.48, "EGG": 0.62, "MILK": 0.50, "WOOL": 0.50, "FERTILIZER": 0.34,
}
# Units per turn we are willing to push into the book at a good price. Keeping
# this small lets town consumption refill the scarcity gap between our sales.
SELL_CAP = {
    "WHEAT": 8, "CARROT": 7, "TOMATO": 5, "STRAWBERRY": 4, "MELON": 3,
    "EGG": 10, "MILK": 4, "WOOL": 3, "FERTILIZER": 5,
}

MAX_HANDS = 12                 # fib(12) = 233/day; past this hiring outruns value
MAX_ANIMALS = 46
DIST_WEIGHT = 2.4              # score points a unit will give up per tile walked
DROP_THRESHOLD = 16            # inventory size that sends a unit to the shed
TASK_LIMIT = 160               # strongest tasks kept for the assignment pass
PLAN_TILES = 40                # empty tiles given a crop plan per turn
OPP_MIRROR = 0.6               # assumed rival volume, as a share of my own line

PASS_ACTION = {"farmer": ["PASS"], "hands": [], "market": []}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _g(o, k, d=None):
    """Read a key from a dict or a kaggle_environments Struct, never raising."""
    try:
        if isinstance(o, dict):
            return o.get(k, d)
        return getattr(o, k, d)
    except Exception:
        return d


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
    if func == "hinge":
        if not T or T <= 0:
            return x
        u = x / T
        return u + HINGE_GAIN * max(0.0, u - 1.0) ** 2
    return x


def price_at(item, inventory):
    """The engine's price curve, so we can price a sale we have not made yet."""
    p = MARKET_PARAMS.get(item)
    if p is None:
        return 1
    base, T = p["base"], p["T"]
    if inventory < I0:
        amp = p["bt"] * base / _shape(p["bf"], T, T)
        v = base + amp * _shape(p["bf"], I0 - inventory, T)
    else:
        amp = p["at"] * base / _shape(p["af"], T, T)
        v = base - amp * _shape(p["af"], inventory - I0, T)
    return max(PRICE_FLOOR, int(round(v)))


def town_drain(item, day, shops):
    """Units of `item` the town will consume for free between now and the end of
    the season. This is the demand floor every price sits on: sell at or under
    this rate and the book stays at or above base."""
    if item == "FERTILIZER":
        return 0.0                       # no shop wants it, town centre skips it
    days_left = SEASON_DAYS - day
    if days_left <= 0:
        return 0.0
    daily = 1.0                          # town centre, one of each, flat, forever
    for name in shops:
        prods = SHOPS.get(name)
        if prods and item in prods:
            daily += SHOP_TICKS_PER_DAY * (2 if len(prods) == 1 else 1)
    total = daily * days_left
    per = EXP_SHOP_DAILY.get(item, 0.0)
    if per > 0.0:
        k = len(shops)
        while k < MAX_SHOP_INSTANCES:
            k += 1
            unlock_day = SHOP_UNLOCK_INTERVAL * k
            if unlock_day >= SEASON_DAYS:
                break
            active = SEASON_DAYS - max(unlock_day, day)
            if active > 0:
                total += per * active
    return total


def _dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _step_toward(pos, target):
    dx = target[0] - pos[0]
    dy = target[1] - pos[1]
    if abs(dx) >= abs(dy):
        if dx > 0:
            return ["EAST"]
        if dx < 0:
            return ["WEST"]
    if dy > 0:
        return ["SOUTH"]
    if dy < 0:
        return ["NORTH"]
    if dx > 0:
        return ["EAST"]
    if dx < 0:
        return ["WEST"]
    return ["PASS"]


def _shed_tiles(n):
    half = n // 2
    return [(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)]


def _inv_total(inv):
    try:
        return sum(v for v in inv.values() if isinstance(v, (int, float)) and v > 0)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Crop planning
# ---------------------------------------------------------------------------

def _expected_crop(crop, plant_day, fertilized):
    """(units, occupied_days) for planting `crop` on `plant_day`. (0, 0) if it
    cannot finish before the season ends."""
    cd = CROPS[crop]
    if not cd["ongoing"]:
        age = HARVEST_AGE[crop]
        if plant_day + age > LAST_DAY:
            return 0, 0
        y = YIELD_FERT[crop] if fertilized else YIELD_PLAIN[crop]
        return y, age
    units = 0
    last = 0
    for k in range(cd["maxy"]):
        # Production lands at the end of day plant_day + age_end; harvestable
        # the following day.
        age_end = cd["first"] - 1 + k * cd["interval"]
        if plant_day + age_end + 1 > LAST_DAY:
            break
        units += 2 if fertilized else 1
        last = age_end + 1
    return units, last


def cash_rate(money):
    """Per-day discount on a tile that pays late. Early cash is not idle money:
    it becomes land and livestock, both of which compound for the rest of the
    season, so a slow crop has to clear a real hurdle to be worth the delay."""
    if money < 700:
        return 0.13
    if money < 2500:
        return 0.06
    if money < 12000:
        return 0.025
    return 0.01


def crop_tile_value(crop, day, days_left, fert, mine, theirs, inv, drain, money):
    """Value per tile-day of committing one more tile to `crop`. None if the
    crop cannot pay for its own seed before the season ends."""
    units_out, occ = _expected_crop(crop, day, fert)
    if units_out <= 0 or occ <= 0:
        return None
    cycles = max(1.0, days_left / float(occ))
    own = mine + 1
    # Their standing tiles are hard evidence, but an empty rival field today
    # says nothing about tomorrow. Assume they mirror a share of my own line, so
    # a crop only looks good while it still looks good under company.
    rival = max(theirs, OPP_MIRROR * own)
    line = units_out * (own + rival) * cycles
    p = price_at(crop, inv + 0.5 * (line - drain))
    value = units_out * p - CROPS[crop]["seed"]
    if value <= 0:
        return None
    return (value / float(occ)) / ((1.0 + cash_rate(money)) ** occ)


def _ongoing_produces_tonight(tile, crop, day):
    """True if this ongoing plant fires a scheduled production at end of `day`."""
    cd = CROPS[crop]
    if not cd["ongoing"] or cd["interval"] <= 0:
        return False
    ds = (day + 1) - tile.get("planted_day", 0) - cd["first"]
    if ds < 0 or ds % cd["interval"] != 0:
        return False
    return ds // cd["interval"] + 1 <= cd["maxy"]


def _wants_fertilizer(tile, crop, day):
    """True if a FERTILIZE now would still buy us a bonus day."""
    if FERT_VALUE.get(crop, 0.0) <= 0:
        return False
    if tile.get("fertilized_until_day", -1) >= day:
        return False
    cd = CROPS[crop]
    age = day - tile.get("planted_day", 0)
    if not cd["ongoing"]:
        ws = (cd["maxday"] + 1) // 2
        if tile.get("yield_units", 0) >= cd["maxy"]:
            return False
        # FERTILIZE covers day..day+2. Applying it before the bonus window opens
        # burns coverage on days that pay nothing, so wait until the window.
        return ws <= age <= cd["maxday"]
    for d in range(day, min(day + 3, LAST_DAY + 1)):
        if _ongoing_produces_tonight(tile, crop, d):
            return True
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def agent(obs):
    try:
        return _decide(obs)
    except Exception:
        return {"farmer": ["PASS"], "hands": [], "market": []}


def _decide(obs):
    player = _g(obs, "player", 0)
    try:
        player = int(player)
    except Exception:
        player = 0
    farms = _g(obs, "farms", None) or []
    if not farms or player >= len(farms):
        return dict(PASS_ACTION)
    farm = farms[player]
    tiles = _g(farm, "tiles", None) or []
    n = len(tiles)
    private = _g(obs, "private", None) or {}
    shed = dict(_g(private, "shed", None) or {})
    seeds = dict(_g(private, "seeds", None) or {})
    invs = list(_g(private, "inventories", None) or [{}])
    money = float(_g(farm, "money", 0) or 0)
    day = int(_g(obs, "day", 0) or 0)
    hour = int(_g(obs, "hour", 0) or 0)
    hands = list(_g(farm, "hands", None) or [])
    farmer_pos = list(_g(farm, "farmer", None) or [0, 0])
    hires_today = int(_g(farm, "hires_today", 0) or 0)

    n_hands = len(hands)
    if n < 4:
        # Degenerate board (contract-validation stub). Stay legal and quiet.
        return {"farmer": ["PASS"], "hands": [["PASS"]] * n_hands, "market": []}

    market = _g(obs, "market", None) or {}
    minv = dict(_g(market, "inventory", None) or {})
    prices = dict(_g(market, "prices", None) or {})
    for item in PRODUCTS:
        if item not in minv:
            minv[item] = I0
        if item not in prices:
            prices[item] = price_at(item, minv[item])

    days_left = SEASON_DAYS - day          # counting today
    final_day = day >= LAST_DAY
    shed_tiles = _shed_tiles(n)

    # ---------------- survey my farm ----------------
    unlocked = []
    plants = []          # (x, y, tile)
    animal_tiles = []    # (x, y, tile) with an animal on it
    free_structs = []    # (x, y, tile) coop/pasture with no animal
    empties = []
    weeds = []
    my_crop_count = {}
    my_animal_count = {}
    for y in range(n):
        row = tiles[y]
        if not isinstance(row, (list, tuple)):
            continue
        for x in range(min(n, len(row))):
            t = row[x]
            if t == "LOCKED":
                continue
            unlocked.append((x, y))
            if t is None:
                empties.append((x, y))
            elif isinstance(t, dict):
                kind = t.get("kind")
                if kind == "PLANT":
                    c = t.get("crop")
                    if c in CROPS:
                        plants.append((x, y, t))
                        my_crop_count[c] = my_crop_count.get(c, 0) + 1
                    else:
                        weeds.append((x, y))
                elif kind == "WEED":
                    weeds.append((x, y))
                elif kind in ("COOP", "PASTURE"):
                    a = t.get("animal")
                    if a in ANIMALS:
                        animal_tiles.append((x, y, t))
                        my_animal_count[a] = my_animal_count.get(a, 0) + 1
                    else:
                        free_structs.append((x, y, t))
    n_unlocked = len(unlocked)
    n_animals = len(animal_tiles)
    n_structs = n_animals + len(free_structs)

    # ---------------- survey the opponent (their farm is public) -------------
    opp_crop = {}
    opp_animal = {}
    if len(farms) > 1:
        otiles = _g(farms[1 - player], "tiles", None) or []
        for row in otiles:
            if not isinstance(row, (list, tuple)):
                continue
            for t in row:
                if isinstance(t, dict):
                    if t.get("kind") == "PLANT":
                        c = t.get("crop")
                        if c in CROPS:
                            opp_crop[c] = opp_crop.get(c, 0) + 1
                    else:
                        a = t.get("animal")
                        if a in ANIMALS:
                            opp_animal[a] = opp_animal.get(a, 0) + 1

    # ---------------- units ----------------
    units = []
    units.append({"i": 0, "pos": (int(farmer_pos[0]), int(farmer_pos[1])),
                  "inv": dict(invs[0]) if invs and isinstance(invs[0], dict) else {}})
    for h in range(n_hands):
        p = hands[h]
        try:
            pos = (int(p[0]), int(p[1]))
        except Exception:
            pos = (n // 2 - 1, n // 2 - 1)
        iv = invs[h + 1] if len(invs) > h + 1 and isinstance(invs[h + 1], dict) else {}
        units.append({"i": h + 1, "pos": pos, "inv": dict(iv)})

    carried = {}
    for u in units:
        for k, v in u["inv"].items():
            if isinstance(v, (int, float)) and v > 0:
                carried[k] = carried.get(k, 0) + v
    wheat_total = shed.get("WHEAT", 0) + carried.get("WHEAT", 0)
    fert_total = shed.get("FERTILIZER", 0) + carried.get("FERTILIZER", 0)
    shed_total = _inv_total(shed)

    # Do we have a fertilizer pipeline? Governs the yield model used for planning.
    fert_flow = n_animals >= 3 or fert_total >= 4

    # ---------------- tile zoning ----------------
    # Animals want to sit close to the shed: they are visited daily for feed,
    # care, harvest and fertilizer, and the wheat they eat comes out of the shed.
    def shed_d(t):
        return min(_dist(t, s) for s in shed_tiles)

    ordered = sorted(unlocked, key=lambda t: (shed_d(t), t[1], t[0]))
    reserve_n = min(len(ordered), max(0, min(MAX_ANIMALS, n_structs + 8)))
    animal_zone = set(ordered[:reserve_n])

    # ---------------- crop preference ----------------
    # Value per tile-day of putting one more tile of crop c in the ground, priced
    # against the book we expect to face: today's inventory, moved by half of the
    # net of (everything this crop line will deliver) minus (what the town will
    # eat for free). "This crop line" counts my tiles, the opponent's visible
    # tiles and the candidate tile, each replanted as often as the season allows.
    shops = list(_g(_g(obs, "town", None) or {}, "unlocked_shops", None) or [])
    drain = {c: town_drain(c, day, shops) for c in CROPS}
    crop_shape = {}
    for c in CROPS:
        units_out, occ = _expected_crop(c, day, fert_flow)
        if units_out > 0 and occ > 0:
            crop_shape[c] = True

    def crop_value(c, extra):
        return crop_tile_value(c, day, days_left, fert_flow,
                               my_crop_count.get(c, 0) + extra,
                               opp_crop.get(c, 0), minv.get(c, I0), drain[c], money)

    # Wheat is also feed, and a starved herd is unrecoverable. While the field
    # under-produces what the animals eat, wheat carries a bonus that decays to
    # nothing exactly when the deficit closes.
    wheat_rate = 1.5 if fert_flow else 1.0
    wheat_deficit = n_animals - my_crop_count.get("WHEAT", 0) * wheat_rate

    # ---------------- tasks ----------------
    tasks = []

    def add(pos, op, score, need=None, avoid=None):
        tasks.append({"pos": pos, "op": op, "score": score, "need": need, "avoid": avoid})

    # -- animals -------------------------------------------------------------
    unfed_risk = 0
    for (x, y, t) in animal_tiles:
        a = ANIMALS[t.get("animal")]
        cu = int(t.get("consecutive_unfed", 0) or 0)
        fed = bool(t.get("fed_today"))
        cared = bool(t.get("cared_today"))
        yu = int(t.get("yield_units", 0) or 0)
        if not fed and cu >= 1:
            unfed_risk += 1
        # Feeding on the last day buys nothing: the end-of-day refresh that
        # would consume it never runs.
        if not fed and day <= LAST_DAY - 1:
            if cu >= 1:
                add((x, y), ["FEED"], 130.0, need="WHEAT")
            else:
                add((x, y), ["FEED"], 72.0, need="WHEAT")
        # CARE banks +1 paid out at the *next* scheduled production, so caring
        # on the last two days pays into a production we never harvest.
        if fed and not cared and day <= LAST_DAY - 2:
            add((x, y), ["CARE"], 62.0)
        if yu > 0:
            if yu >= a["max_held"]:
                # Already capped: every further scheduled tick is discarded.
                add((x, y), ["HARVEST"], 96.0)
            elif final_day or yu + 2 > a["max_held"] or yu >= 3:
                add((x, y), ["HARVEST"], 68.0 + 2.0 * yu)
            elif day >= LAST_DAY - 1:
                add((x, y), ["HARVEST"], 60.0)
        if t.get("fertilizer_available"):
            add((x, y), ["COLLECT_FERTILIZER"], 40.0)

    # -- plants --------------------------------------------------------------
    fert_demand = 0
    for (x, y, t) in plants:
        crop = t.get("crop")
        cd = CROPS[crop]
        age = day - int(t.get("planted_day", day) or 0)
        yu = int(t.get("yield_units", 0) or 0)
        watered = bool(t.get("watered_today"))
        cu = int(t.get("consecutive_unwatered", 0) or 0)
        ongoing = cd["ongoing"]
        # An ongoing plant sets max_lifespan_step only once it has fired every
        # scheduled production; from then on it is a decaying tile, not a crop.
        spent = ongoing and int(t.get("max_lifespan_step", -1) or -1) >= 0

        # harvest
        if ongoing:
            if yu > 0 and age >= cd["first"]:
                if final_day or yu >= 3 or yu + 2 > cd["maxy"]:
                    add((x, y), ["HARVEST"], 76.0 + 2.0 * yu)
                elif day >= LAST_DAY - 1:
                    add((x, y), ["HARVEST"], 66.0)
            if spent and yu <= 0:
                add((x, y), ["DIG"], 34.0)
        else:
            if age >= HARVEST_AGE.get(crop, cd["maxday"]) and yu > 0:
                add((x, y), ["HARVEST"], 80.0 + 2.0 * yu)
            elif final_day and yu > 0 and age >= cd["first"]:
                add((x, y), ["HARVEST"], 74.0)

        # water
        if not watered:
            beneficial = False
            if not ongoing:
                ws = (cd["maxday"] + 1) // 2
                if ws <= age <= cd["maxday"] and yu < cd["maxy"]:
                    beneficial = True
            else:
                if _ongoing_produces_tonight(t, crop, day) and \
                        int(t.get("fertilized_until_day", -1) or -1) >= day:
                    beneficial = True
            alive_matters = day < LAST_DAY and not spent and not (
                not ongoing and age >= HARVEST_AGE.get(crop, cd["maxday"]))
            if beneficial and cu >= 1:
                add((x, y), ["WATER"], 128.0)
            elif beneficial:
                add((x, y), ["WATER"], 84.0)
            elif cu >= 1 and alive_matters:
                add((x, y), ["WATER"], 120.0)
            elif alive_matters and hour >= 12:
                # Spare hands top plants up so a missed day can never chain into
                # a weed. Cheap insurance: weeds are unrecoverable.
                add((x, y), ["WATER"], 14.0)

        # fertilize
        if _wants_fertilizer(t, crop, day):
            fert_demand += 1
            v = FERT_VALUE.get(crop, 0.0)
            if crop == "WHEAT" and fert_total < 3 + fert_demand:
                v = 12.0
            add((x, y), ["FERTILIZE"], v, need="FERTILIZER")

    # -- weeds ---------------------------------------------------------------
    weed_score = 30.0 if not empties else 16.0
    for (x, y) in weeds:
        add((x, y), ["DIG"], weed_score)

    # -- structures and animal placement ------------------------------------
    pending_animals = {a: shed.get(a, 0) + carried.get(a, 0) for a in ANIMALS}
    n_pending = sum(pending_animals.values())
    if n_pending > len(free_structs) and empties and not final_day:
        want_pasture = pending_animals.get("COW", 0) + pending_animals.get("SHEEP", 0) > \
            sum(1 for (_, _, s) in free_structs if s.get("kind") == "PASTURE")
        build_op = ["BUILD_PASTURE"] if want_pasture else ["BUILD_COOP"]
        spots = sorted([e for e in empties if e in animal_zone] or empties,
                       key=lambda t: (shed_d(t), t[1], t[0]))
        for spot in spots[:max(1, n_pending - len(free_structs))]:
            add(spot, build_op, 58.0)
    for (x, y, s) in free_structs:
        kind = s.get("kind")
        for a, ad in ANIMALS.items():
            if ad["structure"] == kind and pending_animals.get(a, 0) > 0:
                add((x, y), ["PLACE", a], 92.0, need=a)

    # -- planting ------------------------------------------------------------
    plantable = [e for e in empties if e not in animal_zone]
    if not plantable and len(empties) > max(0, reserve_n - n_structs):
        plantable = list(empties)
    plantable.sort(key=lambda t: (shed_d(t), t[1], t[0]))
    seed_left = dict(seeds)
    need_seed = []                        # ordered: [(crop, count), ...]
    extra = dict((c, 0) for c in CROPS)
    deficit = wheat_deficit
    if not final_day and crop_shape:
        for spot in plantable[:PLAN_TILES]:
            pick = None
            for c in crop_shape:
                v = crop_value(c, extra[c])
                if v is None:
                    continue
                if c == "WHEAT" and deficit > 0 and days_left > 5:
                    v += 60.0
                if pick is None or v > pick[0]:
                    pick = (v, c)
            if pick is None:
                break
            c = pick[1]
            extra[c] += 1
            if c == "WHEAT":
                deficit -= wheat_rate
            if seed_left.get(c, 0) > 0:
                seed_left[c] -= 1
                add(spot, ["PLANT", c], 78.0)
            else:
                for row in need_seed:
                    if row[0] == c:
                        row[1] += 1
                        break
                else:
                    need_seed.append([c, 1])

    # -- logistics: shed pickups and drops -----------------------------------
    feed_need = sum(1 for (_, _, t) in animal_tiles
                    if not t.get("fed_today")) if day <= LAST_DAY - 1 else 0
    for s in shed_tiles:
        if feed_need > 0 and shed.get("WHEAT", 0) > 0:
            k = max(1, min(int(shed.get("WHEAT", 0)), feed_need, 24))
            # When an animal is one missed day from escaping, fetching its feed
            # has to outrank critical watering (128) and the FEED itself (130) --
            # otherwise every unit walks off to water and the herd starves with
            # wheat sitting in the shed.
            sc = 138.0 if unfed_risk else 78.0
            for _ in range(2):
                add(s, ["PICKUP", "WHEAT", k], sc, avoid="WHEAT")
        if fert_demand > 0 and shed.get("FERTILIZER", 0) > 0:
            k = max(1, min(int(shed.get("FERTILIZER", 0)), fert_demand, 12))
            add(s, ["PICKUP", "FERTILIZER", k], 56.0, avoid="FERTILIZER")
        for a in ANIMALS:
            if shed.get(a, 0) > 0 and free_structs:
                add(s, ["PICKUP", a, int(shed.get(a, 0))], 88.0, avoid=a)

    # ---------------- assignment ----------------
    liquidate = final_day and hour >= 15
    for u in units:
        inv = u["inv"]
        tot = _inv_total(inv)
        if liquidate:
            load = tot
        else:
            # Feed wheat, fertilizer and unplaced animals are working stock, not
            # produce: a unit that just picked up 24 wheat must not turn round
            # and drop it again.
            load = tot - min(inv.get("WHEAT", 0), 24) - min(inv.get("FERTILIZER", 0), 8)
            for a in ANIMALS:
                load -= min(inv.get(a, 0), 3)
        if load >= (1 if liquidate else DROP_THRESHOLD):
            s = min(shed_tiles, key=lambda t: _dist(u["pos"], t))
            score = 150.0 if liquidate else (72.0 + min(load, 40))
            tasks.append({"pos": s, "op": ["DROP"], "score": score,
                          "need": None, "avoid": None, "only": u["i"]})

    # Greedy max-value matching of units to tasks, value = score - walk cost.
    # Only the strongest TASK_LIMIT tasks can win a unit (a unit gives up at most
    # DIST_WEIGHT * board_diameter points to walking), so the tail is pruned to
    # keep the turn cheap. Then the classic lazy trick: keep each unit's current
    # best task and only recompute the units whose pick was just taken.
    U = len(units)
    if len(tasks) > TASK_LIMIT:
        tasks.sort(key=lambda t: -t["score"])
        del tasks[TASK_LIMIT:]
    T = len(tasks)
    tsc = [t["score"] for t in tasks]
    tx = [t["pos"][0] for t in tasks]
    ty = [t["pos"][1] for t in tasks]

    feas = []
    for u in units:
        inv = u["inv"]
        ui = u["i"]
        fl = []
        for j in range(T):
            t = tasks[j]
            only = t.get("only")
            if only is not None and only != ui:
                continue
            need = t["need"]
            if need is not None and inv.get(need, 0) <= 0:
                continue
            avoid = t["avoid"]
            if avoid is not None and inv.get(avoid, 0) > 0:
                continue
            fl.append(j)
        feas.append(fl)

    used = [False] * T
    taken = [False] * U
    best = [None] * U

    def _best_for(k):
        ux, uy = units[k]["pos"]
        bv = None
        bj = -1
        for j in feas[k]:
            if used[j]:
                continue
            v = tsc[j] - DIST_WEIGHT * (abs(ux - tx[j]) + abs(uy - ty[j]))
            if bv is None or v > bv:
                bv = v
                bj = j
        best[k] = (bv, bj) if bj >= 0 else None

    for k in range(U):
        _best_for(k)

    assigned = {}
    for _ in range(U):
        bk = -1
        bv = None
        for k in range(U):
            bk_e = best[k]
            if taken[k] or bk_e is None:
                continue
            if bv is None or bk_e[0] > bv:
                bv = bk_e[0]
                bk = k
        if bk < 0 or bv <= -60.0:
            break
        j = best[bk][1]
        used[j] = True
        taken[bk] = True
        assigned[units[bk]["i"]] = tasks[j]
        for k in range(U):
            if not taken[k] and best[k] is not None and best[k][1] == j:
                _best_for(k)

    unit_actions = {}
    for u in units:
        t = assigned.get(u["i"])
        if t is None:
            # Idle: drift toward the shed so the next supply run is short.
            s = min(shed_tiles, key=lambda q: _dist(u["pos"], q))
            unit_actions[u["i"]] = ["PASS"] if u["pos"] == s else _step_toward(u["pos"], s)
            continue
        if tuple(u["pos"]) == tuple(t["pos"]):
            unit_actions[u["i"]] = list(t["op"])
        else:
            unit_actions[u["i"]] = _step_toward(u["pos"], t["pos"])

    farmer_action = unit_actions.get(0, ["PASS"])
    hand_actions = [unit_actions.get(h + 1, ["PASS"]) for h in range(n_hands)]

    # Atomic PLANT guard: if two units request the same crop and we hold fewer
    # seeds than requests, the engine drops *all* of them. Never let that happen.
    demand = {}
    for a in [farmer_action] + hand_actions:
        if len(a) >= 2 and a[0] == "PLANT":
            demand[a[1]] = demand.get(a[1], 0) + 1
    over = {c for c, k in demand.items() if k > seeds.get(c, 0)}
    if over:
        seen = {}
        def trim(a):
            if len(a) >= 2 and a[0] == "PLANT" and a[1] in over:
                c = a[1]
                seen[c] = seen.get(c, 0) + 1
                if seen[c] > seeds.get(c, 0):
                    return ["PASS"]
            return a
        farmer_action = trim(farmer_action)
        hand_actions = [trim(a) for a in hand_actions]

    # ---------------- market ----------------
    orders = _market_orders(
        obs=obs, day=day, hour=hour, money=money, farm=farm, shed=shed, seeds=seeds,
        prices=prices, minv=minv, n=n, n_unlocked=n_unlocked, n_animals=n_animals,
        n_structs=n_structs, my_animal_count=my_animal_count, opp_animal=opp_animal,
        wheat_total=wheat_total, shed_total=shed_total, hires_today=hires_today,
        n_hands=n_hands, plants=plants, empties=empties, need_seed=need_seed,
        days_left=days_left, final_day=final_day, carried=carried,
        free_structs=free_structs, unfed_risk=unfed_risk, weeds=weeds,
        shops=shops)

    return {"farmer": farmer_action, "hands": hand_actions, "market": orders[:MAX_ORDERS]}


# ---------------------------------------------------------------------------
# Market policy
# ---------------------------------------------------------------------------

def _market_orders(obs, day, hour, money, farm, shed, seeds, prices, minv, n,
                   n_unlocked, n_animals, n_structs, my_animal_count, opp_animal,
                   wheat_total, shed_total, hires_today, n_hands, plants, empties,
                   need_seed, days_left, final_day, free_structs,
                   unfed_risk, weeds, carried, shops):
    head = []      # liquidity + hires: must not be crowded out
    sells = []
    buys = []
    cash = money

    # --- how much wheat must stay home as feed -----------------------------
    feed_reserve = 0 if final_day else min(58, n_animals + 5)
    # ...and how much cash must stay behind to buy that wheat if the field is
    # short. Two consecutive unfed days lose the animal permanently, so this
    # floor outranks every discretionary purchase below.
    unplaced_now = sum(shed.get(a, 0) + carried.get(a, 0) for a in ANIMALS)
    feed_floor = 0.0 if final_day else min(
        2600.0, (n_animals + unplaced_now) * 3.0 * max(22.0, float(prices.get("WHEAT", 25))))

    # --- sells --------------------------------------------------------------
    dump = final_day and hour >= 16
    order_by_value = sorted(PRODUCTS, key=lambda i: -prices.get(i, 0) * min(shed.get(i, 0), 20))
    for item in order_by_value:
        have = int(shed.get(item, 0) or 0)
        if item == "WHEAT" and not dump:
            have -= feed_reserve
        if have <= 0:
            continue
        p = prices.get(item, BASE[item])
        floor = SELL_FLOOR_FRAC.get(item, 0.5) * BASE[item]
        cap = max(SELL_CAP.get(item, 5), (have + 3) // 4)
        if dump:
            qty = have
        elif final_day:
            qty = max(1, (have + max(1, 20 - hour) - 1) // max(1, 20 - hour))
        elif p >= floor:
            qty = min(have, cap)
        elif shed_total > 74:
            qty = min(have, cap)          # shed pressure beats price discipline
        else:
            qty = min(have, max(1, cap // 3))
        if qty > 0:
            sells.append((p * min(qty, 30), ["SELL", item, int(qty)]))
    sells.sort(reverse=True, key=lambda z: z[0])
    sell_orders = [o for _, o in sells]

    # Sell one line first when broke so the same turn's buys can afford anything.
    if cash < 900 and sell_orders:
        head.append(sell_orders.pop(0))

    # --- hire ---------------------------------------------------------------
    if hour <= 2 and not final_day:
        # tile-actions the farm will ask for today; x1.9 covers the walking.
        work = (n_animals * 3.4 + len(plants) * 1.2 + min(len(empties), 28) * 1.8
                + len(weeds) * 0.6)
        want_hands = int(round(work * 1.9 / TURNS_PER_DAY)) - 1
        want_hands = max(1, min(MAX_HANDS, want_hands))
        k = 0
        h = hires_today
        while h < want_hands and k < 5:
            cost = _fib(h)
            if cost > 250 or cash < cost * 8 + 40:
                break
            head.append(["HIRE"])
            cash -= cost
            h += 1
            k += 1

    # --- emergency feed wheat ----------------------------------------------
    if n_animals > 0 and not final_day:
        need = n_animals + 4 - wheat_total
        room = SHED_CAP - shed_total
        if need > 0 and room > 0:
            wp = prices.get("WHEAT", 25)
            urgent = unfed_risk > 0 or wheat_total < n_animals
            if urgent or wp <= 60:
                qty = int(min(need, room, max(1, cash // max(1, wp))))
                if qty > 0:
                    head.append(["BUY_PRODUCT", "WHEAT", qty])
                    cash -= qty * wp

    # --- land ---------------------------------------------------------------
    quads = list(_g(farm, "unlocked_quadrants", None) or ["NW"])
    extra = max(0, len(quads) - 1)
    if extra < 3 and not final_day:
        price = [1000, 2000, 4000][extra]
        used = n_unlocked - len(empties)
        utilisation = used / float(max(1, n_unlocked))
        # Only buy ground we are already able to work, and only while there is
        # enough season left for 25 more tiles to pay $price back.
        if (cash - feed_floor >= price + 450 and utilisation >= 0.55
                and days_left >= 7):
            buys.append(["BUY_LAND"])
            cash -= price

    # --- animals ------------------------------------------------------------
    # Never stockpile stock we have not housed yet: an animal in the shed eats
    # shed capacity, produces nothing, and hides itself from the saturation
    # check below (which counts placed animals).
    unplaced = sum(shed.get(a, 0) + carried.get(a, 0) for a in ANIMALS)
    if (not final_day and unplaced < 3
            and n_animals + unplaced < MAX_ANIMALS
            and n_structs + unplaced < int(0.45 * n_unlocked)
            and (empties or free_structs)):
        best = None
        for a, ad in ANIMALS.items():
            prod_days = days_left - ad["first"]
            if prod_days <= 1:
                continue
            # Steady state with daily CARE: base 1 per scheduled production plus
            # one banked bonus per day since the last one.
            rate = 2.0 if ad["interval"] <= 1 else 1.0 + 1.0 / ad["interval"]
            item = ad["product"]
            own = my_animal_count.get(a, 0) + shed.get(a, 0) + carried.get(a, 0) + 1
            rival = max(opp_animal.get(a, 0), OPP_MIRROR * own)
            line = rate * prod_days * (own + rival)
            p = price_at(item, minv.get(item, I0)
                         + 0.5 * (line - town_drain(item, day, shops)))
            value = rate * prod_days * p - days_left * 26.0   # 26 = a day of feed
            if value > ad["cost"] * 2.0 and cash - feed_floor >= ad["cost"] + 250:
                key = value / float(ad["cost"])
                if best is None or key > best[0]:
                    best = (key, a, ad["cost"])
        if best is not None:
            buys.append(["BUY_ANIMAL", best[1], 1])
            cash -= best[2]

    # --- seeds --------------------------------------------------------------
    # The planting layer already decided what every open tile should hold; buy
    # exactly the seeds that plan is short of, cheapest-to-fund first.
    if need_seed and not final_day and days_left >= 4:
        spend_cap = max(0.0, cash - feed_floor) * 0.55
        for c, k in need_seed[:3]:
            if spend_cap <= 0:
                break
            sc = CROPS[c]["seed"]
            want = min(int(k), int(spend_cap // sc), 16)
            if want > 0:
                buys.append(["BUY_SEED", c, int(want)])
                spend_cap -= want * sc
                cash -= want * sc

    orders = head + sell_orders + buys
    return orders


def _fib(k):
    a, b = 1, 1
    for _ in range(max(0, int(k))):
        a, b = b, a + b
    return a


# ---------------------------------------------------------------------------
# ECONOMIC NOTES  (why the constants above are what they are)
#
# * Labour is cheap but not free. HIRE costs fib(n) per day and resets nightly:
#   12 hands cost $376/day, 15 cost $1,596, 20 cost $17,710. MAX_HANDS = 12 sits
#   just before the knee. 13 units x 24 turns = 312 unit-actions/day, and roughly
#   half of those are walking, so ~150 useful tile-actions/day is the real budget.
#
# * Animals beat crops per unit-action because four different actions (FEED,
#   CARE, HARVEST, COLLECT_FERTILIZER) land on one tile per walk, while a crop
#   tile usually absorbs a single WATER per walk. CARE doubles animal output for
#   one action/day, which is the best marginal action in the game.
#
# * ...but every animal eats 1 WHEAT/day, so a herd is only as big as the wheat
#   field behind it. Buying feed instead works until the wheat book runs dry:
#   wheat's scarcity side is sqrt with amp 1.0, so a 1,500-unit drawdown puts it
#   near $60. Hence the wheat-jumps-the-queue rule when n_animals outruns the
#   field.
#
# * The town is the demand floor and it is *not* uniform. Over a season the shops
#   plus the town centre remove roughly: wheat 525, strawberry 426, carrot 327,
#   milk 327, egg 228, tomato 228, wool 228, melon 30, fertilizer 0. Selling at
#   or under that rate keeps the price at or above base; selling past it is where
#   the premium goods (strawberry, melon, milk, wool: above_target > 1) fall to
#   the $1 floor. So the plan is to saturate each niche and no more, which is why
#   both the crop chooser and the animal chooser price their own projected volume
#   into the book (price_at(inv + proj)) before deciding.
#
# * The opponent's farm is public. Their standing crops and animals are added to
#   `proj`, so a rival strawberry field pushes us toward melon or eggs instead of
#   into a race to the floor on a shared curve.
#
# * EGG is the dump: base $50 with a log glut side (amp 1.72), so 2,000 eggs only
#   walk the price from $50 to $37. It is the one product that absorbs scale.
#
# * Unsold goods score zero. Day 29 has no end-of-day refresh, so nothing in a
#   unit's hands ever reaches the shed by itself: from hour 15 every unit with
#   inventory walks it in, and from hour 16 the book is dumped regardless of price.
# ---------------------------------------------------------------------------
