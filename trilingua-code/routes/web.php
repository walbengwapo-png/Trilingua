<?php

use Illuminate\Support\Facades\Route;
use App\Http\Controllers\Auth\ForgotPasswordController;
use App\Http\Controllers\Auth\ResetPasswordController;
use App\Http\Controllers\Auth\RegisterController;
use App\Http\Controllers\Auth\LoginController;
use App\Http\Controllers\DocumentsController;
use App\Http\Controllers\HistoryController;
use App\Http\Controllers\SettingsController;
use App\Http\Controllers\DashboardController;
use App\Http\Controllers\TranslationController;

Route::get('/', function () {
    return redirect()->route('login');
});

// Clears stale session cookies from previous config (safe to remove after first use)
Route::get('/clear-session', function () {
    return response('Cookies cleared. <a href="/login">Go to login</a>')
        ->withCookie(\Cookie::forget('laravel_session'))
        ->withCookie(\Cookie::forget('XSRF-TOKEN'));
});

// Auth routes with rate limiting
Route::middleware('throttle:10,1')->group(function () {
    Route::get('/register', [RegisterController::class, 'show'])->name('register');
    Route::post('/register', [RegisterController::class, 'store'])->name('register.store');

    Route::get('/login', [LoginController::class, 'show'])->name('login');
    Route::post('/login', [LoginController::class, 'login'])->name('login.attempt');

    // Password reset
    Route::get('/forgot-password', [ForgotPasswordController::class, 'show'])->name('password.request');
    Route::post('/forgot-password', [ForgotPasswordController::class, 'send'])->name('password.email');
    Route::get('/reset-password/{token}', [ResetPasswordController::class, 'show'])->name('password.reset');
    Route::post('/reset-password', [ResetPasswordController::class, 'reset'])->name('password.update');
});

Route::post('/logout', [LoginController::class, 'logout'])
    ->middleware('auth')
    ->name('logout');

// Status endpoint is outside auth middleware so long translations don't hit session expiry
Route::get('/translate/status/{jobId}', [TranslationController::class, 'status'])->name('translate.status');

// Protected routes
Route::middleware(['auth', 'throttle:60,1'])->group(function () {
    Route::get('/dashboard', [DashboardController::class, 'index'])->name('dashboard');

    Route::get('/settings', [SettingsController::class, 'show'])->name('settings');
    Route::post('/settings/account', [SettingsController::class, 'updateAccount'])->name('settings.account');
    Route::post('/settings/password', [SettingsController::class, 'updatePassword'])->name('settings.password');
    Route::post('/settings/general', [SettingsController::class, 'updateGeneral'])->name('settings.general');

    Route::get('/translate', [TranslationController::class, 'show'])->name('translate');
    Route::post('/translate', [TranslationController::class, 'translate'])->name('translate.submit');

    Route::get('/documents', [DocumentsController::class, 'index'])->name('documents');

    Route::get('/history', [HistoryController::class, 'index'])->name('history');
    Route::get('/history/{id}', [HistoryController::class, 'detail'])->name('history.detail');
    Route::post('/history/redownload/{id}', [HistoryController::class, 'redownload'])->name('history.redownload');
    Route::post('/history/redownload-original/{id}', [HistoryController::class, 'redownloadOriginal'])->name('history.redownload-original');
    Route::delete('/history/{id}', [HistoryController::class, 'destroy'])->name('history.destroy');
});