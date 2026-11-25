Getting started
===============

Install LungViZ
---------------

Open a terminal in the LungViZ repository. Use Python 3.9 or newer and create
a virtual environment for the application.

.. code-block:: console

   python -m venv .venv

Activate it in Windows PowerShell with ``.\.venv\Scripts\Activate.ps1``,
in Windows Command Prompt with ``.venv\Scripts\activate.bat``, or in a
macOS or Linux shell with ``source .venv/bin/activate``. Then install LungViZ
and its runtime dependencies.

.. code-block:: console

   python -m pip install -e .
   lungviz

The application opens a Polyscope window and uses its own in-window file
browser. The same entry point is available as ``python -m LungViZ``.

Try the sample airway
---------------------

Run this command from the repository root.

.. code-block:: console

   lungviz examples/sample.exnode examples/sample.exelem examples/sample.exdata

You should see four mesh nodes, three branches, and a separate overlay of two
measurement points. Try these controls in the LungViZ panel.

1. Confirm **Region** is set to **sample_airway**.
2. Enable **Show node identifiers** and **Show element identifiers** to see
   the original IDs. The two sets of numbers refer to different records.
3. Set **Colour by** to **pressure**. Change **Tube radius** from **radius**
   to **Constant** to see how colour and thickness can be controlled separately.
4. In the Polyscope **Scene** panel, expand **sample_airway / data /
   sample_measurements** and enable **measured_pressure** to inspect the
   measurement overlay.
5. Press **Ctrl+Shift+S**, pick a destination, and save a screenshot.

You can also open the same example from **Geometry regions**. Choose
**Load geometry as new region...**, enter the ``examples`` folder, click all
three sample files, and choose **Open files**.

Find your way around the window
-------------------------------

* **Geometry regions** holds the active region selector, import and display
  settings, alignment gizmo, and point editing controls.
* **CT volume** holds the scan loaders and slice controls.
* The Polyscope **Scene** panel holds the individual structures and quantities.
  Use it to show or hide structures, pick geometry, and change per-structure
  display options such as colour maps and scalar ranges.
* The Polyscope **View** menu controls the camera. LungViZ starts in **Free**
  navigation mode so you can inspect the scene from any orientation.
* **Remove region** removes the selected geometry region. **Unload CT**
  removes the scan and its planes. **Clear everything** removes all regions
  and the CT from the current scene.

Use the file browser
--------------------

* Click a folder to enter it, or use **Up** to go to its parent. Paste a folder
  or full file path into **Location** and choose **Go**. On Windows a **Drive**
  selector appears when multiple drives are available.
* **File type** filters visible files. **Show hidden files** reveals names that
  begin with a dot. Changing folder or file type clears the current selection.
* In a geometry dialog, click each file to select it and click again to
  deselect it. Use **Open files** for the batch, **Open file** for one NIfTI,
  and **Select folder** for the DICOM directory you are currently viewing.
* In a save dialog, enter a **Filename** and choose **Save**. The selected
  file type supplies the extension if you omit it. If the chosen path already
  exists, the browser asks you to press **Save** again to replace it.

Command-line options
--------------------

Use ``lungviz --help`` for the command synopsis. Positional paths preload
geometry. All EX paths in one invocation are grouped into one region, and each
STL or PLY path opens as a separate region. Quote paths containing spaces.
Use the CT panel after launch to load a DICOM folder or NIfTI file.
