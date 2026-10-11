from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from yimmparking.domain.brand import BrandClassifier
from yimmparking.domain.geo import GeoPoint, bounding_box, haversine_m, twd97_to_wgs84
from yimmparking.domain.iparking import match_iparking
from yimmparking.domain.model import (
    Availability,
    Brand,
    BrandEvidence,
    City,
    Freshness,
    FreshnessPolicy,
    IParkingStation,
    ParkingLot,
    RouteTime,
)
from yimmparking.domain.ranking import (
    Block,
    Candidate,
    Pool,
    RankingPolicy,
    SortMode,
    arrange,
    pool_within_radius,
    shortlist,
)
from yimmparking.domain.vendor import Preference, Vendor, VendorPick, vendor_of

ORIGIN = GeoPoint(25.0330, 121.5654)


def make_lot(
    source_id: str,
    *,
    name: str = "某某停車場",
    brand: Brand = Brand.OTHER,
    iparking: str | None = None,
    at: GeoPoint = ORIGIN,
    phone: str = "",
    total_car: int | None = 100,
) -> ParkingLot:
    return ParkingLot(
        id=f"taipei:{source_id}",
        city=City.TAIPEI,
        source_id=source_id,
        name=name,
        address="",
        district="",
        location=at,
        phone=phone,
        total_car=total_car,
        brand=brand,
        iparking_code=iparking,
    )


class TestGeo:
    def test_haversine_known_distance(self) -> None:
        # Taipei 101 → Taipei Main Station is roughly 6.5 km.
        d = haversine_m(GeoPoint(25.0340, 121.5645), GeoPoint(25.0478, 121.5170))
        assert 5_000 < d < 5_800

    def test_twd97_matches_published_entrance_coordinate(self) -> None:
        # TPE0002 世貿一館: TWD97 (306711.6088, 2769568.898); entrance listed at 25.0331, 121.5622.
        p = twd97_to_wgs84(306711.6088, 2769568.898)
        assert haversine_m(p, GeoPoint(25.0331, 121.5622)) < 40

    def test_bounding_box_contains_circle(self) -> None:
        box = bounding_box(ORIGIN, 1000)
        east = GeoPoint(ORIGIN.lat, ORIGIN.lng + 0.0099)  # ~1 km east at this latitude
        assert box.min_lng < east.lng < box.max_lng
        assert box.min_lat < ORIGIN.lat < box.max_lat

    def test_geopoint_rejects_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            GeoPoint(95.0, 0.0)


class TestAvailability:
    now = datetime(2026, 10, 10, 14, 0, tzinfo=UTC)

    @pytest.mark.parametrize("raw", [-9, -1, None])
    def test_sentinel_and_missing_are_unknown_not_zero(self, raw: int | None) -> None:
        a = Availability.from_reading(raw, 100, self.now)
        assert a.count is None
        assert not a.is_known

    def test_zero_is_a_real_reading(self) -> None:
        a = Availability.from_reading(0, 100, self.now)
        assert a.is_known
        assert a.count == 0

    def test_over_capacity_is_kept_but_flagged(self) -> None:
        a = Availability.from_reading(263, 209, self.now)
        assert a.count == 263
        assert a.suspect

    def test_unknown_total_is_not_suspect(self) -> None:
        assert not Availability.from_reading(10, None, self.now).suspect

    def test_freshness_thresholds(self) -> None:
        policy = FreshnessPolicy(fresh_s=900, expire_s=3600)
        assert policy.classify(self.now - timedelta(minutes=7), self.now) is Freshness.FRESH
        assert policy.classify(self.now - timedelta(minutes=30), self.now) is Freshness.STALE
        assert policy.classify(self.now - timedelta(hours=3), self.now) is Freshness.EXPIRED
        assert policy.classify(None, self.now) is Freshness.UNKNOWN


class TestBrandClassifier:
    c = BrandClassifier()

    def test_name_match(self) -> None:
        assert self.c.classify("嘟嘟房世貿一館站停車場", "") == (Brand.DODOHOME, BrandEvidence.NAME)
        assert self.c.classify("台灣聯通長春停車場", "") == (Brand.LIANTONG, BrandEvidence.NAME)

    @pytest.mark.parametrize("phone", ["0226550818", "26550818", "02-2655-0818", "(02)26550818"])
    def test_phone_match_for_dodohome_in_any_written_form(self, phone: str) -> None:
        assert self.c.classify("中山堂地下停車場", phone) == (Brand.DODOHOME, BrandEvidence.PHONE)

    @pytest.mark.parametrize("phone", ["25235000", "0225235000", "252350001138"])
    def test_phone_match_for_liantong_including_extension(self, phone: str) -> None:
        assert self.c.classify("光武停車場", phone) == (Brand.LIANTONG, BrandEvidence.PHONE)

    def test_name_outranks_phone(self) -> None:
        # Carries 台灣聯通's phone but is named 嘟嘟房: the name decides.
        assert self.c.classify("嘟嘟房某站", "25235000") == (Brand.DODOHOME, BrandEvidence.NAME)

    def test_unrelated_lot_is_other(self) -> None:
        assert self.c.classify("市府地下停車場", "0227593000") == (Brand.OTHER, BrandEvidence.NONE)

    def test_longer_number_ending_in_same_digits_is_not_a_match(self) -> None:
        # A different number that merely ends with the same eight digits must not match.
        assert self.c.classify("某停車場", "0327550818") == (Brand.OTHER, BrandEvidence.NONE)


def cand(
    source_id: str, distance: float, *, brand: Brand = Brand.OTHER, iparking: str | None = None
) -> Candidate:
    return Candidate(make_lot(source_id, brand=brand, iparking=iparking), distance)


def pref(*shows: tuple[Vendor, int]) -> Preference:
    return Preference.from_picks(VendorPick(vendor, show) for vendor, show in shows)


def _brands() -> list[tuple[Vendor, Brand]]:
    return [
        (Vendor.IPARKING_DODOHOME, Brand.DODOHOME),
        (Vendor.DODOHOME, Brand.DODOHOME),
        (Vendor.LIANTONG, Brand.LIANTONG),
        (Vendor.TIMES, Brand.TIMES),
        (Vendor.USPACE, Brand.USPACE),
    ]


class TestVendorOf:
    @pytest.mark.parametrize(
        ("lot", "expected"),
        [
            (make_lot("a", brand=Brand.DODOHOME, iparking="DDHTPC001"), Vendor.IPARKING_DODOHOME),
            (make_lot("b", brand=Brand.DODOHOME), Vendor.DODOHOME),
            (make_lot("c", brand=Brand.LIANTONG), Vendor.LIANTONG),
            (make_lot("d", brand=Brand.TIMES), Vendor.TIMES),
            (make_lot("e", brand=Brand.USPACE), Vendor.USPACE),
            (make_lot("f"), None),
            # An iParking code on a lot that is not 嘟嘟房 gives it no vendor.
            (make_lot("g", brand=Brand.OTHER, iparking="DDHTPC001"), None),
        ],
    )
    def test_vendor_of(self, lot: ParkingLot, expected: Vendor | None) -> None:
        assert vendor_of(lot) is expected

    def test_times_and_uspace_are_recognised_by_name(self) -> None:
        c = BrandClassifier()
        assert c.classify("Times 內湖路一段", "") == (Brand.TIMES, BrandEvidence.NAME)
        assert c.classify("USPACE晶華酒店附設停車場", "") == (Brand.USPACE, BrandEvidence.NAME)


class TestPreference:
    def test_default_lists_every_vendor_in_declaration_order_showing_two(self) -> None:
        prefs = Preference()
        assert [p.vendor for p in prefs.picks] == list(Vendor)
        assert all(p.show == 2 for p in prefs.picks)

    def test_listed_vendors_come_first_and_the_rest_show_nothing(self) -> None:
        prefs = pref((Vendor.USPACE, 3), (Vendor.LIANTONG, 1))
        assert [p.vendor for p in prefs.picks][:2] == [Vendor.USPACE, Vendor.LIANTONG]
        assert prefs.show_of(Vendor.DODOHOME) == 0
        assert prefs.show_of(Vendor.USPACE) == 3

    def test_a_vendor_listed_twice_is_refused(self) -> None:
        with pytest.raises(ValueError):
            pref((Vendor.LIANTONG, 1), (Vendor.LIANTONG, 2))

    @pytest.mark.parametrize("show", [-1, 9])
    def test_show_count_is_bounded(self, show: int) -> None:
        with pytest.raises(ValueError):
            VendorPick(Vendor.LIANTONG, show)


class TestShortlist:
    @staticmethod
    def pool(*candidates: Candidate) -> Pool:
        return Pool(candidates=tuple(candidates), radius_m=1500)

    @staticmethod
    def ids(chosen: list[Candidate]) -> list[str]:
        return [c.lot.source_id for c in chosen]

    def test_defaults_route_two_of_each_of_the_first_four_vendors(self) -> None:
        pool = self.pool(
            *[cand(f"ip{i}", 100 + i, brand=Brand.DODOHOME, iparking="X") for i in range(3)],
            *[cand(f"dd{i}", 200 + i, brand=Brand.DODOHOME) for i in range(3)],
            *[cand(f"lt{i}", 300 + i, brand=Brand.LIANTONG) for i in range(3)],
            *[cand(f"tm{i}", 400 + i, brand=Brand.TIMES) for i in range(3)],
            *[cand(f"us{i}", 500 + i, brand=Brand.USPACE) for i in range(3)],
            *[cand(f"o{i}", 50 + i) for i in range(5)],
        )
        chosen = shortlist(pool, RankingPolicy())
        assert len(chosen) == 8
        assert self.ids(chosen) == ["ip0", "ip1", "dd0", "dd1", "lt0", "lt1", "tm0", "tm1"]

    def test_the_user_order_decides_which_vendors_are_routed(self) -> None:
        pool = self.pool(
            *[cand(f"us{i}", 300 + i, brand=Brand.USPACE) for i in range(3)],
            *[cand(f"lt{i}", 100 + i, brand=Brand.LIANTONG) for i in range(3)],
            *[cand(f"o{i}", 50 + i) for i in range(10)],
        )
        policy = RankingPolicy(preference=pref((Vendor.USPACE, 2), (Vendor.LIANTONG, 0)))
        chosen = self.ids(shortlist(pool, policy))
        assert chosen[:2] == ["us0", "us1"]  # USPACE first, two of them
        assert "lt0" not in chosen  # LIANTONG shows none, so it gets no vendor slot
        assert len(chosen) == 8  # the rest of the budget goes to the nearest lots

    def test_budget_is_never_exceeded(self) -> None:
        pool = self.pool(
            *[cand(f"d{i}", 10 + i, brand=Brand.DODOHOME) for i in range(20)],
            *[cand(f"l{i}", 10 + i, brand=Brand.LIANTONG) for i in range(20)],
        )
        policy = RankingPolicy(preference=pref((Vendor.DODOHOME, 8), (Vendor.LIANTONG, 8)))
        assert len(shortlist(pool, policy)) == 8

    def test_with_no_configured_vendor_nearby_the_nearest_lots_are_routed(self) -> None:
        pool = self.pool(*[cand(f"o{i}", 100 + i) for i in range(12)])
        assert self.ids(shortlist(pool, RankingPolicy())) == [f"o{i}" for i in range(8)]

    def test_distance_mode_routes_the_nearest_lots_of_any_vendor(self) -> None:
        pool = self.pool(
            cand("dd", 900, brand=Brand.DODOHOME),
            *[cand(f"o{i}", 100 + i) for i in range(10)],
        )
        chosen = shortlist(pool, RankingPolicy(mode=SortMode.DISTANCE))
        assert len(chosen) == 8
        assert "dd" not in self.ids(chosen)

    def test_empty_pool(self) -> None:
        assert shortlist(Pool(candidates=(), radius_m=1500), RankingPolicy()) == []


class TestArrange:
    @staticmethod
    def routed(seconds: int) -> RouteTime:
        return RouteTime(seconds, seconds)

    def test_vendor_sections_follow_the_user_order(self) -> None:
        policy = RankingPolicy(preference=pref((Vendor.LIANTONG, 2), (Vendor.DODOHOME, 2)))
        items = [
            (cand("dd", 100, brand=Brand.DODOHOME), None),
            (cand("lt", 300, brand=Brand.LIANTONG), None),
            (cand("lt2", 200, brand=Brand.LIANTONG), None),
            (cand("o", 50), None),
        ]
        out = arrange(items, policy)
        assert [(r.lot.source_id, r.block) for r in out] == [
            ("lt2", Block.PRIORITY),
            ("lt", Block.PRIORITY),
            ("dd", Block.PRIORITY),
            ("o", Block.OTHER),
        ]
        assert [r.vendor for r in out[:3]] == [Vendor.LIANTONG, Vendor.LIANTONG, Vendor.DODOHOME]

    def test_within_a_vendor_a_walking_time_beats_distance(self) -> None:
        policy = RankingPolicy(preference=pref((Vendor.LIANTONG, 3)))
        items = [
            (cand("near", 100, brand=Brand.LIANTONG), self.routed(900)),
            (cand("far", 900, brand=Brand.LIANTONG), self.routed(300)),
            (cand("unrouted", 50, brand=Brand.LIANTONG), None),
        ]
        out = arrange(items, policy)
        assert [r.lot.source_id for r in out] == ["far", "near", "unrouted"]
        assert out[2].walking is None  # never invented

    def test_overflow_of_a_vendor_moves_to_the_other_section_by_time(self) -> None:
        policy = RankingPolicy(preference=pref((Vendor.LIANTONG, 1)))
        items = [
            (cand("lt1", 100, brand=Brand.LIANTONG), None),
            (cand("lt2", 200, brand=Brand.LIANTONG), self.routed(500)),
            (cand("lt3", 300, brand=Brand.LIANTONG), None),
        ]
        out = arrange(items, policy)
        assert [(r.lot.source_id, r.block) for r in out] == [
            ("lt2", Block.PRIORITY),
            ("lt1", Block.OTHER),
            ("lt3", Block.OTHER),
        ]

    def test_vendor_sections_are_capped_at_twelve(self) -> None:
        policy = RankingPolicy(preference=pref(*[(v, 3) for v in Vendor]))
        items = [
            (cand(f"{v.value}{i}", 100 + i, brand=b), None) for v, b in _brands() for i in range(3)
        ]
        out = arrange(items, policy)
        assert sum(r.block is Block.PRIORITY for r in out) == 12
        assert sum(r.block is Block.OTHER for r in out) == 3  # the overflow past the cap

    def test_the_other_section_is_capped_at_eight(self) -> None:
        items = [(cand(f"o{i}", 100 + i), None) for i in range(12)]
        out = arrange(items, RankingPolicy())
        assert len(out) == 8
        assert all(r.block is Block.OTHER and r.vendor is None for r in out)

    def test_a_small_operator_is_listed_after_the_vendors_by_distance(self) -> None:
        items = [
            (cand("small", 50), None),
            (cand("dd", 900, brand=Brand.DODOHOME), None),
        ]
        out = arrange(items, RankingPolicy(preference=pref((Vendor.DODOHOME, 1))))
        assert [r.lot.source_id for r in out] == ["dd", "small"]

    def test_distance_mode_is_one_list_by_time_then_distance_capped_at_twenty(self) -> None:
        policy = RankingPolicy(mode=SortMode.DISTANCE)
        items = [
            (cand("a", 300), self.routed(200)),
            (cand("b", 100), None),
            (cand("c", 50), self.routed(900)),
        ]
        out = arrange(items, policy)
        assert [r.lot.source_id for r in out] == ["a", "c", "b"]
        assert {r.block for r in out} == {Block.DISTANCE}
        many = [(cand(f"x{i}", 100 + i), None) for i in range(25)]
        assert len(arrange(many, policy)) == 20


class TestPool:
    def test_radius_expands_until_enough_results(self) -> None:
        cands = [Candidate(make_lot(f"n{i}"), 1800 + i) for i in range(6)]
        pool = pool_within_radius(cands, RankingPolicy(min_results=5))
        assert pool.radius_m == 3000
        assert len(pool.candidates) == 6

    def test_stops_at_smallest_sufficient_radius(self) -> None:
        cands = [Candidate(make_lot(f"n{i}"), 100 + i) for i in range(6)]
        cands.append(Candidate(make_lot("far"), 2500))
        pool = pool_within_radius(cands, RankingPolicy(min_results=5))
        assert pool.radius_m == 1500
        assert "far" not in [c.lot.source_id for c in pool.candidates]

    def test_returns_empty_when_nothing_in_max_radius(self) -> None:
        pool = pool_within_radius([Candidate(make_lot("x"), 9000)], RankingPolicy())
        assert pool.candidates == ()
        assert pool.radius_m == 5000


class TestIParkingMatching:
    def station(self, code: str, at: GeoPoint) -> IParkingStation:
        return IParkingStation(code=code, name=code, address="", city_code="TPC", location=at)

    def test_matches_nearest_dodohome_lot_within_range(self) -> None:
        near = make_lot("near", brand=Brand.DODOHOME, at=GeoPoint(25.0331, 121.5654))
        farther = make_lot("farther", brand=Brand.DODOHOME, at=GeoPoint(25.0335, 121.5654))
        got = match_iparking([near, farther], [self.station("S1", ORIGIN)])
        assert got == {near.id: "S1"}

    def test_non_dodohome_lot_never_gets_the_flag(self) -> None:
        neighbour = make_lot("n", brand=Brand.OTHER, at=GeoPoint(25.03301, 121.5654))
        assert match_iparking([neighbour], [self.station("S1", ORIGIN)]) == {}

    def test_out_of_range_station_matches_nothing(self) -> None:
        lot = make_lot("l", brand=Brand.DODOHOME, at=GeoPoint(25.0400, 121.5654))
        assert match_iparking([lot], [self.station("S1", ORIGIN)]) == {}

    def test_nearer_station_wins_a_contested_lot(self) -> None:
        lot = make_lot("l", brand=Brand.DODOHOME, at=ORIGIN)
        s_far = self.station("FAR", GeoPoint(25.0335, 121.5654))
        s_near = self.station("NEAR", GeoPoint(25.0331, 121.5654))
        assert match_iparking([lot], [s_far, s_near]) == {lot.id: "NEAR"}
