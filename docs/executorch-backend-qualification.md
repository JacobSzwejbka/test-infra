# ExecuTorch publication qualification

Only ExecuTorch publication changes. Other packages and dry-run promotion keep
their existing behavior. No viable/strict rules are changed.

The ExecuTorch `Backend Qualification` workflow always runs the full QNN, Arm
(including VGF), XNNPACK and Vulkan matrices on its workflow commit. The binary
upload step waits for a successful qualification on that exact SHA before any
S3, R2 or PyPI publication. A newer failed or pending qualification cannot be
replaced by an older successful run.

Uploaded S3 wheels carry `source-sha` metadata. Promotion checks the actual
selected wheels' metadata and their qualification, and rejects missing
provenance or a mixture of source commits. PyPI staging preserves the metadata
after wheel repackaging; final PyPI publication checks the staged objects too.

## Rollout

Merge and deploy the ExecuTorch workflow changes on the source branches first,
then merge the shared publication guard. Release branches need the qualification
workflow before their artifacts can be published. Existing candidates and
staged wheels without source metadata need to be rebuilt and restaged; this
guard intentionally refuses to certify legacy artifacts from another commit.

The qualification action can resolve a ref once and return its immutable SHA
for an AAR build. Binary uploads require a full source SHA because resolving a
mutable branch after the build could certify a different commit.

Qualification failure, missing runs, API errors and timeouts fail publication.
Retry the qualification or restore service availability, then retry publication.
