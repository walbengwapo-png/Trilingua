# Trilingua — Enterprise Document Localization Platform
## Architectural Design Document v2.0

> **Status:** Proposed Architecture  
> **Date:** July 2026  
> **Author:** Lead Software Architect  
> **Target:** Production-ready document localization engine for DepEd Modules, educational materials, and professional documents

---

## Table of Contents

1. [Complete System Architecture](#1-complete-system-architecture)
2. [Recommended Folder Structure](#2-recommended-folder-structure)
3. [Backend Workflow](#3-backend-workflow)
4. [Translation Workflow](#4-translation-workflow)
5. [API Design](#5-api-design)
6. [Database Schema Improvements](#6-database-schema-improvements)
7. [Queue Architecture](#7-queue-architecture)
8. [Storage Architecture](#8-storage-architecture)
9. [Translation Memory Implementation](#9-translation-memory-implementation)
10. [Document Object Graph Design](#10-document-object-graph-design)
11. [Error Handling Strategy](#11-error-handling-strategy)
12. [Performance Optimization Strategy](#12-performance-optimization-strategy)
13. [Future Scalability Recommendations](#13-future-scalability-recommendations)

---

## 1. Complete System Architecture

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LARAVEL (PHP)                                     │
│                                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  ┌───────────────┐ │
│  │ Auth/Users  │  │ Projects     │  │ Queue Manager  │  │ Translation   │ │
│  │ Uploads     │  │ Document     │  │ (Horizon)      │  │ History       │ │
│  │ Billing     │  │ Management   │  │                │  │ TM UI         │ │
│  └──────┬──────┘  └──────┬───────┘  └───────┬────────┘  └───────┬───────┘ │
│         │                │                   │                  │         │
│         └────────────────┴───────────────────┴──────────────────┘         │
│                              │ HTTP/REST                                 │
│                     ┌────────┴────────┐                                  │
│                     │   API Gateway   │                                  │
│                     │  (Laravel API)  │                                  │
│                     └────────┬────────┘                                  │
│                              │ JSON                                      │
└──────────────────────────────┼───────────────────────────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │   Redis (Queue)     │
                    │   PostgreSQL (DB)   │
                    │   MinIO/S3 (Files)  │
                    └─────────────────────┘
                               │ HTTP/REST
┌──────────────────────────────┼───────────────────────────────────────────┐
│                    PYTHON MICROSERVICE                                   │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    API LAYER (FastAPI)                           │   │
│  │  POST /translate  │  POST /analyze  │  POST /validate          │   │
│  │  GET  /status/{id}│  GET  /health    │  POST /tm/query         │   │
│  └────────────────────────┬─────────────────────────────────────────┘   │
│                           │                                             │
│  ┌────────────────────────┴─────────────────────────────────────────┐   │
│  │                   PIPELINE ORCHESTRATOR                          │   │
│  │                                                                  │   │
│  │  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌─────────┐ ┌───────┐ │   │
│  │  │Document  │ │ Semantic  │ │ Context  │ │Smart    │ │Quality│ │   │
│  │  │Intelligen│ │ Analysis  │ │ Engine   │ │Transla- │ │Valida-│ │   │
│  │  │ce Layer  │ │ Engine    │ │          │ │tion Eng │ │tion   │ │   │
│  │  └──────────┘ └───────────┘ └──────────┘ └─────────┘ └───────┘ │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                           │                                             │
│  ┌────────────────────────┴─────────────────────────────────────────┐   │
│  │                   ADAPTIVE RECONSTRUCTOR                          │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────┐  │   │
│  │  │DOCX In-  │ │PPTX In-  │ │XLSX In-  │ │PDF       │ │TXT/  │  │   │
│  │  │place     │ │place     │ │place     │ │Reconstruc│ │CSV   │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────┘  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    ADAPTER LAYER                                  │   │
│  │  ┌────┐ ┌───────┐ ┌──────┐ ┌──────┐ ┌────┐ ┌──────┐ ┌──────┐  │   │
│  │  │PDF │ │ DOCX  │ │ PPTX │ │ XLSX │ │TXT │ │HTML  │ │ EPUB │  │   │
│  │  │Adap│ │Adapter│ │Adapter│ │Adapt │ │Adap│ │Future│ │Future│  │   │
│  │  │ter │ │       │ │      │ │er    │ │ter │ │      │ │      │  │   │
│  │  └────┘ └───────┘ └──────┘ └──────┘ └────┘ └──────┘ └──────┘  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                           │                                             │
│  ┌────────────────────────┴─────────────────────────────────────────┐   │
│  │                    AI PROVIDER LAYER                              │   │
│  │  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌──────────┐ ┌─────────┐ │   │
│  │  │GPT-OSS  │ │ Mistral  │ │ OpenAI  │ │ Gemini   │ │Future...│ │   │
│  │  │(Default)│ │(Fallback)│ │(Future) │ │(Future)  │ │         │ │   │
│  │  └─────────┘ └──────────┘ └─────────┘ └──────────┘ └─────────┘ │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Responsibility Split

| Responsibility | Laravel | Python |
|---|---|---|
| User authentication & permissions | ✅ Primary | ❌ |
| File upload & storage management | ✅ Primary | ❌ |
| Project/document CRUD | ✅ Primary | ❌ |
| Translation history & audit logs | ✅ Primary | ❌ |
| Queue management (Horizon) | ✅ Primary | ❌ |
| User-facing UI (filament/admin) | ✅ Primary | ❌ |
| Billing & subscription | ✅ Primary | ❌ |
| Document parsing & analysis | ❌ | ✅ Primary |
| Object Graph construction | ❌ | ✅ Primary |
| Semantic role classification | ❌ | ✅ Primary |
| Context Engine (TM, glossary) | Coordinates storage | ✅ Runtime logic |
| Translation (all pipelines) | ❌ | ✅ Primary |
| Layout reconstruction | ❌ | ✅ Primary |
| Quality validation | ❌ | ✅ Primary |
| Quality report generation | ❌ | ✅ Primary |
| OCR | ❌ | ✅ Primary |
| Persistent TM storage | Coordinates DB | Query/write via API |
| Progress streaming | Queue events | Emit via Redis |

### 1.3 Data Flow (End-to-End)

```
User Uploads File
        │
        ▼
Laravel: Store file → Create job in Horizon → Return job_id
        │
        ▼
Horizon: Dispatch to Python worker via HTTP
        │
        ▼
Python: Receive job → Initialize Document Intelligence Layer
        │
        ├──→ Phase 1: Parse file via Format Adapter → Document Object Graph
        ├──→ Phase 2: Semantic Analysis → Role-annotated Object Graph
        ├──→ Phase 3: Context Engine initialization
        │       ├── Load persistent TM (cross-document)
        │       ├── Extract document glossary
        │       └── Build neighbor/cross-ref indices
        ├──→ Phase 4: Page-window translation
        │       ├── For each page window:
        │       │   ├── Object → role → select pipeline
        │       │   ├── Augment prompt via Context Engine
        │       │   ├── Translate via AI provider
        │       │   ├── Post-process → validate
        │       │   └── Emit progress update → Redis
        │       └── Update Context Engine
        ├──→ Phase 5: Adaptive Layout Reconstruction
        ├──→ Phase 6: Quality Validation → QA Report
        ├──→ Phase 7: Save output file + report
        │
        ▼
Python: Return job result to Laravel (or save to shared storage)
        │
        ▼
Laravel: Update job status → Notify user → Provide download link + QA report
```

---

## 2. Recommended Folder Structure

### 2.1 Laravel (trilingua-code/)

```
trilingua-code/
├── app/
│   ├── Http/
│   │   ├── Controllers/
│   │   │   ├── Api/
│   │   │   │   ├── TranslationController.php      # Job submission
│   │   │   │   ├── DocumentController.php         # CRUD
│   │   │   │   ├── ProjectController.php          # Project management
│   │   │   │   ├── TranslationMemoryController.php # TM management
│   │   │   │   ├── GlossaryController.php          # User glossary
│   │   │   │   └── HealthController.php
│   │   │   └── Web/
│   │   │       └── DashboardController.php
│   │   └── Requests/
│   │       ├── TranslateDocumentRequest.php
│   │       ├── StoreProjectRequest.php
│   │       └── UpdateGlossaryRequest.php
│   ├── Jobs/
│   │   ├── TranslateDocumentJob.php               # Dispatches to Python
│   │   ├── ProcessTranslationCallback.php          # Handles completion
│   │   └── GenerateQualityReport.php
│   ├── Models/
│   │   ├── Project.php
│   │   ├── Document.php
│   │   ├── TranslationJob.php
│   │   ├── TranslationMemoryEntry.php
│   │   ├── GlossaryEntry.php
│   │   └── QualityReport.php
│   ├── Services/
│   │   ├── PythonBridge.php                       # HTTP client to Python
│   │   ├── StorageService.php                     # File path management
│   │   └── TranslationMemoryService.php            # Queries TM DB
│   └── Events/
│       ├── TranslationStarted.php
│       ├── TranslationProgressUpdated.php
│       └── TranslationCompleted.php
├── config/
│   ├── translation.php                            # Python API URL, providers
│   └── queue.php                                   # Horizon config
├── database/
│   └── migrations/
│       ├── create_projects_table.php
│       ├── create_documents_table.php
│       ├── create_translation_jobs_table.php
│       ├── create_translation_memory_entries_table.php
│       ├── create_glossary_entries_table.php
│       └── create_quality_reports_table.php
└── resources/
    └── js/
        └── Components/
            └── TranslationProgress.vue             # Real-time progress bar
```

### 2.2 Python Microservice (trilingua-code/Model/)

```
trilingua-code/Model/
├── server.py                                      # FastAPI entry point
├── requirements.txt
├── config/
│   ├── settings.py                                # Environment configuration
│   ├── providers.py                               # Provider registry
│   └── processing_modes.py                        # Fast/Balanced/Thorough
│
├── dto/                                           # Data Transfer Objects
│   ├── requests.py                                # TranslationRequest, etc.
│   ├── responses.py                               # TranslationResponse, etc.
│   └── graphs.py                                  # DocumentObjectGraph types
│
├── adapters/                                      # FORMAT ADAPTERS
│   ├── base.py                                    # Abstract base adapter
│   ├── pdf_adapter.py                             # PyMuPDF + pdfplumber
│   ├── docx_adapter.py                            # python-docx
│   ├── pptx_adapter.py                            # python-pptx
│   ├── xlsx_adapter.py                            # openpyxl
│   ├── txt_adapter.py                             # Builtin
│   ├── csv_adapter.py                             # csv
│   ├── html_adapter.py                            # Future
│   └── epub_adapter.py                            # Future
│
├── intelligence/                                  # DOCUMENT INTELLIGENCE LAYER
│   ├── graph/                                     # Object Graph
│   │   ├── document_graph.py                      # DocumentObjectGraph class
│   │   ├── page.py                                # Page node
│   │   ├── objects.py                             # TextObject, TableObject, etc.
│   │   └── relations.py                           # Cross-reference, parent-child
│   ├── analyzer/                                  # Document analysis
│   │   ├── document_analyzer.py                   # Type, style, structure
│   │   └── page_analyzer.py                       # Per-page layout analysis
│   ├── semantic/                                  # SEMANTIC ANALYSIS ENGINE
│   │   ├── role_classifier.py                     # Main classifier (hybrid)
│   │   ├── heuristics.py                          # Rule-based role detection
│   │   ├── llm_classifier.py                      # LLM-based role detection
│   │   ├── role_registry.py                       # Role definitions + hierarchy
│   │   └── group_detector.py                      # Question group detection
│   ├── context/                                   # CONTEXT ENGINE
│   │   ├── context_engine.py                      # Central orchestrator
│   │   ├── translation_memory.py                  # TM client (queries Laravel DB)
│   │   ├── glossary.py                            # User + document glossary
│   │   ├── neighbors.py                           # 3-object window neighbor system
│   │   ├── cross_references.py                    # "See Figure X" resolver
│   │   └── language_knowledge.py                  # Expansion ratios, patterns
│   └── features/                                  # Feature extraction
│       ├── layout.py                              # Layout feature extraction
│       └── text.py                                # Text feature extraction
│
├── pipeline/                                      # PIPELINE ORCHESTRATION
│   ├── orchestrator.py                            # Master orchestrator
│   ├── document_pipeline.py                       # Document-level flow
│   ├── translation_pipeline.py                    # Text translation flow
│   └── checkpoint_manager.py                      # Save/resume checkpoints
│
├── translation/                                   # TRANSLATION ENGINE
│   ├── engine.py                                  # Smart Translation Engine
│   ├── registry.py                                # Pipeline registry by role
│   ├── pipelines/                                 # PER-ROLE PIPELINES
│   │   ├── base_pipeline.py                       # Abstract base
│   │   ├── learning_objective.py
│   │   ├── instruction.py
│   │   ├── question.py
│   │   ├── mc_option.py
│   │   ├── answer_blank.py
│   │   ├── answer_key.py
│   │   ├── table_header.py
│   │   ├── caption.py
│   │   ├── reference.py
│   │   ├── paragraph.py
│   │   ├── heading.py
│   │   ├── footer.py
│   │   ├── hyperlink.py
│   │   └── glossary_term.py
│   └── prompts/
│       ├── templates/                             # Per-role system prompts
│       │   ├── academic.yaml
│       │   ├── interrogative.yaml
│       │   ├── imperative.yaml
│       │   ├── condensed.yaml
│       │   └── formal.yaml
│       └── injectors.py                           # Context injection logic
│
├── reconstruction/                                # LAYOUT RECONSTRUCTION
│   ├── base.py                                    # Abstract reconstructor
│   ├── docx_reconstructor.py                      # In-place XML manipulation
│   ├── pptx_reconstructor.py                      # In-place XML manipulation
│   ├── xlsx_reconstructor.py                      # In-place XML manipulation
│   ├── pdf_reconstructor.py                       # PDF rebuild with layout preservation
│   ├── layout_planner.py                          # Pre-reconstruction layout plan
│   └── overflow_resolver.py                       # 3-strategy overflow handling
│
├── validation/                                    # QUALITY VALIDATION
│   ├── engine.py                                  # Quality Validation Engine
│   ├── checks/                                    # Individual check implementations
│   │   ├── image_count.py
│   │   ├── table_count.py
│   │   ├── object_count.py
│   │   ├── untranslated_text.py
│   │   ├── answer_key_integrity.py
│   │   ├── blank_preservation.py
│   │   ├── hyperlink_verification.py
│   │   ├── page_count.py
│   │   ├── numbering_consistency.py
│   │   ├── font_consistency.py
│   │   ├── terminology_consistency.py
│   │   └── grammar_review.py
│   ├── severity.py                                # Severity definitions
│   ├── report.py                                  # QA Report builder
│   └── ai_quality_reviewer.py                     # Existing AI reviewer
│
├── providers/                                     # AI PROVIDER LAYER
│   ├── base.py                                    # Abstract TranslationProvider
│   ├── gptoss.py                                  # GPT-OSS (Ollama Cloud)
│   ├── mistral.py                                 # Mistral AI
│   ├── future_openai.py                           # OpenAI stub
│   ├── future_gemini.py                           # Gemini stub
│   └── future_deepseek.py                         # DeepSeek stub
│
├── memory/                                        # MEMORY MANAGEMENT
│   ├── translation_cache.py                       # In-memory document cache
│   └── document_memory.py                         # Document-level memory
│
├── workers/                                       # BACKGROUND WORKERS
│   ├── document_worker.py                         # Celery/RQ task: translate doc
│   ├── batch_worker.py                            # Batch processing
│   └── cleanup_worker.py                          # Temp file cleanup
│
├── exceptions/                                    # ERROR HANDLING
│   ├── base.py                                    # TrilinguaBaseException
│   ├── adapter_exceptions.py
│   ├── pipeline_exceptions.py
│   ├── translation_exceptions.py
│   ├── validation_exceptions.py
│   └── recovery_exceptions.py
│
├── utils/                                         # UTILITIES
│   ├── logging.py                                 # Structured logging
│   ├── metrics.py                                 # Prometheus metrics
│   ├── progress.py                                # Progress bar/streaming
│   └── serialization.py                           # JSON serialization helpers
│
└── tests/
    ├── unit/
    │   ├── test_semantic_classifier.py
    │   ├── test_context_engine.py
    │   ├── test_validation_engine.py
    │   └── test_role_pipelines.py
    ├── integration/
    │   ├── test_docx_pipeline.py
    │   ├── test_pdf_pipeline.py
    │   └── test_pptx_pipeline.py
    └── fixtures/
        ├── sample_deped_module.docx
        ├── sample_textbook.pdf
        ├── sample_worksheet.xlsx
        └── sample_lesson.pptx
```

---

## 3. Backend Workflow

### 3.1 Document Submission Workflow

```
User
  │
  ├── 1. Upload file via Laravel web UI
  │         │
  │         ├── Validate file type/size
  │         ├── Store file in persistent storage (S3/MinIO)
  │         ├── Create Document record in DB
  │         ├── Create TranslationJob record (status: pending)
  │         └── Dispatch TranslateDocumentJob to Horizon
  │
  ├── 2. Horizon picks up job
  │         │
  │         ├── Update TranslationJob status: processing
  │         ├── POST /translate/document to Python microservice
  │         │   Body: { job_id, file_path, source_lang, target_lang, mode }
  │         └── Return job_id immediately (async processing)
  │
  ├── 3. Python receives request
  │         │
  │         ├── Initialize Document Intelligence Layer
  │         ├── Begin pipeline (see Section 4)
  │         └── Emit progress events to Redis channel: job:{job_id}:progress
  │
  ├── 4. Laravel listens to Redis (Broadcast/WebSocket)
  │         │
  │         ├── Receive progress: { percent, stage, message }
  │         ├── Update TranslationJob.progress
  │         ├── Broadcast to user via Laravel Echo + WebSockets
  │         └── User sees real-time progress in browser
  │
  ├── 5. Python completes
  │         │
  │         ├── Save translated file to output path
  │         ├── Generate Quality Report (JSON)
  │         ├── POST callback to Laravel: { job_id, status, output_path, report }
  │         └── Clean up temp files
  │
  └── 6. Laravel processes callback
            │
            ├── Update TranslationJob status: completed/failed
            ├── Save Quality Report to DB
            ├── Notify user (email/in-app)
            └── User downloads translated file + views QA report
```

### 3.2 Processing Mode Decision Tree

```
User-specified mode?
        │
        ├── "fast"     → Fast mode (no AI analysis, no TM, no role classification)
        │                  Best for: simple text, quick drafts
        │
        ├── "balanced" → Balanced mode (document analysis, role classification,
        │                  TM, context engine, quality validation WARNING+)
        │                  Best for: most documents
        │
        ├── "thorough" → Thorough mode (all features + layout planner,
        │                  AI review, fuzzy TM, quality validation ERROR+)
        │                  Best for: DepEd modules, textbooks, final output
        │
        └── "auto"     → Analyze document characteristics:
                          ├── < 500 words + .txt/.md       → fast
                          ├── < 10 blocks + < 1000 words   → balanced
                          ├── Has tables/headers/PDF        → thorough
                          └── > 50 blocks or > 5000 words  → thorough
```

---

## 4. Translation Workflow

### 4.1 Detailed Pipeline Stages

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: DOCUMENT INTELLIGENCE                                              │
│                                                                             │
│  1a. Select format adapter by file extension                                │
│  1b. Parse file → DocumentObjectGraph                                       │
│       ├── Page objects with dimensions                                     │
│       ├── Text objects with position, font, style                          │
│       ├── Table objects with cell grid + merging                           │
│       ├── Image objects with position, size (reference only)               │
│       ├── Shape/textbox objects                                            │
│       └── Header/footer/page-number objects                                │
│  1c. Validate graph completeness (no missing pages/objects)                │
│                                                                             │
│  Output: DocumentObjectGraph (typed, positioned, styled)                    │
├─────────────────────────────────────────────────────────────────────────────┤
│ STAGE 2: SEMANTIC ANALYSIS                                                  │
│                                                                             │
│  2a. Run heuristic role classifier on all objects                          │
│       ├── Match patterns: _____ → AnswerBlank                             │
│       ├── Match patterns: ^\d+\.\s → ListItem (numbered)                  │
│       ├── Match patterns: ^[A-D]\) → MCOption                             │
│       ├── Match patterns: "What I Need to Know" → LearningObjective       │
│       └── Confidence threshold: 0.85+ for heuristic acceptance             │
│  2b. For low-confidence objects, run LLM role classifier                   │
│       ├── Batch objects by page (reduces LLM calls)                       │
│       ├── Each batch: [object_text + context_text + page_position]        │
│       └── Returns role + confidence for each object                        │
│  2c. Detect object groups                                                 │
│       ├── Question + 4 MCOptions + AnswerBlank → QuestionGroup            │
│       ├── Heading + N paragraphs → SectionGroup                           │
│       └── ListItem sequence → ListGroup                                   │
│  2d. Annotate Object Graph with roles + group memberships                 │
│                                                                             │
│  Output: Role-annotated DocumentObjectGraph                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ STAGE 3: CONTEXT ENGINE INITIALIZATION                                      │
│                                                                             │
│  3a. Load persistent Translation Memory from Laravel DB                    │
│       ├── Query by project (if scoped) or global                           │
│       ├── Build in-memory hash table for O(1) exact lookups               │
│       └── Build BK-tree for O(log n) fuzzy lookups                        │
│  3b. Extract document glossary from annoted graph                         │
│       ├── Role == GlossaryTerm → add to document glossary                 │
│       └── Domain-specific terms from Semantic Analysis → add              │
│  3c. Build neighbor index                                                 │
│       ├── Each object linked to previous/next in reading order            │
│       ├── Parent-child links (table → cells paragraph → runs)            │
│       └── Group membership links                                          │
│  3d. Build cross-reference index                                          │
│       ├── Scan for "see Figure", "Table X", "page N" patterns            │
│       └── Resolve to target objects (page number + object index)          │
│                                                                             │
│  Output: Initialized ContextEngine                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ STAGE 4: PAGE-WINDOW TRANSLATION                                            │
│                                                                             │
│  For each page P in document (window = [P-1, P, P+1]):                     │
│                                                                             │
│  4a. For each object in window:                                            │
│       ├── Check ContextEngine.TM for exact match                          │
│       │   ├── Hit → reuse translation, skip LLM                          │
│       │   └── Miss → continue                                             │
│       ├── Check ContextEngine.TM for fuzzy match (≥85% similarity)        │
│       │   ├── Hit → use with confidence score annotation                  │
│       │   └── Miss → continue                                             │
│       ├── Query ContextEngine for:                                        │
│       │   ├── Neighbor objects (previous, next, parent, children)         │
│       │   ├── Group siblings (MC options collectively)                    │
│       │   ├── Cross-references (resolved figure/table/page refs)          │
│       │   └── Glossary entries matching this object                      │
│       ├── Select pipeline by role:                                        │
│       │   ├── AnswerBlank → AnswerBlankPipeline                          │
│       │   ├── MCOption → MCOptionPipeline                                │
│       │   ├── Question → QuestionPipeline                                │
│       │   └── default → ParagraphPipeline                                 │
│       ├── Execute pipeline:                                               │
│       │   ├── Pre-process (strip markers, preserve patterns)              │
│       │   ├── Build augmented prompt with ContextEngine data              │
│       │   ├── Call AI provider with role-specific temperature             │
│       │   ├── Post-process (re-inject markers, validate structure)        │
│       │   └── Validate intermediate result                                │
│       ├── Record translation in ContextEngine:                            │
│       │   ├── Add to TM (exact)                                           │
│       │   ├── Add to document TM (within-document reuse)                 │
│       │   └── Send to persistent TM queue (batch write)                   │
│       └── Emit progress event                                             │
│                                                                             │
│  4b. After window passes page N:                                          │
│       ├── Page N-2 is finalized (no more neighbor context changes)        │
│       ├── Emit finalized page to reconstructor                            │
│       └── Free page N-2 memory                                            │
│                                                                             │
│  Output: Translated DocumentObjectGraph (annotated with translations)      │
├─────────────────────────────────────────────────────────────────────────────┤
│ STAGE 5: ADAPTIVE LAYOUT RECONSTRUCTION                                     │
│                                                                             │
│  For each page (finalized from Stage 4):                                   │
│                                                                             │
│  5a. FOR DOCX/PPTX/XLSX:                                                  │
│       ├── In-place XML manipulation                                        │
│       │   ├── For each paragraph/shape/cell: replace text with translation │
│       │   ├── Preserve all XML formatting, styles, images, hyperlinks      │
│       │   └── Handle text expansion:                                      │
│       │       ├── If translated_text_fits → replace directly              │
│       │       ├── If translated_text_longer → run overflow_resolver:      │
│       │       │   1. Reduce line spacing                                   │
│       │       │   2. Reduce character spacing                             │
│       │       │   3. Reduce font size (min 0.8x)                          │
│       │       │   4. Expand textbox (if auto-size enabled)                │
│       │       │   5. Move nearby objects (last resort)                    │
│       │       └── If still overflow → WARNING in QA report                │
│       └── Save to output path                                              │
│                                                                             │
│  5b. FOR PDF:                                                             │
│       ├── Use LayoutPlanner to plan adjustments                           │
│       ├── For each page:                                                   │
│       │   ├── Create new PDF page with same dimensions                   │
│       │   ├── Draw non-text elements (images, shapes, lines) as-is        │
│       │   ├── Place translated text at original positions                  │
│       │   ├── Apply layout plan: font scale, position adjustments         │
│       │   └── Handle overflow with continuation objects if needed         │
│       └── Save to output path                                              │
│                                                                             │
│  Output: Translated file (original format)                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ STAGE 6: QUALITY VALIDATION                                                 │
│                                                                             │
│  6a. Run all validation checks (see Section 4.2)                           │
│  6b. Build QualityReport with severity levels                              │
│  6c. Determine recommendation:                                             │
│       ├── CRITICAL count > 0 → "Reject: Requires rework"                  │
│       ├── ERROR count > threshold → "Review: Manual check recommended"    │
│       ├── WARNING count > threshold → "Accept with minor review"          │
│       └── No issues → "Accept: Passed all checks"                         │
│                                                                             │
│  Output: QualityReport JSON                                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ STAGE 7: FINALIZATION                                                       │
│                                                                             │
│  7a. Save translated file to persistent storage                             │
│  7b. Save QualityReport to JSON file                                        │
│  7c. Send callback to Laravel with results                                  │
│  7d. Flush persistent TM queue to database                                  │
│  7e. Clean up temporary files                                               │
│  7f. Free ContextEngine memory                                              │
│                                                                             │
│  Output: job completion callback to Laravel                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Validation Check Matrix

| Check | Severity | Description | Pipeline Response |
|---|---|---|---|
| `image_count_mismatch` | CRITICAL | Translated image count ≠ original | Halt translation |
| `table_count_mismatch` | CRITICAL | Translated table count ≠ original | Halt translation |
| `page_count_changed` | CRITICAL | Page count differs from original | Halt translation |
| `object_count_mismatch` | CRITICAL | Total objects differ significantly | Halt translation |
| `answer_key_corruption` | CRITICAL | Answer letters changed/removed | Halt translation |
| `all_blank_filled` | ERROR | Answer blank has content | Retranslate with stronger constraint |
| `untranslated_text` | ERROR | Source text = target text | Retranslate affected blocks |
| `header_footer_missing` | ERROR | Headers/footers not in output | Retranslate |
| `hyperlink_lost` | WARNING | Hyperlink text not linked | Log for review |
| `numbering_broken` | WARNING | Numbering format inconsistent | Log for review |
| `terminology_inconsistency` | WARNING | Glossary term translated differently | Log for review |
| `grammar_issues` | WARNING | AI reviewer score < 0.7 | Log for review |
| `blank_length_changed` | INFO | Blank underscore count changed | Log only |
| `font_size_changed` | INFO | Font size differs ≤ 2pt | Log only |
| `font_family_changed` | INFO | Font family changed | Log only |

### 4.3 Role-Specific Pipeline Configurations

| Role | Pre-processing | System Prompt Template | Temp | Max Tokens | Post-processing | Validator |
|---|---|---|---|---|---|---|
| **Learning Objective** | Strip number prefix, keep keywords | academic.yaml | 0.4 | 200 | Re-add number prefix | Check for future-tense verbs |
| **Instruction** | Keep bullet markers, extract verbs | imperative.yaml | 0.3 | 300 | Re-inject markers, capitalize first word | Validate imperative mood |
| **Question (stem)** | Preserve `_____` placeholders | interrogative.yaml | 0.4 | 250 | Restore blanks, check question mark | Validate terminal punctuation |
| **MC Option** | Strip choice letter ("A."), keep rest | condensed.yaml | 0.3 | 100 | Re-attach correct choice letter | Validate letter A-D, no duplicates in group |
| **Answer Blank** | Measure blank length | NONE (SKIP) | N/A | N/A | Return blank unchanged | Validate blank exists, length preserved |
| **Answer Key** | Parse `N. Letter` pairs | exact.yaml | 0.1 | 50 | Rebuild pairs, validate letters | CRITICAL: all letters valid |
| **Table Header** | Detect header row (first row of table) | formal.yaml | 0.3 | 100 | Re-check capitalization | Validate header format |
| **Caption** | Preserve "Fig"/"Table" prefix | preserve_structure.yaml | 0.4 | 150 | Re-verify reference consistency | Validate figure/table number |
| **Footer** | Extract page number, preserve as-is | max_50_tokens.yaml | 0.3 | 50 | Re-inject page number | Validate max length 50 tokens |
| **Header** | Preserve document title formatting | formal.yaml | 0.3 | 100 | Re-check formatting | Validate consistency with original |
| **Hyperlink** | Extract URL, keep as metadata | NONE (SKIP TEXT) | N/A | N/A | Re-inject URL, keep text or translate | Validate hyperlink exists |
| **Reference** | Preserve parentheses, author-year | formal.yaml | 0.3 | 200 | Re-verify parentheses | Validate parens preserved |
| **Glossary Term** | Detect term boundary | exact.yaml | 0.1 | 50 | Validate exact match in context | Glossary consistency check |
| **Paragraph** | Full text | standard.yaml | 0.5 | 500 | None | None |
| **Heading** | Preserve numbering, if any | formal.yaml | 0.3 | 100 | Re-check numbering | Validate heading hierarchy |

---

## 5. API Design

### 5.1 Laravel → Python Microservice API

#### Health Check
```
GET /health
Response:
{
  "status": "ok",
  "engine": "provider:gptoss",
  "model": "llama3.1:8b",
  "active_provider": "gptoss",
  "available_providers": ["gptoss", "mistral"],
  "languages": ["English", "Filipino", "Cebuano"],
  "formats": [".docx", ".pdf", ".pptx", ".xlsx", ".txt", ".csv"],
  "provider_status": { "available": true, "model": "llama3.1:8b" }
}
```

#### Document Translation (Async)
```
POST /translate/document
Content-Type: multipart/form-data

Fields:
  job_id: string (required) — UUID from Laravel
  file: UploadFile (required)
  source_lang: string (required)
  target_lang: string (required)
  mode: string (optional, default: "balanced")
  project_id: int (optional) — for TM scoping
  user_glossary: json (optional) — [{source, target}, ...]

Response (202 Accepted):
{
  "job_id": "uuid-here",
  "status": "accepted",
  "estimated_pages": 45,
  "estimated_time_seconds": 120
}
```

#### Translation Status (Polling)
```
GET /translate/status/{job_id}
Response:
{
  "job_id": "uuid-here",
  "status": "processing",  // "pending" | "processing" | "completed" | "failed"
  "progress": {
    "stage": "translating",  // "parsing" | "analyzing" | "translating" | "reconstructing" | "validating"
    "percent": 65,
    "current_page": 30,
    "total_pages": 45,
    "current_object": 450,
    "total_objects": 720,
    "message": "Translating page 30/45..."
  },
  "result": null,  // populated when completed
  "error": null,   // populated when failed
  "created_at": "2026-07-15T10:00:00Z",
  "completed_at": null
}
```

#### Text Translation (Sync)
```
POST /translate/text
Body:
{
  "text": "Hello, how are you?",
  "source_lang": "English",
  "target_lang": "Cebuano",
  "block_type": "paragraph",  // optional
  "context_hint": "",         // optional
  "document_type": ""         // optional
}

Response:
{
  "translated": "Kumusta, ikaw?",
  "provider": "gptoss",
  "model": "llama3.1:8b",
  "token_usage": { "input": 15, "output": 8 },
  "execution_time_ms": 1234
}
```

#### Translation Memory Query
```
POST /tm/query
Body:
{
  "text": "What I Need to Know",
  "source_lang": "English",
  "target_lang": "Cebuano",
  "min_similarity": 0.85  // optional, fuzzy matching threshold
}

Response:
{
  "matches": [
    {
      "text": "What I Need to Know",
      "translated": "Ang Kinahanglan Nakong Mahibaloan",
      "similarity": 1.0,
      "source": "project:42",  // where this TM entry came from
      "confidence": 0.98
    },
    {
      "text": "What I Need To Know",  // note case difference
      "translated": "Ang Kinahanglan Nakong Mahibaloan",
      "similarity": 0.93,
      "source": "project:17",
      "confidence": 0.93
    }
  ]
}
```

#### Document Analysis Only (No translation)
```
POST /analyze
Body: { "file": UploadFile }

Response:
{
  "pages": 45,
  "objects": 720,
  "roles": {
    "heading": 25,
    "paragraph": 320,
    "question": 50,
    "mc_option": 200,
    "answer_blank": 50,
    "answer_key": 50,
    "table_header": 10,
    "table_cell": 15
  },
  "document_type": "educational_module",
  "language": "English",
  "estimated_complexity": "high",
  "recommended_mode": "thorough"
}
```

#### Quality Validation Only
```
POST /validate
Body:
{
  "original_file": UploadFile,
  "translated_file": UploadFile,
  "source_lang": "English",
  "target_lang": "Cebuano"
}

Response:
{
  "overall_score": 0.92,
  "passed": true,
  "critical_count": 0,
  "error_count": 0,
  "warning_count": 2,
  "info_count": 3,
  "checks": [...],
  "recommendation": "Accept with minor review"
}
```

### 5.2 Laravel Web API (for frontend)

```
GET    /api/projects                     → List user's projects
POST   /api/projects                     → Create project
GET    /api/projects/{id}                → Project details
DELETE /api/projects/{id}                → Delete project

GET    /api/projects/{id}/documents      → List documents in project
POST   /api/projects/{id}/documents      → Upload document to project
GET    /api/documents/{id}               → Document details
DELETE /api/documents/{id}               → Delete document

POST   /api/documents/{id}/translate     → Submit translation job
GET    /api/jobs/{id}                    → Job status + progress
GET    /api/jobs/{id}/result             → Download translated file
GET    /api/jobs/{id}/report             → Download quality report

GET    /api/translation-memory           → List TM entries
POST   /api/translation-memory           → Add TM entry
POST   /api/translation-memory/import    → Bulk import TM CSV
GET    /api/translation-memory/export    → Export TM as CSV

GET    /api/glossary                     → List glossary entries
POST   /api/glossary                     → Add glossary entry
POST   /api/glossary/import              → Bulk import glossary
```

---

## 6. Database Schema Improvements

### 6.1 Current Schema Gaps

The current schema (based on controller analysis) lacks:
- Translation Memory persistence
- Document Object Graph metadata
- Quality Report storage
- Job progress tracking
- Project ↔ Document ↔ Job relationships
- Checkpoint/resume data

### 6.2 Proposed Schema

```sql
-- Projects (grouping documents)
CREATE TABLE projects (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id         BIGINT UNSIGNED NOT NULL,
    name            VARCHAR(255) NOT NULL,
    description     TEXT NULL,
    source_lang     VARCHAR(50) NOT NULL DEFAULT 'English',
    target_lang     VARCHAR(50) NOT NULL DEFAULT 'Cebuano',
    default_mode    ENUM('fast', 'balanced', 'thorough') NOT NULL DEFAULT 'balanced',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_projects_user (user_id)
);

-- Documents (uploaded files)
CREATE TABLE documents (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    project_id      BIGINT UNSIGNED NULL,
    user_id         BIGINT UNSIGNED NOT NULL,
    filename        VARCHAR(255) NOT NULL,
    original_path   VARCHAR(500) NOT NULL,        -- Path in storage
    file_format     VARCHAR(10) NOT NULL,          -- docx, pdf, pptx, etc.
    file_size       BIGINT UNSIGNED NOT NULL,      -- Bytes
    page_count      INT UNSIGNED NULL,             -- Populated after analysis
    object_count    INT UNSIGNED NULL,             -- Populated after analysis
    word_count      INT UNSIGNED NULL,
    document_type   VARCHAR(100) NULL,             -- From semantic analysis
    metadata_json   JSON NULL,                     -- Full Document Profile
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_documents_project (project_id),
    INDEX idx_documents_user (user_id)
);

-- Translation Jobs
CREATE TABLE translation_jobs (
    id              CHAR(36) PRIMARY KEY,          -- UUID
    document_id     BIGINT UNSIGNED NOT NULL,
    user_id         BIGINT UNSIGNED NOT NULL,
    project_id      BIGINT UNSIGNED NULL,
    source_lang     VARCHAR(50) NOT NULL,
    target_lang     VARCHAR(50) NOT NULL,
    mode            ENUM('fast', 'balanced', 'thorough', 'auto') NOT NULL DEFAULT 'balanced',
    status          ENUM('pending', 'processing', 'completed', 'failed', 'cancelled')
                        NOT NULL DEFAULT 'pending',
    progress_stage  VARCHAR(50) NULL,              -- Current pipeline stage
    progress_percent DECIMAL(5,2) NULL,            -- 0.00 - 100.00
    current_page    INT UNSIGNED NULL,
    total_pages     INT UNSIGNED NULL,
    error_message   TEXT NULL,
    output_path     VARCHAR(500) NULL,             -- Path to translated file
    report_path     VARCHAR(500) NULL,             -- Path to quality report JSON
    total_time_ms   BIGINT UNSIGNED NULL,
    provider_name   VARCHAR(50) NULL,
    model_name      VARCHAR(100) NULL,
    token_input     INT UNSIGNED NULL,
    token_output    INT UNSIGNED NULL,
    checkpoint_data JSON NULL,                     -- Resume checkpoint
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at    TIMESTAMP NULL,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    INDEX idx_jobs_status (status),
    INDEX idx_jobs_user (user_id),
    INDEX idx_jobs_document (document_id),
    INDEX idx_jobs_created (created_at)
);

-- Translation Memory (persistent, cross-document)
CREATE TABLE translation_memory_entries (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    project_id      BIGINT UNSIGNED NULL,          -- NULL = global TM
    user_id         BIGINT UNSIGNED NULL,           -- NULL = system TM
    source_lang     VARCHAR(50) NOT NULL,
    target_lang     VARCHAR(50) NOT NULL,
    source_text     TEXT NOT NULL,
    translated_text TEXT NOT NULL,
    source_hash     CHAR(64) NOT NULL,              -- SHA-256 for exact lookup
    role            VARCHAR(50) NULL,                -- Semantic role when recorded
    confidence      DECIMAL(5,4) NOT NULL DEFAULT 1.0000,
    usage_count     INT UNSIGNED NOT NULL DEFAULT 1,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_tm_hash (source_hash, source_lang, target_lang),
    INDEX idx_tm_source (source_text(100), source_lang, target_lang),
    INDEX idx_tm_project (project_id),
    INDEX idx_tm_last_used (last_used_at)
);

-- User Glossary
CREATE TABLE glossary_entries (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id         BIGINT UNSIGNED NOT NULL,
    project_id      BIGINT UNSIGNED NULL,
    source_lang     VARCHAR(50) NOT NULL,
    target_lang     VARCHAR(50) NOT NULL,
    source_term     VARCHAR(255) NOT NULL,
    translated_term VARCHAR(255) NOT NULL,
    context         TEXT NULL,                      -- Optional context for disambiguation
    category        VARCHAR(100) NULL,              -- e.g., "academic", "legal", "medical"
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    INDEX idx_glossary_user (user_id),
    INDEX idx_glossary_term (source_term(100), source_lang, target_lang)
);

-- Quality Reports
CREATE TABLE quality_reports (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    job_id          CHAR(36) NOT NULL,
    document_id     BIGINT UNSIGNED NOT NULL,
    overall_score   DECIMAL(5,4) NOT NULL,
    passed          BOOLEAN NOT NULL DEFAULT TRUE,
    critical_count  INT UNSIGNED NOT NULL DEFAULT 0,
    error_count     INT UNSIGNED NOT NULL DEFAULT 0,
    warning_count   INT UNSIGNED NOT NULL DEFAULT 0,
    info_count      INT UNSIGNED NOT NULL DEFAULT 0,
    recommendation  VARCHAR(255) NOT NULL,
    checks_json     JSON NOT NULL,                  -- Full check results array
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES translation_jobs(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    INDEX idx_reports_job (job_id),
    INDEX idx_reports_score (overall_score)
);

-- Document Object Graph Checkpoints (for resume/restore)
CREATE TABLE document_checkpoints (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    job_id          CHAR(36) NOT NULL,
    checkpoint_type ENUM('full_graph', 'translated_pages', 'context_engine') NOT NULL,
    stage           VARCHAR(50) NOT NULL,           -- Pipeline stage when saved
    page_from       INT UNSIGNED NULL,
    page_to         INT UNSIGNED NULL,
    data_path       VARCHAR(500) NOT NULL,          -- Path to checkpoint file (JSON/msgpack)
    file_size       BIGINT UNSIGNED NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES translation_jobs(id) ON DELETE CASCADE,
    INDEX idx_checkpoint_job (job_id),
    INDEX idx_checkpoint_stage (stage)
);
```

### 6.3 Schema Design Rationale

| Decision | Rationale |
|---|---|
| Separate `translation_memory_entries` table | Enables cross-document reuse, separate from per-document cache |
| `source_hash` SHA-256 column | O(1) exact lookup, indexes well, 64 chars fixed width |
| `usage_count` on TM entries | Enables popularity-based pruning for storage limits |
| `last_used_at` on TM | Enables LRU eviction strategy |
| `checkpoint_data` JSON on jobs | Lightweight resume without separate table for simple cases |
| `checks_json` on quality_reports | Flexible schema for evolving validation checks |
| `project_id` nullable on TM/glossary | Supports both project-specific and global entries |
| `role` on TM entries | Enables role-aware TM matching (MC option TM separate from paragraph TM) |

---

## 7. Queue Architecture

### 7.1 Queue Topology

```
                         ┌──────────────────┐
                         │   User Request   │
                         └────────┬─────────┘
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │   Laravel Horizon        │
                    │   (Queue: translations)  │
                    └────────┬────────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │ Python Worker │ │ Python Worker │ │ Python Worker │
    │ (document)    │ │ (document)    │ │ (document)    │
    └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
           │                │                │
           └────────────────┼────────────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │   Redis Pub/Sub  │
                  │ (job:progress)   │
                  └──────────────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │   Laravel Echo    │
                  │   (WebSockets)    │
                  └──────────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │   Browser    │
                    └──────────────┘
```

### 7.2 Queue Configuration

```php
// config/queue.php (Horizon)
'redis' => [
    'driver' => 'redis',
    'connection' => 'default',
    'queue' => [
        'translations',         // Document translation jobs
        'translations:high',    // Priority translations
        'tm:write',             // TM persistence writes
        'cleanup',              // Temp file cleanup
        'default',              // General purpose
    ],
    'retry_after' => 3600,      // 1 hour timeout for translations
    'block_for' => 5,
    'after_commit' => true,
],
```

### 7.3 Worker Scaling Strategy

```
Python Workers:
  ──────────────────────────────────────────────
  Worker Type        │ Concurrency │ Purpose
  ──────────────────────────────────────────────
  document_worker    │ 2-4         │ Document translation (high memory)
  batch_worker       │ 1-2         │ Batch processing (lower priority)
  tm_write_worker    │ 1           │ TM persistence (lightweight)
  cleanup_worker     │ 1           │ Temp file cleanup (scheduled)
  ──────────────────────────────────────────────

  Auto-scaling rule: If queue length > 10, spawn additional document_worker
  Max concurrent: 4 document workers (RAM: ~2GB each for large documents)
```

### 7.4 Celery Configuration (Python side)

```python
# config/celery.py
from celery import Celery

celery_app = Celery(
    'trilingua_workers',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0',
    include=['workers.document_worker', 'workers.batch_worker']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Manila',
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,           # Re-queue on worker crash
    worker_prefetch_multiplier=1,  # Fair scheduling
    task_soft_time_limit=3600,     # 1 hour soft limit
    task_time_limit=3900,          # 65 min hard limit
    task_reject_on_worker_lost=True,
)
```

### 7.5 Progress Streaming Architecture

```
Python Worker
    │
    ├── pipeline.progress = 45%
    │
    ├── Redis PUBLISH job:{job_id}:progress
    │   Payload: { "percent": 45, "stage": "translating",
    │              "current_page": 30, "total_pages": 45,
    │              "message": "Translating page 30/45..." }
    │
    ▼
Laravel Redis SUBSCRIBE job:{job_id}:progress
    │
    ├── Update translation_jobs.progress_percent
    ├── Update translation_jobs.progress_stage
    ├── Update translation_jobs.current_page
    │
    ├── Broadcast event to Laravel Echo channel
    │   Channel: job.{job_id}
    │   Event: TranslationProgressUpdated
    │
    ▼
Browser (Laravel Echo + WebSockets)
    │
    └── Update UI progress bar + stage description
```

---

## 8. Storage Architecture

### 8.1 Storage Layers

```
┌─────────────────────────────────────────────────────────────────────┐
│                        STORAGE ARCHITECTURE                         │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    PERSISTENT STORAGE                        │   │
│  │                    (S3 / MinIO / Local)                      │   │
│  │                                                              │   │
│  │  /uploads/{user_id}/{uuid}/original.{ext}                   │   │
│  │  /uploads/{user_id}/{uuid}/translated.{ext}                 │   │
│  │  /uploads/{user_id}/{uuid}/quality_report.json              │   │
│  │  /checkpoints/{job_id}/stage_{stage}.msgpack                │   │
│  │  /tm/exports/{user_id}/tm_export_{date}.csv                 │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    TEMPORARY STORAGE                         │   │
│  │                    (Local filesystem, TTL: 24h)              │   │
│  │                                                              │   │
│  │  /tmp/trilingua/{job_id}/input.{ext}                        │   │
│  │  /tmp/trilingua/{job_id}/output.{ext}                       │   │
│  │  /tmp/trilingua/{job_id}/checkpoint_{page}.json             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    CACHE STORAGE                             │   │
│  │                    (Redis)                                   │   │
│  │                                                              │   │
│  │  translation_cache:{source_lang}:{target_lang}:{hash}       │   │
│  │      → String value (translated text), TTL: 1 hour          │   │
│  │                                                              │   │
│  │  document_graph:{job_id}                                     │   │
│  │      → Hash (page_number → serialized objects)              │   │
│  │      → TTL: 2 hours (aligned with job lifetime)             │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.2 File Naming Convention

```
Pattern: {scope}/{entity_type}/{identifier}/{variant}.{ext}

Examples:
  uploads/42/job-a1b2c3/original.docx
  uploads/42/job-a1b2c3/translated.docx
  uploads/42/job-a1b2c3/quality_report.json

Checkpoints:
  checkpoints/job-a1b2c3/stage_2_semantic_analysis.msgpack
  checkpoints/job-a1b2c3/stage_4_page_15.msgpack
  checkpoints/job-a1b2c3/stage_4_page_30.msgpack
```

### 8.3 Storage Provider Strategy

```php
// config/filesystems.php
'disks' => [
    'uploads' => [
        'driver' => env('UPLOAD_DRIVER', 'local'),
        'root' => storage_path('app/uploads'),
        'visibility' => 'private',
    ],
    's3' => [
        'driver' => 's3',
        'key' => env('AWS_ACCESS_KEY_ID'),
        'secret' => env('AWS_SECRET_ACCESS_KEY'),
        'region' => env('AWS_DEFAULT_REGION'),
        'bucket' => env('AWS_BUCKET'),
        'visibility' => 'private',
    ],
    'minio' => [
        'driver' => 's3',
        'key' => env('MINIO_ACCESS_KEY'),
        'secret' => env('MINIO_SECRET_KEY'),
        'region' => 'us-east-1',
        'bucket' => env('MINIO_BUCKET', 'trilingua'),
        'endpoint' => env('MINIO_ENDPOINT', 'http://localhost:9000'),
        'use_path_style_endpoint' => true,
        'visibility' => 'private',
    ],
],
```

### 8.4 Storage Lifecycle

```
Upload
  │
  ├── File saved to persistent storage (S3/MinIO/Local)
  ├── Translation job references path
  │
  ├── TRANSLATION BEGINS
  │     ├── File copied to temp storage for processing
  │     └── Temporary checkpoints written every N pages
  │
  ├── TRANSLATION COMPLETES
  │     ├── Translated file saved to persistent storage
  │     ├── Quality report saved alongside
  │     ├── TM entries queued for DB write
  │     └── Temp files cleaned up
  │
  └── USER DOWNLOADS
        ├── File served from persistent storage
        └── Signed URL with expiry (60 min for S3)
```

---

## 9. Translation Memory Implementation

### 9.1 Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     TRANSLATION MEMORY SYSTEM                       │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                   LAYER 1: IN-MEMORY CACHE                  │   │
│  │                   (Python, per-job, O(1))                   │   │
│  │                                                              │   │
│  │  structure: dict[source_lang][target_lang][source_hash]      │   │
│  │  lookup:   O(1) — SHA-256 hash of source text               │   │
│  │  capacity: 10,000 entries per job (LRU eviction)            │   │
│  │  purpose:  Absorb repeated phrases within the same document  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                           │                                         │
│                           ▼                                         │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                LAYER 2: PERSISTENT TM (Redis)               │   │
│  │                (Python, shared across workers)               │   │
│  │                                                              │   │
│  │  structure: Redis Hash: tm:{source_lang}:{target_lang}       │   │
│  │  key:       SHA-256 of source text                           │   │
│  │  value:     { translated, role, confidence, project_id }     │   │
│  │  lookup:    O(1) — Redis hash get                            │   │
│  │  TTL:       7 days (hot TM entries)                          │   │
│  │  purpose:   Cross-job reuse within same day/week             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                           │                                         │
│                           ▼                                         │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              LAYER 3: PERSISTENT TM (SQL/DB)                │   │
│  │              (Laravel, full persistence)                     │   │
│  │                                                              │   │
│  │  structure: translation_memory_entries table                 │   │
│  │  lookup:    O(log n) — B-tree on source_hash                │   │
│  │  capacity:  Unlimited (disk-bound)                           │   │
│  │  purpose:   Long-term storage, export, training data         │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                           │                                         │
│                           ▼                                         │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                LAYER 4: FUZZY MATCHING                      │   │
│  │                (Python, BK-tree + Levenshtein)               │   │
│  │                                                              │   │
│  │  structure: In-memory BK-tree per language pair              │   │
│  │  threshold: 85% similarity (configurable)                    │   │
│  │  lookup:    O(log n) amortized                               │   │
│  │  capacity:  10,000 entries (loaded from Layer 3 on demand)   │   │
│  │  purpose:   Catch minor variations: "What I Need to Know"    │   │
│  │             vs "What I need to know" vs "What I Need To Know"│   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 9.2 TM Lookup Flow

```
translate(text="What I Need to Know", role="learning_objective")
    │
    ├── 1. Layer 1: In-memory cache (per-job)
    │         hash = sha256("What I Need to Know")
    │         result = cache[source_lang][target_lang][hash]
    │         FOUND? → return immediately (O(1))
    │
    ├── 2. Layer 2: Redis cache (cross-job hot)
    │         result = redis.hget("tm:en:ceb", hash)
    │         FOUND? → cache in Layer 1, return (O(1))
    │
    ├── 3. Layer 3: SQL database (full persistence)
    │         result = DB::where('source_hash', hash)
    │                    ->where('source_lang', 'en')
    │                    ->where('target_lang', 'ceb')
    │                    ->first()
    │         FOUND? → cache in Layer 1 + Layer 2, return
    │
    ├── 4. Layer 4: Fuzzy match (no exact found)
    │         candidates = bk_tree.search(text, threshold=0.85)
    │         best = candidates[0] if candidates else None
    │         FOUND? → cache in Layer 1, return with lower confidence
    │
    └── 5. No match → translate via AI provider
              → cache result in all 4 layers
              → queue for DB write (async)
              → return
```

### 9.3 TM Write Strategy (Batch Queue)

```
After each object translation:
    │
    ├── Don't write to DB immediately (too slow)
    │
    ├── Add to in-memory batch buffer
    │   buffer.append({ source, translated, role, confidence })
    │
    ├── If buffer.size >= 100 OR 30 seconds elapsed:
    │       │
    │       ├── Serialize buffer to JSON
    │       ├── Push to Redis list: tm:write_queue
    │       │
    │       └── Laravel worker pops from tm:write_queue:
    │               ├── INSERT ... ON DUPLICATE KEY UPDATE
    │               │   (upsert on source_hash + lang pair)
    │               └── Increment usage_count
    │
    └── TM write worker runs every 5 seconds
```

### 9.4 TM Storage Optimization

```sql
-- Efficient upsert query for TM batch writes
INSERT INTO translation_memory_entries
    (project_id, user_id, source_lang, target_lang,
     source_text, translated_text, source_hash, role, confidence)
VALUES
    (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON DUPLICATE KEY UPDATE
    translated_text = VALUES(translated_text),
    usage_count = usage_count + 1,
    confidence = GREATEST(confidence, VALUES(confidence)),
    last_used_at = NOW();
```

### 9.5 Fuzzy Matching Implementation

```python
# memory/bk_tree.py
class BKTree:
    """BK-tree for fuzzy string matching using Levenshtein distance."""

    def __init__(self, threshold: float = 0.85):
        self.tree = {}  # node_id → (text, children)
        self.texts = {}  # text → TMEntry
        self.threshold = threshold
        self.root = None

    def search(self, query: str) -> list[tuple[str, float]]:
        """Find all matches within similarity threshold.

        Returns: [(matched_text, similarity), ...] sorted by similarity desc.
        """
        if not self.root:
            return []

        max_distance = len(query) - int(len(query) * self.threshold)
        candidates = []

        # BFS with pruning
        stack = [(self.root, None)]
        while stack:
            node_id, parent_id = stack.pop()
            node_text = self.texts[node_id]
            dist = levenshtein(query, node_text)

            if dist <= max_distance:
                similarity = 1.0 - (dist / max(len(query), len(node_text)))
                candidates.append((node_text, similarity))

            # Prune: only explore children within (dist - max_distance, dist + max_distance)
            # BK-tree property: children are grouped by distance
            for child_dist, child_id in self.tree[node_id].get('children', {}).items():
                if abs(child_dist - dist) <= max_distance:
                    stack.append((child_id, node_id))

        candidates.sort(key=lambda x: -x[1])
        return candidates[:5]  # Top 5 matches
```

---

## 10. Document Object Graph Design

### 10.1 Core Data Model

```python
# intelligence/graph/document_graph.py
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum, auto

# ── Enums ──────────────────────────────────────────────────────────────

class ObjectType(Enum):
    TEXT = auto()
    TABLE = auto()
    IMAGE = auto()
    SHAPE = auto()
    TEXTBOX = auto()
    HEADER = auto()
    FOOTER = auto()
    PAGE_NUMBER = auto()
    LIST_ITEM = auto()
    HYPERLINK = auto()

class SemanticRole(Enum):
    # Educational document roles
    LEARNING_OBJECTIVE = auto()
    INSTRUCTION = auto()
    QUESTION_STEM = auto()
    MULTIPLE_CHOICE_OPTION = auto()
    ANSWER_BLANK = auto()
    ANSWER_KEY = auto()
    WORKSHEET_TITLE = auto()

    # Structural roles
    HEADING_1 = auto()
    HEADING_2 = auto()
    HEADING_3 = auto()
    PARAGRAPH = auto()
    CAPTION = auto()
    TABLE_HEADER = auto()
    TABLE_CELL = auto()
    FOOTER_TEXT = auto()
    HEADER_TEXT = auto()
    PAGE_NUMBER_TEXT = auto()

    # Reference roles
    FIGURE_REFERENCE = auto()
    TABLE_REFERENCE = auto()
    CITATION = auto()
    HYPERLINK_TEXT = auto()
    GLOSSARY_TERM = auto()
    REFERENCE_ENTRY = auto()

    # Fallback
    UNKNOWN = auto()

class ObjectRelationType(Enum):
    PARENT = auto()
    CHILD = auto()
    NEXT_SIBLING = auto()
    PREV_SIBLING = auto()
    GROUP_MEMBER = auto()
    CROSS_REFERENCE = auto()
    CONTINUATION = auto()

# ── Position / Bounding Box ──────────────────────────────────────────

@dataclass
class BoundingBox:
    """Position on the page in points (1/72 inch)."""
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2

# ── Style Information ────────────────────────────────────────────────

@dataclass
class TextStyle:
    font_family: str = "helv"
    font_size: float = 11.0
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: int = 0           # RGB integer (0xRRGGBB)
    alignment: Optional[str] = None  # "left", "center", "right", "justify"
    line_spacing: Optional[float] = None
    character_spacing: Optional[float] = None

# ── Document Objects ─────────────────────────────────────────────────

@dataclass
class DocumentObject:
    """A single object in the document. The atomic unit of processing."""
    id: str                          # Unique within document (e.g., "page_3_obj_14")
    object_type: ObjectType
    semantic_role: SemanticRole = SemanticRole.UNKNOWN
    role_confidence: float = 0.0     # 0.0 - 1.0
    original_text: str = ""
    translated_text: str = ""
    bbox: Optional[BoundingBox] = None
    style: TextStyle = field(default_factory=TextStyle)
    page_number: int = 0
    layer: int = 0                   # Z-order (0 = background, 1+ = foreground)
    reading_order: int = 0           # Position in reading sequence
    metadata: dict[str, Any] = field(default_factory=dict)

    # Structure preservation
    format_markers: dict[str, str] = field(default_factory=dict)
    """Preserved structural elements, e.g.:
       {"answer_blank": "______", "number_prefix": "1.", "choice_letter": "A"}"""

    def is_translatable(self) -> bool:
        """Whether this object should be sent to the LLM."""
        return self.semantic_role not in (
            SemanticRole.ANSWER_BLANK,
            SemanticRole.IMAGE,
            SemanticRole.HYPERLINK_TEXT,
        )

    @property
    def word_count(self) -> int:
        return len(self.original_text.split())

# ── Object Relations ─────────────────────────────────────────────────

@dataclass
class ObjectRelation:
    """A relationship between two objects in the document."""
    source_id: str
    target_id: str
    relation_type: ObjectRelationType
    metadata: dict[str, Any] = field(default_factory=dict)

# ── Object Groups ────────────────────────────────────────────────────

@dataclass
class ObjectGroup:
    """A semantic group of objects (e.g., question + options)."""
    id: str
    group_type: str                  # "question_group", "section", "list"
    member_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

# ── Page ─────────────────────────────────────────────────────────────

@dataclass
class Page:
    """A single page in the document."""
    number: int
    width: float                     # Points
    height: float                    # Points
    objects: dict[str, DocumentObject] = field(default_factory=dict)
    """object_id → DocumentObject. Maintained as dict for O(1) lookup."""

    def get_reading_order(self) -> list[DocumentObject]:
        """Return objects sorted by reading order."""
        return sorted(
            self.objects.values(),
            key=lambda o: (o.reading_order, o.bbox.center_y if o.bbox else 0)
        )

# ── Document Graph ───────────────────────────────────────────────────

@dataclass
class DocumentObjectGraph:
    """The canonical representation of a document.

    This is the CENTRAL data structure that all components operate on.
    Format adapters produce it. Semantic analysis annotates it.
    Context engine queries it. Translation engine modifies it.
    Reconstructor consumes it.
    """
    # Identity
    document_id: str = ""
    filename: str = ""
    file_format: str = ""            # "docx", "pdf", "pptx", etc.

    # Metadata
    metadata: dict[str, Any] = field(default_factory=lambda: {
        "title": "",
        "author": "",
        "total_pages": 0,
        "total_objects": 0,
        "source_lang": "",
        "target_lang": "",
        "created_at": "",
    })

    # Structure
    pages: dict[int, Page] = field(default_factory=dict)
    """page_number → Page"""

    # Global lookups
    all_objects: dict[str, DocumentObject] = field(default_factory=dict)
    """object_id → DocumentObject (flattened across all pages)"""

    # Relations
    relations: list[ObjectRelation] = field(default_factory=list)

    # Groups
    groups: list[ObjectGroup] = field(default_factory=list)

    # Document-level
    glossary: list[str] = field(default_factory=list)
    """Extracted glossary terms (for this document)"""

    repeated_phrases: list[str] = field(default_factory=list)
    """Phrases appearing 3+ times (for TM preloading)"""

    errors: list[str] = field(default_factory=list)
    """Warnings/errors from parsing (non-fatal)"""

    # ── Convenience Methods ──────────────────────────────────────────

    def get_object(self, object_id: str) -> Optional[DocumentObject]:
        return self.all_objects.get(object_id)

    def get_objects_by_role(self, role: SemanticRole) -> list[DocumentObject]:
        return [
            obj for obj in self.all_objects.values()
            if obj.semantic_role == role
        ]

    def get_objects_by_type(self, obj_type: ObjectType) -> list[DocumentObject]:
        return [
            obj for obj in self.all_objects.values()
            if obj.object_type == obj_type
        ]

    def get_page_objects(self, page_num: int) -> list[DocumentObject]:
        page = self.pages.get(page_num)
        return list(page.objects.values()) if page else []

    def get_group_objects(self, group_id: str) -> list[DocumentObject]:
        group = next((g for g in self.groups if g.id == group_id), None)
        if not group:
            return []
        return [self.all_objects[oid] for oid in group.member_ids
                if oid in self.all_objects]

    def get_neighbors(self, object_id: str, distance: int = 1) -> list[DocumentObject]:
        """Get neighboring objects in reading order on the same page."""
        obj = self.all_objects.get(object_id)
        if not obj:
            return []
        page = self.pages.get(obj.page_number)
        if not page:
            return []
        reading_order = page.get_reading_order()
        try:
            idx = next(i for i, o in enumerate(reading_order) if o.id == object_id)
        except StopIteration:
            return []
        start = max(0, idx - distance)
        end = min(len(reading_order), idx + distance + 1)
        return [o for o in reading_order[start:end] if o.id != object_id]

    def validate_integrity(self) -> list[str]:
        """Validate graph completeness. Returns list of issues."""
        issues = []
        for page in self.pages.values():
            for obj in page.objects.values():
                if obj.id not in self.all_objects:
                    issues.append(f"Page {page.number} has object {obj.id} not in all_objects")
        for obj_id in self.all_objects:
            page = self.pages.get(self.all_objects[obj_id].page_number)
            if page and obj_id not in page.objects:
                issues.append(f"Object {obj_id} references page {self.all_objects[obj_id].page_number} but not found there")
        return issues

    def to_serializable(self) -> dict:
        """Serialize to JSON-safe dict for checkpointing."""
        # Implementation uses dataclass-asdict with custom encoders
        ...

    @classmethod
    def from_serializable(cls, data: dict) -> 'DocumentObjectGraph':
        """Deserialize from dict."""
        ...

    def estimate_memory_mb(self) -> float:
        """Estimate memory footprint for this graph."""
        total = 0
        for obj in self.all_objects.values():
            total += len(obj.original_text) * 2  # Unicode: 2 bytes/char
            total += 512  # Overhead for dataclass fields
        total += len(self.pages) * 256  # Page overhead
        return total / (1024 * 1024)
```

### 10.2 Example: DepEd Module Object Graph

```
DocumentObjectGraph
├── metadata:
│   ├── title: "Science 6 - Quarter 1 - Module 1"
│   ├── total_pages: 32
│   └── total_objects: 612
│
├── pages[1]:
│   ├── objects:
│   │   ├── "p1_obj_0": DocumentObject
│   │   │   ├── type: HEADER
│   │   │   ├── role: HEADER_TEXT
│   │   │   ├── text: "Science 6 | Quarter 1 | Module 1"
│   │   │   ├── bbox: (72, 50, 540, 70)
│   │   │   └── style: { font_size: 10, bold: true }
│   │   │
│   │   ├── "p1_obj_1": DocumentObject
│   │   │   ├── type: TEXT
│   │   │   ├── role: LEARNING_OBJECTIVE
│   │   │   ├── text: "What I Need to Know"
│   │   │   ├── bbox: (72, 100, 540, 130)
│   │   │   ├── style: { font_size: 16, bold: true }
│   │   │   └── reading_order: 0
│   │   │
│   │   ├── "p1_obj_2": DocumentObject
│   │   │   ├── type: TEXT
│   │   │   ├── role: PARAGRAPH
│   │   │   ├── text: "This module was designed to provide you with fun and meaningful opportunities..."
│   │   │   ├── bbox: (72, 140, 540, 200)
│   │   │   ├── style: { font_size: 11 }
│   │   │   └── reading_order: 1
│   │   │
│   │   ├── "p1_obj_3": DocumentObject
│   │   │   └── ... (image)
│   │   │
│   │   └── "p1_obj_10": DocumentObject
│   │       ├── type: FOOTER
│   │       ├── role: FOOTER_TEXT
│   │       ├── text: "Page 1"
│   │       └── bbox: (72, 750, 540, 770)
│   │
│   └── reading_order: [p1_obj_1, p1_obj_2, ...]
│
├── pages[5]:
│   └── objects:
│       ├── "p5_obj_0": DocumentObject (role: INSTRUCTION, text: "Directions: Read each item carefully.")
│       ├── "p5_obj_1": DocumentObject (role: QUESTION_STEM, text: "1. What is the largest planet?")
│       ├── "p5_obj_2": DocumentObject (role: MULTIPLE_CHOICE_OPTION, text: "A. Mars")
│       ├── "p5_obj_3": DocumentObject (role: MULTIPLE_CHOICE_OPTION, text: "B. Jupiter")
│       ├── "p5_obj_4": DocumentObject (role: MULTIPLE_CHOICE_OPTION, text: "C. Saturn")
│       ├── "p5_obj_5": DocumentObject (role: MULTIPLE_CHOICE_OPTION, text: "D. Neptune")
│       └── "p5_obj_6": DocumentObject (role: ANSWER_BLANK, text: "______")
│
├── relations:
│   ├── Relation(source="p5_obj_1", target="p5_obj_2", type=GROUP_MEMBER, metadata={group: "q1"})
│   ├── Relation(source="p5_obj_1", target="p5_obj_3", type=GROUP_MEMBER, metadata={group: "q1"})
│   ├── Relation(source="p5_obj_1", target="p5_obj_4", type=GROUP_MEMBER, metadata={group: "q1"})
│   ├── Relation(source="p5_obj_1", target="p5_obj_5", type=GROUP_MEMBER, metadata={group: "q1"})
│   └── Relation(source="p5_obj_1", target="p5_obj_6", type=GROUP_MEMBER, metadata={group: "q1"})
│
├── groups:
│   └── ObjectGroup(id="q1", type="question_group", members=["p5_obj_1", "p5_obj_2", ..., "p5_obj_6"])
│
└── glossary: ["photosynthesis", "deposition", "erosion", "weathering"]
```

### 10.3 Serialization Format (Checkpoints)

```python
# Checkpoint file format: MessagePack (binary JSON)
# Smaller, faster to parse than JSON for large object graphs
#
# Structure:
{
  "version": 2,
  "document_id": "uuid",
  "metadata": { ... },
  "pages": [
    {
      "number": 1,
      "width": 612.0,
      "height": 792.0,
      "objects": [
        {
          "id": "p1_obj_0",
          "type": 0,  # ObjectType enum value
          "role": 13, # SemanticRole enum value
          "role_conf": 0.95,
          "orig": "What I Need to Know",
          "trans": "",  # Empty until translated
          "bbox": [72.0, 100.0, 540.0, 130.0],
          "style": { "font_size": 16, "bold": true },
          "page": 1,
          "layer": 0,
          "order": 0,
          "markers": {}
        }
      ]
    }
  ],
  "relations": [
    {"src": "p5_obj_1", "tgt": "p5_obj_2", "type": 4, "meta": {"group": "q1"}}
  ],
  "groups": [
    {"id": "q1", "type": "question_group", "members": ["p5_obj_1", "p5_obj_2", ...]}
  ]
}
```

---

## 11. Error Handling Strategy

### 11.1 Error Classification

```
┌─────────────────────────────────────────────────────────────────────┐
│                      ERROR CLASSIFICATION                           │
│                                                                     │
│  CATEGORY         │ EXAMPLES                    │ RECOVERY ACTION   │
│ ─────────────────────────────────────────────────────────────────── │
│  Input Error      │ File corrupted               │ Return error to  │
│                   │ Unsupported format           │ user with clear  │
│                   │ Empty document               │ message          │
│                   │ Password-protected file      │                  │
│ ─────────────────────────────────────────────────────────────────── │
│  Parse Error      │ Malformed XML (DOCX)         │ Graceful         │
│                   │ Corrupted PDF stream         │ degradation:     │
│                   │ Missing table structure      │ skip damaged     │
│                   │                               │ objects, log     │
│                   │                               │ WARNING, continue│
│ ─────────────────────────────────────────────────────────────────── │
│  Analysis Error   │ LLM timeout (analysis)       │ Fall back to     │
│                   │ Semantic classifier fails     │ heuristic        │
│                   │ Role confidence < 0.5        │ defaults, log     │
│                   │                               │ WARNING          │
│ ─────────────────────────────────────────────────────────────────── │
│  Translation      │ Provider unavailable          │ Retry x3 with    │
│  Error            │ LLM returns empty             │ exponential      │
│                   │ LLM returns invalid format    │ backoff          │
│                   │ Context Engine unavailable    │ Fail single      │
│                   │                               │ object, continue │
│                   │                               │ with ERROR log   │
│ ─────────────────────────────────────────────────────────────────── │
│  Reconstruction   │ Text overflow (unresolvable)  │ Log WARNING,     │
│  Error            │ File write permission         │ return document  │
│                   │ Image missing from output     │ with issues      │
│                   │                               │ flagged          │
│ ─────────────────────────────────────────────────────────────────── │
│  Validation       │ CRITICAL check failed         │ Halt pipeline,   │
│  Error            │ Answer key corrupted          │ return error     │
│                   │ Images lost                   │ report to user   │
│ ─────────────────────────────────────────────────────────────────── │
│  System Error     │ Out of memory                 │ Checkpoint and   │
│                   │ Disk full                     │ fail gracefully  │
│                   │ Database connection lost       │                  │
│ ─────────────────────────────────────────────────────────────────── │
```

### 11.2 Error Handling by Pipeline Stage

```python
# exceptions/base.py

class TrilinguaException(Exception):
    """Base exception for all Trilingua errors."""
    def __init__(self, message: str, *,
                 category: str = "system",
                 severity: str = "ERROR",
                can_retry: bool = False,
                retry_count: int = 0,
                context: dict = None):
        self.message = message
        self.category = category
        self.severity = severity
        self.can_retry = can_retry
        self.retry_count = retry_count
        self.context = context or {}
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {
            "error": self.message,
            "category": self.category,
            "severity": self.severity,
            "can_retry": self.can_retry,
            "context": self.context,
        }


class InputError(TrilinguaException):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category="input", severity="ERROR", **kwargs)


class ParseError(TrilinguaException):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category="parse", severity="WARNING", **kwargs)


class TranslationError(TrilinguaException):
    def __init__(self, message: str, can_retry: bool = True, **kwargs):
        super().__init__(message, category="translation",
                         severity="ERROR", can_retry=can_retry, **kwargs)


class ValidationError(TrilinguaException):
    def __init__(self, message: str, severity: str = "CRITICAL", **kwargs):
        super().__init__(message, category="validation",
                         severity=severity, can_retry=False, **kwargs)
```

```python
# Pipeline error handling pseudocode

def translate_document(request):
    try:
        # Stage 1: Parse
        try:
            graph = adapter.parse(request.file_path)
        except ParseError as e:
            logging.warning(f"Parse issue: {e}")
            graph = partial_graph  # Continue with what we have

        # Stage 2: Semantic Analysis
        try:
            annotate_roles(graph)
        except AnalysisError as e:
            logging.warning(f"Analysis failed, using heuristic roles: {e}")
            apply_heuristic_roles(graph)

        # Stage 3: Context Engine
        try:
            context = ContextEngine(graph)
            context.initialize()
        except Exception as e:
            logging.warning(f"Context Engine failed: {e}")
            context = FallbackContext()  # Reduced context but pipeline continues

        # Stage 4: Translation
        for page in graph.pages:
            for obj in page.get_reading_order():
                for attempt in range(3):  # Max 3 retries
                    try:
                        translated = translate_object(obj, context)
                        obj.translated_text = translated
                        break
                    except TranslationError as e:
                        if attempt < 2 and e.can_retry:
                            time.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        else:
                            logging.error(f"Failed to translate {obj.id}: {e}")
                            obj.translated_text = obj.original_text  # Keep original
                            context.record_issue(obj.id, "untranslated")

        # Stage 5: Reconstruction
        try:
            output_path = reconstruct(graph, request.output_path)
        except ReconstructionError as e:
            logging.error(f"Reconstruction failed: {e}")
            raise TrilinguaException("Document reconstruction failed") from e

        # Stage 6: Validation
        report = validate(graph, output_path)
        if report.critical_count > 0:
            # CRITICAL issues detected
            raise ValidationError(
                f"{report.critical_count} critical issues found",
                severity="CRITICAL"
            )

    except TrilinguaException as e:
        # Save checkpoint for resume
        save_checkpoint(graph, request.job_id)
        return JobResult.failed(e.to_dict())

    return JobResult.success(output_path, report)
```

### 11.3 Checkpoint and Recovery

```python
# pipeline/checkpoint_manager.py

class CheckpointManager:
    """Manages save/resume for long-running translations."""

    CHECKPOINT_INTERVAL = {
        "fast": 50,       # Save every 50 pages
        "balanced": 25,   # Save every 25 pages
        "thorough": 10,   # Save every 10 pages
    }

    def __init__(self, job_id: str, mode: str):
        self.job_id = job_id
        self.interval = self.CHECKPOINT_INTERVAL.get(mode, 25)
        self.last_save_page = 0
        self.checkpoint_dir = f"/tmp/trilingua/{job_id}/checkpoints"

    def should_checkpoint(self, current_page: int) -> bool:
        """Check if we should save a checkpoint."""
        return (current_page - self.last_save_page) >= self.interval

    def save(self, graph: DocumentObjectGraph, current_page: int):
        """Save checkpoint to disk."""
        path = f"{self.checkpoint_dir}/page_{current_page}.msgpack"
        os.makedirs(self.checkpoint_dir, exist_ok=True)

        # Only save essential data (not full graph metadata)
        checkpoint_data = {
            "graph": graph.to_serializable(),
            "translated_pages": self._get_translated_pages(graph),
            "context_engine": self._serialize_context(),
            "timestamp": time.time(),
        }

        with open(path, "wb") as f:
            msgpack.dump(checkpoint_data, f)

        self.last_save_page = current_page
        logging.info(f"Checkpoint saved: page {current_page} → {path}")

    def restore(self, graph: DocumentObjectGraph) -> int:
        """Restore from latest checkpoint. Returns last translated page."""
        if not os.path.exists(self.checkpoint_dir):
            return 0

        # Find latest checkpoint
        checkpoints = sorted(
            [f for f in os.listdir(self.checkpoint_dir) if f.endswith(".msgpack")]
        )
        if not checkpoints:
            return 0

        latest = checkpoints[-1]
        path = os.path.join(self.checkpoint_dir, latest)

        with open(path, "rb") as f:
            data = msgpack.load(f)

        # Restore graph state
        restored_graph = DocumentObjectGraph.from_serializable(data["graph"])
        # ... merge restored data into current graph

        # Extract page number from filename
        page_num = int(latest.split("_")[1].split(".")[0])
        logging.info(f"Restored from checkpoint: page {page_num}")
        return page_num
```

### 11.4 Provider Fallback Strategy

```
Primary Provider (GPT-OSS)
    │
    ├── Available? → Use GPT-OSS
    │
    └── Failed? (timeout/error/empty response)
        │
        ├── Retry 1: +2s delay
        ├── Retry 2: +4s delay
        └── Retry 3: +8s delay
            │
            └── All 3 retries failed?
                │
                ├── Fallback to Mistral?
                │   ├── Mistral available? → Use Mistral
                │   └── Mistral failed? → Return error
                │
                └── No fallback configured?
                    └── Return error: "All providers unavailable"
```

---

## 12. Performance Optimization Strategy

### 12.1 Current Performance Baseline

| Operation | Current Time (est.) | Target |
|---|---|---|
| DOCX parse (50 pages) | 200ms | 200ms (no change needed) |
| PDF parse (50 pages) | 800ms | 500ms |
| Semantic analysis (50 pages) | N/A (new) | 5s (target) |
| Translation per object | 500ms-2s (LLM-dependent) | 300ms-1.5s |
| DOCX reconstruct (50 pages) | 300ms | 300ms (no change needed) |
| PDF reconstruct (50 pages) | 3s | 1s |
| Quality validation | N/A (new) | 2s |
| **Total (50-page document, thorough)** | **~5-10 min** | **~2-5 min** |

### 12.2 Optimization Techniques

#### 12.2.1 Parallel Translation (Page-Level)

```python
# translation/engine.py
from concurrent.futures import ThreadPoolExecutor, as_completed

class SmartTranslationEngine:
    def translate_graph(self, graph: DocumentObjectGraph,
                        context: ContextEngine) -> DocumentObjectGraph:
        """Translate all objects using a thread pool.

        Strategy:
        - Group objects by page (pages are independent)
        - Translate multiple pages concurrently
        - Within a page, translate objects sequentially (context-dependent)
        """
        pages = list(graph.pages.values())
        translated_pages = set()

        with ThreadPoolExecutor(max_workers=3) as executor:
            # Submit page translation tasks
            # But maintain sequential order within each page
            future_to_page = {}
            for page in pages:
                future = executor.submit(
                    self._translate_page, page, graph, context
                )
                future_to_page[future] = page.number

            # Collect results as they complete
            for future in as_completed(future_to_page):
                page_num = future_to_page[future]
                translated_pages.add(page_num)
                context.mark_page_complete(page_num)

        return graph
```

#### 12.2.2 Batched LLM Calls

```python
# Instead of 1 LLM call per object, batch similar objects
def batch_similar_objects(objects: list[DocumentObject], batch_size: int = 5):
    """Group objects by role + page for batched LLM translation."""
    batches = []
    current_batch = []

    for obj in objects:
        if not current_batch:
            current_batch.append(obj)
        elif (obj.semantic_role == current_batch[0].semantic_role
              and obj.page_number == current_batch[0].page_number
              and len(current_batch) < batch_size):
            current_batch.append(obj)
        else:
            batches.append(current_batch)
            current_batch = [obj]

    if current_batch:
        batches.append(current_batch)

    return batches
```

#### 12.2.3 Caching Strategy

```
CACHE LAYER      │ CONTENTS           │ TTL      │ SIZE LIMIT   │ EVICTION
─────────────────┼────────────────────┼──────────┼──────────────┼─────────
Layer 1: In-Mem  │ per-job TM         │ Job life │ 10,000       │ LRU
Layer 2: Redis   │ cross-job TM       │ 7 days   │ 100,000      │ LRU
Layer 3: SQL DB  │ persistent TM      │ Forever  │ Unlimited    │ None
                 │                    │          │              │
Cache 1: parsed  │ parsed file content│ 1 hour   │ 50 files     │ LRU
Cache 2: analysis│ semantic analysis  │ 1 hour   │ 50 files     │ LRU
Cache 3: layout  │ layout plans       │ 30 min   │ 20 files     │ LRU
```

#### 12.2.4 Token Optimization

```python
# Optimize prompts to reduce token usage
def build_translation_prompt(obj: DocumentObject, context: ContextEngine) -> str:
    """Build minimal prompt with essential context only.

    Rules:
    1. Include neighbor context only if semantically relevant
    2. Include glossary only for matching terms
    3. Include TM results only for fuzzy matches
    4. Use role-specific template (shorter than generic)
    """
    prompt_parts = []

    # Template prefix (role-specific, typically 50-100 tokens)
    prompt_parts.append(get_role_template(obj.semantic_role))

    # Context (ONLY if actually useful)
    neighbors = context.get_neighbors(obj.id, distance=1)
    if neighbors and _neighbors_are_relevant(obj, neighbors):
        prompt_parts.append(_format_neighbor_context(neighbors))

    glossary_terms = context.get_glossary_terms(obj.original_text)
    if glossary_terms:
        prompt_parts.append(_format_glossary_context(glossary_terms))

    # The text itself
    prompt_parts.append(f"Text: {obj.original_text}")

    return "\n".join(prompt_parts)
```

#### 12.2.5 Memory Management

```python
def translate_document_streaming(graph: DocumentObjectGraph, context: ContextEngine):
    """Stream translation page-by-page to bound memory usage.

    Memory profile:
    - 3 pages in memory (current + previous + next for context)
    - Old pages serialized to disk and freed
    """
    # Phase 1: Global analysis (document-wide, ~10% of memory)
    semantic_analysis(graph)

    # Phase 2: Page-window translation
    for page_window in sliding_window(graph.pages, window_size=3):
        # page_window = [page_{n-1}, page_n, page_{n+1}]
        current_page = page_window[1]

        # Translate objects in current page
        for obj in current_page.get_reading_order():
            translated = translate_object(obj, context)
            obj.translated_text = translated

        # Free page_n-2 if it exists
        if page_window[0] and page_window[0].number < (current_page.number - 1):
            _serialize_and_free(graph.pages[page_window[0].number - 1])

        yield current_page  # Emit for reconstruction
```

#### 12.2.6 Estimated Performance (Thorough Mode, 50-page DepEd Module)

| Stage | Without Optimization | With Optimization | Improvement |
|---|---|---|---|
| Parse | 800ms | 500ms | 37% |
| Semantic Analysis | 10s | 5s | 50% |
| Translation (600 obj) | 600s (10min) | 240s (4min) | 60% |
| Reconstruction | 3s | 2s | 33% |
| Validation | 5s | 2s | 60% |
| **Total** | **~10.5 min** | **~4 min** | **62%** |

*Note: LLM latency is the dominant factor. Optimizations reduce overhead around the LLM call (batching, caching, prompt efficiency) but cannot eliminate the LLM response time itself.*

---

## 13. Future Scalability Recommendations

### 13.1 Near-Term (0-6 Months)

| Improvement | Effort | Impact | Notes |
|---|---|---|---|
| **Persistent TM** | 2 weeks | High | Biggest quality ROI. Repeated phrases translated consistently. |
| **Role-specific answer blank pipeline** | 1 week | High | Eliminates blank-filling bug entirely. |
| **Checkpoint/recovery** | 1 week | Medium | Enables safe translation of 200+ page documents. |
| **Horizon queue integration** | 2 weeks | Medium | Async processing, no more HTTP timeouts. |
| **Quality validation (basic)** | 2 weeks | High | Catches untranslated text, image loss, page count discrepancies. |
| **Progress streaming** | 1 week | Medium | User can see translation progress in real-time. |

### 13.2 Medium-Term (6-12 Months)

| Improvement | Effort | Impact | Notes |
|---|---|---|---|
| **Semantic Analysis Engine** | 4 weeks | Very High | Educational role classification transforms quality. |
| **Context Engine** | 3 weeks | High | Single source of truth for all contextual data. |
| **Page-window streaming** | 2 weeks | Medium | Enables 500+ page documents. |
| **Full QA with severity** | 3 weeks | High | Automated quality gates. |
| **Role-specific translation pipelines** | 4 weeks | Very High | Answer keys, MC options, blanks handled perfectly. |
| **PDF layout reconstruction** | 6 weeks | High | Currently the weakest format. |
| **Batch translation** | 2 weeks | Medium | Translate multiple documents at once. |

### 13.3 Long-Term (12+ Months)

| Improvement | Effort | Impact | Notes |
|---|---|---|---|
| **Unified Document Intelligence Layer** | 8 weeks | Critical | Foundation for all future format support. |
| **HTML/EPUB adapters** | 4 weeks each | Medium | New document types. |
| **OCR integration (Tesseract/Azure)** | 4 weeks | High | Scanned PDF support. |
| **Fuzzy TM matching** | 2 weeks | Medium | Catches case/typo variations. |
| **Auto-scaling Python workers** | 2 weeks | Medium | Handle peak loads automatically. |
| **Distributed checkpoint storage** | 2 weeks | Low | S3-based resume for any worker. |
| **Active learning** | 8 weeks | Very High | TM entries learn from user corrections. |
| **Custom user models** | 4 weeks | High | Fine-tune on user's document domain. |
| **Real-time collaborative translation** | 12 weeks | Medium | Multiple translators on same document. |
| **AI-powered quality improvement** | 8 weeks | Very High | Auto-fix common issues based on patterns. |

### 13.4 Scalability Limits and Mitigations

| Resource | Current Limit | Mitigation |
|---|---|---|
| **LLM Token Limit** | 8K-32K tokens per call | Object-level translation (not document-level). Each object < 500 tokens typically. |
| **Python Worker RAM** | ~2GB per worker for 100-page doc | Page-window streaming reduces to ~200MB. |
| **Redis Memory** | 1GB typical | LRU eviction on TM cache. Configurable max memory. |
| **Database Writes** | 1000 TM writes/sec | Batch queue (100 entries or 30s). |
| **Concurrent Jobs** | Depends on LLM rate limits | Queue-based throttling. Configurable max workers. |
| **File Upload Size** | 50MB (Laravel default) | Chunked uploads for larger files. |

### 13.5 Architectural Roadmap

```
Phase 1 (Now)
  ┌─────────────────────────────────────────────┐
  │ Fast wins: TM, checkpoints, queue,          │
  │ answer blank fix, basic validation          │
  └─────────────────────────────────────────────┘
                       │
Phase 2 (3 months)
  ┌─────────────────────────────────────────────┐
  │ Semantic Analysis Engine                    │
  │ Context Engine                              │
  │ Page-window streaming                       │
  │ Full Quality Validation with severity       │
  └─────────────────────────────────────────────┘
                       │
Phase 3 (6 months)
  ┌─────────────────────────────────────────────┐
  │ Role-specific translation pipelines         │
  │ PDF layout reconstruction                   │
  │ Batch translation                           │
  └─────────────────────────────────────────────┘
                       │
Phase 4 (12 months)
  ┌─────────────────────────────────────────────┐
  │ Unified Document Intelligence Layer         │
  │ HTML/EPUB adapters                          │
  │ OCR integration                             │
  │ Fuzzy TM matching                           │
  │ Auto-scaling workers                        │
  └─────────────────────────────────────────────┘
                       │
Phase 5 (18+ months)
  ┌─────────────────────────────────────────────┐
  │ Active learning (TM from corrections)       │
  │ Custom user models                          │
  │ Real-time collaborative translation         │
  │ AI-powered quality improvement              │
  └─────────────────────────────────────────────┘
```

---

## Appendix A: Comparison: Current vs. Proposed Architecture

| Dimension | Current | Proposed | Improvement |
|---|---|---|---|
| **Document Model** | Flat dict list | Structured object graph | ✅ Complete |
| **Format Handling** | Direct library calls | Pluggable adapters → canonical graph | ✅ Extensible |
| **Object Detection** | Heuristic (gap analysis) | Hybrid (heuristic + LLM) | ✅ Accurate |
| **Role Awareness** | None (block_type only) | 20+ semantic roles | ✅ Transformational |
| **Translation** | One prompt template | 15+ role-specific pipelines | ✅ Precise |
| **Context** | Buffer (5 items) + weak memory | Dedicated Context Engine | ✅ Comprehensive |
| **Layout** | Reconstruct from scratch (PDF) | Adaptive reuse of original | ✅ Faithful |
| **Quality** | Optional BLEU score | Severity-based QA report | ✅ Rigorous |
| **TM** | Per-document, hash-only | Persistent, fuzzy-matched | ✅ Persistent |
| **Queue** | None (sync) | Horizon + Celery + Redis | ✅ Async |
| **Progress** | None | Real-time WebSocket streaming | ✅ Transparent |
| **Recovery** | None | Checkpoint/resume | ✅ Reliable |
| **Memory** | Full document in RAM | Page-window streaming | ✅ Efficient |
| **Laravel/Python Split** | Fluid boundaries | Clear API contract | ✅ Maintainable |

---

## Appendix B: Glossary

| Term | Definition |
|---|---|
| **Document Object Graph** | Canonical, structured representation of a document with typed objects, positions, styles, and relations. |
| **Semantic Role** | The purpose/function of a text object in its document context (e.g., "Learning Objective", "MC Option"). |
| **Context Engine** | Central service managing all contextual information during translation: TM, glossary, neighbors, cross-references. |
| **Translation Memory** | Persistent store of source→translation pairs enabling reuse across documents. |
| **Fuzzy Matching** | Finding near-exact matches using string similarity (Levenshtein distance). |
| **Page-Window Processing** | Processing 3 pages at a time (previous, current, next) for memory efficiency while preserving context. |
| **Role-Specific Pipeline** | A complete processing chain (preprocess → prompt → LLM → postprocess → validate) specialized for one semantic role. |
| **Format Adapter** | Pluggable component that reads a specific file format and produces a canonical Document Object Graph. |
| **Severity-Based Validation** | Quality checks classified as INFO/WARNING/ERROR/CRITICAL with defined pipeline responses per level. |
| **BK-Tree** | A tree data structure optimized for fuzzy string matching queries. |
| **Canonical Representation** | The application-owned, format-agnostic document model that all components use instead of library-specific types. |

---

*End of Architectural Design Document v2.0*