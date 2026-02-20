# Introduction

Monaimetrics is an opinionated, automated trading platform that applies a series of tried and tested investment rules to build and manage a growth focused portfolio. Users can adjust basic parameters but the majority of the work and decisions are automated to take advantage of 1) code's objectiveness as the models follow the rules and 2) the speed of automation, as the system can track and follow a large amount of news and data to assess trade viability.

The system includes comprehensive reporting to ensure the user is always aware of the portfolio's performance and the rationale for each trade. There is also a risk management / QAQC module to assess performance against benchmarks and aggregated indices.

---
# Intent

# Strategies

# Quick Set Up

Key to the functionality of the app are exertanl data sources and a trading platform. [Alpaca](https://alpaca.markets/) offers both with a simple pay as you go pricing system for API access. Add these credentials to the .env file. You default to a paper only account which the app will work with for testing and configuration.

_(Note that the APi keys can be 'hidden' towards the bottom of th Alpaca dashbord. Scroll down and look in the right hand info colum.)
_
```
/.env
# Alpaca Trading API (paper or live)
ALPACA_API_KEY=add_key_here
ALPACA_SECRET_KEY=add_secret_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets/v2

```

# Trivia

*The name Monaimetrics is a play on the original name of Jim Simon's first fund, 'Monemetrics'*
