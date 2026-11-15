"""Reporting helpers."""

from .figures import plot_confusion_matrix, plot_subject_accuracy
from .html import render_loso_report

__all__ = ["plot_confusion_matrix", "plot_subject_accuracy", "render_loso_report"]
