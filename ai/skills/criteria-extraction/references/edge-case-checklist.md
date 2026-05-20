# Edge Case Checklist

Systematic categories to apply against EVERY requirement when extracting
acceptance criteria. For each requirement, walk through every applicable
category and generate specific edge cases.

## Input Validation
- Null / undefined / missing value
- Empty string / empty array / empty object
- Whitespace-only string
- Value at minimum boundary (0, 1, empty)
- Value at maximum boundary (max length, max count, max size)
- Value exceeding maximum (max + 1, over limit)
- Negative values where positive expected
- Wrong type (string where number expected, object where array expected)
- Malformed input (invalid email, partial URL, broken JSON)
- Unicode / special characters / emoji
- HTML/script injection strings
- Extremely long input (10x expected max)

## State & Lifecycle
- Operation on uninitialized / default state
- Operation during loading / pending state
- Operation after deletion / cleanup
- Rapid repeated operations (double-click, double-submit)
- Operation interrupted midway (tab close, navigation, disconnect)
- State after error recovery (retry after failure)
- Stale state (data changed since last fetch)
- Empty state (first use, no data yet)
- Full state (at capacity, all slots used)

## Concurrency & Timing
- Two users acting on the same resource simultaneously
- Request arrives after timeout
- Response arrives after component unmounted / page navigated
- Race between create and delete of same resource
- Optimistic update rolled back on server error
- Cache invalidation during concurrent writes

## Error & Failure
- Network timeout
- Network disconnect mid-operation
- Server returns 4xx (400, 401, 403, 404, 409, 422, 429)
- Server returns 5xx (500, 502, 503)
- Server returns unexpected shape (missing fields, extra fields)
- Partial success (batch where some items succeed, some fail)
- Cascading failure (dependency down)
- Disk full / quota exceeded
- Permission denied at OS or API level

## Authorization & Access
- Unauthenticated user attempting authenticated action
- User with insufficient permissions
- User accessing another user's resource
- Expired token / session
- Permission changed after page load but before action
- Admin vs. regular user behavior differences

## UI & Interaction (when applicable)
- Browser back/forward during operation
- Page refresh during operation
- Multiple tabs with same view
- Viewport: mobile, tablet, desktop
- Keyboard-only navigation
- Screen reader accessibility
- Slow network (3G simulation)
- Right-to-left text direction

## Data Boundary
- Exactly one item (not zero, not many)
- Maximum page size of paginated results
- Last page of paginated results (partial page)
- Filter/search with zero results
- Filter/search with one result
- Sort order with identical values (stable sort?)
- Data with all optional fields missing
- Data with all optional fields present
