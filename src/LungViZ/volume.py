"""CT volume loading with patient/world-coordinate transforms."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

import numpy as np


class VolumeLoadError(ValueError):
    """Raised when medical image data cannot be converted to a 3D volume."""


@dataclass
class CTVolume:
    name: str
    source: Path
    values: np.ndarray
    spacing: np.ndarray
    transform: np.ndarray
    display_range: Tuple[float, float]
    warnings: List[str] = field(default_factory=list)

    @property
    def bound_high(self) -> np.ndarray:
        return self.spacing * np.maximum(np.asarray(self.values.shape) - 1, 0)

    @property
    def center_world(self) -> np.ndarray:
        local = np.append(self.bound_high * 0.5, 1.0)
        return (self.transform @ local)[:3]

    @property
    def world_axes(self) -> np.ndarray:
        axes = np.asarray(self.transform[:3, :3], dtype=float)
        norms = np.linalg.norm(axes, axis=0)
        norms[norms == 0] = 1.0
        return axes / norms


def _display_range(values: np.ndarray) -> Tuple[float, float]:
    finite = values[np.isfinite(values)]
    if not finite.size:
        return (0.0, 1.0)
    low, high = np.percentile(finite, [1.0, 99.0])
    if low == high:
        high = low + 1.0
    return float(low), float(high)


def load_nifti(path: str | Path) -> CTVolume:
    """Load a NIfTI image while preserving its voxel-to-world affine."""

    try:
        import nibabel as nib
    except ImportError as exc:  # pragma: no cover - dependency installation issue
        raise VolumeLoadError("NIfTI support requires nibabel") from exc

    source = Path(path).expanduser().resolve()
    try:
        image = nib.load(str(source))
        values = np.asarray(image.get_fdata(dtype=np.float32))
    except Exception as exc:
        raise VolumeLoadError(f"Could not read NIfTI image {source.name}: {exc}") from exc

    warnings: List[str] = []
    if values.ndim > 3:
        warnings.append("The NIfTI image has multiple frames; displaying the first frame")
        values = values[(slice(None), slice(None), slice(None)) + (0,) * (values.ndim - 3)]
    if values.ndim != 3:
        raise VolumeLoadError(f"Expected a 3D NIfTI image, found shape {values.shape}")

    affine = np.asarray(image.affine, dtype=float)
    spacing = np.linalg.norm(affine[:3, :3], axis=0)
    if np.any(spacing <= 0):
        raise VolumeLoadError("NIfTI affine contains a zero voxel spacing")
    transform = np.eye(4, dtype=float)
    transform[:3, :3] = affine[:3, :3] / spacing
    transform[:3, 3] = affine[:3, 3]

    return CTVolume(
        name=source.name.removesuffix(".gz").removesuffix(".nii"),
        source=source,
        values=values,
        spacing=spacing,
        transform=transform,
        display_range=_display_range(values),
        warnings=warnings,
    )


def _first_number(value, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value[0])
    except (TypeError, IndexError):
        return float(value)


def load_dicom_directory(path: str | Path) -> CTVolume:
    """Load one DICOM series and convert stored values to Hounsfield units."""

    try:
        import pydicom
    except ImportError as exc:  # pragma: no cover - dependency installation issue
        raise VolumeLoadError("DICOM support requires pydicom") from exc

    source = Path(path).expanduser().resolve()
    if not source.is_dir():
        raise VolumeLoadError(f"DICOM path is not a directory: {source}")

    datasets = []
    for candidate in sorted(item for item in source.rglob("*") if item.is_file()):
        try:
            dataset = pydicom.dcmread(str(candidate), force=True)
            if hasattr(dataset, "PixelData") and hasattr(dataset, "Rows"):
                datasets.append(dataset)
        except Exception:
            continue
    if not datasets:
        raise VolumeLoadError(f"No readable DICOM image slices found in {source}")

    series = {}
    for dataset in datasets:
        key = str(getattr(dataset, "SeriesInstanceUID", "unknown-series"))
        series.setdefault(key, []).append(dataset)
    warnings: List[str] = []
    if len(series) > 1:
        selected_key, selected = max(series.items(), key=lambda item: len(item[1]))
        ignored = len(datasets) - len(selected)
        warnings.append(
            f"The folder contains {len(series)} DICOM series; loaded the largest "
            f"({selected_key}) and ignored {ignored} image(s)"
        )
        datasets = selected

    first = datasets[0]
    orientation = np.asarray(
        getattr(first, "ImageOrientationPatient", [1, 0, 0, 0, 1, 0]),
        dtype=float,
    )
    if orientation.size != 6:
        raise VolumeLoadError("DICOM ImageOrientationPatient must contain six values")
    x_axis = orientation[:3]
    y_axis = orientation[3:]
    x_axis /= np.linalg.norm(x_axis) or 1.0
    y_axis /= np.linalg.norm(y_axis) or 1.0
    z_axis = np.cross(x_axis, y_axis)
    z_axis /= np.linalg.norm(z_axis) or 1.0

    def projected_position(dataset) -> float:
        position = getattr(dataset, "ImagePositionPatient", None)
        if position is not None:
            return float(np.dot(np.asarray(position, dtype=float), z_axis))
        return float(getattr(dataset, "InstanceNumber", 0))

    datasets.sort(key=projected_position)
    has_patient_positions = all(
        getattr(dataset, "ImagePositionPatient", None) is not None
        for dataset in datasets
    )
    projections = np.asarray([projected_position(dataset) for dataset in datasets])
    if has_patient_positions and len(projections) > 1:
        differences = np.diff(projections)
        nonzero = np.abs(differences[np.abs(differences) > 1e-8])
        slice_spacing = float(np.median(nonzero)) if nonzero.size else 1.0
    else:
        slice_spacing = abs(
            _first_number(
                getattr(first, "SpacingBetweenSlices", None),
                _first_number(getattr(first, "SliceThickness", None), 1.0),
            )
        )
    pixel_spacing = np.asarray(getattr(first, "PixelSpacing", [1.0, 1.0]), dtype=float)
    if pixel_spacing.size != 2:
        raise VolumeLoadError("DICOM PixelSpacing must contain two values")
    spacing = np.asarray([pixel_spacing[1], pixel_spacing[0], slice_spacing], dtype=float)

    arrays = []
    for dataset in datasets:
        try:
            pixels = np.asarray(dataset.pixel_array, dtype=np.float32)
        except Exception as exc:
            raise VolumeLoadError(
                "A DICOM slice could not be decoded. Compressed series may require "
                f"an optional pydicom pixel decoder: {exc}"
            ) from exc
        slope = _first_number(getattr(dataset, "RescaleSlope", None), 1.0)
        intercept = _first_number(getattr(dataset, "RescaleIntercept", None), 0.0)
        arrays.append(pixels * slope + intercept)

    if len(arrays) == 1 and arrays[0].ndim == 3:
        stack = arrays[0]
        warnings.append("Loaded a multi-frame DICOM object")
    elif all(array.ndim == 2 for array in arrays):
        try:
            stack = np.stack(arrays, axis=0)
        except ValueError as exc:
            raise VolumeLoadError("DICOM slices do not have consistent dimensions") from exc
    else:
        raise VolumeLoadError("The DICOM series mixes incompatible frame dimensions")

    values = np.transpose(stack, (2, 1, 0)).astype(np.float32, copy=False)
    position = np.asarray(
        getattr(datasets[0], "ImagePositionPatient", [0, 0, 0]), dtype=float
    )
    transform = np.eye(4, dtype=float)
    transform[:3, :3] = np.column_stack((x_axis, y_axis, z_axis))
    transform[:3, 3] = position

    window_center = getattr(first, "WindowCenter", None)
    window_width = getattr(first, "WindowWidth", None)
    if window_center is not None and window_width is not None:
        center = _first_number(window_center, 0.0)
        width = abs(_first_number(window_width, 1.0))
        display_range = (center - width * 0.5, center + width * 0.5)
    else:
        display_range = (-1000.0, 400.0)

    return CTVolume(
        name=source.name,
        source=source,
        values=values,
        spacing=spacing,
        transform=transform,
        display_range=display_range,
        warnings=warnings,
    )
