"""Public package exports."""

from document_processing_agenticflow.graph import app, build_graph
from document_processing_agenticflow.tools import get_document_tools

__all__ = ["app", "build_graph", "get_document_tools"]


def main() -> None:
    from document_processing_agenticflow.cli import main as cli_main

    raise SystemExit(cli_main())
