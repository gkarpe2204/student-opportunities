from datetime import date

from tracker import sources

MLH = [{
    "id": "a", "name": "HackUMass", "startsAt": "2026-11-13T01:11:11Z", "endsAt": "2026-11-15T23:59:59Z",
    "url": "/events/hackumass/prizes", "location": "Amherst, Massachusetts", "formatType": "physical",
    "websiteUrl": "https://hackumass.com", "customFields": {"hackathon_focus": ["Software"]},
    "venueAddress": {"city": "Amherst", "state": "Massachusetts", "country": "US"},
}, {
    "id": "b", "name": "Global Hack Week", "startsAt": "2026-12-01T01:11:11Z", "endsAt": "2026-12-07T23:59:59Z",
    "url": "/events/ghw", "location": "Everywhere, Worldwide", "formatType": "digital", "websiteUrl": None,
    "customFields": {}, "venueAddress": {"city": "Everywhere", "state": "Worldwide", "country": "US"},
}]

DEVPOST = [{
    "title": "Cosmo Hacks 2026", "url": "https://cosmohacks.devpost.com/",
    "submission_period_dates": "Dec 19, 2026 - Jan 18, 2027",
    "displayed_location": {"icon": "globe", "location": "Online"},
    "themes": [{"name": "Beginner Friendly"}, {"name": "Open Ended"}, {"name": "Web"}],
    "prize_amount": "$<span data-currency-value>146,770</span>", "organization_name": "Cosmo Hacks",
}, {
    "title": "Secret Hack", "url": "https://x.devpost.com/", "submission_period_dates": "Jan 01 - 02, 2027",
    "displayed_location": {"icon": "map-marker", "location": "Boston, MA"}, "invite_only": True,
}]


def test_mlh_in_person_and_online():
    a, b = sources.mlh_events(MLH)
    assert (a.start, a.end, a.location, a.country, a.online) == (
        date(2026, 11, 13), date(2026, 11, 15), "Amherst, Massachusetts", "United States", False)
    assert a.category == "hackathon" and a.url == "https://hackumass.com" and "In-person" in a.topics
    assert b.online and b.location == "" and b.url == "https://www.mlh.com/events/ghw"


def test_devpost_dates_prize_and_invite_only_skipped():
    (c,) = sources.devpost_events(DEVPOST)
    assert (c.start, c.end, c.online) == (date(2026, 12, 19), date(2027, 1, 18), True)
    assert c.topics == ["Online", "Beginner Friendly", "Open Ended", "$146,770 in prizes"]


def test_devpost_place_from_maps_link():
    page = ('<div class="info">\n Invite only\n </div><a target="_blank" '
            'href="https://maps.google.com/?q=4480%202nd%20Ave%2C%20Sacramento%2C%20CA%2095817%2C%20USA">Aggie Square</a>')
    assert sources.devpost_place(page, "Aggie Square") == ("Sacramento, CA (Aggie Square)", True)
    assert sources.devpost_place("no map", "WPI - Campus Center") == ("WPI - Campus Center", False)
