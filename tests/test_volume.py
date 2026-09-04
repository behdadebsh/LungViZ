from pathlib import Path

import nibabel as nib
import numpy as np
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

from LungViZ.volume import load_dicom_directory, load_nifti


def test_load_nifti_preserves_affine_direction_spacing_and_origin(tmp_path):
    values = np.arange(24, dtype=np.float32).reshape(2, 3, 4)
    affine = np.asarray(
        [
            [-1.0, 0.0, 0.0, 10.0],
            [0.0, 2.0, 0.0, 20.0],
            [0.0, 0.0, 3.0, 30.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )
    path = tmp_path / "scan.nii.gz"
    nib.save(nib.Nifti1Image(values, affine), path)

    volume = load_nifti(path)

    np.testing.assert_allclose(volume.values, values)
    np.testing.assert_allclose(volume.spacing, [1, 2, 3])
    np.testing.assert_allclose(np.diag(volume.transform)[:3], [-1, 1, 1])
    np.testing.assert_allclose(volume.transform[:3, 3], [10, 20, 30])


def _write_dicom_slice(path: Path, z: float, instance: int, pixels: np.ndarray) -> None:
    metadata = FileMetaDataset()
    metadata.MediaStorageSOPClassUID = CTImageStorage
    metadata.MediaStorageSOPInstanceUID = generate_uid()
    metadata.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset = FileDataset(str(path), {}, file_meta=metadata, preamble=b"\0" * 128)
    dataset.SOPClassUID = CTImageStorage
    dataset.SOPInstanceUID = metadata.MediaStorageSOPInstanceUID
    dataset.Modality = "CT"
    dataset.Rows, dataset.Columns = pixels.shape
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 1
    dataset.PixelSpacing = [2.0, 1.0]
    dataset.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    dataset.ImagePositionPatient = [10.0, 20.0, z]
    dataset.InstanceNumber = instance
    dataset.RescaleSlope = 2.0
    dataset.RescaleIntercept = -1000.0
    dataset.PixelData = pixels.astype(np.int16).tobytes()
    dataset.save_as(path, enforce_file_format=True)


def test_load_dicom_sorts_slices_and_converts_to_patient_space_hu(tmp_path):
    _write_dicom_slice(
        tmp_path / "second.dcm", 35.0, 2, np.asarray([[4, 5, 6], [7, 8, 9]])
    )
    _write_dicom_slice(
        tmp_path / "first.dcm", 30.0, 1, np.asarray([[0, 1, 2], [3, 4, 5]])
    )

    volume = load_dicom_directory(tmp_path)

    assert volume.values.shape == (3, 2, 2)
    np.testing.assert_allclose(volume.spacing, [1, 2, 5])
    np.testing.assert_allclose(volume.transform[:3, 3], [10, 20, 30])
    assert volume.values[0, 0, 0] == -1000
    assert volume.values[0, 0, 1] == -992
