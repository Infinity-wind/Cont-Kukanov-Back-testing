# Cont-Kukanov-Back-testing

This project implements and back-tests a Smart Order Router (SOR) based on the static cost model proposed by Cont & Kukanov in *"Optimal Order Placement in Limit Order Markets"*. The goal is to minimize the expected total cost of executing a 5000-share buy order across one or more venues.

## Overview

- **Allocator**: Follows exact pseudocode in `allocator_pseudocode.txt`, enumerating allocations in 100-share steps and choosing the one with the lowest penalized cost.
- **Data**: Based on `l1_day.csv`, a simulated feed from a single venue over a 9-minute period.
- **Cost Components**:
  - Execution price (`ask + fee`)
  - Rebate for non-executed shares
  - Penalty for underfill / overfill (`λ_under`, `λ_over`)
  - Queue-risk penalty (`θ_queue`)

## Code Structure

- `backtest.py`:
  - `load_data()` cleans and parses the market feed.
  - `allocate()` implements the enumerative split logic.
  - `run_backtest()` executes the order over time with rolling forward logic.
  - Baseline strategies implemented: **Best Ask**, **TWAP**, **VWAP**.
  - Outputs a single JSON summary to `stdout`.

## Parameter Search

We perform a grid search over:

```
lambda_over:   [0, 0.1, 0.5, 1, 2]
lambda_under:  0, 0.1, 0.5, 1, 2]
theta_queue:   [0, 0.01, 0.1, 0.2]
```

The best-performing parameter set was:
```json
{
  "lambda_over": 0,
  "lambda_under": 0,
  "theta_queue": 0.0
}
```

This set achieved a modest **3.6 basis point improvement** over the Best Ask and VWAP baselines, though **underperformed TWAP** by 2.9 bps, likely due to the lack of penalty terms or multiple venues.

## Suggested Improvement

The current implementation assumes:
- Instant execution up to displayed size
- No queueing or slippage dynamics

**To improve realism**, we suggest introducing:
- A **queue position model**: penalize orders that arrive late or behind larger resting orders
- **Simulated delay / latency**: e.g., apply a 1-2 second delay before fills are eligible
- **Market impact model**: include penalty for large instantaneous fills at thin books

Such enhancements would better reflect the advantages of intelligent venue selection and timing in real-world SORs.

## ✅ Run

Run with:
```bash
python backtest.py
```

This prints one summary JSON and optionally saves `results.png` (if plotting is added).