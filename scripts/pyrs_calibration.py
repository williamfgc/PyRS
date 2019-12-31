import numpy
import time
from pyrs.projectfile import HidraProjectFile, HidraProjectFileMode
from pyrs.utilities import calibration_file_io
from pyrs.calibration import peakfit_calibration

# DEFAULT VALUES FOR DATA PROCESSING
DEFAULT_CALIBRATION = None
DEFAULT_INSTRUMENT = None
DEFAULT_MASK = None
DEFAULT_POWDER = None
DEFAULT_IPTS = 22731
DEFAULT_PIN = None
DEFAULT_PIN = None
DEFAULT_CYCLE = 482


def SaveCalibError(calibrator, fName):
    calibrator.singleEval(ConstrainPosition=True)

    tths = sorted(list(calibrator.ReductionResults.keys()))

    Rois = list(calibrator.ReductionResults[tths[0]].keys())
    DataPoints = len(calibrator.ReductionResults[tths[0]][Rois[0]][0])

    DataOut = numpy.zeros((DataPoints, 3*len(tths)*len(Rois)))
    header = ''

    lcv = -1
    for i_tth in tths:
        for j in list(calibrator.ReductionResults[i_tth].keys()):
            tempdata = calibrator.ReductionResults[i_tth][j]
            print i_tth, j

            lcv += 1
            DataOut[:, lcv*3+0] = tempdata[0]
            DataOut[:, lcv*3+1] = tempdata[1]
            DataOut[:, lcv*3+2] = tempdata[2]
            header += ',pos{}_roi{}_tth,pos{}_roi{}_obs,pos{}_roi{}_calc'.format(i_tth, j[0],
                                                                                 i_tth, j[0], i_tth, j[0])

    DataOut = DataOut[:, :lcv*3+3]

    print DataOut.shape
    numpy.savetxt(fName, DataOut, delimiter=',', header=header[1:])


if __name__ == '__main__':
    from argparse import ArgumentParser
    parser = ArgumentParser(description='Script for auto-reducing HB2B')
    parser.add_argument('--IPTS', nargs='?', default=DEFAULT_IPTS,
                        help='Run number for stepping file (default=%(default)s)')
    parser.add_argument('--pin', nargs='?', default=DEFAULT_PIN,
                        help='Run number for stepping file (default=%(default)s)')
    parser.add_argument('--instrument', nargs='?', default=DEFAULT_INSTRUMENT,
                        help='instrument configuration file overriding embedded (arm, pixel number'
                        ' and size) (default=%(default)s)')
    parser.add_argument('--method', nargs='?', default=DEFAULT_CALIBRATION,
                        help='method used for instrument geometry calibration (default=%(default)s)')
    parser.add_argument('--calibration', nargs='?', default=DEFAULT_CALIBRATION,
                        help='instrument geometry calibration file overriding embedded (default=%(default)s)')
    parser.add_argument('--mask', nargs='?', default=DEFAULT_MASK,
                        help='masking file (PyRS hdf5 format) or mask name (default=%(default)s)')
    parser.add_argument('--powder', nargs='?', default=DEFAULT_POWDER,
                        help='Run number for powder file (default=%(default)s)')
    parser.add_argument('--cycle', nargs='?', default=DEFAULT_CYCLE,
                        help='HFIR run cycle (default=%(default)s)')

    options = parser.parse_args()

    # generate project name if not already determined
    if options.pin is None:
        pin_engine = None
    else:
        pin_project_file = '/HFIR/HB2B/IPTS-{}/shared/ProjectFiles/HB2B_{}.h5'.format(options.IPTS, options.pin)
        pin_engine = HidraProjectFile(pin_project_file, mode=HidraProjectFileMode.READONLY)

    if options.powder is None:
        powder_engine = None
    else:
        powder_project_file = '/HFIR/HB2B/IPTS-{}/shared/ProjectFiles/HB2B_{}.h5'.format(options.IPTS, options.powder)
        powder_engine = HidraProjectFile(powder_project_file, mode=HidraProjectFileMode.READONLY)

    # instrument geometry
    if options.instrument == DEFAULT_INSTRUMENT:
        idf_name = 'data/XRay_Definition_1K.txt'
    else:
        idf_name = options.instrument

    hb2b = calibration_file_io.import_instrument_setup(idf_name)
    calibrator = peakfit_calibration.PeakFitCalibration(hb2b, pin_engine, powder_engine)

    if options.calibration is not None:
        calibrator.get_archived_calibration(options.calibration)

#    calibrator._calib[0] = 0.002600685374401848
#    calibrator._calib[2] = -0.020583807174127174
#    calibrator._calib[6] = 1.537467969479386

    if options.method in [DEFAULT_CALIBRATION, 'geometry']:
        SaveCalibError(calibrator, 'HB2B_{}_before.csv'.format(options.pin))
        calibrator.CalibrateGeometry()
        print calibrator.get_calib()

    if options.method in [DEFAULT_CALIBRATION, 'testshift']:
        SaveCalibError(calibrator, 'HB2B_{}_shift1.txt'.format(options.pin))
        calibrator._calib[2] = -0.020583807174127174
        # SaveCalibError(calibrator, 'HB2B_{}_shift2.txt'.format(options.pin))

    if options.method in ['shift']:
        calibrator.singlepeak = False
        calibrator.CalibrateShift(ConstrainPosition=True)
        print calibrator.get_calib()

    if options.method in ['rotate']:
        calibrator.CalibrateRotation(ConstrainPosition=True)
        print calibrator.get_calib()

    if options.method in ['wavelength']:
        calibrator.singlepeak = False
        calibrator.calibrate_wave_length()
        print calibrator.get_calib()

    if options.method in ['full']:
        calibrator.singlepeak = False
        calibrator.FullCalibration(ConstrainPosition=True)
        print calibrator.get_calib()

    if options.method == 'distance':
        calibrator.calibrate_distance(ConstrainPosition=True, Brute=True)
        print calibrator.get_calib()

    if options.method == 'geoNew':
        print 'Calibrating Geometry in Steps'
        calibrator.calibrate_shiftx(ConstrainPosition=True)
        print calibrator.get_calib()
        calibrator.calibrate_distance(ConstrainPosition=False)
        print calibrator.get_calib()
        calibrator.calibrate_wave_length(ConstrainPosition=True)
        print calibrator.get_calib()
        calibrator.CalibrateRotation()
        print calibrator.get_calib()
        calibrator.FullCalibration()
        print calibrator.get_calib()

    if options.method in [DEFAULT_CALIBRATION, 'runAll']:
        calibrator = peakfit_calibration.PeakFitCalibration(hb2b, pin_engine, powder_engine)
        calibrator.FullCalibration()
        FullCalib = calibrator.get_calib()

        calibrator = peakfit_calibration.PeakFitCalibration(hb2b, pin_engine, powder_engine)
        calibrator.CalibrateGeometry()
        GeoCalib = calibrator.get_calib()

        calibrator = peakfit_calibration.PeakFitCalibration(hb2b, pin_engine, powder_engine)
        calibrator.CalibrateRotation()
        RotateCalib = calibrator.get_calib()

        calibrator = peakfit_calibration.PeakFitCalibration(hb2b, pin_engine, powder_engine)
        calibrator.CalibrateShift()
        ShiftCalib = calibrator.get_calib()

        calibrator = peakfit_calibration.PeakFitCalibration(hb2b, pin_engine, powder_engine)
        calibrator.calibrate_wave_length()
        LambdaCalib = calibrator.get_calib()

        print FullCalib
        print GeoCalib
        print RotateCalib
        print ShiftCalib
        print LambdaCalib

    datatime = time.strftime('%Y-%m-%dT%H-%M', time.localtime())
    fName = '/HFIR/HB2B/shared/CAL/cycle{}/HB2B_{}_{}.json'.format(options.cycle, calibrator.mono, datatime)
#    file_name = os.path.join(os.getcwd(), fName)
    calibrator.write_calibration(fName)