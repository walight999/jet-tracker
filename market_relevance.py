"""Market relevance classifier.

Three values: None / Indirect / Direct. Default is None — market
relevance must earn its place in the alert. The old auto-XAU tag is
explicitly retired.

"Direct" requires correlation with a real-time market-moving event
(news, sanctions, escalation). That data source does not exist in v1,
so Direct is unreachable here. Add it in v2 when source #2 is online.
"""


def classify(scoring_result, summary, meta):
    comp = scoring_result["components"]
    sens = comp["aircraft_sensitivity"]
    route = comp["route_anomaly"]
    cluster = comp["cluster_factor"]
    category = meta.get("category", "")

    if sens >= 2 and route >= 2:
        return {
            "relevance": "Indirect",
            "reason": "Sensitive aircraft active on a sensitive route.",
        }
    if cluster >= 2 and sens >= 2:
        return {
            "relevance": "Indirect",
            "reason": "Sensitive aircraft activity above recent baseline.",
        }
    if category == "sanctioned" and route >= 2:
        return {
            "relevance": "Indirect",
            "reason": "Sanctioned aircraft logistics on a sensitive route.",
        }
    return {"relevance": "None", "reason": None}
