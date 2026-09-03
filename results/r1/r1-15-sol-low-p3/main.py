"""Rule based Kaggriculture agent, developed from the supplied game specification."""

SAFE = {"farmer": ["PASS"], "hands": [], "market": []}
CROPS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")
PRODUCTS = CROPS + ("EGG", "MILK", "WOOL", "FERTILIZER")
HARVEST_AGE = {"WHEAT": 4, "CARROT": 3, "TOMATO": 8,
               "STRAWBERRY": 10, "MELON": 10}
SEED_COST = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50,
             "STRAWBERRY": 100, "MELON": 80}


def _move(pos, target):
    x, y = pos
    tx, ty = target
    # Alternating axis preference spreads equal-distance units a little.
    if (x + y) & 1:
        if y != ty:
            return ["SOUTH" if ty > y else "NORTH"]
        if x != tx:
            return ["EAST" if tx > x else "WEST"]
    else:
        if x != tx:
            return ["EAST" if tx > x else "WEST"]
        if y != ty:
            return ["SOUTH" if ty > y else "NORTH"]
    return ["PASS"]


def _choose_crop(obs, counts):
    day = int(obs.get("day", 0))
    prices = obs.get("market", {}).get("prices", {})
    shops = obs.get("town", {}).get("unlocked_shops", [])
    demand = {c: 1 for c in CROPS}
    table = {
        "BAKERY": ("WHEAT",), "PIZZA_SHOP": ("WHEAT", "TOMATO"),
        "BRUNCH_SPOT": ("WHEAT", "STRAWBERRY"),
        "ICE_CREAM_SHOP": ("WHEAT", "STRAWBERRY"),
        "PET_CAFE": ("CARROT", "CARROT"),
        "SMOOTHIE_SHOP": ("STRAWBERRY",),
        "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
    }
    for shop in shops:
        for crop in table.get(shop, ()):
            demand[crop] += 6

    # Early short crops finance land; late planting must mature before day 30.
    money = float(obs.get("farms", [{}])[int(obs.get("player", 0))].get("money", 0))
    allowed = ["WHEAT", "CARROT"] if day < 5 or money < 5000 else list(CROPS)
    allowed = [c for c in allowed if day + HARVEST_AGE[c] <= 29]
    if not allowed:
        return None
    scores = {}
    for c in allowed:
        price = float(prices.get(c, {"WHEAT": 25, "CARROT": 35,
                                    "TOMATO": 60, "STRAWBERRY": 120,
                                    "MELON": 250}[c]))
        yields = {"WHEAT": 4, "CARROT": 3, "TOMATO": 4,
                  "STRAWBERRY": 4, "MELON": 6}
        gross = price * yields[c] - SEED_COST[c]
        # Normalize by occupancy and discourage a monoculture glut.
        scores[c] = gross / (HARVEST_AGE[c] + 1) * (1 + .035 * demand[c]) / (1 + .055 * counts.get(c, 0))
    return max(allowed, key=lambda c: scores[c])


def _unit_actions(obs, me, private):
    tiles = me["tiles"]
    day, hour = int(obs.get("day", 0)), int(obs.get("hour", 0))
    units = [me["farmer"]] + list(me.get("hands", []))
    counts = {c: 0 for c in CROPS}
    urgent, harvest, weeds, empty = [], [], [], []
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            if tile is None:
                empty.append((x, y))
            elif isinstance(tile, dict):
                kind = tile.get("kind")
                if kind == "WEED":
                    weeds.append((x, y))
                elif kind == "PLANT":
                    crop = tile.get("crop")
                    counts[crop] = counts.get(crop, 0) + 1
                    age = day - int(tile.get("planted_day", day))
                    if not tile.get("watered_today", False):
                        urgent.append((x, y))
                    if int(tile.get("yield_units", 0)) > 0 and age >= HARVEST_AGE.get(crop, 99):
                        harvest.append((x, y))

    crop = _choose_crop(obs, counts)
    seeds = private.get("seeds", {})
    can_plant = crop is not None and int(seeds.get(crop, 0)) > 0 and hour < 20

    # Global priority prevents irreversible losses. Harvest is delayed until peak.
    targets = urgent or harvest or weeds or (empty if can_plant else [])
    remaining = list(targets)
    actions = []
    for pos in units:
        x, y = pos
        tile = tiles[y][x] if 0 <= y < len(tiles) and 0 <= x < len(tiles[y]) else "LOCKED"
        here = (x, y)
        action = None
        if here in urgent:
            action = ["WATER"]
        elif not urgent and here in harvest:
            action = ["HARVEST"]
        elif not urgent and not harvest and here in weeds:
            action = ["DIG"]
        elif not urgent and not harvest and not weeds and can_plant and tile is None:
            action = ["PLANT", crop]
        if action is not None:
            actions.append(action)
            if here in remaining:
                remaining.remove(here)
            continue
        if remaining:
            target = min(remaining, key=lambda q: abs(q[0] - x) + abs(q[1] - y))
            remaining.remove(target)
            actions.append(_move(pos, target))
        else:
            actions.append(["PASS"])
    return actions, crop, len(empty)


def _livestock_actions(obs, me, private):
    tiles = me["tiles"]
    units = [me["farmer"]] + list(me.get("hands", []))
    invs = list(private.get("inventories", []))
    shed_geese = int(private.get("shed", {}).get("COW", 0))
    shed_wheat = int(private.get("shed", {}).get("WHEAT", 0))
    animal_tasks, harvest_tasks, vacant_coops, empty, weeds = [], [], [], [], []
    animals = 0
    coops = 0
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            if tile is None:
                empty.append((x, y))
            elif isinstance(tile, dict):
                kind = tile.get("kind")
                if kind == "WEED": weeds.append((x, y))
                elif kind == "PASTURE":
                    coops += 1
                    if tile.get("animal"):
                        animals += 1
                        if not tile.get("fed_today", False): animal_tasks.append((x, y))
                        elif tile.get("fertilizer_available", False): animal_tasks.append((x, y))
                        elif not tile.get("cared_today", False): animal_tasks.append((x, y))
                        elif int(tile.get("yield_units", 0)) > 0: harvest_tasks.append((x, y))
                    else:
                        vacant_coops.append((x, y))

    actions = []
    remaining = list(animal_tasks or harvest_tasks)
    access = [(4, 4), (5, 4), (4, 5), (5, 5)]
    for i, pos in enumerate(units):
        x, y = pos
        tile = tiles[y][x] if 0 <= y < len(tiles) and 0 <= x < len(tiles[y]) else "LOCKED"
        inv = invs[i] if i < len(invs) and isinstance(invs[i], dict) else {}
        carrying = int(inv.get("COW", 0)) > 0
        has_feed = int(inv.get("WHEAT", 0)) > 0
        here = (x, y)
        action = None
        if animals and not has_feed and shed_wheat > 0 and here in access and not carrying:
            take = min(6, shed_wheat)
            action = ["PICKUP", "WHEAT", take]
            shed_wheat -= take
        elif isinstance(tile, dict) and tile.get("kind") == "PASTURE" and tile.get("animal"):
            if not tile.get("fed_today", False) and has_feed: action = ["FEED"]
            elif tile.get("fertilizer_available", False): action = ["COLLECT_FERTILIZER"]
            elif not tile.get("cared_today", False): action = ["CARE"]
            elif int(tile.get("yield_units", 0)) > 0: action = ["HARVEST"]
        elif carrying and isinstance(tile, dict) and tile.get("kind") == "PASTURE" and not tile.get("animal"):
            action = ["PLACE", "COW"]
        elif carrying and tile is None:
            action = ["BUILD_PASTURE"]
        elif not carrying and shed_geese > 0 and here in access:
            action = ["PICKUP", "COW", 1]
            shed_geese -= 1
        elif not animal_tasks and not harvest_tasks and not carrying and not vacant_coops and empty and coops < 24 * len(me.get("unlocked_quadrants", ["NW"])):
            if tile is None: action = ["BUILD_PASTURE"]
        elif not animal_tasks and not harvest_tasks and not carrying and not vacant_coops and weeds:
            if isinstance(tile, dict) and tile.get("kind") == "WEED": action = ["DIG"]
        if action is not None:
            actions.append(action)
            if here in remaining: remaining.remove(here)
            continue
        if animals and not has_feed and shed_wheat > 0 and not carrying:
            choices = access
        elif carrying:
            choices = vacant_coops + empty
        elif not carrying and shed_geese > 0:
            choices = access
        elif remaining:
            choices = remaining
        elif not animal_tasks and not harvest_tasks and (shed_geese > 0 or carrying) and empty:
            choices = empty
        elif not animal_tasks and not harvest_tasks and not vacant_coops and empty:
            choices = empty
        elif weeds:
            choices = weeds
        else:
            choices = []
        if choices:
            target = min(choices, key=lambda q: abs(q[0]-x)+abs(q[1]-y))
            if target in remaining: remaining.remove(target)
            if target in vacant_coops: vacant_coops.remove(target)
            if target in empty: empty.remove(target)
            actions.append(_move(pos, target))
        else:
            actions.append(["PASS"])
    return actions, animals, coops, len(empty)


def _agent(obs):
    p = int(obs.get("player", 0))
    me = obs["farms"][p]
    private = obs.get("private", {})
    day, hour = int(obs.get("day", 0)), int(obs.get("hour", 0))
    actions, animals, coops, empty_n = _livestock_actions(obs, me, private)
    market = []
    shed = private.get("shed", {})

    # Liquidate continuously: avoids the shed cap and realizes prices before a glut.
    for item in PRODUCTS:
        n = int(shed.get(item, 0))
        if n > 0:
            market.append(["SELL", item, n])

    unlocked = len(me.get("unlocked_quadrants", ["NW"]))
    money = float(me.get("money", 0))
    # Unlock in the prescribed NE, SW, SE price order, after retaining working cash.
    next_land = {1: 1000, 2: 2000, 3: 4000}.get(unlocked)
    if next_land and day <= 18 and money > next_land + 1800:
        market.insert(0, ["BUY_LAND"])

    # Goose ranch: fertilizer is a daily, non-accumulating $100 output and eggs
    # have a glut-resistant curve. Buy gradually so feed liquidity is preserved.
    in_shed = int(shed.get("COW", 0))
    desired = min(60, 8 + day * 2, 24 * unlocked)
    if animals + in_shed < desired and money > 1400 and day < 13:
        n = min(2, desired - animals - in_shed, int((money - 1200) // 400))
        if n > 0: market.insert(0, ["BUY_ANIMAL", "COW", n])
    wheat = int(shed.get("WHEAT", 0))
    need_wheat = max(0, animals * 2 + 8 - wheat)
    if need_wheat and money > need_wheat * 30 + 150:
        market.insert(0, ["BUY_PRODUCT", "WHEAT", need_wheat])

    # Cheap parallel labor is the central investment; hires reset each day.
    # The 8th and later hires are much less attractive on a small field; retaining
    # liquidity is essential before the first harvest.
    target_hands = min(15, max(5, (animals + 2) // 3 + 3))
    if money < 300:
        target_hands = min(target_hands, 3)
    hires = int(me.get("hires_today", 0))
    if hour < 3 and hires < target_hands:
        for _ in range(min(target_hands - hires, 10 - len(market))):
            market.append(["HIRE"])

    market = market[:10]
    return {"farmer": actions[0] if actions else ["PASS"],
            "hands": actions[1:], "market": market}


def agent(obs):
    try:
        return _agent(obs)
    except Exception:
        return {"farmer": ["PASS"], "hands": [], "market": []}
