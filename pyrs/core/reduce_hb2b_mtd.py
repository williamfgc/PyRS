import os
import numpy
from mantid.simpleapi import FilterEvents, LoadEventNexus, LoadInstrument, GenerateEventsFilter
from mantid.simpleapi import ConvertSpectrumAxis, ResampleX, Transpose, AddSampleLog, GeneratePythonScript
from mantid.simpleapi import SortXAxis, CreateWorkspace
from mantid.api import AnalysisDataService as ADS
from pyrs.utilities import checkdatatypes
from pyrs.utilities import file_util
import calibration_file_io
from pyrs.core.calibration_file_io import ResidualStressInstrumentCalibration


def histogram_data(raw_vec_x, raw_vec_y, target_vec_2theta):
    """
    histogram again a set of point data (this is a backup solution)
    it yields exactly the same result as numpy.histogram() except it does not work with unordered vector X
    :param raw_vec_x:
    :param raw_vec_y:
    :param target_vec_2theta:
    :return:
    """
    raw_index = 0
    raw_size = raw_vec_x.shape[0]

    # compare the first entry
    if raw_vec_x[0] < target_vec_2theta[0]:
        # target range is smaller. need to throw away first several raw bins
        raw_index = numpy.searchsorted(raw_vec_x, [target_vec_2theta[0]])[0]
        target_index = 0
    elif raw_vec_x[0] > target_vec_2theta[0]:
        raw_index = 0
        target_index = numpy.searchsorted(target_vec_2theta, [raw_vec_x[0]])[0]
    else:
        # equal.. not very likely
        raw_index = 0
        target_index = 0

    target_size = target_vec_2theta.shape[0] - 1

    target_vec_y = numpy.zeros(shape=(target_size,), dtype='float')

    for bin_i in range(target_index, target_size):
        #
        # x_i = target_vec_2theta[bin_i]
        x_f = target_vec_2theta[bin_i+1]
        while raw_vec_x[raw_index] < x_f and raw_index < raw_size:
            target_vec_y[bin_i] += raw_vec_y[raw_index]
            raw_index += 1
        # END-WHILE
    # END-FOR

    return target_vec_2theta, target_vec_y, numpy.sqrt(target_vec_y)


class MantidHB2BReduction(object):
    """ Reducing the data using Mantid algorithm
    """
    def __init__(self):
        """
        initialization
        """
        self._curr_reduced_data = None   # dict[ws name]  = vec_2theta, vec_y, vec_e

        # data workspace to reduce
        self._data_ws_name = None

        # instrument file
        self._mantid_idf = None

        # calibration: an instance of ResidualStressInstrumentCalibration
        self._instrument_calibration = None

        # TODO - FUTURE - Need to find out which one, resolution or number of bins, is more essential
        self._2theta_resolution = 0.1
        self._num_bins = 1800  # NUM_BINS = [1800, 2500]

        return

    @staticmethod
    def convert_from_raw_to_2theta(matrix_ws_name, test_mode=False):
        """
        Convert from raw to workspace with unit X as
        :param matrix_ws_name: name of input workspace
        :param test_mode: test mode.... cannot give out correct result
        :return: workspace in unit 2theta and transposed to 1-spectrum workspace (handler)
        """
        print ('[DB...BAT] Report: Convert raw to 2theta')

        # check input
        checkdatatypes.check_string_variable('Input raw data workspace name', matrix_ws_name)
        if not ADS.doesExist(matrix_ws_name):
            raise RuntimeError('Raw data workspace {} does not exist in Mantid ADS.'.format(matrix_ws_name))

        # convert to 2theta - counts
        matrix_ws = ADS.retrieve(matrix_ws_name)
        print ('[DB...BAT] Raw workspace: number of histograms = {}, Unit = {}'
               ''.format(matrix_ws.getNumberHistograms(), matrix_ws.getAxis(0).getUnit().unitID()))

        ConvertSpectrumAxis(InputWorkspace=matrix_ws_name, Target='Theta', OutputWorkspace=matrix_ws_name,
                            EnableLogging=False, OrderAxis=False)

        # convert from N-spectra-single element to 1-spectrum-N-element
        raw_data_ws = Transpose(InputWorkspace=matrix_ws_name, OutputWorkspace=matrix_ws_name, EnableLogging=False)
        print ('[DB.....BAT.....PROBLEM] Raw workspace {}: num histograms = {}, sum(Y) = {}\nY: {}'
               ''.format(matrix_ws_name, raw_data_ws.getNumberHistograms(), raw_data_ws.readY(0).sum(),
                         raw_data_ws.readY(0)))

        return raw_data_ws

    def reduce_to_2theta(self, matrix_ws_name, two_theta_min=None, two_theta_max=None, num_2theta_bins=None,
                         mask=None, target_vec_2theta=None):
        """ Reduce the raw matrix workspace, with instrument already loaded, to 2theta
        :param matrix_ws_name:
        :param two_theta_min:
        :param two_theta_max:
        :param num_2theta_bins:
        :param mask:
        :return:
        """
        # convert with Axis ordered
        raw_data_ws = self.convert_from_raw_to_2theta(matrix_ws_name, test_mode=False)  # order Axis

        # mask if required
        if mask is not None:
            checkdatatypes.check_numpy_arrays('Mask vector', [mask, raw_data_ws.readY(0)], 1, True)
            masked_vec = raw_data_ws.dataY(0)
            masked_vec *= mask
        # END-IF(mask)

        # set up resolutin and number of bins for re-sampling/binning
        if two_theta_min is None:
            two_theta_min = raw_data_ws.readX(0)[0]
        else:
            checkdatatypes.check_float_variable('Mininum 2theta for binning', two_theta_min, (-180, 180))
        if two_theta_max is None:
            two_theta_max = raw_data_ws.readX(0)[-1]
        else:
            checkdatatypes.check_float_variable('Maximum 2theta for binning', two_theta_max, (-180, 180))
        if two_theta_min >= two_theta_max:
            raise RuntimeError('2theta range ({}, {}) is not acceptable.'.format(two_theta_min, two_theta_max))
        if num_2theta_bins is not None:
            # checkdatatypes.check_float_variable('2theta resolution', num_2theta_bins, (0.0001, 10))
            # num_bins = int((two_theta_max - two_theta_min) / num_2theta_bins)
            num_bins = num_2theta_bins
        else:
            num_bins = self._num_bins

        # rebin
        if False:
            ResampleX(InputWorkspace=raw_data_ws, OutputWorkspace=matrix_ws_name, XMin=two_theta_min,
                      XMax=two_theta_max,
                      NumberBins=num_bins, EnableLogging=False)
            reduced_ws = ADS.retrieve(matrix_ws_name)
            vec_2theta = reduced_ws.readX(0)
            vec_y = reduced_ws.readY(0)
            vec_e = reduced_ws.readE(0)
        elif False:
            # proved that histogram_data == numpy.histogram
            assert target_vec_2theta is not None, 'In this case, target vector X shall be obtained from '
            vec_2theta, vec_y, vec_e = histogram_data(raw_data_ws.readX(0), raw_data_ws.readY(0), target_vec_2theta)
        elif True:
            # experimenting to use SortXAxis, (modified) ResampleX
            import time
            t0 = time.time()

            raw_2theta = raw_data_ws.readX(0)
            raw_counts = raw_data_ws.readY(0)
            raw_error = raw_data_ws.readE(0)

            # create a 1-spec workspace
            CreateWorkspace(DataX=raw_2theta, DataY=raw_counts, DataE=raw_error, NSpec=1, OutputWorkspace='prototype')

            t1 = time.time()

            # Sort X-axis
            SortXAxis(InputWorkspace='prototype', OutputWorkspace='prot_sorted', Ordering='Ascending',
                      IgnoreHistogramValidation=True)

            t2 = time.time()

            # Resample
            binned = ResampleX(InputWorkspace='prot_sorted', OutputWorkspace=matrix_ws_name, XMin=two_theta_min,
                      XMax=two_theta_max,
                      NumberBins=num_bins, EnableLogging=False)

            t3 = time.time()

            print ('[STAT] Create workspace: {}\n\tSort: {}\n\tResampleX: {}'
                   ''.format(t1 - t0, t2 - t0, t3 - t0))

            vec_2theta = binned.readX(0)
            vec_y = binned.readY(0)
            vec_e = binned.readY(0)

        else:
            # use numpy histogram
            raw_2theta = raw_data_ws.readX(0)
            raw_counts = raw_data_ws.readY(0)
            print ('bins = {}'.format(num_bins))
            vec_y, vec_2theta = numpy.histogram(raw_2theta, bins=num_bins, range=(two_theta_min, two_theta_max),
                                                weights=raw_counts)

            # TODO - NEXT - Here is where the detector efficiency (vanadium) and Lorentzian correction step in
            # blabla .. ...

            # take care of normalization
            vec_1 = numpy.zeros(raw_counts.shape) + 1
            vec_weights, v2t = numpy.histogram(raw_2theta, bins=num_bins, range=(two_theta_min, two_theta_max),
                                               weights=vec_1)
            # correct all the zero count bins
            for i, bin_weight_i in enumerate(vec_weights):
                if bin_weight_i < 1.E-2:  # practically zero
                    vec_weights[i] = 1.E5
            # END-FOR

            # calculate uncertainties before vec Y is changed
            # process the uncertainty
            vec_e = numpy.sqrt(vec_y)

            # normalize by bin weight
            vec_y = vec_y / vec_weights
            vec_e = vec_e / vec_weights  # for example: 3 measuremnts: n, n , n, then by this e = sqrt(n/3)
        # END-IF-ELSE

        # do some study on the workspace dimension
        print ('[DB...BAT] 2theta range: {}, {}; 2theta-size = {}, Y-size = {}'
               ''.format(vec_2theta[0], vec_2theta[-1], len(vec_2theta), len(vec_y)))
        print ('[DB...BAT] Y: {}'.format(vec_y))

        # GeneratePythonScript(InputWorkspace=reduced_ws, Filename='reduce_mantid.py')
        # file_util.save_mantid_nexus(workspace_name=matrix_ws_name, file_name='debugmantid.nxs')

        return vec_2theta, vec_y, vec_e

    def _reduced_to_2theta(self, matrix_ws_name):
        """
        convert to 2theta data set from event workspace
        :param matrix_ws_name:
        :param raw_nexus_file_name:
        :return: 3-tuple: vec 2theta, vec Y and vec E
        """
        # locate calibration file
        if raw_nexus_file_name is not None:
            run_date = file_util.check_creation_date(raw_nexus_file_name)
            try:
                cal_ref_id = self._calibration_manager.check_load_calibration(exp_date=run_date)
            except RuntimeError as run_err:
                err_msg = 'Unable to locate calibration file for run {} due to {}\n'.format(run_date, run_err)
                cal_ref_id = None
        else:
            cal_ref_id = None

        # load instrument
        if cal_ref_id is not None:
            self._set_geometry_calibration(matrix_ws_name, self.calibration_manager.get_geometry_calibration(cal_ref_id))

        LoadInstrument(Workspace=matrix_ws_name, InstrumentName='HB2B', RewriteSpectraMap=True)

        ConvertSpectrumAxis(InputWorkspace=matrix_ws_name, Target='Theta', OutputWorkspace=matrix_ws_name,
                            EnableLogging=False)
        Transpose(InputWorkspace=matrix_ws_name, OutputWorkspace=matrix_ws_name, EnableLogging=False)

        ResampleX(InputWorkspace=matrix_ws_name, OutputWorkspace=matrix_ws_name, XMin=twotheta_min, XMax=twotheta_min,
                  NumberBins=num_bins, EnableLogging=False)

        # TODO - 20181204 - Refer to "WANDPowderReduction" - ASAP(0)


        return vec_2theta, vec_y, vec_e

    @staticmethod
    def _get_nexus_file(ipts_number, run_number):
        """
        get Nexus file (name)
        :param ipts_number:
        :param run_number:
        :return:
        """
        checkdatatypes.check_int_variable('IPTS number', ipts_number, (1, None))
        checkdatatypes.check_int_variable('Run number', run_number, (1, None))

        # check IPTS
        ipts_path = os.path.join('/HFIR/HB2B/', 'IPTS-{}'.format(ipts_number))
        if not os.path.exists(ipts_path):
            return False, 'Unable to find {}'.format(ipts_path)

        # check run number
        nexus_name = os.path.join(ipts_path, 'nexus/HB2B_{}.nxs.h5'.format(run_number))
        if not os.path.exists(nexus_name):
            return False, 'Unable to find {} under {}' \
                          ''.format('nexus/HB2B_{}.nxs.h5'.format(run_number), ipts_path)

        return True, nexus_name

    @staticmethod
    def _load_event_nexus(nexus_file_name, ws_name=False):
        """
        load event Nexus file
        :param nexus_file_name:
        :return:
        """
        if ws_name is None:
            ws_name = os.path.basename(nexus_file_name).split('.nxs')[0] + '_event'

        LoadEventNexus(Filename=nexus_file_name, OutputWorkspace=ws_name, LoadLogs=True)

        return ws_name

    @staticmethod
    def _set_geometry_calibration(ws_name, calibration_dict):
        """
        set the calibrated geometry parameter to workspace such that
        :param ws_name:
        :param calibration_dict:
        :return:
        """
        workspace = retrieve_workspace(ws_name)

        # set 2theta 0
        two_theta = get_log_value(workspace, 'twotheta')
        two_theta += calibration_dict['2theta_0']
        set_log_value(workspace, 'twotheta', two_theta)

        # shift parameters
        set_log_value(workspace, 'shiftx', calibration_dict['shiftx'])
        set_log_value(workspace, 'shifty', calibration_dict['shifty'])

        # spin...
        # TODO - 20181204 - Refer to IDF for the rest of parameters

    @staticmethod
    def _slice_mapping_scan(ws_name):
        """
        slice (event filtering) workspace by mapping scans
        :param ws_name:
        :return: a list of sliced EventWorkspaces' names
        """
        event_ws = retrieve_workspace(ws_name, must_be_event=True)

        # get logs
        try:
            scan_index_log = event_ws.run().getProperty('scan_index')
        except KeyError as key_err:
            raise RuntimeError('scan_index does not exist in {}.  Failed to slice for mapping run.'
                               'FYI {}'.format(ws_name, key_err))

        # generate event filter for the integer log
        splitter_name = ws_name + '_mapping_splitter'
        info_ws_name = ws_name + '_mapping_split_info'
        GenerateEventsFilter(InputWorkspace=event_ws, OutputWorkspace=splitter_name,
                             InformationWorkspace=info_ws_name,
                             LogName='scan_index', MinimumLogValue=1, LogValueInterval=1)

        # filter events
        out_base_name = ws_name + '_split_'
        result = FilterEvents(InputWorkspace=ws_name, SplitterWorkspace=splitter_name,
                              OutputWorkspaceBaseName=out_base_name, InformationWorkspace=info_ws_name,
                              GroupWorkspaces=True)

        output_ws_names = result.OutputWorkspaceNames  # contain 'split___ws_unfiltered'

        return output_ws_names

    def add_nexus_run(self, ipts_number, exp_number, run_number):
        """
        add a NeXus file to the project
        :param ipts_number:
        :param exp_number:
        :param run_number:
        :param file_name:
        :return:
        """
        nexus_file = hb2b_utilities.get_hb2b_raw_data(ipts_number, exp_number, run_number)

        self.add_nexus_file(ipts_number, exp_number, run_number, nexus_file)

        return

    def add_nexus_file(self, ipts_number, exp_number, run_number, nexus_file):
        """

        :param ipts_number:
        :param exp_number:
        :param run_number:
        :param nexus_file:
        :return:
        """
        if ipts_number is None or exp_number is None or run_number is None:
            # arbitrary single file
            self._single_file_manager.add_nexus(nexus_file)
        else:
            # well managed file
            self._archive_file_manager.add_nexus(ipts_number, exp_number, run_number, nexus_file)

        return

    def get_workspace(self):
        """
        Get the handler to the workspace
        :return:
        """
        checkdatatypes.check_string_variable('Data worksapce name', self._data_ws_name)

        return ADS.retrieve(self._data_ws_name)

    def load_instrument(self, two_theta_value, idf_name, calibration):
        """
        Load instrument with calibration to
        :return:
        """
        if self._data_ws_name is None or ADS.doesExist(self._data_ws_name) is False:
            raise RuntimeError('Reduction HB2B (Mantid) has no workspace set to reduce')
        else:
            data_ws = ADS.retrieve(self._data_ws_name)

        # check calibration
        assert isinstance(calibration, calibration_file_io.ResidualStressInstrumentCalibration), 'blabla'
        print ('[DB...BAT] Input calibration: {}'.format(calibration))

        # check idf & calibration & 2theta
        checkdatatypes.check_file_name(idf_name, True, False, False, 'Mantid IDF for HB2B')

        # set 2theta value if the workspace does not contain it
        if two_theta_value:
            # if 2theta is not None: must be a float
            checkdatatypes.check_float_variable('Two theta value', two_theta_value, (-181., 181))

        # check whether it is necessary to set 2theta
        try:
            two_theta_property = data_ws.run().getProperty('2theta')
            if two_theta_value:
                add_2theta = True
            else:
                add_2theta = True
        except RuntimeError:
            # 2theta does not exist
            if two_theta_value:
                add_2theta = True
            else:
                raise RuntimeError('2theta must be given for workspace without 2theta log')
        # END-IF-TRY

        if add_2theta:
            print ('[INFO] 2theta degree = {}'.format(two_theta_value))
            AddSampleLog(Workspace=self._data_ws_name, LogName='2theta',
                         LogText='{}'.format(two_theta_value),  # arm_length-DEFAULT_ARM_LENGTH),
                         LogType='Number Series', LogUnit='meter',
                         NumberType='Double')

        # set up sample logs
        # cal::arm
        AddSampleLog(Workspace=self._data_ws_name, LogName='cal::arm',
                     LogText='{}'.format(calibration.center_shift_z),  # arm_length-DEFAULT_ARM_LENGTH),
                     LogType='Number Series', LogUnit='meter',
                     NumberType='Double')

        # cal::deltax
        AddSampleLog(Workspace=self._data_ws_name, LogName='cal::deltax',
                     LogText='{}'.format(calibration.center_shift_x),
                     LogType='Number Series', LogUnit='meter',
                     NumberType='Double')
        #
        # cal::deltay
        AddSampleLog(Workspace=self._data_ws_name, LogName='cal::deltay',
                     LogText='{}'.format(calibration.center_shift_y),
                     LogType='Number Series', LogUnit='meter',
                     NumberType='Double')

        # cal::roty
        AddSampleLog(Workspace=self._data_ws_name, LogName='cal::roty',
                     LogText='{}'.format(calibration.rotation_y),
                     LogType='Number Series', LogUnit='degree',
                     NumberType='Double')

        # cal::flip
        AddSampleLog(Workspace=self._data_ws_name, LogName='cal::flip',
                     LogText='{}'.format(calibration.rotation_x),
                     LogType='Number Series', LogUnit='degree',
                     NumberType='Double')

        # cal::spin
        AddSampleLog(Workspace=self._data_ws_name, LogName='cal::spin',
                     LogText='{}'.format(calibration.rotation_z),
                     LogType='Number Series', LogUnit='degree',
                     NumberType='Double')

        # load instrument
        LoadInstrument(Workspace=self._data_ws_name,
                       Filename=idf_name,
                       InstrumentName='HB2B', RewriteSpectraMap='True')

        return

    def mask_detectors(self, mask_vector):
        """
        Mask detectors
        :param mask_vector:
        :return:
        """


    def reduce_rs_nexus(self, nexus_name, auto_mapping_check, output_dir, do_calibration,
                        allow_calibration_unavailable):
        """ reduce an HB2B nexus file
        :param nexus_name:
        :param auto_mapping_check:
        :param output_dir:
        :param do_calibration: flag to calibrate the detector
        :param allow_calibration_unavailable: if True and do_calibration is True, then when calibration file cannot
                be found, reduction will be continued with a warning.  Otherwise, an exception will be thrown
        :return:
        """
        # load data with check
        event_ws_name = self._load_event_nexus(nexus_name)

        # is it a mapping run?
        if auto_mapping_check:
            is_mapping_run = self._check_mapping_run(event_ws_name)
        else:
            is_mapping_run = False

        # slice data
        if is_mapping_run:
            event_ws_list = self._slice_mapping_scan(event_ws_name)
        else:
            event_ws_list = [event_ws_name]

        # reduce
        reduced_data_dict = dict()
        err_msg = ''
        for ws_name in event_ws_list:
            try:
                if do_calibration:
                    calibration_dict = self.calibration_manager.get_calibration(data_file=nexus_name)
                    if calibration_dict is None and not allow_calibration_unavailable:
                        raise RuntimeError('Unable to locate calibration file for {}'.format(nexus_name))
                    elif calibration_dict is None and allow_calibration_unavailable:
                        err_msg + 'Unable to find calibration for {}\n'.format(nexus_name)
                    corr_data = self._reduced_to_2theta(ws_name, calibration_dict)
                else:
                    corr_data = self._reduced_to_2theta(ws_name, None)
            except RuntimeError as run_err:
                err_msg += 'Failed to convert {} to 2theta space due to {}\n'.format(ws_name, run_err)
            else:
                reduced_data_dict[ws_name, corr_data] = corr_data
        # END-FOR

        # set to the class variable
        self._curr_reduced_data = reduced_data_dict

        # save file
        out_file_name = os.path.join(os.path.basename(nexus_name).split('.')[0], '.hdf5')
        self.save_reduced_data(reduced_data_dict, out_file_name)

        return

    def reduce_rs_run(self, ipts_number, run_number, is_mapping, do_calibration):
        """ reduce an HB2B run
        :param ipts_number:
        :param run_number:
        :param is_mapping:
        :param do_calibration: flag to do calibration (if it exists)
        :return: (dict, str): dict[ws name] = data set, error message
        """
        # get file
        status, ret_obj = self._get_nexus_file(ipts_number, run_number)
        if status:
            nxs_file_name = ret_obj
        else:
            err_msg = ret_obj
            raise RuntimeError('Unable to reduce ITPS-{} Run {} due to {}'.format(ipts_number, run_number, err_msg))

        # load data
        event_ws_name = self._load_event_nexus(nxs_file_name)

        # chop?
        if is_mapping:
            event_ws_list = self._slice_mapping_scan(event_ws_name)
        else:
            event_ws_list = [event_ws_name]

        # reduce
        reduced_data_dict = dict()
        err_msg = ''
        for ws_name in event_ws_list:
            try:
                if do_calibration:
                    corr_data = self._reduced_to_2theta(ws_name, nxs_file_name)
                else:
                    corr_data = self._reduced_to_2theta(ws_name, None)
            except RuntimeError as run_err:
                err_msg += 'Failed to convert {} to 2theta space due to {}\n'.format(ws_name, run_err)
            else:
                reduced_data_dict[ws_name, corr_data] = corr_data
        # END-FOR

        # set to the class variable
        self._curr_reduced_data = reduced_data_dict

        return reduced_data_dict, err_msg

    def save_reduced_data(self, reduced_data_dict, file_name):
        """
        save the set of reduced data to a hdf file
        :param reduced_data_dict: dict[ws name] = vec_2theta, vec_Y, vec_E
        :param file_name:
        :return:
        """
        checkdatatypes.check_file_name(file_name, check_exist=False, check_writable=True,
                                       is_dir=False)
        checkdatatypes.check_dict('Reduced data dictionary', reduced_data_dict)

        # create a list of scan log indexes
        scan_index_dict = dict()

        if len(reduced_data_dict) == 1:
            # non-mapping case
            scan_index = 1
            ws_name = reduced_data_dict[reduced_data_dict.keys[0]]
            data_set = reduced_data_dict[ws_name]
            scan_index_dict[scan_index] = ws_name, data_set

        else:
            # mapping case
            for ws_name in reduced_data_dict.keys():
                scan_index_i = int(ws_name.split('_')[-1])
                scan_index_dict[scan_index_i] = ws_name, reduced_data_dict[ws_name]
        # END-IF-ELSE

        scandataio.save_hb2b_reduced_data(scan_index_dict, file_name)

        return

    def set_calibration(self, calibration):
        """
        Set the instrument calibration
        :param calibration:
        :return:
        """
        assert isinstance(calibration, ResidualStressInstrumentCalibration),\
            'Instrument-calibration instance {} must be of ResidualStressInstrumentCalibration, but not an instance ' \
            'of type {}'.format(calibration, type(calibration))

        self._instrument_calibration = calibration

        return

    def set_workspace(self, ws_name):
        """
        set the workspace that is ready for reduction to 2theta
        :param ws_name:
        :return:
        """
        checkdatatypes.check_string_variable('Workspace name', ws_name)

        if ADS.doesExist(ws_name):
            self._data_ws_name = ws_name
        else:
            raise RuntimeError('Workspace {} does not exist in ADS'.format(ws_name))

        return


    def set_2theta_resolution(self, delta_two_theta):
        """
        set 2theta resolution
        :param delta_two_theta: 2theta resolution
        :return:
        """
        checkdatatypes.check_float_variable('2-theta resolution', delta_two_theta, (1.E-10, 10.))

        self._2theta_resolution = delta_two_theta

        return