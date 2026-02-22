# Monaimetrics

An opinionated, automated trading platform that applies a series of tried and tested investment rules to build and manage a growth-focused portfolio. The system scores stocks through multiple frameworks (Stage Analysis, CANSLIM, Magic Formula, Event Cascade, Asymmetry), sizes positions via Kelly criterion, and manages risk with layered stop-losses, trailing stops, and circuit breakers.

Includes prediction market arbitrage (Kalshi) and an AI-powered research mode for answering technical questions about holdings and strategy.

---

## Setup

### 1. Install dependencies

```bash
pip install -e .
```

### 2. Configure environment variables

Create a `.env` file in the project root:

```bash
# Alpaca Trading API (required)
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets/v2

# Research mode (optional — powers the AI search feature)
GROQ_API_KEY=your_groq_key

# Prediction market arbitrage (optional)
KALSHI_API_KEY=your_kalshi_key
KALSHI_PRIVATE_KEY_PEM="-----BEGIN EC PRIVATE KEY-----\n...\n-----END EC PRIVATE KEY-----"
KALSHI_USE_DEMO=true
ARB_DRY_RUN=true

# Alpha signals API auth (optional — see Alpha Signals section below)
DECIS_API_KEY=your_key
DECIS_BASE_URL=https://api.example.com
```

You default to a paper-only Alpaca account, which the app works with for testing and configuration.

> **Note:** Alpaca API keys can be found towards the bottom of the Alpaca dashboard. Scroll down and look in the right-hand info column.

### 3. Run the dashboard

```bash
python -m monaimetrics.cli
```

The dashboard offers: portfolio summary, activity report, growth report, and a trade planning mode that runs the full assessment cycle.

---

## Alpha Signals

Alpha signals let external data feeds (APIs, indices, gauges) influence trade scoring. The system is configured entirely through `alpha_signals.yaml` — no code changes needed to add or remove data sources.

### How it works

1. A **signal** is a single API source, fetched once and normalized to a value between -1.0 and +1.0
2. Each signal has one or more **effects** that route that value to specific trade types (sectors/industries)
3. Effects specify **polarity**: `bull` keeps the signal's sign, `bear` flips it

This means one real-world event can have opposite impacts on different sectors:

```
Country stability drops -> normalized to -1.0
  -> "bull" effect on financials:  -1.0 kept   -> confidence drops (bad for banks)
  -> "bear" effect on energy:      -1.0 flipped -> confidence rises (good for oil)
```

### Enable alpha signals

Alpha signals are **disabled by default**. To enable, set `enabled: true` in the `AlphaSignalsConfig` in `config.py` (or wire it to an env var).

### Configure `alpha_signals.yaml`

The file lives at the project root. Each signal needs:

```yaml
signals:
  - id: "unique_id"                    # Identifier for caching
    name: "Human-readable name"
    source:
      type: "rest_api"
      url_template: "https://api.example.com/data"  # Use {base_url} for env-configured hosts
      auth_env_var: "YOUR_API_KEY_ENV_VAR"           # Reads this env var, sends as Bearer token
      response_path: "data.nested.value"             # Dot-path to extract the number from JSON
    normalization:
      method: "range"                  # "range", "zscore", or "threshold"
      min_value: 0                     # For range: maps min->-1.0, max->+1.0
      max_value: 100
      invert: false                    # true flips the normalized value
    ttl_minutes: 60                    # How long to cache before re-fetching

    effects:
      - name: "What this effect does"
        polarity: "bull"               # "bull" = positive signal helps, "bear" = flips sign
        trade_types: ["energy", "oil"] # Which sectors this applies to, or ["all"]
        weight: 1.0                    # Multiplier (0.0-1.0)
        max_adjustment: 10.0           # Max confidence points this effect can add/remove
        apply_to: "both"              # "buy", "sell", or "both"
```

**Normalization methods:**

| Method | Parameters | Behavior |
|---|---|---|
| `range` | `min_value`, `max_value` | Linear map: min -> -1.0, max -> +1.0 |
| `zscore` | `mean`, `std` | Z-score clamped to [-1.0, +1.0] |
| `threshold` | `threshold` | Binary: >= threshold -> +1.0, below -> -1.0 |

All methods support `invert: true` to flip the result.

### Trade type resolution

The system auto-detects each symbol's sector from Alpaca. To override or add custom categories (e.g., "shipping", "defense"), add a `trade_types` section:

```yaml
trade_types:
  XOM: ["energy", "oil"]
  LMT: ["defense", "industrials"]
  MAERSK: ["shipping", "logistics"]
```

Manual entries merge with auto-detected values.

### Limits

- Each effect is capped at its `max_adjustment` (points)
- Total alpha adjustment across all effects is capped at `global_max_adjustment` (default: 15 points)
- On the sell side, alpha only triggers a sell when the adjustment is strongly negative (<= -10 pts) and no other sell signals are active

---

## Research Mode

The web interface includes an AI-powered search that answers technical questions about the codebase, strategies, and holdings. It uses Groq and reference documents stored in `_developer/*.md`. Set `GROQ_API_KEY` in your `.env` to enable it.

---

## Running Tests

```bash
pytest tests/
```

All tests use constructed data — no API keys or live connections required.

---

*The name Monaimetrics is a play on the original name of Jim Simons's first fund, "Monemetrics."*
