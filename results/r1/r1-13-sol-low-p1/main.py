"""A defensive, stateless rule-based Kaggriculture agent."""

FALLBACK = {"farmer": ["PASS"], "hands": [], "market": []}
PRODUCTS = ("MELON", "CARROT", "WHEAT", "TOMATO", "STRAWBERRY",
            "MILK", "WOOL", "EGG", "FERTILIZER")
SEED_COST = {"MELON": 80, "CARROT": 20, "WHEAT": 10}


def _move(pos, goal):
    x, y = pos
    gx, gy = goal
    # Alternating the preferred axis reduces congestion without needing memory.
    if (x + y) & 1:
        if y != gy:
            return ["SOUTH" if gy > y else "NORTH"]
        if x != gx:
            return ["EAST" if gx > x else "WEST"]
    else:
        if x != gx:
            return ["EAST" if gx > x else "WEST"]
        if y != gy:
            return ["SOUTH" if gy > y else "NORTH"]
    return ["PASS"]


def _inside_action(tile, day, crop):
    if tile is None:
        return ["PLANT", crop]
    if not isinstance(tile, dict):
        return ["DIG"] if tile != "LOCKED" else ["PASS"]
    kind = tile.get("kind")
    if kind == "WEED":
        return ["DIG"]
    if kind == "PLANT":
        age = day - int(tile.get("planted_day", day))
        ripe = {"MELON": 10, "CARROT": 3, "WHEAT": 4,
                "TOMATO": 8, "STRAWBERRY": 10}.get(tile.get("crop"), 99)
        if int(tile.get("yield_units", 0)) > 0 and age >= ripe:
            return ["HARVEST"]
        if not tile.get("watered_today", False):
            return ["WATER"]
    return ["PASS"]


def _plan(obs):
    player = int(obs.get("player", 0))
    farms = obs.get("farms") or []
    me = farms[player]
    tiles = me.get("tiles") or []
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    private = obs.get("private") or {}
    shed = private.get("shed") or {}
    seeds = private.get("seeds") or {}

    # Melons have the strongest action-adjusted return before their maturity
    # deadline. Carrots turn the land once more at the end of the season.
    prices = (obs.get("market") or {}).get("prices") or {}
    # Net revenue per occupied day. Reacting to the live shared price prevents
    # symmetric agents from feeding a premium-product glut all season.
    candidates = []
    if day <= 19:
        candidates.append(((6 * float(prices.get("MELON", 250)) - 80) / 11, "MELON"))
    if day <= 26:
        candidates.append(((3 * float(prices.get("CARROT", 35)) - 20) / 4, "CARROT"))
    if day <= 25:
        candidates.append(((4 * float(prices.get("WHEAT", 25)) - 10) / 5, "WHEAT"))
    crop = max(candidates)[1] if candidates else "WHEAT"
    planting_open = bool(candidates)

    urgent, ripe, weeds, empty = [], [], [], []
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            if tile == "LOCKED":
                continue
            if tile is None:
                if planting_open:
                    empty.append((x, y, "plant"))
            elif isinstance(tile, dict):
                kind = tile.get("kind")
                if kind == "WEED":
                    weeds.append((x, y, "dig"))
                elif kind == "PLANT":
                    age = day - int(tile.get("planted_day", day))
                    threshold = {"MELON": 10, "CARROT": 3, "WHEAT": 4,
                                 "TOMATO": 8, "STRAWBERRY": 10}.get(tile.get("crop"), 99)
                    if int(tile.get("yield_units", 0)) > 0 and age >= threshold:
                        ripe.append((x, y, "harvest"))
                    elif not tile.get("watered_today", False):
                        urgent.append((x, y, "water"))

    # Harvest before watering only when already ripe; otherwise survival wins.
    task_groups = [urgent, ripe, weeds, empty]
    positions = [me.get("farmer", [4, 4])] + list(me.get("hands") or [])
    remaining_groups = [list(group) for group in task_groups]
    actions = []
    inventories = list(private.get("inventories") or [])
    shed_access = {(4, 4), (5, 4), (4, 5), (5, 5)}
    for unit_i, pos in enumerate(positions):
        # The final automatic drop occurs after the scoring horizon. Bring the
        # last harvest home early enough to sell it on a subsequent turn.
        inv = inventories[unit_i] if unit_i < len(inventories) else {}
        if day == 29 and hour >= 14 and inv:
            if tuple(pos) in shed_access:
                actions.append(["DROP"])
            else:
                actions.append(_move(tuple(pos), (4, 4)))
            continue
        remaining = next((group for group in remaining_groups if group), None)
        if remaining is None:
            actions.append(["PASS"])
            continue
        px, py = pos
        idx = min(range(len(remaining)),
                  key=lambda i: (abs(remaining[i][0] - px) + abs(remaining[i][1] - py), i))
        tx, ty, typ = remaining.pop(idx)
        if px == tx and py == ty:
            if typ == "water":
                actions.append(["WATER"])
            elif typ == "harvest":
                actions.append(["HARVEST"])
            elif typ == "dig":
                actions.append(["DIG"])
            else:
                actions.append(["PLANT", crop])
        else:
            actions.append(_move((px, py), (tx, ty)))

    market = []
    # Realize cash continuously and keep the shed away from its hard cap.
    for item in PRODUCTS:
        n = int(shed.get(item, 0) or 0)
        if n > 0 and len(market) < 10:
            market.append(["SELL", item, n])

    money = float(me.get("money", 0) or 0)
    unlocked = len(me.get("unlocked_quadrants") or ["NW"])
    # One land purchase at a time makes the cash reserve calculation reliable.
    land_cost = (1000, 2000, 4000)[unlocked - 1] if unlocked < 4 else 0
    if land_cost and money >= land_cost + 1200 and len(market) < 10:
        market.append(["BUY_LAND"])
        money -= land_cost

    # Buy only the next work wave. Buying for every empty tile on every travel
    # turn strands cash in duplicate seed inventory.
    wave = min(len(empty), len(positions))
    need = max(0, wave - int(seeds.get(crop, 0) or 0))
    buy = min(need, int(max(0, money - 500) // SEED_COST[crop]))
    if buy and len(market) < 10:
        market.append(["BUY_SEED", crop, buy])
        money -= buy * SEED_COST[crop]

    # 12 total units can service a full farm comfortably within 24 turns.
    hires = int(me.get("hires_today", 0) or 0)
    target_hires = 11 if day < 29 else 5
    fib = [1, 1]
    while len(fib) <= target_hires:
        fib.append(fib[-1] + fib[-2])
    while hires < target_hires and len(market) < 10 and money >= fib[hires] + 250:
        market.append(["HIRE"])
        money -= fib[hires]
        hires += 1

    return {"farmer": actions[0] if actions else ["PASS"],
            "hands": actions[1:], "market": market[:10]}


def agent(obs):
    try:
        return _plan(obs)
    except Exception:
        hands = []
        try:
            p = int(obs.get("player", 0))
            hands = [["PASS"] for _ in obs.get("farms", [])[p].get("hands", [])]
        except Exception:
            pass
        return {"farmer": ["PASS"], "hands": hands, "market": []}
