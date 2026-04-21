# DB module rules

## Connection
postgresql://epoch_user:devpassword@localhost:5432/complianceos_db

## Two tables only

### transactions (audit log)
- id: UUID primary key
- transaction_id: String
- request_payload: JSONB
- claude_raw_output: Text
- decision: String
- score: Integer
- confidence: String
- reason: Text
- rule_references: ARRAY(String)
- recommended_action: String
- processing_ms: Integer
- created_at: DateTime

### regulatory_chunks (vector store)
- id: UUID primary key
- source_document: String
- chunk_index: Integer
- content: Text
- embedding: Vector(384)
- jurisdiction: String (FATF/MiCA/MAS/FCA)
- created_at: DateTime

## Rules
- SQLAlchemy 2.0 async only
- asyncpg driver
- UUID default for all primary keys
- All queries parameterized
