"""Food categories shown as filters. Grouped from Google's primary place type.

An unlisted type falls into OTHER rather than being guessed at, so a new Google type never hides
a place; it only lands in "其他" until it is added here.
"""

from __future__ import annotations

from enum import StrEnum


class FoodCategory(StrEnum):
    CHINESE = "chinese"
    JAPANESE = "japanese"
    KOREAN = "korean"
    THAI = "thai"
    SOUTHEAST_ASIAN = "southeast_asian"
    WESTERN = "western"
    SEAFOOD = "seafood"
    CAFE = "cafe"
    OTHER = "other"


_BY_TYPE: dict[str, FoodCategory] = {
    "chinese_restaurant": FoodCategory.CHINESE,
    "dim_sum_restaurant": FoodCategory.CHINESE,
    "japanese_restaurant": FoodCategory.JAPANESE,
    "sushi_restaurant": FoodCategory.JAPANESE,
    "ramen_restaurant": FoodCategory.JAPANESE,
    "izakaya_restaurant": FoodCategory.JAPANESE,
    "korean_restaurant": FoodCategory.KOREAN,
    "vietnamese_restaurant": FoodCategory.SOUTHEAST_ASIAN,
    "thai_restaurant": FoodCategory.THAI,
    "indonesian_restaurant": FoodCategory.SOUTHEAST_ASIAN,
    "malaysian_restaurant": FoodCategory.SOUTHEAST_ASIAN,
    "asian_restaurant": FoodCategory.SOUTHEAST_ASIAN,
    "indian_restaurant": FoodCategory.SOUTHEAST_ASIAN,
    "italian_restaurant": FoodCategory.WESTERN,
    "french_restaurant": FoodCategory.WESTERN,
    "american_restaurant": FoodCategory.WESTERN,
    "mediterranean_restaurant": FoodCategory.WESTERN,
    "mexican_restaurant": FoodCategory.WESTERN,
    "pizza_restaurant": FoodCategory.WESTERN,
    "hamburger_restaurant": FoodCategory.WESTERN,
    "steak_house": FoodCategory.WESTERN,
    "seafood_restaurant": FoodCategory.SEAFOOD,
    "cafe": FoodCategory.CAFE,
    "coffee_shop": FoodCategory.CAFE,
    "bakery": FoodCategory.CAFE,
    "dessert_shop": FoodCategory.CAFE,
    "ice_cream_shop": FoodCategory.CAFE,
    "tea_house": FoodCategory.CAFE,
}


def category_of(primary_type: str | None) -> FoodCategory:
    if primary_type is None:
        return FoodCategory.OTHER
    return _BY_TYPE.get(primary_type, FoodCategory.OTHER)
