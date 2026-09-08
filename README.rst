
***************
LungViZ
***************

LungViZ is an interactive viewer for regional one-dimensional OpenCMISS/CMGUI
meshes, triangulated surfaces, and medical image volumes. It displays
``.exnode``, ``.exelem``, ``.exdata``, STL, and PLY geometry together with
DICOM or NIfTI CT images in a Polyscope window.

Features
--------

* Load each EX mesh or node set into an isolated region with its own identifier namespace.
* Add files to an existing region when its exnode and exelem files are selected separately.
* Inspect original node and element identifiers and 1D connectivity.
* Read grid-based ``Values:`` blocks as fields associated with mesh elements.
* Colour a network by any nodal or element scalar field, vector component, or magnitude.
* Render radius fields as variable-radius tubes with an adjustable display scale.
* Select one or many mesh nodes and move them with the mouse or an exact translation vector.
* Undo, redo, reset, and export edited coordinates to a new ``.exnode`` file.
* Display multi-component fields as Polyscope vectors.
* Overlay ``.exdata`` locations and their fields as point clouds.
* Display standalone ``.exnode`` regions as independent point clouds.
* Load STL and PLY triangle surfaces with independent adjustable opacity.
* Drop supported geometry files directly into the Polyscope window.
* Load a DICOM series folder or NIfTI CT volume using patient/world coordinates.
* Inspect CT intensity on grayscale axial, coronal, and sagittal planes without drawing a solid volume.
* Show, hide, slide, translate, or rotate each CT plane independently, or unload the CT.
* Interactively transform a mesh region to align it with the CT when coordinate frames differ.
* Continue using Polyscope's native picking, camera, screenshot, colour-map, and structure controls.
* Start with free-orientation camera navigation by default.
* Save a named PNG or JPEG screenshot to a chosen folder.

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

Click **Load geometry as new region...** and select the files belonging to one mesh.
Every new-region operation creates a separate node-number namespace, so another
exnode file containing the same node identifiers cannot overwrite that mesh.
If the coordinate and connectivity files are selected at different times, use
**Add files to region...** for the second selection. An exnode-only region is
shown as a point cloud.

The same loader accepts triangulated STL and PLY surface files. Each selected
surface file becomes an independent region with its own **Surface opacity**
slider and alignment transform. Opacity ranges from 0 (transparent) to 1
(opaque) and starts at 0.65 so an EX network or CT slice can remain visible
through the surface. Files can also be dropped directly into the Polyscope
window. LungViZ starts with Polyscope's **Free** camera navigation style; it can
still be changed from the standard View menu.

Use **Colour by** and **Tube radius** for the most common field
visualisations. The standard Polyscope Scene panel exposes every imported
quantity, including node and element identifiers, for detailed inspection.
Element fields are registered on network edges and labelled ``[elements]``. A field
whose name contains ``radius`` is applied automatically, preferring an element
radius when both associations are available. Select ``Constant`` to return to
uniform thickness. Colour only changes the selected colour map; tube radius is
an independent geometric control. Flow is mapped linearly over its data range,
which can be adjusted in Polyscope's Scene panel.

When a flow field is selected, enable **Logarithmic flow colours** to colour by
``log10(flow)``. This spreads values spanning several orders of magnitude across
the colour map while leaving the imported flow values unchanged. Adjust **Flow
colour lower bound** and **Flow colour upper bound** directly below the toggle;
both sliders use the original flow units and update the log10 map range. Any
finite non-positive values use the colour of the smallest positive flow because
a base-10 logarithm is not defined for them. The Polyscope legend is labelled
with the resulting log10 values; for example, 4 represents an original flow of
``10^4``. **Reset flow colour bounds** restores the positive data range.

The **Radius scale** control multiplies the selected radius field for display
without changing the imported data. It uses a logarithmic range from 0.001 to
10 and starts at 0.25 to reduce overlapping rounded capsules at large proximal
branches. Choose **Use physical radius (1 x)** whenever the radius and coordinate
files use compatible units and true physical scale is desired.

For element-based radii, **Smooth tube joins** derives temporary shared node
radii and draws tapered segments so neighbouring vessels meet continuously. The
calculation uses the root-mean-square of incident element radii, retaining more
of the larger vessel at a junction without using oversized maximum-radius joins.
This is purely a rendering option: node coordinates, element connectivity,
imported fields, editing, and exported EX files are unchanged. Turn it off to
restore exact constant-radius cylinders for each element.

Use Polyscope's single **Screenshot** button to choose an explicit PNG or JPEG
filename and folder; ``Ctrl+Shift+S`` opens the same Save As workflow. The
button's adjacent menu still controls its file format and transparent-background
setting. Captures exclude the interface panels.

Enable **Edit nodes / data points** to display pickable handles for a 1D mesh,
standalone EXNODE region, or EXDATA-only region. Click to replace the selection,
Shift-click to add a point, or Ctrl-click to toggle one. The orange selection
has a Polyscope translation gizmo for mouse movement. Enter a ``Translation
delta`` to add the same x, y, z displacement to every selected point; a single
selected point also exposes its absolute position. Connected mesh segments
update without changing their connectivity, and cubic Hermite display samples
are regenerated. Use undo, redo, or reset before choosing **Export edited EX
file...**. Export preserves the loaded file's headers, identifiers, derivatives,
and non-coordinate fields and never overwrites the loaded file.

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
