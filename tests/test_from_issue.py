from datetime import date

import pytest
import yaml

from tracker.from_issue import Invalid, append_entry, build_entry, parse_form

BODY = """### Event name

HackBeanpot 2027

### Website

https://hackbeanpot.com

### Category

Hackathon

### Start date

2027-02-13

### End date

_No response_

### Location

Boston, MA

### Format

In-person

### Next deadline (registration, scholarship, abstracts)

2026-12-01

### What is that deadline for?

_No response_

### Does it fund students to attend? (travel grants, scholarships)

Travel stipends

### Topics (comma-separated)

Beginner friendly, Boston
"""


def test_parse_and_build():
    e = build_entry(parse_form(BODY), existing=[])
    assert e == {"name": "HackBeanpot 2027", "category": "hackathon", "url": "https://hackbeanpot.com",
                 "start": date(2027, 2, 13), "end": date(2027, 2, 13), "deadline": date(2026, 12, 1),
                 "location": "Boston, MA", "deadline_label": "Deadline", "funding": "Travel stipends",
                 "topics": ["In-person", "Beginner friendly", "Boston"]}


@pytest.mark.parametrize("change, msg", [
    ({"url": "javascript:alert(1)"}, "full link"),
    ({"category": "Something else"}, "category"),
    ({"start": "someday"}, "start date"),
])
def test_rejects_bad_input(change, msg):
    form = {**parse_form(BODY), **change}
    with pytest.raises(Invalid, match=msg):
        build_entry(form, existing=[])


def test_rejects_duplicates():
    with pytest.raises(Invalid, match="already on the list"):
        build_entry(parse_form(BODY), existing=[{"name": "HackBeanpot"}])


def test_append_keeps_yaml_valid(tmp_path):
    p = tmp_path / "w.yml"
    p.write_text("- name: A\n  url: https://a.org\n")
    append_entry(build_entry(parse_form(BODY), existing=[]), str(p))
    data = yaml.safe_load(p.read_text())
    assert [e["name"] for e in data] == ["A", "HackBeanpot 2027"]
