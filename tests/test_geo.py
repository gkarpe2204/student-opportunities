from tracker.geo import country_of, region_of


def test_country_of():
    assert country_of("Boston, MA") == "United States"
    assert country_of("Austin, TX, U.S.A.") == "United States"
    assert country_of("Atlanta, Georgia") == "United States"
    assert country_of("Tbilisi, Georgia") == "Georgia"
    assert country_of("London, U.K.") == "United Kingdom"
    assert country_of("Hengqin, Zhuhai, China (Hybrid)") == "China"
    assert country_of("Whistler, BC, CANADA") == "Canada"
    assert country_of("", online=True) == "Online"
    assert country_of("") == "Location TBA"


def test_region_of():
    assert region_of("United States") == "North America"
    assert region_of("Germany") == "Europe"
    assert region_of("Online") == "Online"
