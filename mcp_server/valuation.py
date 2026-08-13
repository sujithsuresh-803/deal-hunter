"""Best-value engine.

For a product offer on one platform, evaluate every payment card against the
best available coupon and rank by *net effective price* — what you actually end
up out of pocket after coupon + instant bank discount + reward value.

Stacking model (typical for Indian e-commerce):
    subtotal        = listed price
    - coupon        (best single coupon, auto/coded)
    = after_coupon
    - instant       (card instant discount, applied on the post-coupon amount)
    = amount_charged (what hits the card)
    - reward_value  (cashback / redeemable points on amount_charged)
    = net_effective
"""
from __future__ import annotations

from .models import CardOffer, Coupon, ProductOffer


def _best_coupon(price: float, coupons: list[Coupon]) -> tuple[Coupon | None, float]:
    best: Coupon | None = None
    best_d = 0.0
    for c in coupons:
        d = c.discount_on(price)
        if d > best_d:
            best, best_d = c, d
    return best, best_d


def evaluate_offer(
    offer: ProductOffer, coupons: list[Coupon], cards: list[CardOffer]
) -> dict:
    """Rank payment options for a single platform offer."""
    if offer.price is None:
        return {"platform": offer.platform, "error": "no price available"}

    price = offer.price
    coupon, coupon_d = _best_coupon(price, coupons)
    after_coupon = round(price - coupon_d, 2)

    options: list[dict] = []

    # Baseline: pay with a card that has no offers here (or cash).
    options.append(
        {
            "card": "None / generic card",
            "coupon": coupon.code if coupon else None,
            "coupon_discount": coupon_d,
            "instant_discount": 0.0,
            "amount_charged": after_coupon,
            "reward_value": 0.0,
            "net_effective": after_coupon,
        }
    )

    for card in cards:
        instant = card.instant_discount_on(offer.platform, after_coupon)
        amount_charged = round(after_coupon - instant, 2)
        reward = card.reward_value_on(amount_charged)
        net = round(amount_charged - reward, 2)
        options.append(
            {
                "card": card.name,
                "network": card.network,
                "coupon": coupon.code if coupon else None,
                "coupon_discount": coupon_d,
                "instant_discount": instant,
                "amount_charged": amount_charged,
                "reward_value": reward,
                "net_effective": net,
            }
        )

    options.sort(key=lambda o: o["net_effective"])
    best = options[0]
    return {
        "platform": offer.platform,
        "title": offer.title,
        "url": offer.url,
        "listed_price": price,
        "best_option": best,
        "total_savings": round(price - best["net_effective"], 2),
        "all_options": options,
    }


def best_across_platforms(evaluations: list[dict]) -> dict | None:
    """Given per-platform evaluations, pick the globally cheapest net price."""
    priced = [e for e in evaluations if "best_option" in e]
    if not priced:
        return None
    winner = min(priced, key=lambda e: e["best_option"]["net_effective"])
    return {
        "platform": winner["platform"],
        "title": winner["title"],
        "url": winner["url"],
        "listed_price": winner["listed_price"],
        "pay_with": winner["best_option"]["card"],
        "coupon": winner["best_option"]["coupon"],
        "net_effective_price": winner["best_option"]["net_effective"],
        "total_savings": winner["total_savings"],
    }
