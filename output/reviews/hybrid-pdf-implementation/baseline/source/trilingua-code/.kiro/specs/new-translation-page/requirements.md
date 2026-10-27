# Requirements Document

## Introduction

The New Translation page is a core feature of the TriLingua Laravel application that allows authenticated users to translate text or documents between English, Cebuano, and Filipino (Tagalog). The page presents a two-panel layout — a source panel on the left and a translated output panel on the right — and integrates with the existing Python-based NLLB-200 translation backend (`document_translator_v3.py`). It must match the existing TriLingua UI design system (sidebar layout, CSS custom properties, card-based design).

## Glossary

- **Translation_Page**: The `/translate` route and its associated Blade view, controller, and CSS.
- **Source_Panel**: The left panel where the user enters text or uploads a document.
- **Output_Panel**: The right panel that displays the translated result.
- **Language_Selector**: A `<select>` element that lets the user choose a language (English, Cebuano, or Filipino).
- **Character_Counter**: A live display showing the current character count against the 8 000-character limit (e.g. `0/8000`).
- **Translate_Button**: The primary action button that submits the translation request.
- **Swap_Button**: The icon button between the two panels that exchanges the source and target languages.
- **Attachment_Button**: The button that opens a file-picker for document uploads.
- **Translation_Controller**: The Laravel controller (`TranslationController`) that handles HTTP requests for the Translation_Page.
- **Translation_Service**: The PHP service class (`TranslationService`) that invokes the Python translation backend via subprocess.
- **Python_Backend**: The `document_translator_v3.py` script that performs NLLB-200-based translation.
- **Supported_Formats**: `.docx`, `.pdf`, `.txt`, `.md`, `.rtf`, `.odt`, `.csv`.
- **NLLB_Language_Code**: The BCP-47-style code used by the Python_Backend — `eng_Latn` (English), `ceb_Latn` (Cebuano), `tgl_Latn` (Filipino).
- **Sidebar**: The `<aside>` element rendered by `layouts/app.blade.php` containing the application navigation links.

---

## Requirements

### Requirement 1: Page Access and Layout

**User Story:** As an authenticated user, I want to navigate to a dedicated New Translation page, so that I can access all translation features in one place.

#### Acceptance Criteria

1. THE Translation_Page SHALL be accessible at the `/translate` route for authenticated users only.
2. WHEN an unauthenticated user visits `/translate`, THE system SHALL redirect the user to the login page.
3. THE Translation_Page SHALL extend `layouts/app.blade.php` and render within the existing sidebar layout.
4. THE Translation_Page SHALL display a two-panel layout with the Source_Panel on the left and the Output_Panel on the right, each occupying 50% of the available content width with a minimum width of 280 px per panel.
5. THE Translation_Page SHALL apply a dedicated per-view CSS file (`resources/css/views/translation.css`) loaded via `@vite`.
6. THE Translation_Page SHALL use only CSS custom properties defined in `base.css` (`--bg`, `--card-bg`, `--text`, `--muted`, `--primary`, `--accent`, `--border`, `--radius`) for colors, backgrounds, and borders.
7. WHEN the viewport width is 768 px or less, THE Translation_Page SHALL stack the Source_Panel above the Output_Panel in a single column.
8. THE Translation_Page SHALL set the page title to "New Translation" so that the browser tab and the layout header both display "New Translation - TriLingua".

---

### Requirement 2: Language Selection and Swap

**User Story:** As a user, I want to choose source and target languages and swap them instantly, so that I can control the direction of translation without re-entering text.

#### Acceptance Criteria

1. THE Source_Panel SHALL contain a Language_Selector offering the options English, Cebuano, and Filipino, defaulting to English on page load.
2. THE Output_Panel SHALL contain a Language_Selector offering the options English, Cebuano, and Filipino, defaulting to Cebuano on page load.
3. THE Translation_Page SHALL display a Swap_Button positioned between the Source_Panel header and the Output_Panel header.
4. WHEN the user activates the Swap_Button, THE Translation_Page SHALL exchange the selected value of the source Language_Selector with the selected value of the target Language_Selector without a page reload, and SHALL clear the Output_Panel translated text.
5. WHEN the user activates the Swap_Button and the Source_Panel is in plain-text mode, THE Translation_Page SHALL move the current source textarea content into the source textarea (now showing the previously-target language) and clear the Output_Panel. IF the Source_Panel is in file-attachment mode, THE Swap_Button SHALL exchange only the Language_Selectors and SHALL NOT remove the attached file.
6. IF the source Language_Selector and the target Language_Selector would result in the same language after a swap, THEN THE Swap_Button SHALL NOT perform the swap and SHALL display an inline error message adjacent to the language selectors stating that source and target languages must differ.
7. IF the source Language_Selector and the target Language_Selector have the same value when the user activates the Translate_Button, THEN THE Translation_Controller SHALL return a validation error message displayed inline within the Source_Panel adjacent to the language selectors, stating that source and target languages must differ.

---

### Requirement 3: Plain Text Input and Character Counter

**User Story:** As a user, I want to type or paste text directly into the source panel and see a live character count, so that I know when I am approaching the input limit.

#### Acceptance Criteria

1. THE Source_Panel SHALL contain a `<textarea>` that accepts plain text input up to 8 000 characters.
2. THE Source_Panel SHALL display a Character_Counter below the textarea showing the format `{current}/8000` (e.g. `0/8000`).
3. WHEN the user types or pastes text into the textarea, THE Character_Counter SHALL update within 100 ms without a page reload.
4. IF the user pastes text that would cause the character count to exceed 8 000, THEN THE Translation_Page SHALL truncate the pasted content so that the total character count equals exactly 8 000 and SHALL NOT exceed the limit.
5. IF the character count reaches 8 000, THEN THE Translation_Page SHALL prevent additional characters from being entered into the textarea via keyboard input.
6. WHEN the character count exceeds 7 500, THE Character_Counter SHALL add the CSS class `counter-warning` to its element, visually changing its color to indicate the user is near the limit.
7. WHEN the character count drops to 7 500 or below, THE Character_Counter SHALL remove the CSS class `counter-warning` from its element, reverting to its default appearance.

---

### Requirement 4: Document File Upload

**User Story:** As a user, I want to upload a document file for translation, so that I can translate entire documents without copying and pasting their content.

#### Acceptance Criteria

1. THE Source_Panel SHALL display an Attachment_Button that opens a native file-picker dialog when activated.
2. THE Attachment_Button SHALL restrict the file-picker to files with extensions `.docx`, `.pdf`, `.txt`, `.md`, `.rtf`, `.odt`, and `.csv` via the `accept` attribute.
3. WHEN the user selects a valid file, THE Source_Panel SHALL display the selected filename in a file-info area and SHALL hide the plain-text textarea.
4. WHEN the user selects a valid file, THE Translation_Page SHALL hide the Character_Counter display.
5. IF the user selects a file whose extension is not one of the Supported_Formats, THEN THE Translation_Page SHALL display an inline error message listing the Supported_Formats and SHALL NOT store or submit the file.
6. IF the user selects a file whose size exceeds 10 MB (10 485 760 bytes), THEN THE Translation_Page SHALL display an inline error message stating the 10 MB limit and SHALL NOT store or submit the file.
7. THE Source_Panel SHALL display a remove button adjacent to the filename that, when activated, clears the selected file, hides the file-info area, shows the plain-text textarea, and shows the Character_Counter.
8. WHEN the user removes the selected file, THE Translation_Page SHALL reset the file input element so that the same file can be re-selected if needed.

---

### Requirement 5: Translation Submission

**User Story:** As a user, I want to click a Translate button to submit my text or document, so that I can receive the translated output.

#### Acceptance Criteria

1. THE Translation_Page SHALL display a Translate_Button that submits the translation request.
2. WHEN the user activates the Translate_Button with plain text in the textarea, THE Translation_Controller SHALL send the text and language pair to the Translation_Service for processing.
3. WHEN the user activates the Translate_Button with a document file selected, THE Translation_Controller SHALL upload the file and send the file path and language pair to the Translation_Service for processing.
4. WHILE a translation is in progress, THE Translation_Page SHALL display a loading indicator within or adjacent to the Translate_Button and SHALL set the Translate_Button to a disabled state to prevent duplicate submissions. WHEN the Translation_Service returns a result or error, THE Translation_Page SHALL remove the loading indicator and re-enable the Translate_Button.
5. IF the textarea is empty and no file is selected when the user activates the Translate_Button, THEN THE Translation_Controller SHALL return a validation error message prompting the user to enter text or upload a file, without invoking the Translation_Service.
6. WHEN the Translation_Service returns a successful result for plain text input, THE Output_Panel SHALL display the translated text.
7. WHEN the Translation_Service returns a successful result for a document file, THE Output_Panel SHALL display a Download button that, when activated, initiates a browser download of the translated document file.
8. IF the Translation_Service returns an error, THEN THE Translation_Page SHALL display an error message in the Output_Panel area that indicates translation failed and includes the reason reported by the service, without clearing the source input.
9. IF the Translation_Service does not return a response within 60 seconds, THEN THE Translation_Controller SHALL treat the request as failed and return a timeout error message to the Translation_Page.

---

### Requirement 6: Output Panel Actions

**User Story:** As a user, I want to copy or save the translated output, so that I can use the result in other applications or keep a record of it.

#### Acceptance Criteria

1. WHEN the Output_Panel contains translated text, THE Output_Panel SHALL display a Copy button that copies the translated text to the user's clipboard when activated.
2. WHEN the user activates the Copy button and the Clipboard API succeeds, THE Translation_Page SHALL change the Copy button label to "Copied!" for a duration between 1 500 ms and 3 000 ms before reverting to the default "Copy" label.
3. IF the Clipboard API fails when the user activates the Copy button, THEN THE Translation_Page SHALL display an inline error message stating that copying failed, without clearing the translated text.
4. WHEN the Output_Panel contains translated text, THE Output_Panel SHALL display a Save button that, when activated, triggers a browser download of the translated text as a `.txt` file named `translation_YYYYMMDD_HHMMSS.txt` using the current UTC timestamp.
5. WHEN the Output_Panel contains no translated text, THE Copy button and the Save button SHALL have `aria-disabled="true"`, `opacity` of 50% or less, and `pointer-events: none` applied, and SHALL NOT perform any action when activated.
6. WHEN the translation result is a document file, THE Output_Panel SHALL display a Download button for the translated document file and SHALL NOT display the Copy button or the Save button.

---

### Requirement 7: Backend Integration — Translation Service

**User Story:** As a developer, I want a Laravel service that calls the Python translation backend, so that the web application can produce translations without embedding Python logic in PHP.

#### Acceptance Criteria

1. THE Translation_Service SHALL accept a source language name, a target language name, and either a plain-text string or a file path as input.
2. THE Translation_Service SHALL map the human-readable language names (English, Cebuano, Filipino) to the corresponding NLLB_Language_Code values (`eng_Latn`, `ceb_Latn`, `tgl_Latn`).
3. WHEN invoked with plain text, THE Translation_Service SHALL invoke the Python_Backend via a subprocess call, passing the text, source NLLB_Language_Code, and target NLLB_Language_Code, and SHALL return the translated string from stdout.
4. WHEN invoked with a file path, THE Translation_Service SHALL invoke the Python_Backend via a subprocess call, passing the file path, source NLLB_Language_Code, and target NLLB_Language_Code, and SHALL return the path of the translated output file. The output file format SHALL follow the mapping: `.docx` → `.docx`, `.pdf` → `.pdf`, `.txt` → `.txt`, `.md` → `.md`, `.csv` → `.csv`, `.rtf` → `.docx`, `.odt` → `.docx`.
5. IF the Python_Backend process exits with a non-zero status code, THEN THE Translation_Service SHALL throw a `TranslationException` containing the stderr output from the Python_Backend.
6. IF the source language name and target language name passed to the Translation_Service are identical, THEN THE Translation_Controller SHALL reject the request with a validation error message before invoking the Translation_Service.
7. WHEN a plain-text translation is requested, THE Translation_Controller SHALL reject the request with a validation error if the text input is empty or exceeds 8 000 characters.
8. WHEN a file translation is requested, THE Translation_Controller SHALL reject the request with a validation error if the uploaded file's extension is not one of the Supported_Formats or if the file size exceeds 10 MB (10 485 760 bytes).
9. THE Translation_Controller SHALL store uploaded files in Laravel's `storage/app/temp` directory and SHALL delete the uploaded file and the translated output file after the response is sent to the client, whether the translation succeeded or failed.

---

### Requirement 8: Sidebar Navigation Link

**User Story:** As a user, I want the sidebar "New Translation" link to navigate to the translation page, so that I can reach it from any authenticated page.

#### Acceptance Criteria

1. THE web routes file (`routes/web.php`) SHALL define a GET route at `/translate` named `translate`, protected by the `auth` middleware, that dispatches to `TranslationController@show`.
2. THE Sidebar SHALL update the "New Translation" `<a>` element in `layouts/app.blade.php` to use `href="{{ route('translate') }}"`.
3. WHEN the current route matches `translate`, THE Sidebar SHALL apply the `active` CSS class to the "New Translation" `<a>` element using `request()->routeIs('translate')`, consistent with the existing active-class pattern used for the `dashboard` and `settings` links.
