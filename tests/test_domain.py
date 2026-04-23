from app.guards.domain import is_insurance_domain


def test_insurance_keywords():
    assert is_insurance_domain("What is my annual premium for this policy?")
    assert is_insurance_domain("Is flood damage covered under the plan?")


def test_rejects_unrelated_without_keywords():
    assert not is_insurance_domain("Write a python quicksort")


def test_doc_hints():
    assert is_insurance_domain("Does this policy cover rental cars?")
