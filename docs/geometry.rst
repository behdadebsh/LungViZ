Geometry and fields
===================

Load geometry into regions
--------------------------

A region groups the files that belong to one model. Each region has its own
node and element identifiers, so two meshes can both contain node 1. Use a
separate load for each unrelated EX mesh.

.. list-table:: Supported geometry inputs
   :header-rows: 1
   :widths: 24 76

   * - Input
     - What it provides
   * - ``.exnode``
     - Node coordinates and nodal fields. A file loaded on its own appears as
       a point cloud.
   * - ``.exelem``
     - 1D mesh connectivity, grid-based element fields, or both. Add the
       matching coordinate and connectivity files to render the network.
   * - ``.exdata``
     - Independent measurement locations and their fields. Load it with a mesh
       as an overlay or on its own as a point cloud.
   * - ``.stl``, ``.ply``
     - Triangle surface geometry. Each file in a new-region load becomes its
       own surface region.

1. Choose **Load geometry as new region...** and select the related EX files
   in one batch. To open several independent models, repeat the operation for
   each model. You can also drag those batches into the Polyscope window.
2. If files arrive separately, select the target under **Region**, then choose
   **Add files to region...**. For example, add an ``.exelem`` file to the
   region already holding its ``.exnode`` coordinates.
3. Check **Region files** for the loaded filenames and **Import warnings**
   for skipped elements or incompatible inputs. Use **Remove region** if you
   loaded the wrong batch.

Select coordinates and inspect IDs
----------------------------------

Use **Coordinates**, when available, to choose the imported coordinate field
that positions the geometry. Enable **Show node identifiers** for mesh nodes
or standalone EX points, and **Show element identifiers** for a 1D mesh.
These labels come from the EX records. Increase **Number label spacing** to
reduce overlap. When labels compete for space, nearer labels take priority.

Cubic Hermite branches are rendered as multiple segments using nodal
derivatives and element scale factors. **Segments** counts those drawn
segments, so it can exceed the number of EX elements. An element still has
one label. Use the Polyscope **Scene** panel to inspect IDs as quantities.

Colour by a field or show vectors
---------------------------------

* Select a scalar in **Colour by**. Multi-component fields also offer
  individual components and magnitude. Fields marked **[elements]** belong
  to mesh edges. The range shown under **Colour by** is the finite data range.
* Use **Apply colour field** to reapply the choice. Open the quantity in
  Polyscope's **Scene** panel to change its colour map or visual range. For an
  EXDATA overlay, open its own point-cloud structure there to see its fields.
* To see directions, enable the vector quantity in the **Scene** panel.
  LungViZ registers supported two- and three-component fields as arrows.

Nodal fields use primary values and interpolate along rendered branches.
Grid samples in an element's ``Values:`` block are averaged within each
element for colour and radius display. The average gives the original value
when both ends of the element store the same constant.

Use logarithmic flow colours
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Choose a field with ``flow`` in its name under **Colour by**. Flow colours
   start on a linear scale.
2. Enable **Logarithmic flow colours** to spread positive values across the
   colour map by their base-10 logarithm. There must be a positive finite
   value. Finite zero and negative values take the colour of the smallest
   positive flow.
3. If the positive values span a range, adjust **Flow colour lower bound**
   and **Flow colour upper bound** in the original units. The Polyscope
   legend uses log10 units, so a legend value of 4 means 10,000 in the
   original units. Use **Reset flow colour bounds** to return to the full
   positive range.

Set tube thickness and surface opacity
--------------------------------------

* **Tube radius** controls network thickness independently of colour. Select
  **Constant** for a uniform tube or choose a field. LungViZ automatically
  picks a field containing ``radius`` when available and prefers an element
  radius over a nodal radius.
* **Radius scale** multiplies a selected radius field for display. It starts
  at 0.25 and ranges from 0.001 to 10. Use **Use physical radius (1 x)** when
  the radius field and coordinates use compatible units.
* **Smooth tube joins** is available for element-based radii. It derives
  shared radii from neighbouring elements to cover gaps at junctions.
  Rounded caps at the network tips end at the original node positions.
  These operations affect rendering only.
* **Surface opacity** starts at 0.65 for each STL or PLY region. Adjust it
  from 0 (transparent) to 1 (opaque) to reveal or cover an underlying network
  or CT plane.
