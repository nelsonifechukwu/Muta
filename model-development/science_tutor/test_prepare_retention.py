from prepare_retention import EXCLUDE, MANIFEST_SHA


def test_retention_known_judges_families_not_rehearsed():
    assert {"profit", "average_speed", "inheritance"} <= EXCLUDE
    assert len(MANIFEST_SHA) == 64
