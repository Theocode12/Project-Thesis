import components


def test_format_bytes_bytes():
    assert components.format_bytes(0) == "0 B"
    assert components.format_bytes(512) == "512 B"
    assert components.format_bytes(1023) == "1023 B"


def test_format_bytes_kb():
    assert components.format_bytes(1024) == "1 KB"
    assert components.format_bytes(825 * 1024) == "825 KB"
    assert components.format_bytes(1500 * 1024) == "1.5 MB"  # >1MB boundary


def test_format_bytes_mb():
    assert components.format_bytes(2.6 * 1024 * 1024) == "2.6 MB"
    assert components.format_bytes(10 * 1024 * 1024) == "10 MB"


def test_format_bytes_gb():
    assert components.format_bytes(1.2 * 1024 * 1024 * 1024) == "1.2 GB"
    assert components.format_bytes(4 * 1024 * 1024 * 1024) == "4 GB"


def test_format_bytes_negative():
    assert components.format_bytes(-5) == "0 B"


def test_format_bytes_never_raw():
    out = components.format_bytes(825 * 1024)
    assert out == "825 KB"
