"""Lightweight insurance-domain gate before retrieval (guardrails)."""

from __future__ import annotations

import re

# Expanded keyword / pattern set for insurance + policy documents
_INSURANCE_TERMS = frozenset(
    {
        "insurance",
        "policy",
        "policies",
        "coverage",
        "cover",
        "covered",
        "claim",
        "claims",
        "premium",
        "premiums",
        "deductible",
        "copay",
        "co-pay",
        "coinsurance",
        "beneficiary",
        "beneficiaries",
        "underwriting",
        "exclusion",
        "exclusions",
        "endorsement",
        "rider",
        "liability",
        "umbrella",
        "term",
        "whole life",
        "annuity",
        "health",
        "dental",
        "vision",
        "disability",
        "long-term care",
        "ltc",
        "property",
        "casualty",
        "auto",
        "vehicle",
        "homeowners",
        "flood",
        "earthquake",
        "workers",
        "compensation",
        "malpractice",
        "e&o",
        "errors",
        "omissions",
        "actuary",
        "underwriter",
        "loss",
        "adjuster",
        "subrogation",
        "grace period",
        "lapse",
        "surrender",
        "rider",
        "sum insured",
        "sum assured",
        "limit",
        "limits",
    }
)

# Statute-style citations (e.g. §40-2-124, 33-24-46) — insurance code lookups
_STATUTE_CITE = re.compile(r"(?:§\s*)?(?:\d+[a-z]?)(?:-\d+[a-z]?)+", re.I)

# Questions that clearly reference the loaded docs / insurance workflow
_DOC_HINTS = re.compile(
    r"\b(this policy|the policy|my policy|the document|the pdf|coverage table|schedule of benefits|"
    r"what does (my|the) (policy|plan)|am i covered|is .+ covered)\b",
    re.I,
)


def is_insurance_domain(text: str) -> bool:
    t = text.strip().lower()
    if not t:
        return False
    if _STATUTE_CITE.search(text):
        return True
    if _DOC_HINTS.search(text):
        return True
    for term in _INSURANCE_TERMS:
        if term in t:
            return True
    # Short follow-ups in chat often omit keywords — allow "yes/no/what about/next" if prior context exists
    if len(t) < 80 and re.match(r"^(yes|no|ok|thanks|what about|and the|same for|continue)\b", t):
        return True
    return False
