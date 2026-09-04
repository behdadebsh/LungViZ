
***************
LungViZ
***************

LungViZ is an interactive viewer for one-dimensional OpenCMISS/CMGUI meshes.
It reads ``.exnode`` coordinates and nodal fields, ``.exelem`` connectivity,
and ``.exdata`` point data, then displays them in a Polyscope window.

Features
--------

* Load several EX files at once with a native file picker or as command-line arguments.
* Inspect original node and element identifiers and 1D connectivity.
* Colour a network by any scalar field, vector component, or vector magnitude.
* Use a non-negative field such as radius to control the displayed network thickness.
* Display multi-component fields as Polyscope vectors.
* Overlay ``.exdata`` locations and their fields as point clouds.
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

Click **Load EX files...** in the LungViZ panel and select matching files. A
mesh becomes visible when both coordinate nodes and 1D element connectivity
are loaded. Use **Colour field** and **Radius field** for the most common
visualisations. The standard Polyscope Scene panel exposes every imported
quantity, including node and element identifiers, for detailed inspection.

The reader consumes derivative and version parameters correctly but displays
the primary nodal value for each component. It does not evaluate finite-element
basis functions between nodes. Non-1D elements are reported and skipped.

Development
-----------

Install the test extra and run the parser/scene tests::

   python -m pip install -e .[test]
   pytest

Format reference: `The CMGUI EX file format guide
<https://opencmiss.org/documentation/apidoc/zinc/docs/CMGUI_ex_fileFormatGuide.html>`_.
