import numpy as np
from scipy import signal
import xarray as xr
import dcpy.ts
import matplotlib.pyplot as plt


def _process_time(time, cycles_per='s'):

    time = time.copy()
    dt = np.nanmedian(np.diff(time.values) / np.timedelta64(1, cycles_per))

    time = np.cumsum(time.copy()
                     .diff(dim=time.dims[0])
                     / np.timedelta64(1, cycles_per))

    return dt, time


def _estimate_impulse_response(b, a, eps=1e-2):
    ''' From scipy filtfilt docs.
        Input:
             b, a : filter params
             eps  : How low must the signal drop to? (default 1e-2)
    '''

    z, p, k = signal.tf2zpk(b, a)
    r = np.max(np.abs(p))
    approx_impulse_len = int(np.ceil(np.log(eps) / np.log(r)))

    return approx_impulse_len


def _butterworth_coeffs(order, nondim_freq, kind):

    return signal.butter(order, nondim_freq, btype=kind)


def gappy_filter(data, b, a, num_discard='auto'):

    out = np.zeros_like(data) * np.nan

    irlen = _estimate_impulse_response(b, a, 1e-9)
    if num_discard == 'auto':
        num_discard = _estimate_impulse_response(b, a, eps=1e-2)

    segstart, segend = find_segments(data)

    for index, start in np.ndenumerate(segstart):
        stop = segend[index]
        try:
            out[start:stop] = signal.filtfilt(b, a,
                                              data[start:stop],
                                              axis=0, method='gust',
                                              irlen=irlen)
            if num_discard is not None:
                out[start:start + num_discard] = np.nan
                out[stop - num_discard:stop] = np.nan
        except ValueError:
            # segment is not long enough for filtfilt
            pass

    return out.squeeze()


def find_segments(var):
    '''
      Finds and return valid index ranges for the input time series.
      Input:
            var - input time series
      Output:
            start - starting indices of valid ranges
            stop  - ending indices of valid ranges
    '''

    NotNans = np.double(~np.isnan(var))
    edges = np.diff(NotNans)
    start = np.where(edges == 1)[0]
    stop = np.where(edges == -1)[0]

    if start.size == 0 and stop.size == 0:
        start = np.array([0])
        stop = np.array([len(var) - 1])

    else:
        start = start + 1
        if ~np.isnan(var[0]):
            start = np.insert(start, 0, 0)

        if ~np.isnan(var[-1]):
            stop = np.append(stop, len(var) - 1)

    return start, stop


def _wrap_butterworth(data, coord, freq, kind, cycles_per='s', order=2,
                      debug=False):
    '''
    Inputs
    ------

    data : xr.DataArray
    coord : coordinate along which to filter
    freq : "frequencies" for filtering
    cycles_per: optional
        Units for frequency
    order : optional
        Butterworth filter order

    Outputs
    -------

    filtered : xr.DataArray
    '''

    # if len(data.dims) > 1 and coord is None:
    #     raise ValueError('Specify coordinate along which to filter')
    # else:
    #     coord = data.coords[0]

    if data[coord].dtype.kind == 'M':
        dx, x = _process_time(data[coord], cycles_per)
    else:
        dx = np.diff(data[coord][0:2].values)

    b, a = _butterworth_coeffs(order, freq*dx/(1/2), kind)

    data = data.copy()
    if debug:
        dcpy.ts.PlotSpectrum(data, cycles_per=cycles_per)

    old_dims = data.dims
    idim = data.get_axis_num(coord)
    stackdims = data.dims[:idim] + data.dims[idim + 1:]

    # xr.testing.assert_equal(x,
    #                         x.stack(newdim=stackdims)
    #                          .unstack('newdim')
    #                          .transpose(*list(x.dims)))
    if data.ndim > 2:
        # reshape to 2D array
        # 'dim' is now first index
        data = data.stack(newdim=stackdims)

    newdims = data.dims
    if newdims[0] != coord:
        data = data.transpose()
        transposed = True
    else:
        transposed = False

    data.values = np.apply_along_axis(gappy_filter, 0,
                                      data.values,
                                      b, a)

    if data.ndim > 2:
        # unstack back to original shape and ordering
        filtered = data.unstack('newdim').transpose(*list(old_dims))
    else:
        filtered = data

    if transposed:
        filtered = filtered.transpose()

    if debug:
        ylim = plt.gca().get_ylim()
        dcpy.ts.PlotSpectrum(filtered, cycles_per=cycles_per, ax=plt.gca())
        plt.gca().set_ylim(ylim)
        for ff in np.array(freq, ndmin=1):
            plt.axvline(ff)

    return filtered


def bandpass(data, coord, freq, **kwargs):
    return _wrap_butterworth(data, coord, np.sort(freq),
                             kind='bandpass', **kwargs)


def lowpass(data, coord, freq, **kwargs):
    return _wrap_butterworth(data, coord, freq,
                             kind='lowpass', **kwargs)


def highpass(data, coord, freq, **kwargs):
    return _wrap_butterworth(data, coord, freq,
                             kind='highpass', **kwargs)
