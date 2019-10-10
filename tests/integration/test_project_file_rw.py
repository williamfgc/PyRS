from pyrs.core import workspaces
from pyrs.utilities import rs_project_file


def test_rw_raw():
    """Test read a project to workspace and write in the scope of raw data

    Returns
    -------

    """
    raw_project_name = '/home/wzz/Projects/PyRS/tests/testdata/HZB_Raw_Project.hdf'

    # Read to workspace
    source_project = rs_project_file.HydraProjectFile(raw_project_name,
                                                      rs_project_file.HydraProjectFileMode.READONLY)

    # To the workspace
    source_workspace = workspaces.HidraWorkspace('Source HZB')
    source_workspace.load_hidra_project(source_project, load_raw_counts=True,
                                        load_reduced_diffraction=False)

    # Export
    target_project = rs_project_file.HydraProjectFile('HZB_HiDra_Test.hdf',
                                                      rs_project_file.HydraProjectFileMode.OVERWRITE)
    # Experiment data
    source_workspace.save_experimental_data(target_project)

    # Instrument
    target_project.set_instrument_geometry(source_workspace.get_instrument_setup())

    # Save
    target_project.save_hydra_project(True)

    return


if __name__ == '__main__':
    """
    """
    test_rw_raw()
