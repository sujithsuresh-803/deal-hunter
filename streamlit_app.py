"""Deal Hunter — Streamlit front-end.

A second front door onto the same engine that powers the FastAPI app and the MCP
agent. It imports `run_pipeline` directly (no HTTP, no LLM) so it deploys as a
single-file Streamlit app with zero extra services.

Run locally:   streamlit run streamlit_app.py
Deploy:        push to GitHub, then Streamlit Community Cloud → New app → this file.
"""
from __future__ import annotations

import re

import streamlit as st

from mcp_server.cards import load_cards
from mcp_server.pipeline import run_pipeline

st.set_page_config(page_title="Deal Hunter", page_icon="🛒", layout="centered")


def inr(x) -> str:
    """Format a number as ₹ with Indian digit grouping (₹1,23,499)."""
    if x is None:
        return "—"
    n = int(round(float(x)))
    s = str(abs(n))
    if len(s) > 3:
        last3, rest = s[-3:], s[:-3]
        rest = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", rest)
        s = f"{rest},{last3}"
    return f"₹{'-' if n < 0 else ''}{s}"


# ---------------- header ----------------
st.title("🛒 Deal Hunter")
st.caption(
    "The **true price** of a purchase — after the best coupon and the cards you "
    "already own. Compares Amazon.in, Flipkart & HP India."
)

cards = load_cards()
name_to_id = {c.name: c.id for c in cards}

# ---------------- input form ----------------
with st.form("deal"):
    query = st.text_input("Product", placeholder="e.g. HP Victus gaming laptop")
    picked = st.multiselect(
        "Which cards do you own?  (optional — leave empty to consider all)",
        options=list(name_to_id.keys()),
        help="Bank offers stack on top of coupons. Selecting your cards shows your "
        "real out-of-pocket price.",
    )
    submitted = st.form_submit_button("Find the deal", type="primary")

# ---------------- results ----------------
if submitted:
    if not query.strip():
        st.warning("Enter a product to search for.")
        st.stop()

    owned = [name_to_id[n] for n in picked] or None
    with st.spinner("Scraping platforms, matching, stacking coupons & cards…"):
        data = run_pipeline(query, owned_card_ids=owned)

    rec = data["recommended"]
    priced = [p for p in data["per_platform"] if p.get("best_option")]
    conf = round(data["match"]["same_product_confidence"] * 100)

    # status line
    c1, c2, c3 = st.columns(3)
    if data["source"] == "live":
        c1.success("● Live prices")
    else:
        c1.warning("● Sample data")
    c2.info(f"Match: {conf}%")
    c3.info(f"{len(priced)} platforms")

    if not rec:
        st.error("No priced listings found. Try a more specific product name.")
        st.stop()

    # winner
    st.subheader(f"Best deal · {rec['platform'].title()}")
    st.write(rec["title"])

    savings = rec["total_savings"]
    save_pct = round(savings / rec["listed_price"] * 100) if rec["listed_price"] else 0
    m1, m2 = st.columns([1, 1])
    m1.metric("Net effective price", inr(rec["net_effective_price"]),
              delta=f"-{inr(savings)} ({save_pct}%)", delta_color="inverse")
    pay = f"**{rec['pay_with']}**"
    if rec.get("coupon"):
        pay += f"  ·  coupon **{rec['coupon']}**"
    m2.markdown(f"Pay with\n\n{pay}")

    # the math
    win = next((p for p in priced if p["platform"] == rec["platform"]), None)
    if win:
        o = win["best_option"]
        st.markdown("**How the price breaks down**")
        b1, b2, b3, b4, b5 = st.columns(5)
        b1.metric("Listed", inr(win["listed_price"]))
        b2.metric("− Coupon", inr(o["coupon_discount"]))
        b3.metric("− Instant", inr(o["instant_discount"]))
        b4.metric("− Reward", inr(o["reward_value"]))
        b5.metric("= Net", inr(o["net_effective"]))

    st.link_button(f"View on {rec['platform'].title()} →", rec["url"])

    # comparison table
    st.markdown("**All platforms compared**")
    rows = []
    for p in sorted(priced, key=lambda x: x["best_option"]["net_effective"]):
        o = p["best_option"]
        rows.append({
            "Platform": p["platform"].title(),
            "Listed": inr(p["listed_price"]),
            "Best card": o["card"],
            "Coupon": o["coupon"] or "—",
            "Net price": inr(o["net_effective"]),
            "You save": inr(p["total_savings"]),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)

st.divider()
st.caption(
    "Prototype · prices scraped best-effort, sample data shown when a site blocks "
    "the scraper · not financial advice"
)
