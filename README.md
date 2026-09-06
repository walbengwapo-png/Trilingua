# TriLingua - 3-Way Translation System

![TriLingua Banner](docs/banner.png)

> **Capstone Project** - A multilingual document translation system for English, Filipino, and Cebuano languages

[![Laravel](https://img.shields.io/badge/Laravel-12.x-FF2D20?style=flat&logo=laravel)](https://laravel.com)
[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 📖 About This Project

**TriLingua** is a capstone project that provides seamless translation between three Philippine languages: **Cebuano**, **Filipino (Tagalog)**, and **English**. Built with modern web technologies and powered by the NLLB-200 AI model, TriLingua enables both text and document-level translations with high accuracy.

### 🎯 Project Goals

- Preserve and promote Philippine languages through accessible translation technology
- Provide accurate document-level translation for educational and professional use
- Bridge communication gaps between different language communities in the Philippines
- Demonstrate practical application of modern AI/ML models in language processing

## ✨ Features

- **🔄 3-Way Translation**: Translate between Cebuano, Filipino, and English in any direction
- **📄 Document Support**: Upload and translate DOCX, PDF, TXT, MD, CSV, RTF, and ODT files
- **💬 Text Translation**: Quick translation for short texts and phrases
- **📊 Translation History**: Track and manage all your translations
- **🎨 Modern UI**: Clean, responsive interface with dark/light theme support
- **🔐 User Authentication**: Secure account system with password reset
- **📈 Dashboard Analytics**: View translation statistics and activity

## 🛠️ Technology Stack

### Frontend
- **Laravel Blade** - Server-side templating
- **Vite** - Modern build tool
- **Tailwind CSS** - Utility-first CSS framework
- **Vanilla JavaScript** - No framework overhead

### Backend
- **Laravel 12** - PHP web framework
- **PHP 8.2+** - Server-side language
- **SQLite** - Local database
- **Supabase** - Cloud storage (optional)

### AI/ML
- **Python 3.8+** - ML runtime
- **FastAPI** - Translation API server
- **NLLB-200 (600M)** - Facebook's multilingual translation model
- **PyTorch** - Deep learning framework
- **Transformers** - Hugging Face library

## 📋 Prerequisites

Before installation, ensure you have:

- **PHP 8.2+** with extensions: `fileinfo`, `zip`, `pdo_sqlite`, `sqlite3`
- **Composer** - PHP dependency manager
- **Node.js 18+** & npm - JavaScript runtime and package manager
- **Python 3.8+** & pip - Python runtime and package manager
- **Git** - Version control

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/KenUsa-31/Trilingua.git
cd Trilingua/trilingua-code
```

### 2. Install PHP Dependencies

```bash
composer install
```

### 3. Install Node.js Dependencies

```bash
npm install
```

### 4. Install Python Dependencies

```bash
pip install transformers sentencepiece python-docx pdfplumber odfpy striprtf PyMuPDF fastapi uvicorn torch python-multipart
```

### 5. Download the AI Model

```bash
python Model/download_model.py
```

This will download the NLLB-200 model (~2.5GB). It may take several minutes.

### 6. Configure Environment

```bash
cp .env.example .env
php artisan key:generate
```

Edit `.env` and update:
- `APP_NAME=TriLingua`
- `APP_URL=http://localhost:8000`
- Supabase credentials (optional, for document storage)

### 7. Set Up Database

```bash
php artisan migrate
```

### 8. Build Frontend Assets

```bash
npm run build
```

## 🎮 Running the Application

You need to run **two servers** simultaneously:

### Terminal 1: Python Translation Server

```bash
python Model/server.py
```

This starts the ML translation service on `http://127.0.0.1:5000`

### Terminal 2: Laravel Web Server

```bash
php artisan serve
```

This starts the web application on `http://127.0.0.1:8000`

### Access the Application

Open your browser and navigate to: **http://localhost:8000**

## 📚 Documentation

- [Installation Guide](trilingua-code/README.md)
- [Password Reset Guide](trilingua-code/PASSWORD_RESET_GUIDE.md)
- [Dashboard Fix](trilingua-code/DASHBOARD_FIX.md)
- [Authentication Testing](trilingua-code/AUTHENTICATION_TESTING.md)

## 🧪 Testing

### Create a Test User

```bash
php artisan tinker
```

```php
User::create([
    'name' => 'Test User',
    'email' => 'test@example.com',
    'password' => bcrypt('password123')
]);
```

### Run Tests

```bash
php artisan test
```

## 🌐 Supported Languages

| Language | Code | Direction |
|----------|------|-----------|
| English | `eng_Latn` | ↔️ Cebuano, Filipino |
| Cebuano | `ceb_Latn` | ↔️ English, Filipino |
| Filipino | `fil_Latn` | ↔️ English, Cebuano |

## 📁 Project Structure

```
Trilingua/
├── trilingua-code/          # Main application
│   ├── app/                 # Laravel application code
│   │   ├── Http/           # Controllers, Middleware
│   │   ├── Models/         # Eloquent models
│   │   └── Services/       # Business logic
│   ├── Model/              # Python ML server
│   │   ├── server.py       # FastAPI translation server
│   │   └── document_translator_v3.py
│   ├── resources/          # Frontend assets
│   │   ├── views/          # Blade templates
│   │   ├── css/            # Stylesheets
│   │   └── js/             # JavaScript
│   ├── routes/             # Web routes
│   ├── database/           # Migrations, seeders
│   └── public/             # Public assets
└── README.md               # This file
```

## 🤝 Contributing

This is a capstone project, but contributions, issues, and feature requests are welcome!

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request



## 👥 Authors

- **KenUsa-31** - [GitHub Profile](https://github.com/KenUsa-31)

## 🙏 Acknowledgments

- **Facebook AI Research** - For the NLLB-200 translation model
- **Laravel Community** - For the excellent PHP framework
- **Hugging Face** - For the Transformers library
- **University/Institution** - For supporting this capstone project

## 📧 Contact

For questions or feedback about this capstone project, please open an issue on GitHub.

---


