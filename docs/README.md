# Documentation map

Start with the maintained summaries. Follow task contracts for implementation;
use dated release/qualification records as evidence for their exact revision.

| Need | Entry point |
| --- | --- |
| Product and source setup | [Repository README](../README.md) |
| What is delivered, enabled or still unaccepted | [Current project status](PROJECT_STATUS.md) |
| Components, trust/data boundaries and stores | [Architecture](ARCHITECTURE.md) |
| Capabilities and acceptance | [Features](FEATURES.md) |
| Active priorities and exit criteria | [Roadmap](ROADMAP.md) |
| Architecture findings and maintenance decisions | [October 14 review](ARCHITECTURE_REVIEW_2026-10-14.md) |
| Local development commands | [Development](DEVELOPMENT.md#cpu-quick-start), [environment doctor](DEVELOPMENT_ENVIRONMENT.md) |
| Backend/Web entry | [Server README](../server/README.md), [Web development](WEB_DEVELOPMENT.md) |
| Phone/TV entry | [Android README](../clients/android/README.md) |
| Family trial | [v58 Chinese test guide](../clients/android/docs/PHONE_V58_TEST_GUIDE_ZH.md) |
| Deployment/recovery workflow | [Operations](OPERATIONS.md), [source packaging](SOURCE_PACKAGING.md) |
| Replaceable models and infrastructure | [Provider architecture](MODEL_PROVIDER_ARCHITECTURE.md), [model directory](../models/README.md) |
| Private manifest and model quality gates | [Deployment manifest](MODEL_DEPLOYMENT_MANIFEST.md), [qualification](MODEL_QUALIFICATION.md) |
| Monorepo transition and old repository disposition | [Repository transition](REPOSITORY_TRANSITION.md) |
| Source ownership/import provenance | [Source ledger](feature-source-changes.json), [contributing](../CONTRIBUTING.md) |
| Reader progress and source status | [Reader UX](READER_PROGRESS_AND_SOURCES.md) |
| Long recording retention and withdrawal | [Intake foundation](ORAL_HISTORY_INTAKE_FOUNDATION.md), [withdrawal prototype](ORAL_HISTORY_WITHDRAWAL.md) |

## Document roles

**Maintained summaries** describe current source contracts and link to a dated
runtime snapshot. Public default-off configuration is distinct from an explicitly
enabled installation. **Task contracts** define request shapes, revision, privacy
and lifecycle behavior. **Dated evidence** records a particular source, test,
package or operation; a later release does not retroactively change it.

Features and Roadmap retain their earlier notes in collapsed historical sections.
Development is a chronological qualification log with stable command sections.
The architecture index labels older snapshots explicitly. Historical “pending”
statements are not the active backlog; start with Project Status and Roadmap.

## Update rule for future work

1. Update the affected task contract and its implementation evidence.
2. Update Features/Roadmap and Project Status only for the acceptance level proved.
3. Record source/CI, package, live runtime and physical/family results separately.
4. Append changed source-document hashes to the provenance ledger and check links.
5. Keep private endpoints, accounts, database/media paths, model weights, credentials,
   signing keys and full operator receipts outside Git.

No deployment, activation, deletion or remote publication is authorized by reading
these documents. Use the exact current operation scope and preserved rollback plan.

## Product introduction and family memory direction

- [Introduction website source](../website/README.md): Chinese-first project
  purpose/features, fictional family examples and cartoon illustrations.
- [Family memory hub](FAMILY_MEMORY_HUB.md): proposed long oral histories,
  relative/event organization, attributed contributions and reviewed chapters.

- [Oral-history intake foundation](ORAL_HISTORY_INTAKE_FOUNDATION.md): internal
  bounded section/receipt contract and remaining withdrawal/transport gates.
