# 🇲🇾 RinggitDeals MY — Automated PC Game Regional Price Arbitrage Tracker

**Live Storefront:** [https://sronaldooo.github.io/ringgit-deals-my/](https://sronaldooo.github.io/ringgit-deals-my/)

RinggitDeals MY is a serverless Python + GitHub Actions data pipeline and static web app that helps Malaysian PC gamers identify when global USD sales from **authorized publisher-sourced retailers** (Green Man Gaming, Fanatical, Humble Store) beat **Steam Malaysia's regional MYR pricing**.

## ⚙️ Architecture & Engineering Highlights

* **Zero-Cost Serverless Pipeline:** Scheduled GitHub Actions cron job (`0 */6 * * *`) executes `tracker.py`, persists JSON state directly to the repository, and deploys automatically via GitHub Pages at RM0/month infrastructure cost.
* **Live MYR Regional Arbitrage Engine:** Queries live `USD -> MYR` exchange rates alongside Valve's official `store.steampowered.com/api/appdetails?cc=my` endpoint (with rate-limit backoff) to compute exact Ringgit savings over local Steam pricing.
* **Idempotent Multi-Channel Alerting:** Pushes rich cover-art banners via the Telegram Bot `sendPhoto` API (with automatic graceful fallback to HTML `sendMessage` and rolling 500-item deduplication cache in `posted_deals.json`) plus Discord embed webhooks.
* **Two-Phase Compliance Design:** Respects aggregator redirect rules in Phase 1 while providing modular URL builders for approved official retailer data feeds (Impact / Awin) in Phase 2.

## 🚀 Local Quickstart

```bash
pip install requests
python tracker.py
python -m http.server 8000
