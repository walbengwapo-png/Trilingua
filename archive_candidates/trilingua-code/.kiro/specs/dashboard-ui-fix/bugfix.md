# Bugfix Requirements Document

## Introduction

Four pages in the TriLingua application — Dashboard, New Translation, My Documents, and Saved Translations (History) — display hardcoded/mock data instead of real user data, and their layouts do not match the intended design mockups. The dashboard shows static numbers (24 documents, 12 translations, 45,280 words) and fake recent-translation rows regardless of what the authenticated user has actually done. The New Translation page is missing the character counter limit display (0/5000), speaker icons, and the correct two-panel visual structure. The My Documents page lacks search/filter controls, tab filters with real counts, and the translation progress bar. The Saved Translations (History) page lacks grouping by language pair, match percentage badges, and per-card action icons. All pages must be updated to pull real data from the authenticated user's records and to render the correct UI layout.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN an authenticated user visits the Dashboard THEN the system displays a hardcoded "Welcome back" greeting without the user's real name in the stats area.

1.2 WHEN an authenticated user visits the Dashboard THEN the system displays hardcoded stat values (24 Total Documents, 12 Translations This Month, 45,280 Words Translated) instead of counts derived from the user's actual translation history.

1.3 WHEN an authenticated user visits the Dashboard THEN the system displays two hardcoded fake rows in the Recent Translations table ("Mother Tongue-Based" and "Comparative Study") instead of the user's real recent translations.

1.4 WHEN an authenticated user visits the Dashboard THEN the system does not show a Quick Actions panel (New Translation, Upload Document, Browse Corpus shortcuts).

1.5 WHEN an authenticated user visits the Dashboard THEN the storage indicator in the sidebar shows a hardcoded 25% fill with no real storage usage data.

1.6 WHEN an authenticated user visits the New Translation page THEN the system does not display a "0/5000" character counter matching the design (the current limit is 8000 and the counter label does not match the mockup).

1.7 WHEN an authenticated user visits the New Translation page THEN the system does not show speaker (text-to-speech) icon buttons on either the source or target panel.

1.8 WHEN an authenticated user visits the My Documents page THEN the system does not show a search bar, Language filter dropdown, Status filter dropdown, or grid/list view toggle.

1.9 WHEN an authenticated user visits the My Documents page THEN the system does not show tab filters (All, Recent, Shared, Archived) with real document counts.

1.10 WHEN an authenticated user visits the My Documents page THEN the document cards do not show a translation progress bar with a percentage.

1.11 WHEN an authenticated user visits the Saved Translations page THEN the system displays a flat table of all history records instead of grouping them by language pair.

1.12 WHEN an authenticated user visits the Saved Translations page THEN the system does not show a match percentage badge on each translation card.

1.13 WHEN an authenticated user visits the Saved Translations page THEN the system does not show per-card action icons (copy, download, share, bookmark).

1.14 WHEN an authenticated user visits the Saved Translations page THEN the system does not show a header with the total saved count badge, a search bar, a "Group by Language Pair" dropdown, or a Sort dropdown.

### Expected Behavior (Correct)

2.1 WHEN an authenticated user visits the Dashboard THEN the system SHALL display "Welcome back, [user's real name]" using the name stored in the authenticated user's record.

2.2 WHEN an authenticated user visits the Dashboard THEN the system SHALL display stat cards showing: the real count of the user's document-type translation records as "Total Documents", the real count of translation records created in the current calendar month as "Translations This Month", and the real total word count derived from the user's translation records as "Words Translated".

2.3 WHEN an authenticated user visits the Dashboard THEN the system SHALL display the user's most recent translation records (up to 5) in the Recent Translations table, showing Document name, Languages (source → target), Date, Status, and Confidence columns populated from real data.

2.4 WHEN an authenticated user visits the Dashboard THEN the system SHALL display a Quick Actions panel containing links/buttons for "New Translation", "Upload Document", and "Browse Corpus".

2.5 WHEN an authenticated user visits the Dashboard THEN the storage indicator SHALL reflect real storage usage derived from the user's uploaded document records.

2.6 WHEN an authenticated user visits the New Translation page THEN the system SHALL display a character counter showing "0/5000" (with a 5000-character limit) that updates as the user types.

2.7 WHEN an authenticated user visits the New Translation page THEN the system SHALL display speaker icon buttons on both the source panel and the target panel for text-to-speech functionality.

2.8 WHEN an authenticated user visits the My Documents page THEN the system SHALL display a search bar, a Language filter dropdown, a Status filter dropdown, and a grid/list view toggle above the document grid.

2.9 WHEN an authenticated user visits the My Documents page THEN the system SHALL display tab filters — All (with total count), Recent (with count), Shared (with count), and Archived (with count) — where all counts reflect the user's real document data.

2.10 WHEN an authenticated user visits the My Documents page THEN each document card SHALL display a translation progress bar with a percentage indicating translation completion status.

2.11 WHEN an authenticated user visits the Saved Translations page THEN the system SHALL group translation cards by language pair (e.g., "Cebuano → Tagalog 2") with a count badge per group.

2.12 WHEN an authenticated user visits the Saved Translations page THEN each translation card SHALL display a match percentage badge derived from the translation record data.

2.13 WHEN an authenticated user visits the Saved Translations page THEN each translation card SHALL display action icons for copy, download, share, and bookmark.

2.14 WHEN an authenticated user visits the Saved Translations page THEN the system SHALL display a page header with the total saved count badge, a search bar, a "Group by Language Pair" dropdown, and a Sort dropdown.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN an authenticated user submits a text translation on the New Translation page THEN the system SHALL CONTINUE TO send the request to the backend, display the translated result in the target panel, and enable the Copy and Save buttons.

3.2 WHEN an authenticated user attaches a document file on the New Translation page THEN the system SHALL CONTINUE TO validate the file type and size, submit the document for translation, and return a download link for the translated file.

3.3 WHEN an authenticated user clicks the swap button on the New Translation page THEN the system SHALL CONTINUE TO swap the source and target language selections and clear the output panel.

3.4 WHEN an authenticated user visits the My Documents page and clicks "Open" on a document card THEN the system SHALL CONTINUE TO generate a signed download URL and redirect the user to download the file.

3.5 WHEN an authenticated user visits the Saved Translations page and clicks "Re-download" on a document record THEN the system SHALL CONTINUE TO generate a new signed URL and redirect the user to download the file.

3.6 WHEN an authenticated user visits the Saved Translations page and clicks "View" on a text translation record THEN the system SHALL CONTINUE TO open the modal showing the original and translated text.

3.7 WHEN an unauthenticated user attempts to access any protected page (Dashboard, New Translation, My Documents, Saved Translations) THEN the system SHALL CONTINUE TO redirect them to the login page.

3.8 WHEN an authenticated user logs out THEN the system SHALL CONTINUE TO invalidate the session and redirect to the login page.

3.9 WHEN the Dashboard route is accessed THEN the system SHALL CONTINUE TO render within the authenticated app layout (sidebar navigation, header with user name and logout button).

3.10 WHEN the My Documents page has no documents for the user THEN the system SHALL CONTINUE TO display the empty state message and a link to translate the first document.
