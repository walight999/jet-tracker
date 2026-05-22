"""Impact scoring v1.

Pure functions. No I/O. Returns score + components so the alert can
explain itself instead of being a black box.

v1 components (cap 9):
  aircraft_sensitivity  0-3
  route_anomaly         0-3
  cluster_factor        0-3

Event correlation (4th component, cap 12) is deferred to v2 once a
second source (news/sanctions feed) is wired in.
"""

CATEGORY_SENSITIVITY = {
    "celebrity": 0,
    "billionaire": 1,
    "pia": 1,
    "politician": 2,
    "head_of_state": 2,
    "us_mil_isr": 2,
    "us_strategic": 3,
    "sanctioned": 3,
}

SENSITIVE_COUNTRIES = {
    "Iran", "Russia", "Ukraine", "Israel", "Palestine", "Syria",
    "North Korea", "Lebanon", "Yemen", "Libya", "Sudan", "Myanmar",
    "Belarus", "Iraq",
}


def aircraft_sensitivity(category):
    return CATEGORY_SENSITIVITY.get(category, 0)


def _matches_sensitive(place):
    if not place:
        return False
    return any(s in place for s in SENSITIVE_COUNTRIES)


def route_anomaly(started_over, currently_over, category):
    started_sensitive = _matches_sensitive(started_over)
    current_sensitive = _matches_sensitive(currently_over)

    if not started_sensitive and not current_sensitive:
        return 0
    if started_sensitive and current_sensitive:
        return 3
    score = 2
    if category == "sanctioned":
        score = 3
    return score


def cluster_factor(recent_alert_count):
    if recent_alert_count <= 2:
        return 0
    if recent_alert_count <= 4:
        return 1
    if recent_alert_count <= 7:
        return 2
    return 3


def level_for(score):
    if score <= 3:
        return "Low", "Log"
    if score <= 5:
        return "Medium", "Monitor"
    if score <= 7:
        return "High", "Alert"
    return "Critical", "Escalate"


def compute(meta, summary, recent_alert_count):
    category = meta.get("category", "")
    sens = aircraft_sensitivity(category)
    route = route_anomaly(
        summary.get("started_over"),
        summary.get("currently_over"),
        category,
    )
    cluster = cluster_factor(recent_alert_count)
    score = sens + route + cluster
    level, action = level_for(score)
    return {
        "score": score,
        "level": level,
        "action": action,
        "components": {
            "aircraft_sensitivity": sens,
            "route_anomaly": route,
            "cluster_factor": cluster,
        },
    }
