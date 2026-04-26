"""Industry → underwriting risk proxies (NAICS-style buckets)."""

INDUSTRY_RISK = {
    "restaurant": 0.92,
    "retail": 0.55,
    "warehouse": 0.62,
    "office": 0.35,
    "manufacturing": 0.78,
    "other": 0.5,
}

INDUSTRY_LABELS = {
    "restaurant": "Restaurant / food service",
    "retail": "Retail",
    "warehouse": "Warehouse / distribution",
    "office": "Professional office",
    "manufacturing": "Manufacturing",
    "other": "General business",
}
