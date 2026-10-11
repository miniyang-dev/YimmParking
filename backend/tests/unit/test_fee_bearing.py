from __future__ import annotations

import pytest

from yimmparking.domain.fee import hourly_car_rate
from yimmparking.domain.geo import GeoPoint, initial_bearing_deg

ORIGIN = GeoPoint(25.0375, 121.5637)


class TestHourlyCarRate:
    # Strings below are copied from the live Taipei feed.
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("計時：小型車80元/時，停車全程以半小時計。停車未滿10分鐘不收費。", 80),
            ("小型車：計時 30元/時(09-18)，10元/時(18-09)，全程以半小時計；月租 全日4,200元", 30),
            (
                "小型車：計時 120元/時，停車未滿1小時以1小時計，逾1小時以上，未滿半小時以半小時計。",
                120,
            ),
            ("計時：小型車60元/時，大客車150元/時，停車未滿1小時以1小時計。", 60),
            (
                "計時：小型車(含大型重型機車)30元/時，停車全程以半小時計。月租：小型車全日7,200元/月。",
                30,
            ),
            ("計時：180元/時，停車全程以半小時計。月租：全日15,000元/月。", 180),
            # New Taipei style (no "/時"), copied from the live feed.
            ("小型車計時60元;", 60),
            ("小型車計時20元;小型車計時40元;小型車月租2200元;身障車月租1100元;機車免費;", 20),
            ("機車計時20元;小型車計時50元;小型車月租5000元;", 50),
        ],
    )
    def test_reads_the_first_car_rate(self, text: str, expected: int) -> None:
        assert hourly_car_rate(text) == expected

    def test_motorcycle_only_lot_has_no_car_rate(self) -> None:
        assert hourly_car_rate("機車：20元/次，隔日另計。") is None

    def test_motorcycle_rate_is_never_mistaken_for_car_rate(self) -> None:
        assert hourly_car_rate("機車20元/時；月租 全日5,000元") is None

    def test_new_taipei_motorcycle_only_is_unknown(self) -> None:
        assert hourly_car_rate("機車計時20元;機車月租1500元;") is None

    def test_monthly_only_text_is_unknown(self) -> None:
        assert hourly_car_rate("月租：小型車全日5,000元/月") is None

    def test_free_text_is_unknown_not_zero(self) -> None:
        assert hourly_car_rate("免費停車") is None
        assert hourly_car_rate("") is None


class TestBearing:
    def test_cardinal_directions(self) -> None:
        assert initial_bearing_deg(
            ORIGIN, GeoPoint(ORIGIN.lat + 0.01, ORIGIN.lng)
        ) == pytest.approx(0, abs=0.5)
        assert initial_bearing_deg(
            ORIGIN, GeoPoint(ORIGIN.lat, ORIGIN.lng + 0.01)
        ) == pytest.approx(90, abs=0.5)
        assert initial_bearing_deg(
            ORIGIN, GeoPoint(ORIGIN.lat - 0.01, ORIGIN.lng)
        ) == pytest.approx(180, abs=0.5)
        assert initial_bearing_deg(
            ORIGIN, GeoPoint(ORIGIN.lat, ORIGIN.lng - 0.01)
        ) == pytest.approx(270, abs=0.5)

    def test_result_is_always_in_range(self) -> None:
        for dlat in (-0.02, 0, 0.02):
            for dlng in (-0.02, 0.02):
                b = initial_bearing_deg(ORIGIN, GeoPoint(ORIGIN.lat + dlat, ORIGIN.lng + dlng))
                assert 0 <= b < 360
