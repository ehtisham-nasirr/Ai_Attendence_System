# Git Standards

## Commit Messages

Use conventional commits with a scope and, where applicable, the requirement ID:

```
feat(backend): add shift CRUD (FR-21)
feat(engine): keyframe-only decoding in IDLE mode (NFR-4, NFR-15)
fix(backend): night shift day close uses shift start date (FR-21)
refactor(frontend): extract shared DataTable
docs: update runbook for adding an engine node
test(engine): add degradation ladder tests
```

Scopes: `common`, `engine`, `backend`, `frontend`, `infra`, `docs`.

Avoid vague/non-descriptive messages:

```
update
changes
final
final2
new
stuff
```

## Never Commit

```
.env
.venv/ venv/
node_modules/
__pycache__/
*.pyc
dist/
build/
# FaceTrack-specific
models/            *.onnx  *.xml  *.bin   ← model files are downloaded by scripts/download_models.py
recordings/        *.mp4  *.mkv  *.ts     ← test video stays on the shared test store
snapshots/         enroll/                 ← face images of real people
*.npy *.faiss                              ← embeddings / indexes
```

Face images, recordings and embeddings of real employees are biometric data — they must **never** be committed, including in tests. Test fixtures use synthetic or explicitly consented sample faces stored outside Git.

...unless the project explicitly requires one of these to be tracked (rare — confirm before doing so).
