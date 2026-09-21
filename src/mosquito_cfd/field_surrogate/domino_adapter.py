"""Emit the DoMINO keys this corpus can honestly fill -- the volume half only.

Imports neither ``physicsnemo`` nor ``torch`` at any scope, so the package stays importable on the
CPU-only CI runner and this change adds no dependency.
"""
