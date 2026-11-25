Build the guide
===============

Run these commands from the LungViZ repository root. Use a Python 3.11 or
newer environment for Sphinx. The guide can be built independently of the
LungViZ application and its runtime dependencies.

.. code-block:: console

   python -m pip install -r docs/requirements.txt
   python -m sphinx -M html docs build/docs -W

Open ``build/docs/html/index.html`` to read the guide locally. ``-W`` makes
Sphinx treat build warnings as errors.

Build a PDF with LaTeX
----------------------

With a complete LaTeX toolchain and ``latexmk`` on your PATH, run the
following command. See the `Sphinx LaTeX builder requirements`_ for platform
dependencies.

.. code-block:: console

   python -m sphinx -M latexpdf docs build/docs -W

The result is ``build/docs/latex/lungviz-user-guide.pdf``.

Print to PDF in a browser
-------------------------

If you prefer a browser PDF, build the single-page version of the guide.

.. code-block:: console

   python -m sphinx -M singlehtml docs build/docs -W

Open ``build/docs/singlehtml/index.html`` and choose your browser's
**Print** and **Save as PDF** options.

.. _Sphinx LaTeX builder requirements: https://www.sphinx-doc.org/en/master/usage/builders/index.html#sphinx.builders.latex.LaTeXBuilder
