"""
backend.adapters.renderer
=========================

Two PDF renderers behind the ``PDFRenderer`` port:

* ``RenderCVAdapter``     — Typst + RenderCV (``sb2nov`` / ``classic`` /
  ``moderncv`` themes). Wraps the existing ``render_service`` module.
* ``PlaywrightHTMLAdapter`` — headless Chromium rendering the Jinja2
  template at ``backend/templates/classic.html.j2``. Used when the user
  selects ``classic_html`` theme, and as the universal fallback when
  RenderCV fails.

Selection happens in ``factory.build_pdf_renderer``.
"""