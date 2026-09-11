import pytest

try:
    import stellar_lense_accel
except ImportError:
    stellar_lense_accel = None

pytestmark = pytest.mark.skipif(
    stellar_lense_accel is None,
    reason="stellar_lense_accel Rust extension not installed",
)


def test_extension_importable():
    assert stellar_lense_accel is not None
