# Post-audit Package F — targeted performance and UI inspection

The previously identified admin review double-load is already removed by
Package B: `ReviewController` paginates blocks (25 per page) and does not load
the unused full `$documentBlocks` collection. No additional query abstraction
or speculative caching was added.

The isolated browser run reached member login, dashboard, and translation
views with built assets. A 390px viewport had no document-width overflow;
the input and Translate action remained within the page width. This is a
limited smoke check, not a keyboard/screen-reader or full mobile matrix.

`npm run build` reports large preview dependencies: Mammoth ~499 kB, XLSX
~500 kB, PPTX preview ~1.35 MB before gzip. This is a build warning, not a
measured page-time bottleneck; changing bundles without a user-path profile
would be speculative. There was no deployment-shaped runtime or representative
large document available to measure HTML size, PHP/worker memory, queue wait,
download memory, or concurrent-upload behavior. Package F's performance gate
is therefore **open**, with those measurements required before claiming the
intended size/concurrency limits. No migration, data repair, or rollback step.

