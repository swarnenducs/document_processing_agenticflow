"""LangGraph shared state for the document processing pipeline."""

from __future__ import annotations

from typing import Any, TypedDict

from document_processing_agenticflow.models.schemas import (
    ConfidenceReport,
    ExtractionValidationResult,
    ExtractedTemplate,
    GenerationResult,
    MappingResult,
    ValidationResult,
)


class DocumentProcessingState(TypedDict, total=False):
    """State passed between LangGraph nodes."""

    template_path: str
    data_path: str
    output_path: str
    json_data: dict[str, Any]
    extracted: ExtractedTemplate
    extraction_validation: ExtractionValidationResult
    mapping: MappingResult
    generation: GenerationResult
    validation: ValidationResult
    confidence: ConfidenceReport
    errors: list[str]
    status: str
    # Retry / validation controls
    retry_count: int
    max_retries: int
    validation_threshold: float
    skip_validation: bool
    skip_extraction_validation: bool
