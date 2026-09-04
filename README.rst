
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
* Display multi-component fields as Polyscope vectors.
* Overlay ``.exdata`` locations and their fields as point clouds.
* Display standalone ``.exnode`` regions as independent point clouds.
* Load a DICOM series folder or NIfTI CT volume using patient/world coordinates.
* Inspect CT intensity with three initially orthogonal, translatable and rotatable slice planes.
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

Use **Colour field** and **Radius field** for the most common field
visualisations. The standard Polyscope Scene panel exposes every imported
quantity, including node and element identifiers, for detailed inspection.
Element fields are registered on network edges; if an element and nodal field
have the same name, the element version is labelled ``[elements]``. A field
whose name contains ``radius`` is applied automatically, preferring an element
radius when both associations are available. Select ``Constant`` to return to
uniform thickness.

For CT data, choose **Load DICOM folder...** or **Load NIfTI...**. DICOM pixel
values are converted with their rescale slope/intercept, normally yielding
Hounsfield units. Image orientation, origin, and voxel spacing are retained.
The three coloured planes start at the volume centre; their Polyscope widgets
can translate and rotate them independently. If an EX mesh is in a different
coordinate frame, enable its **Alignment transform gizmo**.

The reader consumes derivative and version parameters correctly. Cubic Hermite
1D coordinate fields are sampled using their first nodal derivatives and
element scale factors, so curved branches are not reduced to endpoint chords.
Other fields display their primary nodal values and are linearly interpolated
over the rendered centreline. Grid-based element fields retain their element
association. Their samples are averaged within each element for edge colour and
radius display; this is exact for element files that repeat one constant value
at both xi endpoints. Non-1D elements are reported and skipped.
For compressed DICOM transfer syntaxes, pydicom may request an optional pixel
decoder such as pylibjpeg.

Development
-----------

Install the test extra and run the parser/scene tests::

   python -m pip install -e .[test]
   pytest

Format reference: `The CMGUI EX file format guide
<https://opencmiss.org/documentation/apidoc/zinc/docs/CMGUI_ex_fileFormatGuide.html>`_.
