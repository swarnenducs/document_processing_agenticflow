# document-processing-mcp

| Status | Path |
|--------|------|
| M | `document-processing-mcp/.env.example` |
| AM | `document-processing-mcp/config/prompt_versions.json` |
| A | `document-processing-mcp/package_azure_webapp.ps1` |
| A | `document-processing-mcp/package_azure_webapp.sh` |
| R | `document-processing-mcp/prompts/agent.yml` → `agent.1.0.0.yml` |
| R | `extraction_validator.yml` → `prompts/extraction_validator.1.0.0.yml` |
| RM | `mapper.yml` → `prompts/mapper.1.0.0.yml` |
| R | `document-processing-mcp/prompts/validator.yml` → `validator.1.0.0.yml` |
| A | `document-processing-mcp/prompts/marker_synthesizer.1.0.0.yml` |
| MM | `document-processing-mcp/src/document_processing_mcp/graph.py` |
| MM | `document-processing-mcp/src/document_processing_mcp/models/state.py` |
| MM | `document-processing-mcp/src/document_processing_mcp/nodes/pipeline.py` |
| M | `document-processing-mcp/src/document_processing_mcp/services/confidence.py` |
| MM | `document-processing-mcp/src/document_processing_mcp/services/document_generator.py` |
| M | `document-processing-mcp/src/document_processing_mcp/services/document_job.py` |
| M | `document-processing-mcp/src/document_processing_mcp/services/field_mapper.py` |
| A | `document-processing-mcp/src/document_processing_mcp/services/library_match.py` |
| A | `document-processing-mcp/src/document_processing_mcp/services/marker_apply.py` |
| A | `document-processing-mcp/src/document_processing_mcp/services/marker_synthesizer.py` |
| A | `document-processing-mcp/src/document_processing_mcp/services/master_data.py` |
| M | `document-processing-mcp/src/document_processing_mcp/services/placeholders.py` |
| A | `document-processing-mcp/src/document_processing_mcp/services/table_fill_infer.py` |
| M | `document-processing-mcp/src/document_processing_mcp/services/prompts/__init__.py` |
| M | `document-processing-mcp/src/document_processing_mcp/services/prompts/loader.py` |
| A | `document-processing-mcp/src/document_processing_mcp/services/prompts/prompt_versions.py` |
| A | `document-processing-mcp/src/document_processing_mcp/services/prompts/marker_synthesizer_prompt.py` |
| R | `prompts/yml/agent.yml` → `agent.1.0.0.yml` |
| R | `extraction_validator.yml` → `yml/extraction_validator.1.0.0.yml` |
| RM | `mapper.yml` → `yml/mapper.1.0.0.yml` |
| R | `validator.yml` → `yml/validator.1.0.0.yml` |
| A | `document-processing-mcp/src/document_processing_mcp/services/prompts/yml/marker_synthesizer.1.0.0.yml` |
| M | `document-processing-mcp/src/document_processing_mcp/storage/db.py` |
| M | `document-processing-mcp/src/document_processing_mcp/storage/job_sink.py` |
| M | `document-processing-mcp/src/document_processing_mcp/storage/sql_models.py` |
| A | `document-processing-mcp/tests/test_document_generator_namespaces.py` |
| A | `document-processing-mcp/tests/test_markers.py` |
| A | `document-processing-mcp/tests/test_master_data.py` |
| M | `document-processing-mcp/tests/test_pipeline.py` |
| MM | `document-processing-mcp/tests/test_prompt_yaml.py` |
| A | `document-processing-mcp/tests/test_table_fill_infer.py` |
