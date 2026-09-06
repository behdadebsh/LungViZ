
***************
LungViZ
***************

LungViZ is an interactive viewer for regional one-dimensional OpenCMISS/CMGUI
meshes and medical image volumes. It displays ``.exnode``, ``.exelem``, and
``.exdata`` data together with DICOM or NIfTI CT images in a Polyscope window.

Features
--------

* Load each EX mesh or node set into an isolated region with its own identifier namespace.
* Add files to an existing region when its exnode and exelem files are selected separately.
* Inspect original node and element identifiers and 1D connectivity.
* Read grid-based ``Values:`` blocks as fields associated with mesh elements.
* Colour a network by any nodal or element scalar field, vector component, or magnitude.
* Render element radius fields as variable-radius tubes in physical mesh units.
* Select one or many mesh nodes and move them with the mouse or an exact translation vector.
* Undo, redo, reset, and export edited coordinates to a new ``.exnode`` file.
* Display multi-component fields as Polyscope vectors.
* Overlay ``.exdata`` locations and their fields as point clouds.
* Display standalone ``.exnode`` regions as independent point clouds.
* Load a DICOM series folder or NIfTI CT volume using patient/world coordinates.
* Inspect CT intensity on grayscale axial, coronal, and sagittal planes without drawing a solid volume.
* Show, hide, slide, translate, or rotate each CT plane independently, or unload the CT.
* Interactively transform a mesh region to align it with the CT when coordinate frames differ.
* Continue using Polyscope's native picking, camera, screenshot, colour-map, and structure controls.

Installation
------------

Python 3.9 or newer is required. Create and activate a virtual environment, then
install the minimum runtime requirements and the package::

   python -m venv .venv

On Windows::

   .venv\Scripts\activate

On macOS or Linux::

   source .venv/bin/activate

Then install and run::

   python -m pip install -r requirements.txt
   python -m pip install -e .
   lungviz

You can preload files from the command line::

   lungviz model.exnode model.exelem measurements.exdata

Or try the included small branching airway example::

   lungviz examples/sample.exnode examples/sample.exelem examples/sample.exdata

Usage notes
-----------

Click **Load EX as new region...** and select the files belonging to one mesh.
Every new-region operation creates a separate node-number namespace, so another
exnode file containing the same node identifiers cannot overwrite that mesh.
If the coordinate and connectivity files are selected at different times, use
**Add files to region...** for the second selection. An exnode-only region is
shown as a point cloud.

Use **Colour by** and **Tube radius** for the most common field
visualisations. The standard Polyscope Scene panel exposes every imported
quantity, including node and element identifiers, for detailed inspection.
Element fields are registered on network edges and labelled ``[elements]``. A field
whose name contains ``radius`` is applied automatically, preferring an element
radius when both associations are available. Select ``Constant`` to return to
uniform thickness. Colour only changes the selected colour map; tube radius is
an independent geometric control. Flow is mapped linearly over its data range,
which can be adjusted in Polyscope's Scene panel.

Enable **Edit mesh nodes** to display pickable node handles. Click to replace
the selection, Shift-click to add a node, or Ctrl-click to toggle one. The
orange selection has a Polyscope translation gizmo for mouse movement. Enter a
``Translation delta`` to add the same x, y, z displacement to every selected
node; a single selected node also exposes its absolute position. Connected
segments update without changing their connectivity, and cubic Hermite display
samples are regenerated. Use undo, redo, or reset before choosing **Export
edited EXNODE...**. Export preserves the loaded node file's headers, identifiers,
derivatives, and non-coordinate fields and never overwrites the loaded file.

For CT data, choose **Load DICOM folder...** or **Load NIfTI...**. DICOM pixel
values are converted with their rescale slope/intercept, normally yielding
Hounsfield units. Image orientation, origin, and voxel spacing are retained.
The three grayscale planes start at the volume centre and are hidden by default.
Enable only the views you need, move native slices with their sliders, or use
the selected plane's transform gizmo for an oblique view. Oblique images are
trilinearly resampled as the plane moves. **Unload CT** removes all three planes.
If an EX mesh is in a different coordinate frame, enable its **Alignment
transform gizmo**.

The reader consumes derivative and version parameters correctly. Cubic Hermite
1D coordinate fields are sampled using their first nodal derivatives and
element scale factors, so curved branches are not reduced to endpoint chords.
Other fields display their primary nodal values and are linearly interpolated
over the rendered centreline. Grid-based element fields retain their element
association. Their samples are averaged within each element for edge colour and
radius display; this is exact for element files that repeat one constant value
at both xi endpoints. Field values for element identifiers outside the loaded
connectivity are ignored. Non-1D elements are reported and skipped.
For compressed DICOM transfer syntaxes, pydicom may request an optional pixel
decoder such as pylibjpeg.

Development
-----------

Install the test extra and run the parser/scene tests::

   python -m pip install -e .[test]
   pytest

Format reference: `The CMGUI EX file format guide
<https://opencmiss.org/documentation/apidoc/zinc/docs/CMGUI_ex_fileFormatGuide.html>`_.
