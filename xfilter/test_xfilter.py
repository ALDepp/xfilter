import numpy as np
import pytest
import xarray as xr

from .xfilter import lowpass, highpass, bandpass


def assert_allclose(a, b, **kwargs):
    xr.testing.assert_allclose(a, b, **kwargs)
    xr.testing._assert_internal_invariants(a)
    xr.testing._assert_internal_invariants(b)


@pytest.fixture
def test_data():
    π = np.pi
    t = np.arange(0, 20001, 4)  # in days
    freqs = dict(zip(["high", "mid", "low"], [5, 100, 1000]))
    data = xr.Dataset()
    for name, f in freqs.items():
        data[name] = xr.DataArray(
            np.sin(2 * π / f * t), dims=["time"], coords={"time": t}
        )

    data["total"] = data.low + data.mid + data.high
    data.attrs["freqs"] = freqs.values()
    return data


@pytest.mark.parametrize("gappy", [True, False])
@pytest.mark.parametrize(
    "filt, freq, expect",
    [
        (lowpass, 1 / 250, "low"),
        (highpass, 1 / 40, "high"),
        (bandpass, (1 / 40, 1 / 250), "mid"),
    ],
)
def test_filters(test_data, filt, freq, expect, gappy):
    actual = filt(test_data.total, coord="time", freq=freq, order=4, gappy=gappy)
    expected = test_data[expect].where(~np.isnan(actual))
    assert_allclose(actual, expected, atol=1e-2)


@pytest.mark.parametrize(
    "filt, freq",
    [(lowpass, 1 / 50), (highpass, 1 / 50), (bandpass, (1 / 40, 1 / 250))],
)
def test_map_overlap(test_data, filt, freq):
    actual = filt(
        test_data.total.chunk({"time": 1001}), coord="time", freq=freq, gappy=False
    ).compute()
    expected = filt(test_data.total, coord="time", freq=freq, gappy=False)

    assert (np.isnan(actual) == np.isnan(expected)).all()
    assert_allclose(actual, expected)
