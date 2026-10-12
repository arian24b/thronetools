# ThroneTools

[English](README.md)

ابزار خط فرمان چندسکویی برای نصب، به‌روزرسانی، پشتیبان‌گیری، بازیابی و حذف **Throne** (و NekoRay قدیمی) روی لینوکس، macOS و ویندوز. پایگاه‌داده‌های geoip و geosite را هم نصب می‌کند و روی لینوکس و macOS هات‌اسپات وای‌فای را روشن و خاموش می‌کند.

## نصب

پایتون ۳٫۱۲ تا ۳٫۱۵.

```bash
uv tool install thronetools      # یا: pipx install thronetools
thronetools --help
```

از روی کلون: `uv sync && uv run thronetools --help`.

## دستورها

| دستور | کار |
|---|---|
| `install` | نصب Throne |
| `app-update --app {throne,nekoray}` | به‌روزرسانی Throne به آخرین نسخه |
| `app-version --app {throne,nekoray}` | نمایش نسخه و مسیر نصب |
| `backup --app A [--output PATH]` | پشتیبان‌گیری از تنظیمات در یک فایل zip |
| `restore --app A --zip FILE` | بازیابی یک پشتیبان |
| `remove [--app A]` | حذف Throne یا NekoRay (اگر هر دو نصب باشند می‌پرسد کدام) |
| `reinstall --app A [--backup] [--output PATH] [--force]` | حذف و نصب دوباره، در صورت نیاز همراه با پشتیبان |
| `geo-install --app A` | نصب یا تازه‌سازی geoip و geosite |
| `hotspot enable [--iface I] [--ssid S] [--password P] [--dry-run]` | روشن کردن هات‌اسپات (لینوکس، macOS) |
| `hotspot disable [--dry-run]` | خاموش کردن آن |

جایی که `--app` اختیاری است، مقدار پیش‌فرضش `throne` است. اگر در `restore` و `reinstall` آن را ننویسید، ابزار می‌پرسد؛ در `hotspot enable` هم رمز را می‌پرسد.

> `app-version` و `app-update` قبلاً `version` و `update` نام داشتند. این دو نام اکنون برای خود ابزار هستند (پایین‌تر را ببینید).

## نمونه‌ها

```bash
thronetools install
thronetools app-update --app throne
thronetools geo-install --app throne
thronetools backup --app nekoray --output ~/Backups
thronetools restore --app throne --zip ~/Backups/throne-backup-2026-02-17.zip
thronetools reinstall --app throne --backup
thronetools hotspot enable --iface wlp2s0 --dry-run     # فقط دستورها را چاپ می‌کند
```

بسته به سیستم‌عامل و مدیر بسته، بعضی عملیات به دسترسی بالاتر (root یا ادمین) نیاز دارند.

## دستورهای مشترک

این ابزار روی [cfuicli](https://github.com/arian24b/cfui) ساخته شده و ظاهر و رفتارش با بقیهٔ ابزارهای این مجموعه یکی است.

```bash
thronetools help [command]     # راهنما؛ -h روی هر دستور کار می‌کند
thronetools version            # نسخه و مخزن گیت (همچنین: -v)
thronetools update [--check]   # به‌روزرسانی خود ابزار؛ --check فقط نسخه‌ها را مقایسه می‌کند
thronetools -q ...             # حالت آرام: بدون بنر و یادداشت (یا THRONETOOLS_QUIET=1)
```

- اگر گزینهٔ اجباری جا افتاده باشد و ابزار را در ترمینال اجرا کرده باشید، مقدارش را می‌پرسد. در pipe یا CI با پیام `--flag is required. Pass --flag <value> or run interactively.` متوقف می‌شود (کد خروج ۲).
- خطاها در یک کادر قرمز روی stderr و با کد خروج غیرصفر نمایش داده می‌شوند. با Ctrl-C کد خروج ۱۳۰ است.
- رنگ فقط در ترمینال استفاده می‌شود. با `NO_COLOR=1` خاموش می‌شود.

## توسعه

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv build
```

ابزارهای مرتبط: [LinkCovery](https://github.com/arian24b/linkcovery)، [PEM](https://github.com/arian24b/pem)، [ollama-tool-cli](https://github.com/arian24b/ollamatools).

## مجوز

MIT
