GOLD_TAGS = {
    "geopolitical",
    "geopolitical_asia",
    "geopolitical_eu",
    "risk_off",
    "oil_gold",
}


def macro_note(tag):
    if not tag:
        return None
    if tag in GOLD_TAGS:
        return "🟡 XAU watch — potential geopolitical mover"
    if tag == "mil_logistics":
        return "🟠 Mil logistics — monitor for sustained pattern"
    return None
