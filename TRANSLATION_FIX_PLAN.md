# TriLingua Translation System — Comprehensive Fix Plan

## Executive Summary

After analyzing the codebase, I've identified **3 critical issues** affecting the translation system:

1. **Layout Issues** — CSS/design problems causing "all over the place" appearance
2. **Performance/Speed Issues** — Laravel timeout before Python completes translation
3. **Translation Quality Issues** — Subpar output from the NLLB model

---

## Issue #1: Translation Layout Problems

### Current State
- The `translation.blade.php` uses a two-panel grid layout with language bar at top
- CSS (`translation.css`) has proper flexbox/grid structure
- **Problem**: The layout appears broken/unpolished

### Root Causes
1. **Missing CSS variables**: The `translation.css` uses CSS variables (`--card-bg`, `--border`, `--text`, `--primary`, `--muted`) that depend on global CSS which may not be loading properly
2. **Height calculation**: `height: calc(100vh - 120px)` assumes a fixed header height that may not match the actual layout
3. **Panel overflow**: `min-height: 280px` on textarea/output is hardcoded and doesn't account for footer/button areas
4. **No loading state styling**: The spinner in the translate button exists but there's no visual feedback for document upload progress

### Fixes Required
- [ ] Add fallback CSS variables for `translation.css` 
- [ ] Fix height calculation using flexbox instead of viewport units
- [ ] Make textarea/output areas truly responsive with proper min-height
- [ ] Add loading overlay for document translation (since it takes longer)
- [ ] Fix z-index stacking for download button and file info

---

## Issue #2: Performance & Timeout Problems

### Current State
- **Laravel timeout**: PHP default `max_execution_time` is typically 30-60 seconds
- **Laravel session timeout**: 120 minutes (from `config/session.php`)
- **Python service timeout**: 180 seconds (3 minutes) in `TranslationService.php`
- **Problem**: Laravel kills the request before Python finishes processing

### Architecture Flow
```
User → Laravel (POST /translate) → TranslationService (cURL to Python)
                                                    ↓
                                    Python server.py (takes 60-180s)
                                                    ↓
                                    Laravel returns JSON response
```

### Root Causes
1. **PHP max_execution_time**: Default 30s, but translation can take 2-3 minutes
2. **Rate limiting**: `throttle:60,1` allows 60 requests/minute but doesn't help with long-running requests
3. **Synchronous processing**: Laravel waits for Python to finish before responding → browser times out
4. **No queue/job system**: Translation happens in real-time instead of background job
5. **Session locking**: Laravel locks session during request, blocking concurrent requests from same user

### Fixes Required
- [ ] **CRITICAL**: Increase PHP `max_execution_time` to 300s (5 minutes) in `.htaccess` or `php.ini`
- [ ] **CRITICAL**: Implement Laravel Queue for background translation jobs
- [ ] **HIGH**: Add polling mechanism for document translation status
- [ ] **HIGH**: Increase Laravel timeout middleware specifically for `/translate` route
- [ ] **MEDIUM**: Release session lock early in controller
- [ ] **MEDIUM**: Add progress indicators in UI

---

## Issue #3: Translation Quality Problems

### Current State
- **Model**: `facebook/nllb-200-distilled-600M` (600M parameter distilled version)
- **Languages**: English, Cebuano, Filipino
- **Quality**: Subpar for Cebuano/Filipino (low-resource languages)

### Root Causes
1. **Model choice**: NLLB-200 Distilled 600M is the *smallest/fastest* version but produces lowest quality
2. **Chunking strategy**: Splitting at 80 tokens may break context unnecessarily for Cebuano/Filipino
3. **Generation parameters**: 
   - `num_beams=4` is low for quality (should be 8-12)
   - `repetition_penalty=1.3` is good but `no_repeat_ngram_size=4` might be too aggressive
4. **No domain adaptation**: Generic translation without context-specific tuning
5. **Minimal preprocessing**: No text normalization for Filipino/Cebuano contractions or special characters
6. **Single model**: No fallback or ensemble approach

### Fixes Required
- [ ] **HIGH**: Switch to `facebook/nllb-200-1.3B` (1.3B parameter version) for better quality
- [ ] **HIGH**: Increase `num_beams` to 8 for beam search
- [ ] **MEDIUM**: Implement dynamic chunk sizing based on language pair
- [ ] **MEDIUM**: Add language-specific preprocessing (normalize Filipino contractions, etc.)
- [ ] **MEDIUM**: Add post-processing rules for common NLLB errors in Cebuano/Filipino
- [ ] **LOW**: Consider glossary/custom terminology support for domain-specific terms

---

## Recommended Implementation Order

### Phase 1: Immediate Fixes (0-2 hours)
1. **Increase PHP timeout** — Add to `.htaccess`:
   ```
   php_value max_execution_time 300
   php_value memory_limit 512M
   ```
2. **Fix CSS layout** — Add CSS variable fallbacks and responsive fixes
3. **Add error handling** — Better user feedback when translations fail

### Phase 2: Performance Improvements (2-5 hours)
4. **Implement queue system**:
   ```php
   // Create translation job
   class TranslateDocument implements ShouldQueue
   {
       use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;
   }
   ```
5. **Add polling endpoint** — `/translate/status/{job_id}`
6. **Frontend polling** — Check status every 2s, show progress bar

### Phase 3: Quality Improvements (5-10 hours)
7. **Upgrade model** — Download and configure 1.3B model
8. **Optimize parameters** — Tune beam search, chunk size, repetition penalties
9. **Add language-specific rules** — Filipino/Cebuano normalization

---

## Detailed Technical Changes

### 1. PHP Configuration (`.htaccess` or `php.ini`)
```apache
<IfModule mod_php8.c>
    php_value max_execution_time 300
    php_value memory_limit 512M
    php_value upload_max_filesize 10M
    php_value post_max_size 10M
    php_value max_input_time 300
</IfModule>
```

### 2. Laravel Route Update (`routes/web.php`)
```php
// Add timeout middleware specifically for translation
Route::post('/translate', [TranslationController::class, 'translate'])
    ->name('translate.submit')
    ->middleware(['auth', 'throttle:10,1', 'timeout:280']); // Custom timeout
```

### 3. Queue Implementation (Partial)
```php
// TranslationController.php - dispatch job instead of synchronous
if ($request->hasFile('document')) {
    $job = new TranslateDocumentJob(
        $uploadedFile,
        $sourceLang,
        $targetLang,
        $pdfColumnMode,
        Auth::id()
    );
    dispatch($job);
    
    return response()->json([
        'job_id' => $job->uuid(),
        'status' => 'processing',
        'message' => 'Translation started. Poll /translate/status/{job_id} for updates.'
    ]);
}
```

### 4. Model Upgrade (`Model/server.py`)
```python
# Change from:
model_name = "facebook/nllb-200-distilled-600M"

# To:
model_name = "facebook/nllb-200-1.3B"  # Better quality, slower
```

### 5. CSS Variable Fallbacks (`resources/css/views/translation.css`)
```css
.translation-page {
    --card-bg: #fff;
    --border: #e5e7eb;
    --text: #1f2937;
    --primary: #3b82f6;
    --muted: #6b7280;
    
    display: flex;
    flex-direction: column;
    /* other styles */
}
```

### 6. Translation Quality Parameters (`Model/document_translator_v3.py`)
```python
# Current:
output_ids = model.generate(
    **inputs,
    forced_bos_token_id=forced_id,
    max_new_tokens=max_new,
    num_beams=4,  # ← Increase to 8
    early_stopping=True,
    repetition_penalty=1.3,
    no_repeat_ngram_size=4,
    length_penalty=1.0,
)

# Improved:
output_ids = model.generate(
    **inputs,
    forced_bos_token_id=forced_id,
    max_new_tokens=max_new,
    num_beams=8,  # Better quality
    early_stopping=True,
    repetition_penalty=1.4,  # Slightly higher
    no_repeat_ngram_size=3,  # Less aggressive
    length_penalty=1.2,  # Slightly prefer longer outputs
    temperature=0.7,  # Add some randomness
)
```

---

## Testing Checklist

- [ ] Text translation works and completes within timeout
- [ ] Document translation doesn't timeout (with queue system)
- [ ] Layout displays correctly on desktop (1920px, 1366px)
- [ ] Layout displays correctly on mobile (768px, 375px)
- [ ] Progress indicator shows during long translations
- [ ] Error messages display properly when translation fails
- [ ] Download link appears after document translation completes
- [ ] Translation quality improvement verified for Cebuano/Filipino
- [ ] No session timeout during long translations

---

## Risk Assessment

| Change | Risk | Mitigation |
|--------|------|------------|
| Increase PHP timeout | Medium — server resources | Monitor memory usage, set reasonable limits |
| Implement queue | High — requires Redis/DB | Provide fallback to synchronous if queue fails |
| Upgrade model | Medium — slower translation | Keep 600M as option, make 1.3B default |
| CSS changes | Low — visual only | Test on multiple screen sizes |

---

## Estimated Timeline

- **Phase 1 (Critical)**: 2 hours — Fixes timeout and layout issues
- **Phase 2 (Performance)**: 5 hours — Queue system and polling
- **Phase 3 (Quality)**: 10 hours — Model upgrade and parameter tuning

**Total: ~17 hours** (can be parallelized to ~10 hours with multiple developers)

---

## Success Metrics

1. **No timeouts**: 95% of translations complete without Laravel timeout
2. **Layout score**: CSS score >90 on Lighthouse
3. **Translation quality**: BLEU score improvement of 10-15% on test set
4. **User satisfaction**: Reduced complaint rate about slow/broken translations
5. **Response time**: UI responds within 100ms (document upload shows "processing")