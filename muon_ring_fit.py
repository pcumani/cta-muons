import argparse
from astropy import log
from ctapipe.utils.datasets import get_path
from ctapipe.io.hessio import hessio_event_source
import numpy as np
from ctapipe.utils.linalg import rotation_matrix_2d
import pandas as pd
from joblib import Parallel, delayed

from ctapipe.calib.camera.calibrators import (
    calibration_parameters,
    calibrate_event,
    calibration_arguments,
)
from ctapipe.calib.array.muon import (
    psf_likelihood_fit,
    mean_squared_error,
    photon_ratio_inside_ring,
)


def rotate(x, y, angle):
    x, y = np.dot(rotation_matrix_2d(angle), [x, y])
    return x, y


def fit_event(event, pixel_x, pixel_y, params):

    event = calibrate_event(event, params)
    photons = event.dl1.tel[1].pe_charge
    size = np.sum(photons)

    if size < 500:
        return None

    pixel_x = pixel_x.value
    pixel_y = pixel_y.value

    mask = photons > 10

    if not np.any(mask):
        return None

    r, x, y, sigma = psf_likelihood_fit(
        pixel_x[mask],
        pixel_y[mask],
        photons[mask],
    )

    ratio = photon_ratio_inside_ring(
        pixel_x[mask],
        pixel_y[mask],
        photons[mask],
        center_x=x,
        center_y=y,
        radius=r,
        width=sigma,
    )
    error = mean_squared_error(
        pixel_x[mask],
        pixel_y[mask],
        photons[mask],
        center_x=x,
        center_y=y,
        radius=r,
    )

    return {
        'x': x,
        'y': y,
        'r': r,
        'sigma': sigma,
        'mean_squared_error': error,
        'ratio_inside': ratio,
        'event_number': event.count,
        'size': size,
    }

parser = argparse.ArgumentParser(description='Display each event in the file')
parser.add_argument(
    '-f', '--file', dest='input_path', action='store',
    default=get_path('gamma_test.simtel.gz'),
    help='path to the input file. Default = gamma_test.simtel.gz'
)


def main():

    calibration_arguments(parser)
    args = parser.parse_args()

    params = calibration_parameters(args)

    log.debug("[file] Reading file")

    source = hessio_event_source(args.input_path)
    event = next(source)

    pixel_x = event.meta.pixel_pos[1][0]
    pixel_y = event.meta.pixel_pos[1][1]

    with Parallel(36, verbose=10) as pool:

        result = pool(
            delayed(fit_event)(event, pixel_x, pixel_y, params)
            for event in source
        )

    df = pd.DataFrame(list(filter(lambda x: x is not None, result)))
    df.to_hdf('fit_results.hdf5', 'data')


if __name__ == '__main__':
    main()