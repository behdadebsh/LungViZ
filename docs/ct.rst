CT slices and alignment
=======================

Open a volume
-------------

* For DICOM, choose **Load DICOM folder...**, navigate into the directory
  containing the series, then choose **Select folder**. LungViZ searches
  inside subfolders. If it finds several series, it loads the one with the
  most readable image files and reports the choice under **CT warnings**.
* For NIfTI, choose **Load NIfTI...**, select a ``.nii`` or ``.nii.gz`` file,
  and choose **Open file**. If it contains multiple frames, LungViZ displays
  the first and reports that choice under **CT warnings**.

LungViZ displays one volume at a time. Loading a new scan replaces the
previous one. The CT panel shows the volume name and dimensions, coordinate
system, voxel-axis directions, origin, and spacing.

Show and move the planes
------------------------

1. Turn on **Show Axial**, **Show Coronal**, or **Show Sagittal**. The three
   planes start at their middle slices with visibility turned off.
2. Move the corresponding **Axial slice**, **Coronal slice**, or
   **Sagittal slice** slider to step through that volume axis.
3. For an oblique section, choose a plane under **Plane to rotate** and enable
   **Plane transform gizmo**. Drag the arrows to translate or the rotation
   handles to tilt it. The grayscale image is resampled as the plane moves.
   You can keep other planes visible while adjusting the selected one.
4. Choose **Reset CT slices** to recreate the middle slices with their native
   orientations and initial hidden visibility. Choose **Unload CT** to
   remove the volume and all three planes.

The viewer uses grayscale slice surfaces. DICOM pixel values are rescaled
using each image's slope and intercept, normally to Hounsfield units. The
initial grayscale range uses the DICOM window when available, or -1000 to 400
otherwise. NIfTI uses the 1st and 99th percentiles of finite voxel values.

Align geometry with the scan
----------------------------

1. Load the mesh or surface and the scan, and show at least two planes so
   you can compare landmarks from more than one direction.
2. Check **Coordinates**, **Voxel axes**, **Origin**, and **Spacing** in the
   CT panel against the convention and units used by your geometry.
3. Select the geometry under **Region**, then enable **Alignment transform
   gizmo**. Use the handles to translate or rotate the region in the scene.
   For a surface overlay, adjust **Surface opacity** so the CT remains visible.
4. Turn off the gizmo when you finish. The alignment transform applies to the
   displayed region, including any measurement overlays in it. EX export uses
   the coordinates stored by the point editor.

Coordinate conventions
~~~~~~~~~~~~~~~~~~~~~~

* DICOM uses LPS patient coordinates. Positive X, Y, and Z point left,
  posterior, and superior, respectively.
* NIfTI with voxel axes containing L, P, and either S or I, including L/P/I,
  is reordered and flipped as needed into L/P/S voxel order. LungViZ updates
  the affine and origin for that voxel order and expresses them in patient LPS.
* Other NIfTI orientations, including R/A/S, keep the stored voxel order and
  RAS+ world affine. Positive RAS+ axes point right, anterior, and superior.

If landmarks appear on opposite sides, compare the reported coordinate
systems before adjusting the alignment. RAS+ and LPS use opposite signs for
the first two world axes. The CT slice sliders follow voxel directions, and
the anatomical labels follow the closest corresponding patient axes.
