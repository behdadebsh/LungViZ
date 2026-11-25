Edit points and save results
============================

Select and move points
----------------------

Select a 1D mesh, a standalone EXNODE region, or a standalone EXDATA region
and enable **Edit nodes / data points**. To edit a measurement cloud that you
normally view over a mesh, load its EXDATA as a separate region. In a region
with several measurement clouds and no mesh or node cloud, the first valid
cloud is the editable structure.

.. list-table:: Point selection
   :header-rows: 1
   :widths: 35 65

   * - Control
     - Effect
   * - Click a handle
     - Replace the selection with that point.
   * - Shift-click a handle
     - Add the point to the selection.
   * - Ctrl-click a handle
     - Toggle the point in the selection.
   * - **Select all points**
     - Select all editable points in the region.
   * - **Clear selection**
     - Deselect every point.

Selected points are orange. Drag their translation arrows to move them
together. To move them by a specified offset, enter X, Y, and Z values in
**Translation delta** and choose **Apply translation**. With exactly one
point selected, use **Absolute position** and **Set absolute position** to
move it to specific coordinates. Connected branches follow the edited nodes.

Rotate, mirror, or delete
-------------------------

* Set **Transform centre** to the desired pivot, or choose **Use region
  centroid** to use the mean position of its editable points. Enter a
  **Rotation angle (degrees)** and choose **Rotate X**, **Rotate Y**, or
  **Rotate Z** to rotate all editable points about that global axis through
  the pivot.
* Use **Mirror XY**, **Mirror XZ**, or **Mirror YZ** to reflect all editable
  points across the corresponding plane through the pivot. Whole-region
  rotation and mirroring transform coordinate derivatives for curved branches
  as well as the point positions.
* Use **Delete selected nodes** to remove the selected points. Deleting a
  mesh node removes every element connected to it. At least one node or data
  point must remain.
* Use **Undo point edit** and **Redo point edit** to step through edits,
  including deletions. **Reset selected points** and **Reset all points**
  restore the loaded positions and coordinate derivatives of points still in
  the region. Use **Undo point edit** to recover a deletion.

Export edited EX files
----------------------

1. With point editing enabled, choose **Export edited EX files...**.
2. Select a folder and name the primary output. It defaults to the input
   name with an ``_edited`` suffix. Meshes and node clouds use ``.exnode``.
   Standalone measurement clouds use ``.exdata``.
3. Choose **Save**. Associated element files are written beside the primary
   output using the same base name and ``.exelem``. If there are additional
   documents of the same type, LungViZ adds their source stems to the output
   names. Use a fresh base name or output folder. The save dialog checks the
   primary filename, and companion files are written automatically.
4. To verify the output, load the exported node and element files together
   as a new region, or load the exported EXDATA on its own.

The export preserves EX headers and the IDs and non-coordinate fields of
retained records. It writes edited coordinates, including any transformed
coordinate derivatives, and omits deleted records. Each exported document
must use a different path from its source. The region alignment gizmo
changes the placement of the display. Use the point editor for coordinate
changes you need in your exported data.

Save a screenshot
-----------------

1. Set the camera, field colours, and geometry or CT visibility for the view
   you want to capture.
2. Press **Ctrl+Shift+S** or use Polyscope's **Screenshot** button. Its
   adjacent menu provides the format and background options.
3. In the browser choose PNG or JPEG under **File type**, select a folder,
   and enter the filename. Use PNG for a transparent background. Then choose
   **Save**.

The capture excludes the interface panels. If you used the Polyscope button
and cancel **Save As**, the automatically numbered screenshot stays in the
working directory. Check the LungViZ status message for the saved path.
