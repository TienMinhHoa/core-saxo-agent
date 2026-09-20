import pytest

from saxophone.platform.concurrency import create_blocking_io_limiter


def test_blocking_io_limiter_rejects_invalid_capacity() -> None:
    with pytest.raises(ValueError, match="positive"):
        create_blocking_io_limiter(0)

    with pytest.raises(ValueError, match="integer"):
        create_blocking_io_limiter(True)


def test_blocking_io_limiter_has_configured_capacity() -> None:
    limiter = create_blocking_io_limiter(3)

    assert limiter.total_tokens == 3
