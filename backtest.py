import pandas as pd
import numpy as np
import json
import matplotlib.pyplot as plt

STEP = 100
ORDER_SIZE = 5000

def compute_cost(split, venues, order_size, λo, λu, θ):
    executed = 0
    cash_spent = 0
    for i in range(len(venues)):
        ask, ask_size, fee, rebate = venues[i]
        exe = min(split[i], ask_size)
        executed += exe
        cash_spent += exe * (ask + fee)
        maker_rebate = max(split[i] - exe, 0) * rebate
        cash_spent -= maker_rebate
    underfill = max(order_size - executed, 0)
    overfill = max(executed - order_size, 0)
    risk_pen = θ * (underfill + overfill)
    cost_pen = λu * underfill + λo * overfill
    return cash_spent + risk_pen + cost_pen

def allocate(order_size, venues, λo, λu, θ):
    N = len(venues)
    splits = [[0] * N]

    for v in range(N):
        new_splits = []
        for alloc in splits:
            used = sum(alloc)
            max_v = min(order_size - used, venues[v][1])
            for q in range(0, max_v + 1, STEP):
                new_alloc = alloc.copy()
                new_alloc[v] = q
                new_splits.append(new_alloc)
        splits = new_splits

    best_cost = float('inf')
    best_split = [0] * N
    for alloc in splits:
        if sum(alloc) != order_size:
            continue
        cost = compute_cost(alloc, venues, order_size, λo, λu, θ)
        if cost < best_cost:
            best_cost = cost
            best_split = alloc

    return best_split, best_cost

def run_backtest(snapshots, λo, λu, θ):
    shares_left = ORDER_SIZE
    total_cost = 0
    for snapshot in snapshots:
        if shares_left <= 0:
            break
        venues = snapshot
        if len(venues) == 0:
            continue
        split, _ = allocate(shares_left, venues, λo, λu, θ)
        if not split or len(split) != len(venues):
            continue
        for i in range(len(venues)):
            ask, ask_size, fee, rebate = venues[i]
            exe = min(split[i], ask_size)
            total_cost += exe * (ask + fee)
            shares_left -= exe
            if exe < split[i]:
                total_cost -= (split[i] - exe) * rebate
    avg_price = total_cost / ORDER_SIZE
    return total_cost, avg_price

def baseline_best_ask(snapshots):
    total_cost = 0
    shares_left = ORDER_SIZE
    for snapshot in snapshots:
        ask, ask_size, fee, rebate = snapshot[0]
        qty = min(shares_left, ask_size)
        total_cost += qty * (ask + fee)
        shares_left -= qty
        if shares_left <= 0:
            break
    avg_price = total_cost / ORDER_SIZE
    return total_cost, avg_price

def baseline_twap(snapshots, df):
    ts_list = sorted(df["ts_event"].unique())
    interval = 60
    selected_ts = ts_list[::interval]
    selected_snapshots = [snap for snap, ts in zip(snapshots, ts_list) if ts in set(selected_ts)]

    total_cost = 0
    shares_left = ORDER_SIZE
    shares_per_trade = STEP

    for snapshot in selected_snapshots:
        if shares_left <= 0:
            break
        ask, ask_size, fee, rebate = snapshot[0]
        qty = min(shares_per_trade, ask_size, shares_left)
        total_cost += qty * (ask + fee)
        shares_left -= qty
    avg_price = total_cost / ORDER_SIZE
    return total_cost, avg_price

def baseline_vwap(snapshots):
    total_cost = 0
    shares_left = ORDER_SIZE
    for snapshot in snapshots:
        ask, ask_size, fee, rebate = snapshot[0]
        if ask_size <= 0:
            continue
        qty = min(ask_size, shares_left)
        total_cost += qty * (ask + fee)
        shares_left -= qty
        if shares_left <= 0:
            break
    avg_price = total_cost / ORDER_SIZE
    return total_cost, avg_price

def load_data(path):
    df = pd.read_csv(path)

    df = df.dropna(subset=["ask_px_00", "ask_sz_00"])
    df = df[df["ask_sz_00"] > 0]
    df = df.drop_duplicates(subset=["ts_event", "publisher_id"])
    df = df.sort_values("ts_event")

    snapshots = []
    for ts, group in df.groupby("ts_event"):
        venues = []
        for _, row in group.iterrows():
            venues.append([
                row["ask_px_00"],
                int(row["ask_sz_00"]),
                0.0,  # fee
                0.0   # rebate
            ])
        if venues:
            snapshots.append(venues)

    return snapshots, df


def get_cumulative_cost_series(strategy_fn, snapshots, *args):
    shares_left = ORDER_SIZE
    cumulative = []
    total_cost = 0

    for snapshot in snapshots:
        if shares_left <= 0:
            break

        venues = snapshot
        qty = 0
        cost = 0

        if strategy_fn == run_backtest:
            split, _ = allocate(shares_left, venues, *args)
            for i in range(len(venues)):
                ask, ask_size, fee, rebate = venues[i]
                exe = min(split[i], ask_size, shares_left)
                cost += exe * (ask + fee)
                shares_left -= exe
                if exe < split[i]:
                    cost -= (split[i] - exe) * rebate
        elif strategy_fn == baseline_best_ask:
            ask, ask_size, fee, rebate = snapshot[0]
            qty = min(STEP, ask_size, shares_left)
            cost = qty * (ask + fee)
            shares_left -= qty
        elif strategy_fn == baseline_vwap:
            ask, ask_size, fee, rebate = snapshot[0]
            qty = min(ask_size, shares_left)
            cost = qty * (ask + fee)
            shares_left -= qty
        elif strategy_fn == baseline_twap:
            ts_list = [snap[0] for snap in snapshots]
            index = snapshots.index(snapshot)
            if index % 60 != 0:
                cumulative.append(total_cost)
                continue
            ask, ask_size, fee, rebate = snapshot[0]
            qty = min(STEP, ask_size, shares_left)
            cost = qty * (ask + fee)
            shares_left -= qty

        total_cost += cost
        cumulative.append(total_cost)

    while len(cumulative) < len(snapshots):
        cumulative.append(total_cost)

    return cumulative




if __name__ == "__main__":
    snapshots, df = load_data("l1_day.csv")

    # grid research
    param_grid = [
        (λo, λu, θ)
        for λo in [0, 0.1, 0.5, 1, 2]
        for λu in [0, 0.1, 0.5, 1, 2]
        for θ in [0, 0.01, 0.1, 0.2]
    ]

    best_params = None
    best_cost = float("inf")
    best_avg_price = 0

    for λo, λu, θ in param_grid:
        cost, avg = run_backtest(snapshots, λo, λu, θ)
        if cost < best_cost:
            best_cost = cost
            best_avg_price = avg
            best_params = {
                "lambda_over": λo,
                "lambda_under": λu,
                "theta_queue": θ
            }

    best_ask_total, best_ask_avg = baseline_best_ask(snapshots)
    twap_total, twap_avg = baseline_twap(snapshots, df)
    vwap_total, vwap_avg = baseline_vwap(snapshots)


    result = {
        "best_parameters": best_params,
        "optimized_result": {
            "total_cash": round(best_cost, 2),
            "avg_price": round(best_avg_price, 3)
        },
        "baselines": {
            "best_ask": {
                "total_cash": round(best_ask_total, 2),
                "avg_price": round(best_ask_avg, 3)
            },
            "twap": {
                "total_cash": round(twap_total, 2),
                "avg_price": round(twap_avg, 3)
            },
            "vwap": {
                "total_cash": round(vwap_total, 2),
                "avg_price": round(vwap_avg, 3)
            }
        },
        "savings_bps": {
            "vs_best_ask": round(10000 * (best_ask_avg - best_avg_price) / best_ask_avg, 1),
            "vs_twap": round(10000 * (twap_avg - best_avg_price) / twap_avg, 1),
            "vs_vwap": round(10000 * (vwap_avg - best_avg_price) / vwap_avg, 1)
        }
    }
    
    print(json.dumps(result, indent=2))

tuned_curve = get_cumulative_cost_series(run_backtest, snapshots, *best_params.values())
best_ask_curve = get_cumulative_cost_series(baseline_best_ask, snapshots)
twap_curve = get_cumulative_cost_series(baseline_twap, snapshots)
vwap_curve = get_cumulative_cost_series(baseline_vwap, snapshots)

plt.figure(figsize=(10, 6))
plt.plot(tuned_curve, label='Tuned SOR', color='red', linewidth=2)
plt.plot(best_ask_curve, label='Best Ask', color='blue', linestyle='--')
plt.plot(twap_curve, label='TWAP', color='green', linestyle='-.')
plt.plot(vwap_curve, label='VWAP', color='purple', linestyle=':')

plt.xlabel("Snapshot Index")
plt.ylabel("Cumulative Spend ($)")
plt.title("Cumulative Execution Cost")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig("results.png")
