"""
Analysis module for Toggl Time Journal.

Reads from data/toggl.db and produces a single comprehensive HTML report
covering longitudinal composition, changepoint detection, rhythm analysis,
activity correlations, text mining, and life phase segmentation.

Usage:
    python -m analysis
    python -m analysis --output path/to/report.html
    python -m analysis --only longitudinal,changepoints
    python -m analysis --start 2020-01-01 --end 2025-12-31
"""
