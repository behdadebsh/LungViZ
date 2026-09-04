"""Backward-compatible entry point for the historical module name."""

from .application import LungVizApplication, main

Window = LungVizApplication

__all__ = ["LungVizApplication", "Window", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
