import components


def test_format_count_small():
    assert components.format_count(0) == "0"
    assert components.format_count(999) == "999"


def test_format_count_thousands():
    assert components.format_count(1_000) == "1K"
    assert components.format_count(1_500) == "1.5K"
    assert components.format_count(999_999) == "1000K"


def test_format_count_millions():
    assert components.format_count(1_000_000) == "1M"
    assert components.format_count(2_345_678) == "2.3M"
    assert components.format_count(999_999_999) == "1000M"


def test_format_count_billions():
    assert components.format_count(1_000_000_000) == "1B"
    assert components.format_count(1_250_000_000) == "1.2B"


def test_format_count_no_trailing_zero():
    assert components.format_count(1_200) == "1.2K"
    assert components.format_count(1_100) == "1.1K"
