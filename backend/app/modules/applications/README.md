# Applications module

Owns a user's job applications and their lifecycle: delivery details, status
changes, interview events, reviews, notes, tags, and activity logs.

## Public boundary

- HTTP handlers call `ApplicationService` for state-changing use cases.
- `ApplicationRepository` is the only place in this module that issues ORM
  queries for a migrated use case.
- Query-only endpoints may move to `queries.py` as they are migrated.

## Rules for future changes

1. Do not call `Session.commit()` from a router for an applications use case.
2. A status change and its activity log must be written in one transaction.
3. Other modules create applications through this module's service, rather
   than importing `Delivery` and writing it directly.
4. Keep existing `/api/deliveries` routes until an explicitly versioned API
   migration is planned.

## Current migration scope

Create, update, delete, bulk delivery, event, and note use cases are handled
by `ApplicationService`. Read models are handled by `ApplicationQueryService`,
and CSV import/export is handled by `ApplicationCsvService`.
