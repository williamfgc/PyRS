import traceback
from pyrs.dataobjects.fields import generateParameterField, StressField, StrainField
from pyrs.core.summary_generator_stress import SummaryGeneratorStress
from pyrs.projectfile import HidraProjectFile, HidraProjectFileMode  # type: ignore
from pyrs.core.workspaces import HidraWorkspace
from qtpy.QtCore import Signal, QObject


class Model(QObject):
    propertyUpdated = Signal(str)
    failureMsg = Signal(str, str, str)

    def __init__(self):
        super().__init__()
        self._e11 = None
        self._e22 = None
        self._e33 = None
        self._e11_peaks = dict()
        self._e22_peaks = dict()
        self._e33_peaks = dict()
        self._peakTags = []
        self._selectedPeak = None
        self._stress = None

    def set_workspace(self, name, filename):
        setattr(self, name, filename)

    @property
    def e11(self):
        return self._e11

    @e11.setter
    def e11(self, filename):
        self._e11, self._e11_peaks = self.load_hidra_project_file(filename, '11')
        self._peakTags = list(self._e11_peaks.keys())
        self.propertyUpdated.emit("peakTags")

    @property
    def e11_peaks(self):
        return self._e11_peaks

    @property
    def e22(self):
        return self._e22

    @e22.setter
    def e22(self, filename):
        self._e22, self._e22_peaks = self.load_hidra_project_file(filename, '22')

    @property
    def e22_peaks(self):
        return self._e22_peaks

    @property
    def e33(self):
        return self._e33

    @e33.setter
    def e33(self, filename):
        self._e33, self._e33_peaks = self.load_hidra_project_file(filename, '33')

    @property
    def e33_peaks(self):
        return self._e33_peaks

    @property
    def peakTags(self):
        return self._peakTags

    @property
    def selectedPeak(self):
        return self._selectedPeak

    @selectedPeak.setter
    def selectedPeak(self, tag):
        self._selectedPeak = tag
        self.propertyUpdated.emit("selectedPeak")

    @property
    def d0(self):
        return self.e11_peaks[self.selectedPeak].get_d_reference()[0][0]

    @d0.setter
    def d0(self, d0):
        for peaks in [self.e11_peaks, self.e22_peaks, self.e33_peaks]:
            if self.selectedPeak in peaks:
                peaks[self.selectedPeak].set_d_reference(d0)

    def validate_selection(self, direction):
        if getattr(self, f'e{direction}') is None:
            return f"e{direction} file hasn't been loaded"

        if self.e11 is None:
            return "e11 is not loaded, the peak tags from this file will be used"

        if not self.e11_peaks:
            return "e11 contains no peaks, fit peaks first"

        if self.selectedPeak not in getattr(self, f'e{direction}_peaks'):
            return f"Peak {self.selectedPeak} is not in e{direction}"

    def get_field(self, direction, plot_param, stress_case):
        try:
            if plot_param == "stress":
                self._stress.select(direction)
                return self._stress
            elif plot_param == "strain" and direction == "33" and stress_case == "In-plane stress":
                return self._stress.strain33
            else:
                return generateParameterField(plot_param,
                                              hidraworkspace=getattr(self, f'e{direction}'),
                                              peak_collection=getattr(self, f'e{direction}_peaks')[self.selectedPeak])
        except Exception as e:
            self.failureMsg.emit(f"Failed to generate field for parameter {plot_param} in direction {direction}",
                                 str(e),
                                 traceback.format_exc())
            return None

    def calculate_stress(self, stress_case, youngModulus, poissonsRatio):
        self._stress = StressField(StrainField(hidraworkspace=self.e11,
                                               peak_collection=self.e11_peaks[self.selectedPeak]),
                                   StrainField(hidraworkspace=self.e22,
                                               peak_collection=self.e22_peaks[self.selectedPeak]),
                                   StrainField(hidraworkspace=self.e33,
                                               peak_collection=self.e33_peaks[self.selectedPeak])
                                   if stress_case == "diagonal" else None,
                                   youngModulus, poissonsRatio, stress_case)

    def write_stress_to_csv(self, filename):
        stress_csv = SummaryGeneratorStress(filename, self._stress)
        stress_csv.write_summary_csv()

    def get_default_csv_filename(self):
        runnumbers = [getattr(self._stress, f'strain{d}').peak_collections[0].runnumber for d in ('11', '22', '33')]
        return "HB2B_{}_stress_grid_{}.csv".format('_'.join(str(run) for run in runnumbers if run != -1),
                                                   self.selectedPeak)

    def load_hidra_project_file(self, filename, direction):
        try:
            source_project = HidraProjectFile(filename, mode=HidraProjectFileMode.READONLY)
            ws = HidraWorkspace(direction)
            ws.load_hidra_project(source_project, False, False)
            peaks = dict()
            for peak in source_project.read_peak_tags():
                peaks[peak] = source_project.read_peak_parameters(peak)
            return ws, peaks
        except Exception as e:
            self.failureMsg.emit(f"Failed to load {filename}. Check that this is a Hidra Project File",
                                 str(e),
                                 traceback.format_exc())
            return None, dict()
