"""Tests for the CPGRAMS profile scraping (app/rpa/submitter + API model)."""

import pytest

from app.api.cpgrams import ProfileResponse
from app.rpa.submitter import CPGRAMSSubmitter
from app.rpa.selectors import SELECTORS


class FakeLocator:
    def __init__(self, value: str = "", count: int = 1, values: list[str] | None = None):
        self._value = value
        self._count = count
        self._values = values

    @property
    def first(self) -> "FakeLocator":
        return self

    def count(self) -> int:
        return self._count

    def input_value(self) -> str:
        return self._value

    def get_attribute(self, _name: str) -> str:
        return self._value

    def inner_text(self) -> str:
        return self._value

    def all_input_values(self) -> list[str]:
        return self._values or ([""] * self._count if self._count else [])


class FakePage:
    def __init__(self, values: dict[str, str]):
        self._values = values

    def locator(self, sel: str) -> FakeLocator:
        if sel.startswith(SELECTORS["profile_state_select"]):
            v = self._values.get("state", "")
            if "option" in sel:
                return FakeLocator(value="Uttar Pradesh" if v == "UP" else "", count=1)
            return FakeLocator(value=v, count=1)
        if sel.startswith(SELECTORS["profile_district_select"]):
            v = self._values.get("district", "")
            if "option" in sel:
                return FakeLocator(value="Sitapur" if v == "333" else "", count=1)
            return FakeLocator(value=v, count=1)
        if sel.startswith(SELECTORS["profile_country_select"]):
            v = self._values.get("country", "")
            if "option" in sel:
                return FakeLocator(value="India" if v == "001" else "", count=1)
            return FakeLocator(value=v, count=1)
        if sel == SELECTORS["profile_address_inputs"]:
            return FakeLocator(count=len(self._values.get("addresses", [])),
                               values=self._values.get("addresses", []))
        if sel == SELECTORS["profile_gender_radio"]:
            return FakeLocator(count=0)
        if ":checked" in sel:
            return FakeLocator(count=0)
        return FakeLocator(value=self._values.get("name", ""), count=1)


@pytest.mark.asyncio
async def test_scrape_profile_reads_fields():
    submitter = CPGRAMSSubmitter()
    page = FakePage({
        "name": "Ram Kumar",
        "gender": "",
        "state": "UP",
        "district": "333",
        "country": "001",
        "addresses": ["Premise 12", "Sector 5"],
        "pincode": "261001",
    })

    profile = await submitter._scrape_profile(page)  # noqa: SLF001
    assert profile["name"] == "Ram Kumar"
    assert profile["state"] == "Uttar Pradesh"
    assert profile["district"] == "Sitapur"
    assert profile["country"] == "India"
    assert profile["address_lines"] == ["Premise 12", "Sector 5"]


@pytest.mark.asyncio
async def test_scrape_profile_missing_fields_are_empty():
    submitter = CPGRAMSSubmitter()
    page = FakePage({})
    profile = await submitter._scrape_profile(page)  # noqa: SLF001
    assert profile["name"] == ""
    assert profile["state"] == ""
    assert profile["district"] == ""
    assert profile["address_lines"] == []


def test_profile_response_model_roundtrip():
    resp = ProfileResponse(
        account_key="mobile-9876543210",
        name="Ram Kumar",
        email="ram@example.com",
        mobile="9876543210",
        address_lines=["Premise 12", "Sector 5"],
        state="Uttar Pradesh",
        district="Sitapur",
        pincode="261001",
    )
    data = resp.model_dump()
    assert data["account_key"] == "mobile-9876543210"
    assert data["address_lines"] == ["Premise 12", "Sector 5"]