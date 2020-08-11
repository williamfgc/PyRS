# extentable version of dict https://treyhunner.com/2019/04/why-you-shouldnt-inherit-from-list-and-dict-in-python/
from collections import Iterable, MutableMapping
import numpy as np
from scipy.cluster.hierarchy import fclusterdata
from scipy.spatial import cKDTree
from typing import Optional, Union, List, NamedTuple, Tuple
from pyrs.utilities.convertdatatypes import to_int
from .constants import HidraConstants, DEFAULT_POINT_RESOLUTION  # type: ignore

__all__ = ['SampleLogs', 'SubRuns']


def _coerce_to_ndarray(value):
    r"""
    Cast input subrun lists into a numpy array

    Parameters
    ----------
    value: int, list np.ndarray, ~pyrs.dataobjects.sample_logs.SubRuns,

    Returns
    -------
    np.ndarray
    """
    if isinstance(value, np.ndarray):
        return value
    elif isinstance(value, SubRuns):
        return value._value  # pylint: disable=protected-access
    else:
        return np.atleast_1d(value)


class SubRuns(Iterable):
    r"""
    A (mostly) immutable object that allows for getting the index of its arguments.

    Default constructor returns an instance with zero-length subruns. This is the only version of
    subrun that can have its value updated

    Parameters
    ----------
    subruns: list
        A list of subrun numbers
    """

    def __init__(self, subruns=None):
        self._value = np.ndarray((0))
        if subruns is not None:
            self.set(subruns)

    def __getitem__(self, key):
        return self._value[key]

    def __eq__(self, other):
        r"""
        Two SubRuns instances are equal if and only if their subrun list are identical

        Parameters
        ----------
        other: int, list, np.ndarray, ~pyrs.dataobjects.sample_logs.Subruns
            Extended comparison to objects of other type than the SubRun class
        Returns
        -------
        bool
        """
        other = _coerce_to_ndarray(other)
        if other.size != self._value.size:
            return False
        else:
            return np.all(other == self._value)

    def __ne__(self, other):
        r"""
        Two SubRuns instances are different if only if their subrun list are not identical

        Parameters
        ----------
        other: int, list, np.ndarray, ~pyrs.dataobjects.sample_logs.Subruns
            Extended comparison to objects of other type than the SubRun class

        Returns
        -------
        bool
        """
        return not (self.__eq__(other))

    def __iter__(self):
        iterable = self._value.tolist()
        return iterable.__iter__()

    def __repr__(self):
        return repr(self._value)

    def __str__(self):
        return str(self._value)

    @property
    def size(self):
        r"""
        Total number of subruns

        Returns
        -------
        int
        """
        return self._value.size

    @property
    def shape(self):
        return self._value.shape

    @property
    def ndim(self):
        return self._value.ndim

    def __len__(self):
        return self._value.size

    def empty(self):
        r"""
        Assert if the list of subruns is empty

        Returns
        -------
        bool
        """
        return self._value.size == 0

    def set(self, value):
        r"""
        Initialize the list of subruns

        Parameters
        ----------
        value: int, list, np.ndarray, ~pyrs.dataobjects.sample_logs.SubRuns
            Input list of subruns

        Raises
        ------
        RuntimeError
            Attempt to initialize a list that was initialized previously
        RuntimeError
            input subruns are not sorted in increasing order
        """
        value = _coerce_to_ndarray(value)
        if not self.empty():
            if self.__ne__(value):
                raise RuntimeError('Cannot change subruns when non-empty '
                                   '(previous={}, new={})'.format(self._value, value))
        if not np.all(value[:-1] < value[1:]):
            raise RuntimeError('subruns are not sorted in increasing order')
        self._value = value.astype(int)

    def raw_copy(self):
        r"""
        Raw copy of underlying values

        Returns
        -------
        np.ndarray
        """
        return np.copy(self._value)

    def get_indices(self, subruns):
        r"""
        Find index positions in `self._values` matching the numbers contained
        in the input list `subruns`

        When `subruns` is a list, its first and last values must be in  `self._values`

        Examples
        --------
        >>> s = Subruns([1, 2, 3, 4, 5])
        >>> s.get_indices(s)
        array([0, 1, 2, 3, 4])
        >>> s.get_indices(3)
        array([2])
        >>> s.get_indices([4, 5, 1])
        array([3, 4, 0])

        Parameters
        ----------
        subruns: int, list, np.ndarray, ~pyrs.dataobjects.sample_logs.SubRuns

        Returns
        -------
        np.ndarray

        Raises
        ------
        IndexError
            No matching numbers are found
        """
        if self.__eq__(subruns):
            return np.arange(self._value.size)
        else:
            subruns = _coerce_to_ndarray(subruns)
            # look for the single value
            if subruns.size == 1:
                # Find index of array self_value containing the query subruns
                indices = np.nonzero(self._value == subruns[0])[0]
                if indices.size > 0:
                    return indices
            # check that the first and last values are in the array
            elif subruns[0] in self._value and subruns[-1] in self._value:
                return np.searchsorted(self._value, subruns)

        # fall-through is an error
        raise IndexError('Failed to find subruns={} in {}'.format(subruns, self._value))


class SampleLogs(MutableMapping):
    r"""
    Log data for the selected subrun numbers

    Private data structures:
    - list of selected subrun numbers
    - log entries for the selected subrun numbers
    Each log entry must contain a list of same size as the list of selected subrun numbers, so that
    we have one log value for each selected subrun

    Parameters
    ----------
    kwargs: dict
        Map of log names to log data
    """

    SUBRUN_KEY = HidraConstants.SUB_RUNS  # string in the Nexus logs identifying the subrun numbers

    def __init__(self, **kwargs):
        self._data = dict(kwargs)  # data structure containing the log data
        self._subruns = SubRuns()  # list of included subruns
        self._plottable = set([self.SUBRUN_KEY])  # list of log entries that can be plotted

    def __del__(self):
        del self._data
        del self._subruns

    def __delitem__(self, key):
        r"""
        Remove one log entry, including the contents of the `SubRuns` object if so requested

        Parameters
        ----------
        key: str
            Log entry
        """
        if key == self.SUBRUN_KEY:
            self.subruns = SubRuns()  # set to empty subruns
        else:
            del self._data[key]

    def __getitem__(self, key):
        r"""
        Log data for all or for a subset of the sub run numbers

        If `type(key)==str`, then the key is the name of a log value, and this function fetches
        the log values for all subruns contained in `self._subruns`.
        If `type(key)==tuple`, then key is of the form `(name, subruns)` where `name` is the name
        of the log entry, and `subruns` is an instance of either `int`, `list`, `np.ndarray`,
        or `SubRuns`. This function will fetch the log values for the subruns numbers contained
        in `subruns`.

        Examples
        --------
        >>> sample_logs['sub-runs']
        array([1, 2, 3, 8, 9])  # all subrun numbers stored in sample_logs objects
        >>> sample_logs['vx']
        array([3.456, 4.324, 5.889, 23.925, 24.572])  # vx coordinates for all stored subrun numbers
        >>> sample_logs[('vx', [0, 1, 2])]
        array([3.456, 4.324, 5.889])  # vx coordinates for subrun numbers 1, 2, and 3
        >>> sample_logs[('sub-runs', [0, 1, 2])]
        RuntimeError: Cannot use __getitem__ to get subset of subruns

        Parameters
        ----------
        key: str, tuple

        Returns
        -------
        np.ndarray

        Raises
        ------
        RuntimeError
            when requesting a subset of subruns
        """
        if isinstance(key, tuple):
            key, subruns = key
        else:
            subruns = None

        if key == self.SUBRUN_KEY:
            if subruns:  # Example: key == ('sub-runs', [0, 1, 2])  request the first three subrun numbers
                raise RuntimeError('Cannot use __getitem__ to get subset of subruns')
            return self._subruns
        else:
            if (subruns is None) or self.matching_subruns(subruns):
                return self._data[key]  # all log values contained for this log entry
            else:
                # log values for this log entry and for the requested subrun numbers
                return self._data[key][self.get_subrun_indices(subruns)]

    def __iter__(self):
        r"""
        Iterate over the names of the log entries

        Returns
        -------
        dict_keyiterator
        """
        return iter(self._data)

    def __len__(self):
        r"""
        Number of log entries

        Returns
        -------
        int
        """
        # does not include subruns
        return len(self._data)

    def __setitem__(self, key, value):
        r"""
        Initialize/update the subruns instance, or insert/update the value of a log entry

        `value` is coerced into a numpy array, which could be a one-item array if passing an int of float.

        Parameters
        ----------
        key: str
            Name of the log value, or dedicated string 'sub-runs'
        value: int, flat, list, np.ndarray, ~pyrs.dataobjects.sample_logs.Subruns
            A list of subrun numbers of the values of a log entry

        Raises
        ------
        ValueError
            Attempt to insert/update the value of a log entry prior to initialization of the
            selected subruns list
        ValueError
            Attempt to insert/update the value of a log entry with a list of different size
            then the selected subruns list
        """
        value = _coerce_to_ndarray(value)
        if key == self.SUBRUN_KEY:
            self.subruns = SubRuns(value)  # use full method
        else:
            if self._subruns.size == 0:
                raise RuntimeError('Must set subruns first')
            elif value.size != self.subruns.size:
                raise ValueError('Number of values[{}] isn\'t the same as number of '
                                 'subruns[{}]'.format(value.size, self.subruns.size))
            self._data[key] = value
            # add this to the list of plottable parameters
            if value.dtype.kind in 'iuf':  # int, uint, float
                self._plottable.add(key)

    def plottable_logs(self):
        r"""
        List of names of all the logs that are to be plotted

        This list always includes ~pyrs.projectfile.HidraConstants.SUB_RUNS
        in addition to all the other plottable logs

        Returns
        -------
        list
        """
        return list(self._plottable)

    def constant_logs(self, atol=0.):
        r"""
        List of log names for logs having a constant value

        Parameters
        ----------
        atol: float
            Log values to be plotted having a stddev smaller than `atol` (inclusive) will be
            considered as constant

        Returns
        -------
        list
        """
        result = list()
        # plottable logs are the numeric ones
        for key in sorted(self.keys()):
            if key == self.SUBRUN_KEY:
                continue
            elif key in self._plottable:  # plottable logs contain numbers
                if self._data[key].std() <= atol:
                    result.append(key)
            elif np.alltrue(self._data[key] == self._data[key][0]):  # all values are equal
                result.append(key)
        return result

    @property
    def subruns(self):
        r"""
        List of selected subruns

        Returns
        -------
        ~pyrs.dataobjects.sample_logs.SubRuns
        """
        return self._subruns

    @subruns.setter
    def subruns(self, value):
        r"""
        Initialize the list of selected subruns

        RuntimeError
            Attempt to initialize a list that was initialized previously
        RuntimeError
            input subruns are not sorted in increasing order
        """
        self._subruns.set(value)

    def matching_subruns(self, subruns):
        r"""
        Compare the list of selected subruns to an input list of subrun numbers

        Parameters
        ----------
        subruns: int, list, np.ndarray, ~pyrs.dataobjects.sample_logs.SubRuns

        Returns
        -------
        bool
        """
        return self._subruns == subruns

    def get_subrun_indices(self, subruns):
        r"""
        Find index positions in the list of selected subruns matching the numbers contained
        in the input list `subruns`

        When `subruns` is a list, its first and last values must be in the list of selected
        subruns

        Examples
        --------
        >>> s = SampleLogs()
        >>> s.subruns = [1, 2, 3, 4, 5]
        >>> s.get_indices(s)
        array([0, 1, 2, 3, 4])
        >>> s.get_indices(3)
        array([2])
        >>> s.get_indices([4, 5, 1])
        array([3, 4, 0])

        Parameters
        ----------
        subruns: int, list, np.ndarray, ~pyrs.dataobjects.sample_logs.SubRuns

        Returns
        -------
        np.ndarray

        Raises
        ------
        IndexError
            No matching numbers are found
        """
        return self._subruns.get_indices(subruns)

    def get_pointlist(self, subruns=None) -> 'PointList':
        r"""
        Create a ~pyrs.dataobjects.sample_logs.PointList instance from the vx, vy, and vz logs

        Parameters
        ----------
        subruns: int, list, np.ndarray, ~pyrs.dataobjects.sample_logs.SubRuns
            Create a :py:obj:`PointList` instance using the vx, vy, and vz values associated
            to this list of subrun numbers.

        Returns
        -------
        ~pyrs.dataobjects.sample_logs.PointList

        Raises
        ------
        ValueError
            One of more of logs vx, vy, or vz are missing in this sample logs
        """
        VX, VY, VZ = 'vx', 'vy', 'vz'

        # check the values exist
        missing = []
        for logname in (VX, VY, VZ):
            if logname not in self:
                missing.append(logname)
        if missing:
            raise ValueError('Failed to find positions in logs. Missing {}'.format(', '.join(missing)))

        # create a PointList on the fly
        # passing the subruns down allow for slicing/selecting
        return PointList([self[VX, subruns], self[VY, subruns], self[VZ, subruns]])


class _DirectionExtents(NamedTuple):
    min: float  # minimum value of the sample coordinate along one particular direction
    max: float  # maximum value of the sample coordinate along one particular direction
    delta: float  #


class DirectionExtents(_DirectionExtents):
    r"""
    Spacing parameters for sample positions sampled along a particular direction.

    Two sample positions are deemed the same if they differ by less than some distance, here a
    class attribute termed 'precision'.

    Attributes:
        min: minimum sample position sampled
        max: maximum sample position sampled
        delta: average spacing between unique sample positions sampled
    """

    def __new__(cls, coordinates: List[float], resolution=DEFAULT_POINT_RESOLUTION):
        r"""
        Find the minimum, maximum, and spacing in a list of coordinates.

        Parameters
        ----------
        coordinates: list
        resolution: float
            Two coordinates are considered the same if their distance is less than this value.
        """
        coordinates_floored = [resolution * int(x / resolution) for x in coordinates]
        coordinates_floored_count = len(set(coordinates_floored))
        # `delta` is the spacing between unique coordinates. Use resolution if only one unique coordinate
        if coordinates_floored_count == 1:
            min_coord = max_coord = np.average(coordinates)
            delta = resolution
        else:
            min_coord = np.min(coordinates)
            max_coord = np.max(coordinates)
            delta = (max_coord - min_coord) / (coordinates_floored_count - 1)
        extents_tuple = super(DirectionExtents, cls).__new__(cls, min_coord, max_coord, delta)
        super(DirectionExtents, cls).__setattr__(extents_tuple, '_numpoints', coordinates_floored_count)
        super(DirectionExtents, cls).__setattr__(extents_tuple, '_resolution', resolution)
        return extents_tuple

    @property
    def numpoints(self):
        r"""
        Number of centerpoints, where the mininum and maximum extents are the first and last center-points.
        """
        return self._numpoints

    @property
    def number_of_bins(self):
        r"""
        Number of spacings separating consecutive bin boundaries.
        """
        return self._numpoints  # same as number of center points

    @property
    def resolution(self):
        r"""
        Discriminating distance to assert if two original coordinate values are one and the same.
        """
        return self._resolution  # same as number of center points

    def to_createmd(self, input_units: str = 'mm', output_units: str = 'mm') -> str:
        r"""
        Minimum and maximum extents to be passed as argument Extent of Mantid algorithm
        `CreateMDWorkspace <https://docs.mantidproject.org/nightly/algorithms/CreateMDWorkspace-v1.html>`_.

        Input extents for CreateMDWorkspace become the first and last bin boundaries, and the
        minimum and maximum extents are the first and last center-points

        Note: precision is limited to three decimal places.

        Parameters
        ----------
        input_units: str
            Units of the direction extents
        output_units: str
            Units of the output extents

        Returns
        -------
        str
        """
        factors = {'mm_to_mm': 1., 'm_to_m': 1., 'm_to_mm': 1.e3, 'mm_to_m': 1.e-3}
        f = factors[input_units + '_to_' + output_units]
        pair_template = {'m': '{0: .6f},{1: .6f}', 'mm': '{0: .3f},{1: .3f}'}[output_units]
        pair = pair_template.format(f * self.min - f * self.delta / 2, f * self.max + f * self.delta / 2)
        pair = pair.replace(' ', '')  # remove white-spaces
        # deal with corner case having zero with a negative sign
        zero = {'m': '0.000000', 'mm': '0.000'}[output_units]  # different precision
        pair = pair.replace('-' + zero, zero)
        return pair

    def to_binmd(self, input_units: str = 'mm', output_units: str = 'mm') -> str:
        r"""
        Binning parameters to be passed as one of the AlignedDimX arguments of Mantid algorithm
        `BinMD <>`_.

        Note: precision is limited to three decimal places.

        input_units: str
            Units of the direction extents
        output_units: str
            Units of the output extents

        Returns
        -------
        str
        """
        extents = self.to_createmd(input_units=input_units, output_units=output_units)
        return f'{extents},{self.number_of_bins}'.replace(' ', '')


ExtentTriad = Tuple[DirectionExtents, DirectionExtents, DirectionExtents]  # a shortcut


class PointList:
    ATOL: float = 0.01

    class _PointList(NamedTuple):
        r"""Data structure containing the list of coordinates. Units are in milimeters."""
        vx: List[float]  # coordinates stored in log name HidraConstants.SAMPLE_COORDINATE_NAMES[0]
        vy: List[float]  # coordinates stored in log name HidraConstants.SAMPLE_COORDINATE_NAMES[1]
        vz: List[float]  # coordinates stored in log name HidraConstants.SAMPLE_COORDINATE_NAMES[2]

    @staticmethod
    def tolist(input_source: Union[SampleLogs, List[List[float]], Iterable]) \
            -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        r"""
        Cast coordinate points of some input data structure into a list of numpy arrays.

        This function makes sure we initialize a `_PointList` namedtuple with a list of list

        Parameters
        ----------
        input_source: SampleLogs, list, np.ndarray

        Returns
        -------
        list
            A three item list, where each item are the coordinates of the points along one of the three
            dimensions
        """
        if isinstance(input_source, list) or isinstance(input_source, tuple):
            return (np.asarray(input_source[0], dtype=float),
                    np.asarray(input_source[1], dtype=float),
                    np.asarray(input_source[2], dtype=float))
        elif isinstance(input_source, SampleLogs):
            return tuple([np.asarray(input_source[name]) for name  # type: ignore
                          in HidraConstants.SAMPLE_COORDINATE_NAMES])
        elif isinstance(input_source, np.ndarray):
            if input_source.shape[0] != 3:
                raise RuntimeError('Cannot unpack ndarray with shape {}'.format(input_source.shape))
            return (input_source[0], input_source[1], input_source[2])
        raise RuntimeError(f'Could not convert {input_source} to a tuple of ndarray.')

    def __init__(self, input_source: Union[SampleLogs, List[List[float]], Iterable]) -> None:
        r"""
        List of sample coordinates.

        - Units are set to milimeters always.
        - point_list.vx returns the list of coordinates along the first axis
        - point_list[42] return the (vx, vy, vz) coordinates of point 42
        - point_list.coordinates retuns a numpy array of shape (number_points, 3)
        - Iteration iterates over each point, not over each direction.

        Parameters
        ----------
        input_source: ~pyrs.dataobjects.sample_logs.SampleLogs, ~collections.abc.Iterable
            data structure containing the values of the coordinates for each direction.
        """
        coordinates = PointList.tolist(input_source)

        # A few validation on the coordinates before assignment to attributes
        assert len(coordinates) == 3, 'One set of coordinates is required for each direction'
        assert len(set([len(c) for c in coordinates])) == 1, 'Directions have different number of coordinates'
        for coordinates_along_axis in coordinates:  # coordinates must have
            assert np.all(np.isfinite(coordinates_along_axis)), 'some coordinates do not have finite values'

        self._vx: np.ndarray = coordinates[0]
        self._vy: np.ndarray = coordinates[1]
        self._vz: np.ndarray = coordinates[2]

    def __len__(self) -> int:
        return len(self._vx)  # assumed all the three directions have the same number of coordinate values

    @property
    def vx(self):
        return self._vx

    @property
    def vy(self):
        return self._vy

    @property
    def vz(self):
        return self._vz

    def __getitem__(self, item: Union[int, str]) -> Tuple[float, float, float]:
        r"""Enable self[0],... self[N] as well as making this class iterable over the 3D points."""
        key = to_int('item', item, min_value=0, max_value=len(self) + 1)
        return (self._vx[key], self._vy[key], self._vz[key])

    def __eq__(self, other) -> bool:
        # default implementation of __ne__ is to not the call to __eq__
        # this is not current resilient against points in different order
        if len(self) != len(other):
            return False

        if (len(self.vx) != len(other.vx)) or (len(self.vy) != len(other.vy)) or (len(self.vz) != len(other.vz)):
            return False

        return np.allclose(self.vx, other.vx, atol=self.ATOL) and np.allclose(self.vy, other.vy, atol=self.ATOL) \
            and np.allclose(self.vz, other.vz, atol=self.ATOL)

    def is_contained_in(self, other: 'PointList', resolution: float = DEFAULT_POINT_RESOLUTION) -> bool:
        r"""
        For every point in the list, check that a point in the other list exist within
        a distance smaller than the resolution.

        Parameters
        ----------
        other: ~pyrs.dataobjects.sample_logs.PointList
        resolution: float
            Two points are considered the same if they are separated by a distance smaller than this quantity.

        Returns
        -------
        bool
        """
        # For every self.coordinate, find the closest neighbor in other.coordinates
        distances, other_indexes = cKDTree(other.coordinates).query(self.coordinates, k=1)
        return bool(np.all(distances < resolution))

    def is_equal_within_resolution(self, other: 'PointList', resolution: float = DEFAULT_POINT_RESOLUTION) -> bool:
        r"""
        Check two lists are equal within resolution by checking that the other list is contained in the
        current list, and viceversa.

        It is not required that the two lists have equal length, because either list may contain
        redundant points (points within resolution)

        Parameters
        ----------
        other: ~pyrs.dataobjects.sample_logs.PointList
        resolution: float
            Two points are considered the same if they are separated by a distance smaller than this quantity

        Returns
        -------
        bool
        """
        return self.is_contained_in(other, resolution=resolution) \
            and other.is_contained_in(self, resolution=resolution)

    @property
    def coordinates(self) -> np.ndarray:
        r"""
        Array of point coordinates with shape (number_points, 3)

        Returns
        -------
        numpy.ndarray
        """
        return np.array([self.vx, self.vy, self.vz]).transpose()

    def coordinates_along_direction(self, direction: Union[int, str]):
        r"""
        Coordinate values along one of the three directions.

        Parameters
        ----------
        direction: int, str
            Either a number from 0 to 2 or a string, one of 'vx', 'vy', or 'vz'

        Returns
        -------
        np.ndarray
            1D array with shape (number of points,)
        """
        int_to_attr = ('vx', 'vy', 'vz')
        if isinstance(direction, int):
            direction = int_to_attr[direction]
        return getattr(self, direction)

    def coordinates_irreducible(self, resolution: float = DEFAULT_POINT_RESOLUTION) -> np.ndarray:
        r"""
        Array of point coordinates where dimensions orthogonal to a linear or surface scan are removed.

        For linear scans, the coordinates are 1D, and for surface scans the coordinates are 2D.

        Parameters
        ----------
        resolution: float
            Two coordinates are considered the same if their distance is less than this value. Determines the
            coordinate increment in the extents.

        Returns
        -------
        ~numpy.ndarray
            Array with shape = (number of scanned points, D), where D is one for linear scans, 2 for surface scans,
            and 3 for volume scans.
        """
        direction_coordinates = list()
        for direction_index, extent in enumerate(self.extents(resolution=resolution)):
            if extent.numpoints == 1:
                continue  # discard this dimension
            direction_coordinates.append(self.coordinates_along_direction(direction_index))
        return np.array(direction_coordinates).transpose()

    def linear_scan_vector(self, resolution: float = DEFAULT_POINT_RESOLUTION) -> Optional[np.ndarray]:
        r"""
        For linear scans, find the direction of the scan.

        A `PointList` represents a linear scan when two of the vx, vy, and vz directions contain
        only a unique value that can discerned given a `resolution`.

        Parameters
        ----------
        resolution: float
            Two coordinates are considered the same if their distance is less than this value.

        Returns
        -------
        np.ndarray, None
        """
        values_count = [extent.numpoints for extent in self.extents(resolution=resolution)]
        if values_count.count(1) == 2:  # two directions have only one unique value
            direction_vector = [0, 0, 0]  # initialize the vector pointing along the direction of the linear scan
            for direction_index in range(3):  # probe each of the vx, vy, and vz directions
                if values_count[direction_index] > 1:
                    direction_vector[direction_index] = 1  # e.g. [1, 0, 0] if linear scan along vx
                    return np.array(direction_vector)
        return None  # the list of points do not represent a linear scan

    def aggregate(self, other: 'PointList') -> 'PointList':
        r"""
        Bring the points from other list into the list of points. Because points are ordered,
        this operation is not commutative.

        The order of the combined points is the order of points in the first list, followed by the
        points from the second list as originally ordered.

        Parameters
        ----------
        other: ~pyrs.dataobjects.sample_logs.PointList

        Returns
        -------
        ~pyrs.dataobjects.sample_logs.PointList
        """
        return PointList((np.concatenate((self._vx, other._vx)),
                          np.concatenate((self._vy, other._vy)),
                          np.concatenate((self._vz, other._vz))))

    def cluster(self, resolution: float = DEFAULT_POINT_RESOLUTION) -> List[List]:
        r"""
        Cluster the points according to mutual euclidean distance.

        The return value is a list with as many elements as clusters. Each list element represents one
        cluster, and is made up of a list of point-list indexes, specifying the sample points belonging
        to one cluster.

        The returned list is sorted by the length of the list items, with the longest list item being the
        first. Each list item is sorted by increasing point-list index.

        Parameters
        ----------
        resolution: float
            Two points are considered the same if they are separated by a distance smaller than this quantity

        Returns
        -------
        list
        """
        # fclusterdata returns a vector T of length equal to the number of points. T[i] is the cluster number to
        # which point i belongs. Notice that cluster numbers begin at 1, not 0.
        cluster_assignments = fclusterdata(self.coordinates, resolution, criterion='distance', method='single')
        # variable `clusters` is a list of lists, each list-item containing the point-list indexes for one cluster
        clusters: List[List] = [[] for _ in range(max(cluster_assignments))]
        for point_index, cluster_number in enumerate(cluster_assignments):
            clusters[cluster_number - 1].append(point_index)
        # Sort the clusters by size (i.e, sort the list items by list length)
        clusters = sorted(clusters, key=lambda x: len(x), reverse=True)
        # Sort the points indexes within each cluster according to increasing index
        return [sorted(indexes) for indexes in clusters]

    def has_overlapping_points(self, resolution: float = DEFAULT_POINT_RESOLUTION) -> bool:
        r"""
        Find if two or more sample points are closer than `resolution

        Parameters
        ----------
        resolution: float
            Two points are considered the same if they are separated by a distance smaller than this quantity

        Returns
        -------
        bool
        """
        largest_cluster = self.cluster(resolution=resolution)[0]  # the first cluster is the largest
        if len(largest_cluster) > 1:
            return True
        return False

    def intersection_aggregated_indexes(self, other: 'PointList',
                                        resolution: float = DEFAULT_POINT_RESOLUTION) -> List:
        r"""
        Bring the points from another list and find the indexes of the aggregated point list
        corresponding to the common points.

        Two points are considered common if they are within a certain distance. Both points are kept when
        returning the common points.

        Parameters
        ----------
        other: ~pyrs.dataobjects.sample_logs.PointList
        resolution: float
            Two points are considered the same if they are separated by a distance smaller than this quantity

        Returns
        -------
        list
        """
        all_points = self.aggregate(other)
        clusters = all_points.cluster(resolution=resolution)
        # Find the clusters having more than one index. These clusters contain common elements
        points_common_indexes = list()
        for point_indexes in clusters:
            if len(point_indexes) == 1:
                break
            points_common_indexes.extend(point_indexes)
        return sorted(points_common_indexes)

    def intersection(self, other: 'PointList', resolution: float = DEFAULT_POINT_RESOLUTION) -> 'PointList':
        r"""
        Bring the points from another list and find the points common to both lists.

        Two points are considered common if they are within a certain distance. Both points are kept when
        returning the common points.

        Parameters
        ----------
        other: ~pyrs.dataobjects.sample_logs.PointList
        resolution: float
            Two points are considered the same if they are separated by a distance smaller than this quantity

        Returns
        -------
        ~pyrs.dataobjects.sample_logs.PointList
        """
        points_common_indexes = self.intersection_aggregated_indexes(other, resolution=resolution)
        # common_points_coordinates.shape == number_common_points x 3
        common_points_coordinates = self.aggregate(other).coordinates[points_common_indexes]
        return PointList(common_points_coordinates.transpose())  # needed (3 x number_common_points) shaped array

    def fuse_aggregated_indices(self, other: 'PointList',
                                resolution: float = DEFAULT_POINT_RESOLUTION,
                                single_value: bool = True) -> List:
        r"""
        Add the points from two lists and find the indexes of the aggregated point list
        corresponding to non redundant points.

        When two points are within a small distance from each other, one point is redundant and can be discarded.

        Parameters
        ----------
        other: ~pyrs.dataobjects.sample_logs.PointList
        resolution: float
            Two points are considered the same if they are separated by a distance smaller than this quantity
        single_values: bool
            Return only the lowest index for each cluster

        Returns
        -------
        list
        """
        # combine all points into a single long list with the first points having the lower indices
        all_points = self.aggregate(other)
        # create clusters of all points that are within ``resolution`` distance of each other
        clusters = all_points.cluster(resolution=resolution)

        if single_value:
            # Pick only the first point out of each cluster
            return sorted([point_indexes[0] for point_indexes in clusters])
        else:
            return sorted(clusters)

    def fuse_with(self, other: 'PointList', resolution: float = DEFAULT_POINT_RESOLUTION) -> 'PointList':
        r"""
        Add the points from two lists and discard redundant points.

        When two points are within a small distance from each other, one point is redundant and can be discarded.

        Parameters
        ----------
        other: ~pyrs.dataobjects.sample_logs.PointList
        resolution: float
            Points separated by less than this quantity are considered the same point. Units are mili meters.

        Returns
        -------
        ~pyrs.dataobjects.sample_logs.PointList
        """
        points_unique_indices = self.fuse_aggregated_indices(other, resolution=resolution)
        # points_unique_coordinates.shape == number_common_points x 3
        points_unique_coordinates = self.aggregate(other).coordinates[points_unique_indices]
        return PointList(points_unique_coordinates.transpose())  # needed (3 x number_common_points) shaped array

    def extents(self, resolution=DEFAULT_POINT_RESOLUTION) -> ExtentTriad:
        r"""
        Extents along each direction. Each extent is composed of the minimum and maximum coordinates,
        as well a coordinate increment.

        A resolution distance is needed to discriminate among coordinate values that are considered
        too close. Two coordinates within a `resolution` distance are considered one and the same.
        The number of unique coordinate values is used to determine the coordinate increment.

        Parameters
        ----------
        resolution: float
            Two coordinates are considered the same if their distance is less than this value.

        Returns
        -------
        list
            three-item list, where each item is an object of type ~pyrs.dataobjects.sample_logs.DirectionExtents.
        """
        return DirectionExtents(self.vx, resolution=resolution),\
            DirectionExtents(self.vy, resolution=resolution),\
            DirectionExtents(self.vz, resolution=resolution)

    def linspace(self, resolution: float = DEFAULT_POINT_RESOLUTION) -> List[np.ndarray]:
        r"""
        Evenly spaced coordinates over each of the direction, using the `extents`

        Uses ~numpy.linspace

        Parameters
        ----------
        resolution: float
            Two coordinates are considered the same if their distance is less than this value. Determines the
            coordinate increment in the extents.

        Returns
        -------
        list
            A three-item list where each item is a list of evenly spaced coordinates, one item per direction.
        """
        extents = self.extents(resolution=resolution)
        return [np.linspace(extent.min, extent.max, num=extent.numpoints, endpoint=True) for extent in extents]

    def mgrid(self, resolution: float = DEFAULT_POINT_RESOLUTION, irreducible: bool = False) -> np.ndarray:
        r"""
        Create a regular 3D point grid, using the `extents`.

        Uses ~numpy.mgrid

        Parameters
        ----------
        resolution: float
            Two coordinates are considered the same if their distance is less than this value. Determines the
            coordinate increment in the extents.
        irreducible: bool
            For surface and linear scans, discard the dimensions orthogonal to the scan direction or surface.

        Returns
        -------
        ~numpy.ndarray
            A three item array, where each items is an array specifying the value of each
            coordinate (vx, vy, or vz) at the points of the regular grid
        """
        epsilon = 1.e-09  # ensures extent.max is included in each slice
        slices = list()
        for extent in self.extents(resolution=resolution):
            if extent.numpoints == 1 and irreducible is True:
                continue  # discard this dimension
            slices.append(slice(extent.min, extent.max + epsilon, extent.delta))
        return np.mgrid[slices]

    def grid_point_list(self, resolution: float = DEFAULT_POINT_RESOLUTION) -> 'PointList':
        r"""
        Using the extents of the list, create a new `PointList` filling the points of the regular grid
        constructed using the extents.

        Parameters
        ----------
        resolution: float
            Two coordinates are considered the same if their distance is less than this value.

        Returns
        -------
        ~pyrs.dataobjects.sample_logs.PointList
        """
        grid = self.mgrid(resolution=resolution)
        scan_dimension = grid.ndim - 1  # 3 for volume, 2 for surface, and 1 for linear scans
        permutation = list(range(1, scan_dimension + 1)) + [0]  # move the (vx, vy, vz) selector to the end
        vx_vy_vz = np.transpose(grid, permutation).reshape(-1, 3).T  # shape = (3, number points)
        return PointList(vx_vy_vz)

    def is_a_grid(self, resolution: float = DEFAULT_POINT_RESOLUTION) -> bool:
        r"""
        Check that the points fill the regular 3D grid created by the extents of the points.

        Parameters
        ----------
        resolution: float
            Two coordinates are considered the same if their distance is less than this value. Determines the
            coordinate increment in the extents.

        Returns
        -------
        bool
        """
        other_list = self.grid_point_list(resolution=resolution)
        return self.is_equal_within_resolution(other_list)


def aggregate_point_lists(*args):
    r"""
    Aggregate a number of ~pyrs.dataobjects.sample_logs.PointList objects into one.

    Returns
    -------
    ~pyrs.dataobjects.sample_logs.PointList
    """
    assert len(args) > 1, 'We need at least two PointList objects to aggregate'
    for arg in args:
        assert isinstance(arg, PointList), 'one of the arguments to aggreage_point_list is not a PointList object'
    aggregated_points = args[0]  # start with the point list of the first scalar field
    for point_list in args[1:]:
        aggregated_points = aggregated_points.aggregate(point_list)  # aggregate remaining lists, one by one
    return aggregated_points
