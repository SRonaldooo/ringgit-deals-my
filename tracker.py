import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
import requests

# =====================================================================
# CONFIGURATION
# Phase 1: Uses CheapShark links (ToS-compliant while getting approved)
# Phase 2: Switch to "phase2_official" once GMG/Fanatical feeds are live
# =====================================================================
AFFILIATE_MODE = os.getenv("AFFILIATE_MODE", "phase1_cheapshark")
USER_AGENT = "RinggitDealsMY/1.0 (+https://github.com/yourusername/ringgit-deals-my)"
MIN_RINGGIT_SAVINGS_FOR_ALERT = 10.0  # Only ping Telegram/Discord if cheaper than Steam MY by >= RM10

# Affiliate IDs (Used only in Phase 2 with official retailer feeds)
GMG_IMPACT_BASE = os.getenv("GMG_IMPACT_BASE", "")       # e.g., https://greenmangaming.sjv.io/c/123456/123456/1234
FANATICAL_AWIN_ID = os.getenv("FANATICAL_AWIN_ID", "")   # e.g., your Awin publisher ID
HUMBLE_PARTNER_ID = os.getenv("HUMBLE_PARTNER_ID", "")   # e.g., ?partner=yourname

# Bot Credentials (Set in GitHub Secrets)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

DEALS_FILE = Path("deals.json")
POSTED_CACHE_FILE = Path("posted_deals.json")

STORE_NAMES = {
    "1": "Steam",
    "2": "GamersGate",
    "3": "Green Man Gaming",
    "7": "GOG",
    "11": "Humble Store",
    "15": "Fanatical",
    "25": "Epic Games Store",
}


def get_usd_to_myr_rate() -> float:
    """Fetches live USD->MYR exchange rate with a safe fallback."""
    try:
        resp = requests.get("https://open.er-api.com/v6/latest/USD", timeout=10)
        resp.raise_for_status()
        return float(resp.json()["rates"]["MYR"])
    except Exception as exc:
        print(f"[WARN] FX lookup failed ({exc}), using fallback 4.45")
        return 4.45


def get_steam_myr_price(steam_app_id: str) -> dict | None:
    """Queries official Steam Storefront API for Malaysia (MYR) pricing."""
    url = "https://store.steampowered.com/api/appdetails"
    params = {"appids": steam_app_id, "cc": "my", "filters": "price_overview"}
    try:
        resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=10)
        if resp.status_code == 429:
            print("[WARN] Steam rate limit hit; backing off 10s...")
            time.sleep(10)
            return None
        data = resp.json().get(str(steam_app_id), {})
        if not data.get("success") or not data.get("data"):
            return None
        po = data["data"].get("price_overview")
        if not po or po.get("currency") != "MYR":
            return None
        return {
            "steam_initial_myr": round(po["initial"] / 100.0, 2),
            "steam_final_myr": round(po["final"] / 100.0, 2),
            "steam_discount_pct": po["discount_percent"],
        }
    except Exception as exc:
        print(f"[WARN] Steam MYR lookup failed for {steam_app_id}: {exc}")
        return None


def build_official_affiliate_link(store_name: str, product_url: str) -> str:
    """Wraps official retailer product feed URLs in Phase 2."""
    if store_name == "Green Man Gaming" and GMG_IMPACT_BASE:
        return f"{GMG_IMPACT_BASE}?{urlencode({'u': product_url})}"
    if store_name == "Fanatical" and FANATICAL_AWIN_ID:
        return (
            f"https://www.awin1.com/cread.php?awinmid=17993"
            f"&awinaffid={FANATICAL_AWIN_ID}&{urlencode({'ued': product_url})}"
        )
    if store_name == "Humble Store" and HUMBLE_PARTNER_ID:
        sep = "&" if "?" in product_url else "?"
        return f"{product_url}{sep}partner={HUMBLE_PARTNER_ID}"
    return product_url


def fetch_phase1_deals(fx_rate: float) -> list[dict]:
    """Phase 1: Pulls discounted PC deals via CheapShark and compares with Steam MYR."""
    url = "https://www.cheapshark.com/api/1.0/deals"
    # Store IDs: 3=GreenManGaming, 11=Humble Store, 15=Fanatical
    params = {"storeID": "3,11,15", "onSale": "1", "pageSize": "25", "sortBy": "Deal Rating"}
    resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=15)
    resp.raise_for_status()
    raw_deals = resp.json()

    enriched = []
    for item in raw_deals:
        app_id = item.get("steamAppID")
        if not app_id:
            continue

        # Respect Steam's 200 req / 5 min limit
        time.sleep(0.5)
        steam_my = get_steam_myr_price(app_id)
        if not steam_my:
            continue

        sale_usd = float(item["salePrice"])
        est_deal_myr = round(sale_usd * fx_rate, 2)
        savings_vs_steam_my = round(steam_my["steam_final_myr"] - est_deal_myr, 2)
        store_name = STORE_NAMES.get(str(item["storeID"]), "Authorized Store")

        enriched.append({
            "id": item["dealID"],
            "title": item["title"],
            "steam_app_id": app_id,
            "store": store_name,
            "sale_usd": sale_usd,
            "est_deal_myr": est_deal_myr,
            "steam_myr": steam_my["steam_final_myr"],
            "steam_retail_myr": steam_my["steam_initial_myr"],
            "savings_vs_steam_myr": savings_vs_steam_my,
            "discount_pct": round(float(item["savings"])),
            "thumb": f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{app_id}/header.jpg",
            # Keep CheapShark redirect unmodified in Phase 1 per CheapShark ToS
            "url": f"https://www.cheapshark.com/redirect?dealID={item['dealID']}",
        })

    # Rank by biggest Ringgit savings against Steam Malaysia
    enriched.sort(key=lambda d: d["savings_vs_steam_myr"], reverse=True)
    return enriched


def load_official_feeds_stub(fx_rate: float) -> list[dict]:
    """
    Phase 2 Stub: Parse your approved GMG Impact Catalog API / Fanatical Awin CSV feed here,
    call get_steam_myr_price(app_id), and wrap URLs via build_official_affiliate_link().
    """
    raise NotImplementedError("Populate with your GMG Impact / Fanatical Awin feed credentials.")


def send_alerts(deals: list[dict]) -> None:
    """Pushes high-value MYR arbitrage deals to Telegram and Discord without duplicates."""
    posted: set[str] = set()
    if POSTED_CACHE_FILE.exists():
        posted = set(json.loads(POSTED_CACHE_FILE.read_text(encoding="utf-8")))

    new_posts = 0
    for deal in deals:
        unique_key = f"{deal['steam_app_id']}:{deal['store']}:{deal['sale_usd']}"
        if unique_key in posted or deal["savings_vs_steam_myr"] < MIN_RINGGIT_SAVINGS_FOR_ALERT:
            continue

        msg = (
            f"🔥 *{deal['title']}* ({deal['store']})\n"
            f"💰 Deal Price: *~RM {deal['est_deal_myr']:.2f}* (${deal['sale_usd']:.2f} USD)\n"
            f"🇲🇾 Steam Malaysia Right Now: RM {deal['steam_myr']:.2f}\n"
            f"✅ *Beats Steam MY by RM {deal['savings_vs_steam_myr']:.2f}*\n"
            f"🔗 Grab official Steam key: {deal['url']}\n"
            f"_(Official publisher-sourced key • Disclosure: partner link)_"
        )

        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
                timeout=10,
            )

        if DISCORD_WEBHOOK_URL:
            requests.post(
                DISCORD_WEBHOOK_URL,
                json={"content": msg.replace("*", "**")},
                timeout=10,
            )

        posted.add(unique_key)
        new_posts += 1
        if new_posts >= 5:  # Cap burst notifications per run
            break

    POSTED_CACHE_FILE.write_text(json.dumps(sorted(list(posted))[-500:], indent=2), encoding="utf-8")


def main() -> None:
    fx_rate = get_usd_to_myr_rate()
    deals = (
        fetch_phase1_deals(fx_rate)
        if AFFILIATE_MODE == "phase1_cheapshark"
        else load_official_feeds_stub(fx_rate)
    )

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "usd_to_myr": fx_rate,
        "deals": deals,
    }
    DEALS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[OK] Saved {len(deals)} deals to {DEALS_FILE} (1 USD = RM {fx_rate})")
    send_alerts(deals)


if __name__ == "__main__":
    main()

