"""Rule based Kaggriculture agent, developed from the supplied game rules."""

SAFE_ACTION = {"farmer": ["PASS"], "hands": [], "market": []}

CROPS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")
SEED_COST = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50,
             "STRAWBERRY": 100, "MELON": 80}
MAX_DAY = {"WHEAT": 4, "CARROT": 3, "TOMATO": 11,
           "STRAWBERRY": 16, "MELON": 10}
FIRST_DAY = {"WHEAT": 2, "CARROT": 2, "TOMATO": 8,
             "STRAWBERRY": 10, "MELON": 10}
ONGOING = {"TOMATO", "STRAWBERRY"}
LAND_COST = (1000, 2000, 4000)
ANIMALS = {"GOOSE": "COOP", "COW": "PASTURE", "SHEEP": "PASTURE"}
WORK_DIVISOR = 7
FEED_BATCH = 1
TOMATO_RESERVE = 40
TOMATO_SHOPS_FOR_RESERVE = 3
TOMATO_RELEASE_DAY = 29
USE_FERTILIZER = True
FERTILIZER_RESERVE = 5
FERTILIZE_TOMATO = False


def _fib_hire_cost(n):
    """Cost of hire number n (zero based) in the current day."""
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def _crop_for(x, y, shops, prices=None):
    """A stable diversified layout, mildly tilted toward observed town demand."""
    counts = {}
    for name in shops:
        counts[name] = counts.get(name, 0) + 1

    # The weights are tile shares.  Premium crops are deliberately capped: their
    # glut curves hit the $1 floor quickly.  Staples get the remaining capacity.
    weights = {
        "WHEAT": 8 + 2 * sum(counts.get(s, 0) for s in
                              ("BAKERY", "PIZZA_SHOP", "BRUNCH_SPOT",
                               "ICE_CREAM_SHOP", "FARMERS_MARKET")),
        "CARROT": 18 + 5 * counts.get("PET_CAFE", 0)
                      + 2 * counts.get("FARMERS_MARKET", 0),
        "TOMATO": 28 + 4 * counts.get("PIZZA_SHOP", 0)
                      + 4 * counts.get("FARMERS_MARKET", 0),
        "STRAWBERRY": 30 + 15 * sum(counts.get(s, 0) for s in
                                    ("BRUNCH_SPOT", "ICE_CREAM_SHOP",
                                     "SMOOTHIE_SHOP", "FARMERS_MARKET")),
        "MELON": 16,
    }
    # Convert the coordinate to a well-spread percentile.  Using a permutation
    # avoids planting each crop as one large, synchronized block.
    rank = ((x * 37 + y * 61 + x * y * 7) % 101) / 101.0
    total = float(sum(weights.values()))
    acc = 0.0
    for crop in CROPS:
        acc += weights[crop] / total
        if rank < acc:
            return crop
    return "MELON"


def _plan_for(x, y, shops, prices=None):
    """Long-run use for a tile: livestock first, otherwise a crop."""
    # A second permutation keeps each quadrant representative.  Livestock opens
    # egg/milk/wool/fertilizer markets while a wheat sleeve offsets daily feed.
    # A small reserve of coops/pastures lets the market controller respond to the
    # first shop reveals without digging productive crops. Empty structures cost
    # no coins; the animal purchase itself remains demand gated below.
    geese, cows, sheep, wheat = 4, 6, 0, 8
    rank = ((x * 53 + y * 29 + x * y * 11 + 17) % 101)
    if rank < geese:
        return "GOOSE"
    if rank < geese + cows:
        return "COW"
    if rank < geese + cows + sheep:
        return "SHEEP"
    if rank < geese + cows + sheep + wheat:
        return "WHEAT"
    return _crop_for(x, y, shops, prices)


def _desired_animals(obs):
    # A fixed small herd won the multi-seed test: reacting to shops buys livestock
    # too late, while a larger opening herd overpays for feed and crashes premium
    # product prices in self-play.
    return {"GOOSE": 2, "COW": 2, "SHEEP": 1}


def _effective_crop(plan, day):
    """Replace a crop which can no longer mature with the best short cycle."""
    return plan


def _worth_planting(crop, prices):
    if crop == "WHEAT":
        return True  # feed substitution value is at least its quoted market price
    units = {"CARROT": 3, "TOMATO": 4, "STRAWBERRY": 4, "MELON": 6}
    return units.get(crop, 0) * int(prices.get(crop, 0) or 0) > SEED_COST.get(crop, 10 ** 9)


def _move_toward(x, y, tx, ty):
    # Alternate the primary axis spatially to spread units on equal-length paths.
    if ((x + y + tx + ty) & 1) == 0:
        if x < tx:
            return ["EAST"]
        if x > tx:
            return ["WEST"]
        if y < ty:
            return ["SOUTH"]
        if y > ty:
            return ["NORTH"]
    else:
        if y < ty:
            return ["SOUTH"]
        if y > ty:
            return ["NORTH"]
        if x < tx:
            return ["EAST"]
        if x > tx:
            return ["WEST"]
    return ["PASS"]


def _jobs(obs, farm, seeds):
    day = int(obs.get("day", 0))
    shops = (obs.get("town") or {}).get("unlocked_shops", []) or []
    prices = ((obs.get("market") or {}).get("prices", {}) or {})
    jobs = []
    # Lower priority number is more urgent.  Watering precedes every optional
    # action, including harvesting, so a plant is never allowed to become a weed.
    for y, row in enumerate(farm.get("tiles", [])):
        for x, tile in enumerate(row):
            if tile == "LOCKED":
                continue
            if tile is None:
                plan = _effective_crop(_plan_for(x, y, shops, prices), day)
                if plan in ANIMALS:
                    jobs.append((4, x, y, ["BUILD_" + ANIMALS[plan]], None))
                elif (_worth_planting(plan, prices) and day + FIRST_DAY[plan] <= 29
                      and seeds.get(plan, 0) > 0):
                    jobs.append((5, x, y, ["PLANT", plan], plan))
                continue
            if not isinstance(tile, dict):
                continue
            kind = tile.get("kind")
            if kind == "WEED":
                jobs.append((4, x, y, ["DIG"], None))
                continue
            if kind in ("COOP", "PASTURE"):
                if tile.get("animal"):
                    if day == 29:
                        if int(tile.get("yield_units", 0) or 0) > 0:
                            jobs.append((0, x, y, ["HARVEST"], None))
                    elif not tile.get("fed_today", False):
                        # Missing once is survivable; missing the following day is
                        # irreversible.  Escalate that second-day feed above every
                        # planting/watering/harvest route.
                        feed_priority = -10 if int(tile.get("consecutive_unfed", 0) or 0) >= 1 else 0
                        jobs.append((feed_priority, x, y, ["FEED"], "NEEDS_WHEAT"))
                    elif int(tile.get("yield_units", 0) or 0) > 0:
                        jobs.append((2, x, y, ["HARVEST"], None))
                    elif not tile.get("cared_today", False):
                        jobs.append((3, x, y, ["CARE"], None))
                    elif tile.get("fertilizer_available", False):
                        jobs.append((4, x, y, ["COLLECT_FERTILIZER"], None))
                continue
            if kind != "PLANT":
                continue
            crop = tile.get("crop")
            age = day - int(tile.get("planted_day", day))
            if day == 29:
                if int(tile.get("yield_units", 0) or 0) > 0 \
                        and age >= FIRST_DAY.get(crop, 99):
                    jobs.append((0, x, y, ["HARVEST"], None))
                continue
            must_water = int(tile.get("consecutive_unwatered", 0) or 0) >= 1
            if not tile.get("watered_today", False):
                # Fresh seeds and anything skipped yesterday are hard safety
                # constraints. One-time crops also get every bonus-window day.
                urgent = 0 if must_water else 1
                jobs.append((urgent, x, y, ["WATER"], None))
                continue
            held = int(tile.get("yield_units", 0) or 0)
            if (USE_FERTILIZER
                    and ((crop == "STRAWBERRY" and age in (9, 13))
                         or (FERTILIZE_TOMATO and crop == "TOMATO" and age in (7, 10)))
                    and int(tile.get("fertilized_until_day", -1) or -1) < day + 2):
                jobs.append((2, x, y, ["FERTILIZE"], "NEEDS_FERT"))
                continue
            if crop in ONGOING:
                if held > 0:
                    jobs.append((2, x, y, ["HARVEST"], None))
                elif age > MAX_DAY.get(crop, 99):
                    jobs.append((3, x, y, ["DIG"], None))
            elif age >= MAX_DAY.get(crop, 99) or day >= 29:
                jobs.append((2, x, y, ["HARVEST"], None))
    return jobs


def _unit_actions(obs, farm, private):
    positions = [farm.get("farmer", [4, 4])] + list(farm.get("hands", []))
    inventories = list(private.get("inventories", []) or [])
    while len(inventories) < len(positions):
        inventories.append({})
    seeds = dict(private.get("seeds", {}) or {})
    jobs = _jobs(obs, farm, seeds)
    actions = [["PASS"] for _ in positions]

    free_units = set(range(len(positions)))
    claimed_jobs = set()

    # Products collected on the last day are worthless unless returned to the
    # shed and sold before the episode ends.  Route loaded units home immediately.
    if int(obs.get("day", 0)) == 29:
        shed_access = ((4, 4), (5, 4), (4, 5), (5, 5))
        for ui in list(free_units):
            inv = inventories[ui] or {}
            if not any(int(inv.get(item, 0) or 0) > 0 for item in
                       ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
                        "EGG", "MILK", "WOOL", "FERTILIZER")):
                continue
            ux, uy = positions[ui]
            if (ux, uy) in shed_access:
                actions[ui] = ["DROP"]
            else:
                tx, ty = min(shed_access, key=lambda p: abs(ux-p[0]) + abs(uy-p[1]))
                actions[ui] = _move_toward(ux, uy, tx, ty)
            free_units.remove(ui)

    if USE_FERTILIZER:
        # Keep fertilizer carriers on their production-window deliveries; general
        # watering work would otherwise repeatedly divert them.
        for ui in list(free_units):
            if int((inventories[ui] or {}).get("FERTILIZER", 0) or 0) <= 0:
                continue
            choices = [(abs(positions[ui][0] - job[1]) + abs(positions[ui][1] - job[2]), ji)
                       for ji, job in enumerate(jobs)
                       if job[4] == "NEEDS_FERT" and ji not in claimed_jobs]
            if not choices:
                continue
            _, ji = min(choices)
            _, tx, ty, op, _ = jobs[ji]
            ux, uy = positions[ui]
            actions[ui] = op if (ux, uy) == (tx, ty) else _move_toward(ux, uy, tx, ty)
            claimed_jobs.add(ji)
            free_units.remove(ui)

    # Finish animal transport before ordinary work.  A bought animal lives in the
    # shed, must be PICKUP-ed by one unit, and can only then be PLACE-d on a matching
    # structure.  Reservations prevent all units selecting the same structure.
    empty_structures = []
    for y, row in enumerate(farm.get("tiles", [])):
        for x, tile in enumerate(row):
            if isinstance(tile, dict) and tile.get("kind") in ("COOP", "PASTURE") \
                    and not tile.get("animal"):
                empty_structures.append((x, y, tile.get("kind")))
    reserved = set()
    for ui in list(free_units):
        inv = inventories[ui] or {}
        carried = next((a for a in ANIMALS if int(inv.get(a, 0) or 0) > 0), None)
        if not carried:
            continue
        choices = [(abs(positions[ui][0] - x) + abs(positions[ui][1] - y), x, y, si)
                   for si, (x, y, kind) in enumerate(empty_structures)
                   if si not in reserved and kind == ANIMALS[carried]]
        if not choices:
            continue
        _, tx, ty, si = min(choices)
        reserved.add(si)
        ux, uy = positions[ui]
        actions[ui] = (["PLACE", carried] if (ux, uy) == (tx, ty)
                       else _move_toward(ux, uy, tx, ty))
        free_units.remove(ui)

    shed = private.get("shed", {}) or {}
    shed_access = ((4, 4), (5, 4), (4, 5), (5, 5))
    if USE_FERTILIZER:
        day = int(obs.get("day", 0))
        due = sum(1 for row in farm.get("tiles", []) for tile in row
                  if isinstance(tile, dict) and tile.get("kind") == "PLANT"
                  and ((tile.get("crop") == "STRAWBERRY"
                        and day - int(tile.get("planted_day", day)) in (9, 13))
                       or (FERTILIZE_TOMATO and tile.get("crop") == "TOMATO"
                           and day - int(tile.get("planted_day", day)) in (7, 10)))
                  and int(tile.get("fertilized_until_day", -1) or -1) < day + 2)
        carried = sum(int((inventories[i] or {}).get("FERTILIZER", 0) or 0)
                      for i in free_units)
        needed = max(0, due - carried)
        available = int(shed.get("FERTILIZER", 0) or 0)
        for ui in list(free_units):
            if needed <= 0 or available <= 0:
                break
            ux, uy = positions[ui]
            if (ux, uy) not in shed_access:
                continue
            qty = min(5, needed, available)
            actions[ui] = ["PICKUP", "FERTILIZER", qty]
            needed -= qty
            available -= qty
            free_units.remove(ui)

    virtual_animals = {a: int(shed.get(a, 0) or 0) for a in ANIMALS}
    unreserved_kinds = [kind for si, (_, _, kind) in enumerate(empty_structures)
                        if si not in reserved]
    for ui in list(free_units):
        animal = next((a for a in ("GOOSE", "COW", "SHEEP")
                       if virtual_animals[a] > 0 and ANIMALS[a] in unreserved_kinds), None)
        if not animal:
            break
        ux, uy = positions[ui]
        if (ux, uy) in shed_access:
            actions[ui] = ["PICKUP", animal, 1]
            virtual_animals[animal] -= 1
            unreserved_kinds.remove(ANIMALS[animal])
        else:
            tx, ty = min(shed_access, key=lambda p: abs(ux-p[0]) + abs(uy-p[1]))
            actions[ui] = _move_toward(ux, uy, tx, ty)
        free_units.remove(ui)

    # At day start only a few units need take bulk wheat; each then services a
    # chain of animals.  The virtual shed balance makes simultaneous PICKUP safe.
    unfed = sum(1 for row in farm.get("tiles", []) for tile in row
                if isinstance(tile, dict) and tile.get("animal")
                and not tile.get("fed_today", False))
    carried_wheat = sum(int((inventories[i] or {}).get("WHEAT", 0) or 0)
                        for i in free_units)
    wheat_needed = max(0, unfed - carried_wheat)
    wheat_in_shed = int(shed.get("WHEAT", 0) or 0)
    for ui in list(free_units):
        if wheat_needed <= 0 or wheat_in_shed <= 0:
            break
        ux, uy = positions[ui]
        if (ux, uy) not in shed_access:
            continue
        # Several short feeder routes are safer than one carrier crossing the
        # whole farm; the latter missed distant animals late in the day.
        qty = min(FEED_BATCH, wheat_needed, wheat_in_shed)
        actions[ui] = ["PICKUP", "WHEAT", qty]
        wheat_needed -= qty
        wheat_in_shed -= qty
        free_units.remove(ui)

    # Match units and tiles afresh every turn.  Exact assignment is unnecessary;
    # the global closest-pair rule prevents the classic all-hands-chase-one-tile
    # failure while retaining short routes as jobs appear and disappear.
    free_jobs = set(range(len(jobs))) - claimed_jobs
    pairs = []
    for ui in free_units:
        ux, uy = positions[ui]
        for ji in free_jobs:
            pri, tx, ty, op, crop = jobs[ji]
            if crop == "NEEDS_WHEAT" and int((inventories[ui] or {}).get("WHEAT", 0) or 0) <= 0:
                continue
            if crop == "NEEDS_FERT" and int((inventories[ui] or {}).get("FERTILIZER", 0) or 0) <= 0:
                continue
            dist = abs(ux - tx) + abs(uy - ty)
            pairs.append((pri, dist, ji, ui))
    pairs.sort()
    for _, _, ji, ui in pairs:
        if ui not in free_units or ji not in free_jobs:
            continue
        pri, tx, ty, op, crop = jobs[ji]
        ux, uy = positions[ui]
        if ux == tx and uy == ty:
            # Do not issue more PLANT commands than the visible seed balance.
            if op[0] == "PLANT":
                if seeds.get(crop, 0) <= 0:
                    free_jobs.remove(ji)
                    continue
                seeds[crop] -= 1
            actions[ui] = op
        else:
            actions[ui] = _move_toward(ux, uy, tx, ty)
        free_units.remove(ui)
        free_jobs.remove(ji)
        if not free_units or not free_jobs:
            break
    return actions


def _market_actions(obs, farm, private):
    money = float(farm.get("money", 0) or 0)
    orders = []
    shed = private.get("shed", {}) or {}
    live_at_start = sum(1 for row in farm.get("tiles", []) for tile in row
                        if isinstance(tile, dict) and tile.get("animal"))
    unplaced_at_start = sum(int(shed.get(a, 0) or 0) for a in ANIMALS)
    unplaced_at_start += sum(sum(int((inv or {}).get(a, 0) or 0) for a in ANIMALS)
                             for inv in (private.get("inventories", []) or []))
    positions = [farm.get("farmer", [4, 4])] + list(farm.get("hands", []))
    inventories = list(private.get("inventories", []) or [])
    shed_access = {(4, 4), (5, 4), (4, 5), (5, 5)}

    # Selling first both protects the 100-item shed and finances later orders in
    # the same queue.  Only harvested products are sold; seeds have their own slot.
    for item in ("MELON", "STRAWBERRY", "TOMATO", "CARROT", "WHEAT",
                 "EGG", "MILK", "WOOL", "FERTILIZER"):
        amount = int(shed.get(item, 0) or 0)
        # DROP is applied before the market queue. Anticipating an eligible loaded
        # unit here lets the newly deposited harvest be sold in the same turn.
        for pos, inv in zip(positions, inventories):
            cashout = int(obs.get("day", 0)) == 29
            if cashout and tuple(pos) in shed_access:
                amount += int((inv or {}).get(item, 0) or 0)
        if item == "TOMATO" and int(obs.get("day", 0)) < TOMATO_RELEASE_DAY:
            tomato_inv = int(((obs.get("market") or {}).get("inventory", {}) or {}).get("TOMATO", 10000))
            tomato_shops = sum(s in ("PIZZA_SHOP", "FARMERS_MARKET")
                               for s in ((obs.get("town") or {}).get("unlocked_shops", []) or []))
            if tomato_inv > 9800 and tomato_shops >= TOMATO_SHOPS_FOR_RESERVE:
                amount = max(0, amount - TOMATO_RESERVE)
        # Wheat is working capital for present and newly placed livestock.  A
        # market sale followed by an emergency repurchase is especially harmful
        # because player/town demand has already raised its price.
        if item == "WHEAT":
            amount = max(0, amount - live_at_start - unplaced_at_start - 4)
        if item == "FERTILIZER" and USE_FERTILIZER and int(obs.get("day", 0)) < 28:
            amount = max(0, amount - FERTILIZER_RESERVE)
        if amount > 0 and len(orders) < 10:
            orders.append(["SELL", item, amount])

    # Land is most valuable early.  Keep enough cash to operate instead of buying
    # the expensive final quadrant at the first technically affordable instant.
    unlocked = len(farm.get("unlocked_quadrants", ["NW"]))
    # The $4,000 SE quadrant becomes affordable only after the first long-cycle
    # harvest in this policy; multi-seed tests showed it does not repay by day 30.
    if unlocked < 3 and len(orders) < 10:
        land_cost = LAND_COST[unlocked - 1]
        threshold = land_cost + (500 if unlocked == 1 else 700)
        if money >= threshold and int(obs.get("day", 0)) <= (3, 20, 18)[unlocked - 1]:
            orders.append(["BUY_LAND"])
            money -= land_cost

    # Livestock adds feed/care/collection cycles, so retain a modest labour margin.
    # absorb harvest/replant spikes.  Fibonacci costs beyond this point dominate.
    tile_count = 25 * unlocked
    target_units = max(4, (tile_count + WORK_DIVISOR - 1) // WORK_DIVISOR)
    target_hands = max(0, target_units - 1)
    hires = int(farm.get("hires_today", 0) or 0)
    while hires < target_hands and len(orders) < 10:
        cost = _fib_hire_cost(hires)
        # Hands are the safety system: even a cash-starved farm must buy the
        # first cheap hires or its already-planted crop becomes unrecoverable.
        if money < cost:
            break
        orders.append(["HIRE"])
        money -= cost
        hires += 1

    # No purchase has a realizable return after this point. Hires can still bring
    # already-produced goods home, so they remain above this cutoff.
    if int(obs.get("day", 0)) >= 29:
        return orders[:10]

    # Buy one day of feed after selling (which frees shed capacity).  Existing
    # leftovers and wheat carried by units both count toward the requirement.
    live_animals = sum(1 for row in farm.get("tiles", []) for tile in row
                       if isinstance(tile, dict) and tile.get("animal"))
    owned_unplaced = sum(int(shed.get(a, 0) or 0) for a in ANIMALS)
    owned_unplaced += sum(sum(int((inv or {}).get(a, 0) or 0) for a in ANIMALS)
                          for inv in (private.get("inventories", []) or []))
    carried_wheat = sum(int((inv or {}).get("WHEAT", 0) or 0)
                        for inv in (private.get("inventories", []) or []))
    feed_deficit = max(0, live_animals + owned_unplaced + 4
                       - int(shed.get("WHEAT", 0) or 0) - carried_wheat)
    if feed_deficit and len(orders) < 10:
        # BUY_PRODUCT is unit-priced dynamically; cap by the visible quote and
        # reserve cash for at least the next day's cheap hands.
        quote = int(((obs.get("market") or {}).get("prices", {}) or {}).get("WHEAT", 25) or 25)
        qty = min(feed_deficit, int(max(0, money - 20) // max(1, quote)))
        if qty > 0:
            orders.append(["BUY_PRODUCT", "WHEAT", qty])
            money -= qty * quote

    # Grow the planned livestock population gradually.  Expensive types are
    # small, diversified sleeves rather than a bet on one fragile premium market.
    shops = (obs.get("town") or {}).get("unlocked_shops", []) or []
    prices = ((obs.get("market") or {}).get("prices", {}) or {})
    desired = _desired_animals(obs)
    existing = {a: int(shed.get(a, 0) or 0) for a in ANIMALS}
    for inv in (private.get("inventories", []) or []):
        for a in ANIMALS:
            existing[a] += int((inv or {}).get(a, 0) or 0)
    for y, row in enumerate(farm.get("tiles", [])):
        for x, tile in enumerate(row):
            if isinstance(tile, dict) and tile.get("animal") in existing:
                existing[tile["animal"]] += 1
    animal_cost = {"GOOSE": 300, "COW": 400, "SHEEP": 500}
    bought_animals = 0
    for animal in ("GOOSE", "COW", "SHEEP"):
        if len(orders) >= 10:
            break
        deficit = desired[animal] - existing[animal]
        # Pace capital expenditure so the new herd cannot consume tomorrow's
        # feed budget before it has produced anything.
        affordable = int(max(0, money - 500) // animal_cost[animal])
        qty = min(2 - bought_animals, max(0, deficit), affordable)
        if qty > 0:
            orders.append(["BUY_ANIMAL", animal, qty])
            money -= qty * animal_cost[animal]
            bought_animals += qty

    # Buy seeds only for currently empty cells of each desired type.  Small spare
    # buffers make replanting prompt without tying up much capital.
    needed = {c: 0 for c in CROPS}
    planted = {c: 0 for c in CROPS}
    for y, row in enumerate(farm.get("tiles", [])):
        for x, tile in enumerate(row):
            if tile is None:
                plan = _effective_crop(_plan_for(x, y, shops, prices), int(obs.get("day", 0)))
                if (plan in needed and _worth_planting(plan, prices)
                        and int(obs.get("day", 0)) + FIRST_DAY[plan] <= 29):
                    needed[plan] += 1
            elif isinstance(tile, dict) and tile.get("kind") == "PLANT":
                crop = tile.get("crop")
                if crop in planted:
                    planted[crop] += 1
    seeds = private.get("seeds", {}) or {}
    # Cheap/short-cycle crops first; a failed expensive bulk buy must not block all
    # planting.  Quantities are capped so changing town demand does not strand cash.
    for crop in ("WHEAT", "CARROT", "TOMATO", "MELON", "STRAWBERRY"):
        if len(orders) >= 10:
            break
        deficit = max(0, needed[crop] + 2 - int(seeds.get(crop, 0) or 0))
        qty = min(deficit, 20)
        # Retain a small next-day labour reserve; seed stock is useless when the
        # workforce cannot water it.
        # A herd which has not reached its planned size needs a much larger cash
        # cushion than a crop-only farm: feed is unrecoverable safety spending.
        reserve = 500 if (live_animals + owned_unplaced) else 75
        affordable = int(max(0, money - reserve) // SEED_COST[crop])
        qty = min(qty, affordable)
        if qty > 0:
            orders.append(["BUY_SEED", crop, qty])
            money -= qty * SEED_COST[crop]
    return orders[:10]


def agent(obs):
    try:
        player = int(obs.get("player", 0))
        farms = obs.get("farms", [])
        if player < 0 or player >= len(farms):
            return dict(SAFE_ACTION)
        farm = farms[player]
        private = obs.get("private", {}) or {}
        actions = _unit_actions(obs, farm, private)
        farmer = actions[0] if actions else ["PASS"]
        hands = actions[1:] if len(actions) > 1 else []
        return {"farmer": farmer, "hands": hands,
                "market": _market_actions(obs, farm, private)}
    except Exception:
        return {"farmer": ["PASS"], "hands": [], "market": []}
