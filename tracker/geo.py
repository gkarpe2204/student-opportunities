"""Turn free-text locations ("Boston, MA", "Hengqin, China (Hybrid)") into a country and region."""
from __future__ import annotations

import re

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico",
}
_US_NAMES = {v.lower() for v in US_STATES.values()} - {"georgia"}  # Georgia is also a country
CA_PROVINCES = {"ontario", "quebec", "british columbia", "alberta", "manitoba", "nova scotia",
                "new brunswick", "saskatchewan", "newfoundland", "prince edward island"}

ALIASES = {
    "usa": "United States", "u.s.a.": "United States", "u.s.a": "United States", "u.k": "United Kingdom", "us": "United States", "u.s.": "United States",
    "united states": "United States", "united state": "United States",
    "united states of america": "United States", "america": "United States",
    "uk": "United Kingdom", "u.k.": "United Kingdom", "england": "United Kingdom",
    "scotland": "United Kingdom", "wales": "United Kingdom", "northern ireland": "United Kingdom",
    "great britain": "United Kingdom",
    "the netherlands": "Netherlands", "holland": "Netherlands",
    "republic of korea": "South Korea", "korea": "South Korea", "korea, south": "South Korea",
    "czechia": "Czech Republic", "uae": "United Arab Emirates", "türkiye": "Turkey",
    "hong kong sar": "Hong Kong", "hong kong": "Hong Kong", "macau": "Macau", "macao": "Macau",
    "prc": "China", "mainland china": "China", "viet nam": "Vietnam",
    "mexico city": "Mexico", "canada": "Canada",
}

REGIONS = {
    "North America": {"United States", "Canada", "Mexico"},
    "Latin America & Caribbean": {"Brazil", "Argentina", "Chile", "Colombia", "Peru", "Uruguay",
                                  "Panama", "Costa Rica", "Barbados", "Puerto Rico", "Ecuador",
                                  "Dominican Republic", "Jamaica", "Bahamas", "Cuba"},
    "Europe": {"United Kingdom", "Ireland", "Germany", "France", "Netherlands", "Belgium",
               "Luxembourg", "Switzerland", "Austria", "Italy", "Spain", "Portugal", "Greece",
               "Cyprus", "Malta", "Denmark", "Sweden", "Norway", "Finland", "Iceland", "Estonia",
               "Latvia", "Lithuania", "Poland", "Czech Republic", "Slovakia", "Hungary", "Slovenia",
               "Croatia", "Serbia", "Bosnia and Herzegovina", "Montenegro", "North Macedonia",
               "Albania", "Romania", "Bulgaria", "Moldova", "Ukraine", "Turkey", "Georgia",
               "Armenia", "Monaco"},
    "Asia": {"China", "Hong Kong", "Macau", "Taiwan", "Japan", "South Korea", "Singapore",
             "Malaysia", "Thailand", "Vietnam", "Indonesia", "Philippines", "Cambodia", "India",
             "Nepal", "Sri Lanka", "Bangladesh", "Pakistan", "Kazakhstan", "Mongolia"},
    "Middle East & Africa": {"United Arab Emirates", "Saudi Arabia", "Qatar", "Israel", "Jordan",
                             "Egypt", "Morocco", "Tunisia", "South Africa", "Nigeria", "Kenya",
                             "Rwanda", "Ghana", "Ethiopia", "Oman", "Bahrain", "Kuwait", "Lebanon",
                             "Iran"},
    "Oceania": {"Australia", "New Zealand", "Fiji"},
}
_REGION_OF = {c: r for r, cs in REGIONS.items() for c in cs}
ONLINE, UNKNOWN = "Online", "Location TBA"
REGION_ORDER = list(REGIONS) + [ONLINE, UNKNOWN]


def _clean(part: str) -> str:
    return re.sub(r"\s+", " ", part).strip(" .")


def country_of(location: str, online: bool = False, hint: str = "") -> str:
    """Best-effort country name; ONLINE for virtual-only events, UNKNOWN when we can't tell."""
    for raw in (hint, location):
        if not raw:
            continue
        text = re.sub(r"\(.*?\)", "", raw)
        text = re.split(r"\s+(?:and|/|&)\s+online", text, flags=re.I)[0]
        parts = [_clean(p) for p in re.split(r"[,/]", text) if _clean(p)]
        if not parts:
            continue
        for part in reversed(parts):
            low = part.lower()
            if low in ("online", "virtual", "remote"):
                continue
            if low in ("tbd", "tba"):
                break
            if low in ALIASES:
                return ALIASES[low]
            if part.upper() in US_STATES and len(part) == 2:
                return "United States"
            if low == "georgia":    # the US state far more often than the country
                return "Georgia" if any(p.lower() in ("tbilisi", "batumi") for p in parts) else "United States"
            if low in _US_NAMES:
                return "United States"
            if low in CA_PROVINCES:
                return "Canada"
            if part in _REGION_OF:
                return part
            title = part.title()
            if title in _REGION_OF:
                return title
            if len(parts) > 1:      # unknown last token: accept as a country name
                return part
    if online or re.search(r"\b(online|virtual)\b", location or "", re.I):
        return ONLINE
    return UNKNOWN


def region_of(country: str) -> str:
    if country in (ONLINE, UNKNOWN):
        return country
    return _REGION_OF.get(country, "Other")
