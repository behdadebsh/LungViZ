Troubleshooting
===============

.. list-table:: Common issues and fixes
   :header-rows: 1
   :widths: 38 62

   * - What you see
     - What to check
   * - ``lungviz`` is unavailable in your terminal.
     - Activate the environment where you installed LungViZ, or launch with
       ``python -m LungViZ`` using that environment's Python interpreter.
   * - Your mesh appears as points or its connectivity is unavailable.
     - Under **Region files**, verify that the same region contains the
       matching ``.exnode`` and connectivity ``.exelem``. Check the region
       status and **Import warnings** for missing nodes or skipped elements.
       Only one-dimensional EX elements are rendered as a network.
   * - Two unrelated meshes share IDs or appear under one region.
     - Load each model in its own batch using **Load geometry as new
       region...**. Keep matching nodes, elements, and element fields together.
   * - An element field is missing from **Colour by**.
     - Check that its file is in the mesh region and that its element IDs
       match the loaded connectivity. Look for the **[elements]** suffix.
   * - A data cloud is visible but you cannot colour it from the mesh controls.
     - Open the corresponding data structure in Polyscope's **Scene** panel
       and enable its field quantity there.
   * - The CT loads but you see no image.
     - Turn on **Show Axial**, **Show Coronal**, or **Show Sagittal**. If you
       previously moved a plane away from the scan, choose **Reset CT slices**
       and re-enable that plane.
   * - The wrong DICOM series loaded.
     - Place the desired series in its own folder and select that folder.
       LungViZ chooses the largest series when it finds several.
   * - A compressed DICOM slice could not be decoded.
     - Read the error for the transfer syntax or decoder required by pydicom.
       Install the matching optional decoder in the LungViZ environment, or
       load an uncompressed copy of the series.
   * - The mesh and CT appear offset, mirrored, or at different scales.
     - Compare their coordinate conventions, origins, and units. Use the
       region's **Alignment transform gizmo** for visual translation or
       rotation. If the units differ, put the geometry and image into
       compatible units before loading them.
   * - The exported coordinates do not match the aligned view.
     - EX export writes the point editor's coordinates. Use point editing
       for persistent position changes, and reload the exported EX files in
       a new region to check the result.
