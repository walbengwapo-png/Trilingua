# Bugfix Requirements Document

## Introduction

Translation history records and translated documents are tied to a session ID rather than the authenticated user's ID. Because a new session is created on every login, users lose access to all their previous translations and documents after logging out and back in. The fix replaces `session_id` with `user_id` (a foreign key to the `users` table) as the ownership identifier throughout the `translation_history` table, `HistoryService`, `TranslationController`, `HistoryController`, and `DocumentsController`.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN an authenticated user logs out and logs back in THEN the system assigns a new session ID, causing all previously saved translation history records to become invisible to that user.

1.2 WHEN an authenticated user logs out and logs back in THEN the system assigns a new session ID, causing all previously saved document records to become invisible to that user on the My Documents page.

1.3 WHEN a translation (text or document) is saved to `translation_history` THEN the system stores `session_id` as the ownership identifier instead of the authenticated user's `user_id`.

1.4 WHEN `HistoryController::redownload` validates ownership of a record THEN the system compares `record['session_id']` against the current session ID, which fails for any session other than the one that created the record.

1.5 WHEN `HistoryService::getHistory` queries `translation_history` THEN the system filters by `session_id`, returning an empty result set for any new session belonging to the same user.

### Expected Behavior (Correct)

2.1 WHEN an authenticated user logs out and logs back in THEN the system SHALL display all translation history records previously created by that user, regardless of session changes.

2.2 WHEN an authenticated user logs out and logs back in THEN the system SHALL display all document records previously created by that user on the My Documents page, regardless of session changes.

2.3 WHEN a translation (text or document) is saved to `translation_history` THEN the system SHALL store the authenticated user's `user_id` as the ownership identifier.

2.4 WHEN `HistoryController::redownload` validates ownership of a record THEN the system SHALL compare `record['user_id']` against the authenticated user's ID (`Auth::id()`), granting access when they match.

2.5 WHEN `HistoryService::getHistory` queries `translation_history` THEN the system SHALL filter by `user_id`, returning all records belonging to that user across all sessions.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a user requests a redownload of a document that belongs to a different user THEN the system SHALL CONTINUE TO return a 403 Forbidden response.

3.2 WHEN a user requests a redownload of a record that does not exist THEN the system SHALL CONTINUE TO return a 404 Not Found response.

3.3 WHEN a translation is saved and the database insert fails THEN the system SHALL CONTINUE TO log the error without blocking the translation response returned to the user.

3.4 WHEN `HistoryService::getHistory` is called THEN the system SHALL CONTINUE TO return records ordered by `created_at` descending, capped at 200 results.

3.5 WHEN `HistoryService::updateExpiry` is called THEN the system SHALL CONTINUE TO update the `signed_url_expires_at` column for the specified record ID.

3.6 WHEN a document translation is performed THEN the system SHALL CONTINUE TO upload the translated file to Supabase Storage and return a signed download URL to the user.

3.7 WHEN a text translation is performed THEN the system SHALL CONTINUE TO return the translated text to the user.
