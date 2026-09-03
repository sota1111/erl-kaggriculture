"""Rule based Kaggriculture agent, written from the supplied game specification.

The policy treats cheap daily hands as a routing problem.  Needs that can destroy
an asset (feed/water) are assigned first, then collection, construction and
planting.  The implementation is intentionally stateless: every decision can be
reconstructed from the observation, which also makes seat changes and retries
safe.
"""

SAFE = {"farmer": ["PASS"], "hands": [], "market": []}

CROPS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")
PRODUCTS = (
    "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
    "EGG", "MILK", "WOOL", "FERTILIZER",
)
SEED_COST = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50,
             "STRAWBERRY": 100, "MELON": 80}
FIRST = {"WHEAT": 2, "CARROT": 2, "TOMATO": 8,
         "STRAWBERRY": 10, "MELON": 10}
PEAK = {"WHEAT": 4, "CARROT": 3, "TOMATO": 11,
        "STRAWBERRY": 16, "MELON": 10}
YIELD = {"WHEAT": 4, "CARROT": 3, "TOMATO": 4,
         "STRAWBERRY": 4, "MELON": 6}
DURATION = {"WHEAT": 5, "CARROT": 4, "TOMATO": 13,
            "STRAWBERRY": 18, "MELON": 11}
CROP_CAPS = {"WHEAT": 10, "CARROT": 15, "TOMATO": 15,
             "STRAWBERRY": 60, "MELON": 15}

ANIMAL_PRODUCT = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}
ANIMAL_COST = {"GOOSE": 300, "COW": 400, "SHEEP": 500}
ANIMAL_STRUCTURE = {"GOOSE": "COOP", "COW": "PASTURE", "SHEEP": "PASTURE"}

# Eggs remain valuable under a glut (logarithmic price curve), unlike the two
# premium animal products.  A few cows and sheep retain exposure to town demand.
ANIMAL_PATTERN = ("GOOSE",)
TARGET_ANIMALS = 0
ANIMAL_START_DAY = 4
HANDS_FULL = 10
USE_FERTILIZER = False
EARLY_CARROT_CAP = 10
SELL_ALL = True
POST_LAND_CASH_TARGET = 10000
DEMAND_SIGNAL = 0.5

MOVE = {(1, 0): "EAST", (-1, 0): "WEST", (0, 1): "SOUTH", (0, -1): "NORTH"}


def _dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _toward(pos, target, unit_index):
    """One deterministic Manhattan step; alternating axes spreads traffic."""
    x, y = pos
    tx, ty = target
    dx, dy = tx - x, ty - y
    if dx and dy:
        horizontal = (abs(dx) > abs(dy)) or (abs(dx) == abs(dy) and unit_index % 2 == 0)
    else:
        horizontal = bool(dx)
    if horizontal:
        return [MOVE[(1 if dx > 0 else -1, 0)]]
    if dy:
        return [MOVE[(0, 1 if dy > 0 else -1)]]
    return ["PASS"]


def _shed_tiles(n):
    h = n // 2
    return ((h - 1, h - 1), (h, h - 1), (h - 1, h), (h, h))


def _nearest_shed(pos, n):
    return min(_shed_tiles(n), key=lambda p: (_dist(pos, p), p[1], p[0]))


def _animal_layout(n):
    """Animal squares ordered from the central shed outwards across all land."""
    sheds = set(_shed_tiles(n))
    cells = [(x, y) for y in range(n) for x in range(n)]
    cells.sort(key=lambda p: (min(_dist(p, s) for s in sheds),
                              (p[0] * 7 + p[1] * 11) % 13, p[1], p[0]))
    return [p for p in cells if p not in sheds][:min(TARGET_ANIMALS, max(0, n * n - 4))]


def _crop_scores(prices, day):
    """Current net income rate, with a modest risk haircut for slow crops."""
    scores = {}
    remaining = 30 - day
    for crop in CROPS:
        if remaining <= FIRST[crop]:
            scores[crop] = -10**9
            continue
        gross = YIELD[crop] * float(prices.get(crop, 1)) - SEED_COST[crop]
        scores[crop] = gross / DURATION[crop]
    # Fast carrots fund the first expansion before any long crop can mature.
    if day < 8:
        scores["CARROT"] += 1000
    return scores


def _choose_crop(prices, day, existing, slot_index, caps_override=None):
    scores = _crop_scores(prices, day)
    ranked = sorted(CROPS, key=lambda c: (-scores[c], c))
    best = ranked[0]
    # Supply-sensitive premium goods are excellent in small lots and disastrous
    # as monocultures.  Soft per-farm caps leave room for the next-best market.
    virtual = dict(existing)
    caps = dict(caps_override or CROP_CAPS)
    if day < 8:
        caps["CARROT"] = EARLY_CARROT_CAP
    for _ in range(slot_index + 1):
        choice = next((c for c in ranked if virtual.get(c, 0) < caps[c]), best)
        virtual[choice] = virtual.get(choice, 0) + 1
    return choice


def _ready_to_harvest(tile, day):
    if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
        return False
    if int(tile.get("yield_units", 0)) <= 0:
        return False
    crop = tile.get("crop")
    age = day - int(tile.get("planted_day", day))
    if age < FIRST.get(crop, 99):
        return False
    # One-time crops are kept to their unfertilized peak; ongoing crops are
    # emptied whenever there is output so decay cannot erase it.
    if crop in ("WHEAT", "CARROT", "MELON"):
        return age >= PEAK[crop] and bool(tile.get("watered_today", False))
    return True


def _task_groups(obs, farm, private, animal_kind):
    """Return priority-ordered (target, action, eligibility) groups."""
    tiles = farm["tiles"]
    n = len(tiles)

    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    animal_cells = _animal_layout(n)
    animal_at = {p: ANIMAL_PATTERN[i % len(ANIMAL_PATTERN)]
                 for i, p in enumerate(animal_cells)}
    enabled_animals = day >= ANIMAL_START_DAY

    unplaced = {a: int((private.get("shed", {}) or {}).get(a, 0)) for a in ANIMAL_PRODUCT}
    for inv in private.get("inventories", []):
        for a in unplaced:
            unplaced[a] += int((inv or {}).get(a, 0))
    empty_structures = {"COOP": 0, "PASTURE": 0}
    for row in tiles:
        for t in row:
            if isinstance(t, dict) and t.get("kind") in empty_structures and "animal" not in t:
                empty_structures[t["kind"]] += 1
    build_budget = dict(unplaced)
    build_budget["GOOSE"] = max(0, build_budget["GOOSE"] - empty_structures["COOP"])
    pasture_waiting = empty_structures["PASTURE"]
    for a in ("COW", "SHEEP"):
        used = min(build_budget[a], pasture_waiting)
        build_budget[a] -= used
        pasture_waiting -= used

    feed, water, place, harvest, collect, care, fertilize = [], [], [], [], [], [], []
    dig, build, plant = [], [], []
    prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
    existing = {c: 0 for c in CROPS}
    empties = []

    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            p = (x, y)
            if tile == "LOCKED":
                continue
            wanted_animal = animal_at.get(p) if enabled_animals else None
            if tile is None:
                if wanted_animal and build_budget.get(wanted_animal, 0) > 0:
                    op = "BUILD_COOP" if wanted_animal == "GOOSE" else "BUILD_PASTURE"
                    build.append((p, [op], None))
                    build_budget[wanted_animal] -= 1
                else:
                    empties.append(p)
                continue
            if not isinstance(tile, dict):
                continue
            kind = tile.get("kind")
            if kind == "WEED":
                dig.append((p, ["DIG"], None))
            elif kind == "PLANT":
                crop = tile.get("crop")
                existing[crop] = existing.get(crop, 0) + 1
                age = day - int(tile.get("planted_day", day))
                fert_due = USE_FERTILIZER and ((crop == "TOMATO" and age == 7)
                            or (crop == "STRAWBERRY" and age in (9, 13)))
                if fert_due and int(tile.get("fertilized_until_day", -1)) < day:
                    fertilize.append((p, ["FERTILIZE"], "FERTILIZER"))
                # A crop occupying a future animal cell is allowed to finish.
                consecutive = int(tile.get("consecutive_unwatered", 0))
                ongoing = crop in ("TOMATO", "STRAWBERRY")
                bonus_start = (PEAK.get(crop, 99) + 1) // 2
                in_bonus_window = (not ongoing and bonus_start <= age <= PEAK.get(crop, -1))
                fertilized = int(tile.get("fertilized_until_day", -1)) >= day
                needs_water = (consecutive >= 1 or in_bonus_window
                               or (ongoing and fertilized))
                if not tile.get("watered_today", False) and needs_water:
                    water.append((p, ["WATER"], None))
                elif _ready_to_harvest(tile, day):
                    harvest.append((p, ["HARVEST"], None))
            elif "animal" in tile:
                if not tile.get("fed_today", False):
                    feed.append((p, ["FEED"], "WHEAT"))
                if int(tile.get("yield_units", 0)) > 0:
                    harvest.append((p, ["HARVEST"], None))
                if tile.get("fertilizer_available", False) and prices.get("FERTILIZER", 0) >= 35:
                    collect.append((p, ["COLLECT_FERTILIZER"], None))
                if not tile.get("cared_today", False) and hour < 21:
                    care.append((p, ["CARE"], None))
            elif kind in ("COOP", "PASTURE"):
                wanted = animal_at.get(p)
                if wanted and ANIMAL_STRUCTURE[wanted] == kind:
                    place.append((p, ["PLACE", wanted], wanted))

    # Crop is selected only when the worker reaches the square.  This permits a
    # fallback to seed types already in stock instead of stranding good seeds.
    if hour <= 20:
        for p in sorted(empties, key=lambda q: (q[1], q[0])):
            plant.append((p, ["PLANT"], None))

    # Destructive-loss prevention is always first.  Near midnight, unloading is
    # inserted before optional jobs by the caller.
    return [feed, water, place, harvest, collect, care, dig, build, plant, fertilize]


def _has(inv, requirement, seed_budget):
    if requirement is None:
        return True
    if requirement.startswith("SEED:"):
        return seed_budget.get(requirement[5:], 0) > 0
    return inv.get(requirement, 0) > 0


def _assign_units(obs, farm, private):
    n = len(farm["tiles"])
    positions = [tuple(farm["farmer"])] + [tuple(p) for p in farm.get("hands", [])]
    inventories = list(private.get("inventories", []))
    while len(inventories) < len(positions):
        inventories.append({})
    inventories = [dict(v or {}) for v in inventories[:len(positions)]]
    shed = dict(private.get("shed", {}) or {})
    hour = int(obs.get("hour", 0))

    actions = [None] * len(positions)
    animal_kinds = set(ANIMAL_PRODUCT)

    # At the shed, first bank carried produce.  Animal cargo is deliberately
    # retained because it is en route to a structure.
    for i, (pos, inv) in enumerate(zip(positions, inventories)):
        carried_goods = sum(v for k, v in inv.items()
                            if k not in animal_kinds and k not in ("WHEAT", "FERTILIZER"))
        if pos in _shed_tiles(n) and carried_goods > 0:
            actions[i] = ["DROP"]

    groups = _task_groups(obs, farm, private, animal_kinds)
    feed_count = len(groups[0])
    fertilize_count = len(groups[9])
    owned_cells = []
    for y, row in enumerate(farm["tiles"]):
        xs = range(n) if y % 2 == 0 else range(n - 1, -1, -1)
        for x in xs:
            if row[x] != "LOCKED":
                owned_cells.append((x, y))
    owner = {}
    total = max(1, len(owned_cells))
    for j, p in enumerate(owned_cells):
        owner[p] = min(len(positions) - 1, j * len(positions) // total)
    place_needs = {}
    for _, _, req in groups[2]:
        place_needs[req] = place_needs.get(req, 0) + 1

    # Equip idle units while they are at the shed.  Virtual stock prevents a
    # crowd of simultaneous PICKUP requests from mostly becoming no-ops.
    virtual_shed = dict(shed)
    carried_animals = {a: sum(inv.get(a, 0) for inv in inventories) for a in animal_kinds}
    equipped_feed = sum(inv.get("WHEAT", 0) for inv in inventories)
    for i, (pos, inv) in enumerate(zip(positions, inventories)):
        if actions[i] is not None or pos not in _shed_tiles(n):
            continue
        if feed_count and inv.get("WHEAT", 0) == 0 and virtual_shed.get("WHEAT", 0) > 0:
            take = min(5, virtual_shed["WHEAT"])
            actions[i] = ["PICKUP", "WHEAT", take]
            virtual_shed["WHEAT"] -= take
            equipped_feed += take
            continue
        my_fertilize = sum(1 for t in groups[9] if owner.get(t[0]) == i)
        if my_fertilize and inv.get("FERTILIZER", 0) == 0 and virtual_shed.get("FERTILIZER", 0) > 0:
            take = min(3, my_fertilize, virtual_shed["FERTILIZER"])
            actions[i] = ["PICKUP", "FERTILIZER", take]
            virtual_shed["FERTILIZER"] -= take
            continue
        if equipped_feed >= feed_count and not any(inv.get(a, 0) for a in animal_kinds):
            picked = None
            for a in ("GOOSE", "COW", "SHEEP"):
                if (place_needs.get(a, 0) > carried_animals.get(a, 0)
                        and virtual_shed.get(a, 0) > 0):
                    picked = a
                    break
            if picked:
                actions[i] = ["PICKUP", picked, 1]
                virtual_shed[picked] -= 1
                carried_animals[picked] += 1
                continue
    # When urgent work is done, route loaded units back before the automatic
    # midnight drop can overflow the shared 100-item shed.
    unload = []
    for i, (pos, inv) in enumerate(zip(positions, inventories)):
        goods = sum(v for k, v in inv.items()
                    if k not in animal_kinds and k not in ("WHEAT", "FERTILIZER"))
        if goods >= 10 or (hour >= 20 and goods > 0):
            unload.append((_nearest_shed(pos, n), ["DROP"], "UNIT:" + str(i)))

    seed_budget = dict(private.get("seeds", {}) or {})
    prices = ((obs.get("market", {}) or {}).get("prices", {}) or {})
    day = int(obs.get("day", 0))

    remaining_feed = list(groups[0])

    # Handle each worker independently.  Immediate tile actions win ties so FEED
    # followed later by HARVEST/CARE does not cause needless trips away and back.
    for i in range(len(positions)):
        if actions[i] is not None:
            continue
        pos = positions[i]
        inv = inventories[i]

        # An animal in hand must reach any compatible empty structure, regardless
        # of which worker normally owns that patch.
        cargo = next((a for a in ("GOOSE", "COW", "SHEEP") if inv.get(a, 0) > 0), None)
        if cargo:
            candidates = [t for t in groups[2] if t[2] == cargo]
            if candidates:
                target, op, _ = min(candidates, key=lambda t: (_dist(pos, t[0]), t[0][1], t[0][0]))
                actions[i] = op if pos == target else _toward(pos, target, i)
                groups[2].remove((target, op, cargo))
                continue

        # Feeding is pooled across blocks: any wheat-carrying worker helps the
        # nearest hungry animal.  This decouples survival from spawn/order quirks.
        if inv.get("WHEAT", 0) > 0 and remaining_feed:
            target, op, req = min(remaining_feed,
                                  key=lambda t: (_dist(pos, t[0]), t[0][1], t[0][0]))
            actions[i] = op if pos == target else _toward(pos, target, i)
            remaining_feed.remove((target, op, req))
            continue

        my_groups = [[t for t in g if owner.get(t[0]) == i] for g in groups]
        my_groups[0] = [t for t in my_groups[0] if t in remaining_feed]

        # A block with hungry animals routes its worker to wheat before it does
        # optional work.  Feed cannot silently lapse due to unlucky hand spawns.
        if my_groups[0] and inv.get("WHEAT", 0) <= 0:
            target = _nearest_shed(pos, n)
            actions[i] = (["PICKUP", "WHEAT", 8]
                          if pos == target and shed.get("WHEAT", 0) > 0
                          else _toward(pos, target, i))
            continue

        # Primary survival work is strict across the block.  Remaining jobs are
        # selected by proximity, with the current square receiving a large bonus
        # so its multi-action animal workflow is completed in place.
        candidates = []
        primary_exists = bool(my_groups[0] or my_groups[1])
        selected_groups = my_groups[:2] if primary_exists else [my_groups[9], *my_groups[2:4]]
        if primary_exists:
            # Once a peak-age crop at the current square has been watered, reap
            # it immediately.  Waiting for a second pass lets end-of-life decay
            # erase one unit every other turn.
            selected_groups += [[t for t in my_groups[3] if t[0] == pos]]
        if not primary_exists:
            # Unload before expendable collection/care/construction late in day.
            selected_groups += [[t for t in unload if t[2] == "UNIT:" + str(i)]]
            selected_groups += my_groups[4:9]
        for priority, group in enumerate(selected_groups):
            for target, op, req in group:
                if _has(inv, req, seed_budget):
                    d = _dist(pos, target)
                    candidates.append((0 if d == 0 else 1, d, priority,
                                       target[1], target[0], target, op, req))
        if candidates:
            *_, target, op, req = min(candidates)
            if pos != target:
                actions[i] = _toward(pos, target, i)
            elif op and op[0] == "PLANT":
                ranked = sorted(CROPS, key=lambda c: (-_crop_scores(prices, day)[c], c))
                crop = next((c for c in ranked if seed_budget.get(c, 0) > 0), None)
                if crop:
                    actions[i] = ["PLANT", crop]
                    seed_budget[crop] -= 1
                else:
                    actions[i] = ["PASS"]
            else:
                actions[i] = op

    return [a if a is not None else ["PASS"] for a in actions]


def _market_orders(obs, farm, private):
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    money = float(farm.get("money", 0))
    shed = private.get("shed", {}) or {}
    prices = ((obs.get("market", {}) or {}).get("prices", {}) or {})
    tiles = farm["tiles"]
    n = len(tiles)

    fertilizer_due = 0
    fertilizer_upcoming = 0
    fertilizer_value = 0.0
    for row in tiles:
        for tile in row:
            if not (isinstance(tile, dict) and tile.get("kind") == "PLANT"):
                continue
            crop = tile.get("crop")
            age = day - int(tile.get("planted_day", day))
            if USE_FERTILIZER and crop == "TOMATO":
                if age == 7:
                    fertilizer_due += 1
                elif age == 6:
                    fertilizer_upcoming += 1
                    fertilizer_value = max(fertilizer_value, 3 * prices.get("TOMATO", 0))
            elif USE_FERTILIZER and crop == "STRAWBERRY":
                if age in (9, 13):
                    fertilizer_due += 1
                elif age in (8, 12):
                    fertilizer_upcoming += 1
                    fertilizer_value = max(fertilizer_value, 2 * prices.get("STRAWBERRY", 0))

    orders = []
    shed_total = sum(max(0, int(v)) for v in shed.values())
    market_inventory = ((obs.get("market", {}) or {}).get("inventory", {}) or {})
    # Continuous liquidation keeps capital working and avoids shed overflow;
    # crop diversification, rather than hoarding, controls price impact.
    growth_target = (10**12 if SELL_ALL or len(farm.get("unlocked_quadrants", ["NW"])) < 4
                     else POST_LAND_CASH_TARGET)
    cash_gap = max(0.0, growth_target - money)
    capacity_excess = max(0, shed_total - 65)
    sale_candidates = []
    for item in sorted(PRODUCTS, key=lambda z: (-prices.get(z, 1), z)):
        qty = int(shed.get(item, 0))
        if qty <= 0:
            continue
        if item == "FERTILIZER" and (fertilizer_due or fertilizer_upcoming):
            continue
        price = float(prices.get(item, 1))
        if day >= 28:
            take = qty
        else:
            shortage = max(0, 10000 - int(market_inventory.get(item, 10000)))
            take = min(qty, shortage)
            if cash_gap > 0:
                need = int((cash_gap + max(price, 1) - 1) // max(price, 1))
                take = max(take, min(qty, need))
            if capacity_excess > 0:
                take = max(take, min(qty, capacity_excess))
        if take > 0:
            sale_candidates.append((price * take, item, take))
            cash_gap = max(0.0, cash_gap - price * take)
            capacity_excess = max(0, capacity_excess - take)
    sale_candidates.sort(reverse=True)
    for _, item, qty in sale_candidates[:6]:
        orders.append(["SELL", item, qty])

    # Unlock one quadrant per turn once its cost leaves an operating reserve.
    unlocked = len(farm.get("unlocked_quadrants", ["NW"]))
    land_costs = (1000, 2000, 4000)
    if unlocked <= 3:
        cost = land_costs[unlocked - 1]
        reserve = 500
        if money >= cost + reserve:
            orders.append(["BUY_LAND"])
            money -= cost

    # Keep one day's feed in the shed/inventories.  Buying removes wheat from the
    # market, partially offsetting the price pressure of crop sales.
    animals = 0
    for row in tiles:
        for tile in row:
            if isinstance(tile, dict) and "animal" in tile:
                animals += 1
    carried_wheat = sum((v or {}).get("WHEAT", 0) for v in private.get("inventories", []))
    wheat_have = int(shed.get("WHEAT", 0)) + carried_wheat
    wheat_target = animals + 30 if animals else 0
    wheat_need = max(0, wheat_target - wheat_have)
    if wheat_need and len(orders) < 10:
        orders.append(["BUY_PRODUCT", "WHEAT", wheat_need])

    fertilizer_have = int(shed.get("FERTILIZER", 0))
    fertilizer_have += sum(int((v or {}).get("FERTILIZER", 0))
                           for v in private.get("inventories", []))
    fertilizer_need = max(0, fertilizer_upcoming + fertilizer_due - fertilizer_have)
    fertilizer_price = float(prices.get("FERTILIZER", 100))
    if (fertilizer_need and fertilizer_price < fertilizer_value
            and money > 1500 and len(orders) < 10
            and shed_total + fertilizer_need < 98):
        affordable = max(0, int((money - 1000) // max(1, fertilizer_price)))
        qty = min(fertilizer_need, affordable)
        if qty:
            orders.append(["BUY_PRODUCT", "FERTILIZER", qty])
            money -= qty * fertilizer_price

    # Progressively populate built animal structures without risking feed money.
    layout = _animal_layout(n)
    desired = {a: 0 for a in ANIMAL_PRODUCT}
    for i, (x, y) in enumerate(layout):
        if tiles[y][x] != "LOCKED" and day >= ANIMAL_START_DAY:
            desired[ANIMAL_PATTERN[i % len(ANIMAL_PATTERN)]] += 1
    owned = {a: int(shed.get(a, 0)) for a in ANIMAL_PRODUCT}
    for inv in private.get("inventories", []):
        for a in owned:
            owned[a] += int((inv or {}).get(a, 0))
    for row in tiles:
        for tile in row:
            if isinstance(tile, dict) and tile.get("animal") in owned:
                owned[tile["animal"]] += 1
    for a in ("GOOSE", "COW", "SHEEP"):
        missing = max(0, desired[a] - owned[a])
        animal_reserve = 2000 if day < 12 else 1500
        affordable = max(0, int((money - animal_reserve) // ANIMAL_COST[a]))
        qty = min(missing, affordable, 4)
        if qty and len(orders) < 10 and shed_total + qty < 96:
            orders.append(["BUY_ANIMAL", a, qty])
            money -= qty * ANIMAL_COST[a]
            shed_total += qty

    # Seed the currently best under-supplied crop.  Seeds do not consume shed
    # capacity, and an overlarge order simply stops when its cash budget runs out.
    vacant = 0
    existing = {c: 0 for c in CROPS}
    animal_cells = set(layout) if day >= ANIMAL_START_DAY else set()
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            if tile is None and (x, y) not in animal_cells:
                vacant += 1
            elif isinstance(tile, dict) and tile.get("kind") == "PLANT":
                existing[tile.get("crop")] = existing.get(tile.get("crop"), 0) + 1
    seed_stock = {c: int(private.get("seeds", {}).get(c, 0)) for c in CROPS}
    seed_total = sum(seed_stock.values())
    if vacant > seed_total and len(orders) < 10 and day < 29:
        committed = {c: existing.get(c, 0) + seed_stock[c] for c in CROPS}
        planning_prices = dict(prices)
        shop_products = {
            "BAKERY": ("EGG", "WHEAT"),
            "PIZZA_SHOP": ("MILK", "TOMATO", "WHEAT"),
            "BRUNCH_SPOT": ("EGG", "WHEAT", "STRAWBERRY"),
            "YARN_STORE": ("WOOL",),
            "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"),
            "PET_CAFE": ("CARROT",),
            "SMOOTHIE_SHOP": ("STRAWBERRY", "MILK"),
            "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
        }
        demand = {c: 1 for c in CROPS}
        unlocked_shops = list((obs.get("town", {}) or {}).get("unlocked_shops", []))
        for shop in unlocked_shops:
            goods = shop_products.get(shop, ())
            rate = 12 if len(goods) == 1 else 6
            for c in goods:
                if c in demand:
                    demand[c] += rate
        # Hinge crops need a deliberately forward-looking signal: their current
        # quote stays deceptively calm until cumulative shop demand crosses T.
        boost = {"WHEAT": 4.0, "CARROT": 12.0, "TOMATO": 42.0,
                 "STRAWBERRY": 10.0, "MELON": 0.5}
        for c in CROPS:
            planning_prices[c] = (planning_prices.get(c, 1)
                                  + DEMAND_SIGNAL * boost[c] * demand[c])
        # Four of the eight equally likely shop types demand strawberries.  A
        # crop planted only after all shops are revealed would mature too late,
        # so reserve the high expected-demand share from the outset.
        planning_caps = dict(CROP_CAPS)
        crop = _choose_crop(planning_prices, day, committed, 0, planning_caps)
        seed_reserve = 1000 if day < 8 and len(farm.get("unlocked_quadrants", [])) == 1 else 900
        affordable = max(0, int((money - seed_reserve) // SEED_COST[crop]))
        crop_cap = (EARLY_CARROT_CAP if day < 8 and crop == "CARROT"
                    else planning_caps[crop])
        quota_room = max(0, crop_cap - committed[crop])
        qty = min(vacant - seed_total, affordable, 24, quota_room)
        if qty > 0:
            orders.append(["BUY_SEED", crop, qty])
            money -= qty * SEED_COST[crop]

    # Ten or eleven mobile workers cover a full mixed farm.  Hires are cheapest
    # at the start of their Fibonacci curve and disappear automatically nightly.
    owned_tiles = sum(1 for row in tiles for tile in row if tile != "LOCKED")
    desired_hands = 8 if owned_tiles <= 50 else (10 if owned_tiles <= 75 else HANDS_FULL)
    if hour < 8:
        missing_hands = max(0, desired_hands - len(farm.get("hands", [])))
        fib_a, fib_b = 1, 1
        for _ in range(int(farm.get("hires_today", 0))):
            fib_a, fib_b = fib_b, fib_a + fib_b
        next_hire = fib_a
        while missing_hands and len(orders) < 10 and money >= next_hire + 250:
            orders.append(["HIRE"])
            money -= next_hire
            next_hire, fib_b = fib_b, next_hire + fib_b
            missing_hands -= 1

    return orders[:10]


def agent(obs):
    try:
        farms = obs.get("farms", [])
        player = int(obs.get("player", 0))
        if not farms or player < 0 or player >= len(farms):
            return dict(SAFE)
        farm = farms[player]
        private = obs.get("private", {}) or {}
        unit_actions = _assign_units(obs, farm, private)
        return {
            "farmer": unit_actions[0] if unit_actions else ["PASS"],
            "hands": unit_actions[1:],
            "market": _market_orders(obs, farm, private),
        }
    except Exception:
        # Invalid actions are survivable; an exception is not.  Keep this broad
        # guard at the archive boundary as required by the submission contract.
        return {"farmer": ["PASS"], "hands": [], "market": []}
