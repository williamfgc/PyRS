# This is the virtual base class as the fitting frame
from pyrs.utilities import checkdatatypes

NATIVE_PEAK_PARAMETERS = {'Gaussian': ['Height', 'PeakCentre', 'Sigma', 'A0', 'A1'],
                          'PseudoVoigt': ['Mixing', 'Intensity', 'PeakCentre', 'FWHM', 'A0', 'A1'],
                          'Voigt': ['LorentzAmp', 'LorentzPos', 'LorentzFWHM', 'GaussianFWHM',
                                    'A0', 'A1']}
EFFECTIVE_PEAK_PARAMETERS = ['Center', 'Height', 'FWHM', 'A0', 'A1']


class RsPeakFitEngine(object):
    """
    virtual peak fit engine
    """
    def __init__(self, sub_run_list, data_set_list, ref_id):
        """
        initialization
        :param data_set_list:
        :param ref_id:
        """
        # check
        checkdatatypes.check_list('Data set list', data_set_list)
        checkdatatypes.check_list('Sun runs', sub_run_list)
        checkdatatypes.check_string_variable('Peak fitting reference ID', ref_id)

        if len(sub_run_list) != len(data_set_list):
            raise RuntimeError('Sub runs ({}) and data sets ({}) have different sizes'
                               ''.format(len(sub_run_list), len(data_set_list)))

        # for scipy: keep the numpy array will be good enough
        self._data_set = data_set_list
        self._reference_id = ref_id
        self._sub_run_list = sub_run_list

        # for fitted result
        self._peak_center_vec = None  # 2D vector for observed center of mass and highest data point
        self._peak_center_d_vec = None  # 1D vector for calculated center in d-spacing

        return

    def export_fit_result(self):
        """
        export fit result for all the peaks
        :return: a dictionary of fitted peak information
        """
        raise NotImplementedError('Virtual base class member method export_fit_result()')

    def fit_peaks(self, peak_function_name, background_function_name, fit_range, scan_index=None):
        """
        fit peaks
        :param peak_function_name:
        :param background_function_name:
        :param fit_range:
        :param scan_index:
        :return:
        """
        raise NotImplementedError('Virtual base class member method fit_peaks()')

    def get_calculated_peak(self, scan_log_index):
        """
        get the calculated peak's value
        :return:
        """
        raise NotImplementedError('Virtual base class member method get_calculated_peak()')

    def get_number_scans(self, param_name):
        """
        get the value of a fitted parameter
        :return:
        """
        raise NotImplementedError('Virtual base class member method get_number_scans()')

    def get_number_scans(self):
        """
        get number of scans in input data to fit
        :return:
        """
        raise NotImplementedError('Virtual base class member method get_number_scans()')

    @staticmethod
    def get_peak_param_names(peak_function, is_effective):
        """ Get the peak parameter names
        :param peak_function:
        :param is_effective:
        :return:
        """
        if is_effective:
            # Effective parameters
            param_names = EFFECTIVE_PEAK_PARAMETERS[:]
            if peak_function == 'PseudoVoigt':
                param_names.append('Mixing')

        else:
            # Native parameters
            try:
                param_names = NATIVE_PEAK_PARAMETERS[peak_function][:]
            except KeyError as key_err:
                raise RuntimeError('Peak type {} not supported.  The supported peak functions are {}.  FYI: {}'
                                   ''.format(peak_function, NATIVE_PEAK_PARAMETERS.keys(), key_err))

        return param_names

    def write_result(self):
        """
        write (append) the peak fitting result to input HDF5 for further data reduction such as
        calculating stress/strain.
        The file format shall be documented as a standard
        :return:
        """
        # TODO - 20180727 - Implement!

# In [17]: log97entry.create_group('peak_fit')
# Out[17]: <HDF5 group "/Diffraction Data/Log 97/peak_fit" (0 members)>
#
# In [18]: peak_fit_97 = log
# %logoff     %logon      %logstart   %logstate   %logstop    log97entry  log98entry
#
# In [18]: peak_fit_97 = log97entry['peak_fit']
#
# In [19]: peak_fit_97['type'
#    ....: ] = 'Gaussian'
#
# In [20]: peak_fit_97['Height'] = 45.0
#
# In [21]: peak_fit_97['Chi2'] = 56.3
#
# In [22]: rwfile.close()



