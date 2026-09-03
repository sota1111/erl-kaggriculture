"""Rule-based livestock agent for Kaggriculture 1.32.7."""

PASS = {"farmer": ["PASS"], "hands": [], "market": []}
PRODUCTS = ("FERTILIZER", "EGG", "MILK", "WOOL", "MELON",
            "STRAWBERRY", "TOMATO", "CARROT", "WHEAT")
SHED_SQUARES = ((4, 4), (5, 4), (4, 5), (5, 5))


def _move(pos, target):
    x, y = pos
    tx, ty = target
    if x < tx:
        return ["EAST"]
    if x > tx:
        return ["WEST"]
    if y < ty:
        return ["SOUTH"]
    if y > ty:
        return ["NORTH"]
    return ["PASS"]


def _dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _quadrant_count(farm):
    return len(farm.get("unlocked_quadrants", ("NW",)))


def _core(obs):
    p = int(obs.get("player", 0))
    farms = obs.get("farms") or []
    if p >= len(farms):
        return PASS
    farm = farms[p]
    tiles = farm.get("tiles") or []
    private = obs.get("private") or {}
    shed = private.get("shed") or {}
    inventories = private.get("inventories") or []
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", obs.get("step", 0) % 24))
    money = float(farm.get("money", 0))
    positions = [farm.get("farmer", [4, 4])] + list(farm.get("hands") or [])

    # Ordered market queue: cash realization always survives the ten-order cap.
    market = []
    for item in PRODUCTS:
        n = int(shed.get(item, 0) or 0)
        if n:
            market.append(["SELL", item, n])

    qcount = _quadrant_count(farm)
    # Land repays itself through permanent fertilizer production. Buy only with a
    # reserve, and one parcel at a time so an order cannot unexpectedly bankrupt us.
    land_cost = (1000, 2000, 4000)[min(qcount - 1, 2)] if qcount < 4 else 10**9
    if qcount < 4 and day >= 9 and money > land_cost + 3000 and len(market) < 10:
        market.append(["BUY_LAND"])

    plants = []
    animals = []
    empty_coops = []
    empty = []
    weeds = []
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            if tile is None:
                empty.append((x, y))
            elif isinstance(tile, dict):
                kind = tile.get("kind")
                if kind == "WEED":
                    weeds.append((x, y))
                elif kind == "PLANT":
                    plants.append(((x, y), tile))
                elif kind == "COOP":
                    if tile.get("animal"):
                        animals.append(((x, y), tile))
                    else:
                        empty_coops.append((x, y))

    # A dozen helpers is a good movement/maintenance compromise; hire orders are
    # spread over turns because the market accepts only ten orders per turn.
    target_hands = (8 if day < 11 else 12) if (plants or animals or empty or empty_coops) and day < 30 else 0
    hires = int(farm.get("hires_today", 0) or 0)
    # Leave two slots for investment orders in the opening.
    hire_now = min(target_hands - hires, max(0, 8 - len(market)))
    if hire_now > 0 and money > 60:
        market.extend([["HIRE"] for _ in range(hire_now)])

    # Melons have the largest robust gross margin per occupied tile. Buy only what
    # can still mature before season end; the engine truncates an unaffordable order.
    seeds = private.get("seeds") or {}
    melon_seeds = int(seeds.get("MELON", 0) or 0)
    plantable = len(empty) if day == 0 else 0
    affordable = max(0, int((money - 800) // 80))
    if plantable > melon_seeds and affordable and len(market) < 10:
        market.append(["BUY_SEED", "MELON", min(plantable - melon_seeds, affordable)])

    # After the opening melon harvest, turn the farm into a durable egg business.
    if day >= 11:
        goose_stock = int(shed.get("GOOSE", 0) or 0)
        missing = max(0, len(empty_coops) - goose_stock)
        buyable = max(0, int((money - 1200) // 300))
        if missing and buyable and len(market) < 10:
            market.append(["BUY_ANIMAL", "GOOSE", min(missing, buyable)])
        wheat = int(shed.get("WHEAT", 0) or 0)
        carried_wheat = sum(int((inv or {}).get("WHEAT", 0) or 0)
                            for inv in inventories if isinstance(inv, dict))
        need = max(0, len(animals) + 6 - wheat - carried_wheat)
        if need and money > need * 30 + 300 and len(market) < 10:
            market.append(["BUY_PRODUCT", "WHEAT", need])

    # Tasks are recomputed from observation every turn and assigned one-to-one.
    # Urgent survival work precedes output work and construction.
    tasks = []
    for pos, tile in plants:
        age = day - int(tile.get("planted_day", day))
        if age >= 10 and int(tile.get("yield_units", 0) or 0) > 0:
            tasks.append((0, pos, ["HARVEST"]))
        elif not tile.get("watered_today"):
            tasks.append((1, pos, ["WATER"]))
    for pos, tile in animals:
        if not tile.get("fed_today"):
            tasks.append((0, pos, ["FEED"]))
        if int(tile.get("yield_units", 0) or 0) > 0:
            tasks.append((2, pos, ["HARVEST"]))
        if tile.get("fertilizer_available"):
            tasks.append((3, pos, ["COLLECT_FERTILIZER"]))
        if not tile.get("cared_today"):
            tasks.append((4, pos, ["CARE"]))
    for pos in weeds:
        tasks.append((6, pos, ["DIG"]))
    if day == 0:
        for pos in empty[:melon_seeds]:
            tasks.append((5, pos, ["PLANT", "MELON"]))
    elif day >= 11:
        # Keep two free cells per quadrant-ish for movement and random weeds.
        for pos in empty[:max(0, min(60 - len(animals) - len(empty_coops), len(empty) - 6))]:
            tasks.append((6, pos, ["BUILD_COOP"]))

    actions = [["PASS"] for _ in positions]
    used_tasks = set()
    # Every day inventories are returned to the shed. Fetch a route-sized feed
    # bundle before dispatching units; without this FEED is a silent no-op.
    feed_waiting = any(not tile.get("fed_today") for _, tile in animals)
    wheat_left = int(shed.get("WHEAT", 0) or 0)
    bundle = max(1, (len(animals) + max(1, len(positions)) - 1) // max(1, len(positions)))
    for i, pos in enumerate(positions):
        inv = inventories[i] if i < len(inventories) and isinstance(inventories[i], dict) else {}
        if feed_waiting and int(inv.get("WHEAT", 0) or 0) == 0 and wheat_left > 0:
            target = min(SHED_SQUARES, key=lambda z: _dist(pos, z))
            take = min(bundle + 1, wheat_left)
            actions[i] = ["PICKUP", "WHEAT", take] if tuple(pos) == target else _move(pos, target)
            if tuple(pos) == target:
                wheat_left -= take
    # Next priority is transporting purchased geese to empty coops.
    goose_left = int(shed.get("GOOSE", 0) or 0)
    available_coops = list(empty_coops)
    for i, pos in enumerate(positions):
        if actions[i] != ["PASS"]:
            continue
        inv = inventories[i] if i < len(inventories) and isinstance(inventories[i], dict) else {}
        if int(inv.get("GOOSE", 0) or 0) and available_coops:
            target = min(available_coops, key=lambda z: _dist(pos, z))
            actions[i] = ["PLACE", "GOOSE"] if tuple(pos) == target else _move(pos, target)
            available_coops.remove(target)
        elif goose_left > 0 and available_coops:
            target = min(SHED_SQUARES, key=lambda z: _dist(pos, z))
            actions[i] = ["PICKUP", "GOOSE", 1] if tuple(pos) == target else _move(pos, target)
            if tuple(pos) == target:
                goose_left -= 1
    # Allocate distinct observable tasks greedily, nearest unit first.
    for priority in range(8):
        choices = [(j, t) for j, t in enumerate(tasks) if t[0] == priority and j not in used_tasks]
        while choices:
            best = None
            for i, pos in enumerate(positions):
                if actions[i] != ["PASS"]:
                    continue
                for j, task in choices:
                    score = (_dist(pos, task[1]), i, j)
                    if best is None or score < best[0]:
                        best = (score, i, j, task)
            if best is None:
                break
            _, i, j, task = best
            actions[i] = task[2] if tuple(positions[i]) == task[1] else _move(positions[i], task[1])
            used_tasks.add(j)
            choices = [(k, t) for k, t in choices if k != j]

    return {"farmer": actions[0], "hands": actions[1:], "market": market[:10]}


def agent(obs):
    try:
        return _core(obs)
    except Exception:
        return {"farmer": ["PASS"], "hands": [], "market": []}
