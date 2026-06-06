# Template: Data Pipelines

## Reliability

- Idempotent operations (safe to retry)
- Checkpointing for resumability
- Dead letter queues for failures
- Schema validation at boundaries

## Data Integrity

- Validate early, fail fast
- Immutable transformations
- Version your schemas
- Preserve lineage/provenance

## Performance

- Batch where possible
- Parallelize independent steps
- Backpressure for rate limiting

## Checklist

- [ ] Safe to re-run (idempotent)
- [ ] Handles partial failures
- [ ] Schema changes backwards compatible
- [ ] Metrics for throughput and lag
