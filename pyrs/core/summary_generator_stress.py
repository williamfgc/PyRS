"""
This module generates reduction summary for stress in plain text CSV file
"""
from typing import Optional

from pyrs.dataobjects.fields import StressField
from pyrs.dataobjects.fields import StrainField
from builtins import int, isinstance
from pyrs.peaks.peak_collection import PeakCollection
import math


class SummaryGeneratorStress:
    """
        Generates a CSV summary from stress fields inputs from multiple project files on a grid point basis.
        From user story `for Grid Information CSV Output
        <github.com/neutrons/PyRS/blob/master/docs/planning/UserStory_GridInformation_CSVOutputs.md>`_
    """

    directions = ['11', '22', '33']
    fields_3dir = ['d', 'FWHM', 'Peak_Height', 'Strain', 'Stress']

    def __init__(self, filename: str, stress: StressField):
        """Initialization

        Parameters
        ----------
        filename: str
            Name of the '.csv' file to write
        stress: StressField
            stress field input to generate summary or full csv files
        """
        # do file name checks
        if not filename:
            raise RuntimeError('Failed to supply output filename for Stress CSV output')

        self._error_postfix = ' when creating stress file: ' + str(filename) + '\n'

        if not filename.endswith('.csv'):
            raise RuntimeError('File name must end with extension ".csv"' + self._error_postfix)

        # check for length of lists
        self._filename: str = str(filename)

        if isinstance(stress, StressField) is False:
            raise RuntimeError(
                'Error: stress input must be of type StressField in SummaryGeneratorStress constructor '
                + self._error_postfix)

        self._stress = stress
        self._strain33_is_calculated = False

        # check for filenames in StrainField per direction
        for direction in SummaryGeneratorStress.directions:
            strain = self._get_strain_field(direction)
            assert isinstance(strain, StrainField)

            # add exception if filenames is empty for 11 and 22 directions
            if not strain.filenames:
                if direction == '11' or direction == '22':
                    raise RuntimeError('StrainField filenames in direction ' + str(direction) +
                                       ' can\'t be empty for Stress CSV output ' + self._filename)
                elif direction == '33':
                    self._strain33_is_calculated = True

    def _write_csv_header(self, handle):
        """
          write projects names, peak_tags, Young's modulus and Poisson ratio
        """
        header = ''

        for direction in SummaryGeneratorStress.directions:
            strain = self._get_strain_field(direction)
            assert isinstance(strain, StrainField)

            if direction == '33' and self._strain33_is_calculated:
                line = '# Direction 33: calculated\n'

            else:
                line = '# Direction ' + str(direction) + ': '
                for filename in strain.filenames:
                    run_number = filename[filename.index('HB2B_') + 5: filename.index('.h5')]
                    line += str(run_number) + ', '

                line = line[:-2] + '\n'

            header += line

        header += '# E: ' + str(self._stress.youngs_modulus) + '\n'
        header += '# v: ' + str(self._stress.poisson_ratio) + '\n'

        handle.write(header)

    def write_summary_csv(self):
        """
            Public function to generate a summary csv file for stress and input fields
        """
        def _write_summary_csv_column_names(handle):
            column_names = 'vx, vy, vz, d0, d0_error, '
            # directional variables
            for field_3dir in SummaryGeneratorStress.fields_3dir:
                for direction in SummaryGeneratorStress.directions:
                    column_names += field_3dir + '_Dir' + direction + ', '
                    column_names += field_3dir + '_Dir' + direction + '_error, '

            column_names = column_names[:-2] + '\n'
            handle.write(column_names)
            return

        def _write_summary_csv_body(handle):

            def _write_number(number) -> str:
                if math.isnan(number):
                    return ', '
                return str(number) + ', '

            def _write_field_3d(row: int, field: str):
                """
                   Writes 3 dimensional entries as value, error pairs per dimension
                   for an input field in a row
                   Args:
                       row: row index for a particular value and error array
                       field: name of the field from SummaryGeneratorStress.fields_3dir
                """
                entries = ''
                for direction in SummaryGeneratorStress.directions:
                    if field == 'Strain':
                        # TODO add check for strain?
                        strain = self._get_strain_field(direction)
                        assert(isinstance(strain, StrainField))

                        strain_value = strain.values[row]
                        strain_error = strain.errors[row]
                        entries += _write_number(strain_value) + _write_number(strain_error)

                    elif field == 'Stress':
                        self._stress.select(direction)
                        stress_value = self._stress.values[row]
                        stress_error = self._stress.errors[row]
                        entries += _write_number(stress_value) + _write_number(stress_error)

                    else:
                        peak_collection = self._get_peak_collection(direction)

                        if field == 'd':
                            # TODO current assumption is that stress and peak collections
                            # arrays for values and errors are of the same size
                            if not isinstance(peak_collection, PeakCollection):
                                entries += ', , '
                            elif row >= len(peak_collection.get_dspacing_center()[0]):
                                entries += ', , '
                            else:
                                d_value = peak_collection.get_dspacing_center()[0][row]
                                d_error = peak_collection.get_dspacing_center()[1][row]
                                entries += _write_number(d_value) + _write_number(d_error)

                        elif field == 'FWHM':

                            if not isinstance(peak_collection, PeakCollection):
                                entries += ', , '
                            elif row >= len(peak_collection.get_effective_params()[0]['FWHM']):
                                entries += ', , '
                            else:
                                fwhm_value = peak_collection.get_effective_params()[0]['FWHM'][row]
                                fwhm_error = peak_collection.get_effective_params()[1]['FWHM'][row]
                                entries += _write_number(fwhm_value) + _write_number(fwhm_error)

                        elif field == 'Peak_Height':

                            if not isinstance(peak_collection, PeakCollection):
                                entries += ', , '
                            elif row >= len(peak_collection.get_effective_params()[0]['Height']):
                                entries += ', , '
                            else:
                                height_value = peak_collection.get_effective_params()[0]['Height'][row]
                                height_error = peak_collection.get_effective_params()[1]['Height'][row]
                                entries += _write_number(height_value) + _write_number(height_error)

                return entries

            # Function starts here
            body = ''

            # write for each row of the CSV body, first coordinates, d0 and
            # then fields in SummaryGeneratorStress.fields_3dir value, error per dimension
            for row, coordinate in enumerate(self._stress.coordinates):

                line = str(coordinate[0]) + ', ' + str(coordinate[1]) + ', ' + str(coordinate[2]) + ', '

                # d0 doesn't depend on direction so just picking the first peak_collection
                for direction in SummaryGeneratorStress.directions:
                    peak_collection = self._get_peak_collection(direction)
                    if not peak_collection:
                        continue

                    if row >= len(peak_collection.get_d_reference()[0]):
                        line += ', , '
                    else:
                        d0_value = peak_collection.get_d_reference()[0][row]
                        d0_error = peak_collection.get_d_reference()[1][row]
                        line += _write_number(d0_value) + _write_number(d0_error)
                        break

                # value error for fields_3dir = ['d', 'FWHM', 'Peak_Height', 'Strain', 'Stress']
                for field_3dir in SummaryGeneratorStress.fields_3dir:
                    line += _write_field_3d(row, field_3dir)

                line = line[:-2] + '\n'

                body += line

            handle.write(body)
            return

        # function starts here
        with open(self._filename, 'w') as handle:
            self._write_csv_header(handle)
            _write_summary_csv_column_names(handle)
            _write_summary_csv_body(handle)

        return

    def _get_strain_field(self, direction: str) -> Optional[StrainField]:
        """
            Returns a StrainField for a particular direction from self._stress
        """
        stress: StressField = self._stress
        stress.select(direction)
        strain = self._stress.strain
        if isinstance(strain, StrainField):
            return strain

        return None

    def _get_peak_collection(self, direction: str) -> Optional[PeakCollection]:
        """
            Returns a peak_collection for a particular direction from self._stress
        """
        strain = self._get_strain_field(direction)
        if isinstance(strain, StrainField):
            return strain.peak_collections[0]

        return None
