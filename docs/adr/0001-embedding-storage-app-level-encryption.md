# ADR-0001: Embeddings encrypted at application level, no HNSW index

**Status:** Accepted (owner decision, 2026-10-03)
**Requirements:** NFR-8, FR-10, FR-13, §11, §15 · **Standards:** 05, 18

## Context
Requirements §11 defines `face_enrollments.embedding` as `vector(512)` with an HNSW index, and also says embeddings are encrypted at rest (NFR-8, AES-256). standards/05 and standards/18 require that encryption to use the project's encryption helper, i.e. application-level AES-256. An HNSW index cannot be built over ciphertext. `vector(512)` also cannot hold 128-d SFace embeddings, the permissive fallback model.

## Decision
- `face_enrollments.embedding_encrypted` and `unknown_faces.embedding_encrypted` are `bytea` holding AES-256-GCM ciphertext produced by `facetrack_common.crypto`. The key comes from `ENCRYPTION_KEY` in the environment, never from code or Git.
- Each row stores `model_name` and `embedding_dim`. Embeddings from different models are never compared.
- There is no HNSW index. Back-office similarity search (FR-10 duplicate warning, unknown-face grouping) decrypts the relevant vectors in memory (at most ~50,000 × 512 floats).
- Live matching uses the engine's in-memory FAISS index, as before.
- The pgvector extension stays enabled so the option remains open.

## Consequences
Biometric data stays unreadable in database dumps and backups without the key. Similarity search costs a decrypt pass, which is acceptable at the specified gallery size (NFR-5: 5,000 employees).
