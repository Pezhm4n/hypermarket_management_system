# 🛒 سامانه مدیریت هایپرمارکت (HMS)
## Hypermarket Management System

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)
![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green?logo=qt&logoColor=white)
![Database](https://img.shields.io/badge/Database-SQLAlchemy%20%7C%20PostgreSQL%20%7C%20SQLite-blue)
![License](https://img.shields.io/badge/License-MIT-orange)

> **سامانه جامع مدیریت فروشگاهی با معماری MVC، دیتابیس هیبریدی و پشتیبانی دو زبانه**
>
> *A comprehensive retail management system featuring MVC architecture, hybrid database strategy, and bilingual support.*

---

## 📋 فهرست مطالب | Table of Contents

- [معرفی پروژه | Overview](#-معرفی-پروژه--overview)
- [تکنولوژی‌های استفاده شده | Tech Stack](#-تکنولوژی‌های-استفاده-شده--tech-stack)
- [ویژگی‌های کلیدی | Key Features](#-ویژگی‌های-کلیدی--key-features)
- [معماری پایگاه داده | Database Architecture](#-معماری-پایگاه-داده--database-architecture)
- [ساختار پروژه | Project Structure](#-ساختار-پروژه--project-structure)
- [نصب و راه‌اندازی | Installation](#-نصب-و-راه‌اندازی--installation)
- [راهنمای کاربری | User Manual](#-راهنمای-کاربری--user-manual)
- [تیم توسعه | Developers](#-تیم-توسعه--developers)

---

## 🎯 معرفی پروژه | Overview

**سامانه مدیریت هایپرمارکت (HMS)** یک نرم‌افزار دسکتاپ مدرن است که با هدف مدیریت یکپارچه فروشگاه‌های بزرگ طراحی شده است. این سیستم با استفاده از زبان پایتون و فریم‌ورک PyQt6 توسعه یافته و از الگوی معماری **MVC (Model-View-Controller)** برای تضمین تفکیک وظایف و قابلیت نگهداری بالا پیروی می‌کند.

**Hypermarket Management System (HMS)** is a modern desktop application designed for seamless retail management. Developed using Python and PyQt6, it strictly follows the **MVC (Model-View-Controller)** architectural pattern to ensure separation of concerns and maintainability.

---

## 🛠 تکنولوژی‌های استفاده شده | Tech Stack

| Category | Technology | Description |
| :--- | :--- | :--- |
| **Core** | Python 3.11+ | زبان اصلی برنامه |
| **GUI** | PyQt6 | رابط کاربری گرافیکی مدرن |
| **ORM** | SQLAlchemy 2.0 | مدیریت ارتباط با پایگاه داده |
| **Database** | PostgreSQL / SQLite | استراتژی هیبریدی (توسعه/انتشار) |
| **Analytics** | Matplotlib & Pandas | رسم نمودارها و تحلیل داده‌ها |
| **Reports** | ReportLab | تولید گزارش‌های PDF |
| **Hardware** | OpenCV & PyZbar | اسکن بارکد با وبکم |
| **Utils** | Selenium | دریافت اطلاعات آنلاین کالا (Web Scraping) |

---

## ✨ ویژگی‌های کلیدی | Key Features

* **Hybrid Database Strategy:** پشتیبانی همزمان از PostgreSQL (برای محیط توسعه و شبکه) و SQLite (برای نسخه پرتابل و تک‌کاربره).
* **Role-Based Access Control (RBAC):** مدیریت سطوح دسترسی کاربران (مدیر، صندوق‌دار، انباردار).
* **Bilingual UI:** تغییر زبان برنامه (فارسی/انگلیسی) به صورت آنی (Runtime).
* **Inventory Intelligence:** هشدار موجودی کم، تاریخ انقضا و مدیریت دسته‌های کالا (Batches).
* **Loyalty System:** سیستم باشگاه مشتریان با قابلیت امتیازدهی و تخفیف خودکار.
* **Financial Security:** سیستم مغایرت‌گیری صندوق (Shift Reconciliation/Z-Report).

---

## 🗄️ معماری پایگاه داده | Database Architecture

این سیستم از یک طراحی پایگاه داده رابطه‌ای (RDBMS) کاملاً نرمال‌سازی شده (تا سطح **3NF**) استفاده می‌کند.

The system utilizes a fully normalized relational database design (**3NF**) to ensure data integrity and efficiency.

### 📊 نمودارها | Diagrams

<details>
<summary><b>نمایش نمودار ER (Entity Relationship)</b></summary>
<br>
<img src="database_images/er.png" alt="ER Diagram" width="100%">
</details>

<details>
<summary><b>نمایش مدل رابطه‌ای (Relational Schema)</b></summary>
<br>
<img src="database_images/relation.png" alt="Relational Model" width="100%">
</details>

### 📑 جداول اصلی | Core Tables

1.  **مدیریت کاربران (Auth):** `UserAccount`, `Role`, `UserRole`, `Employee`
2.  **محصولات و انبار (Inventory):** `Product`, `Category`, `InventoryBatch` (ردیابی تاریخ انقضا و سری ساخت)
3.  **فروش و مالی (Sales):** `Invoice`, `InvoiceItem`, `Payment`, `Shift`, `Returns` (مدیریت مرجوعی)
4.  **تامین و مشتریان (CRM/SCM):** `Supplier`, `Customer`, `PurchaseOrder`

---

## 📂 ساختار پروژه | Project Structure

```text
HMS-project/
├── app/
│   ├── controllers/   # Business Logic (MVC Controllers)
│   ├── models/        # Database Schemas (SQLAlchemy Models)
│   ├── views/         # UI Files & View Logic (PyQt6)
│   │   ├── ui/        # .ui files (Qt Designer)
│   │   └── components/# Reusable UI Widgets
│   ├── core/          # Utilities (DB Manager, Config, Logger)
│   └── i18n/          # Translation Files (JSON)
├── database_images/   # Documentation Images
├── requirements.txt   # Project Dependencies
└── main.py            # Entry Point

```

---

## 🚀 نصب و راه‌اندازی | Installation

### پیش‌نیازها | Prerequisites

* Python 3.11 or higher
* Git

### مراحل نصب | Steps

1. **کلون کردن مخزن | Clone the repository:**
```bash
git clone [https://github.com/Pezhm4n/hypermarket_management_system.git](https://github.com/Pezhm4n/hypermarket_management_system.git)
cd hypermarket_management_system

```


2. **ساخت محیط مجازی (اختیاری) | Create Virtual Environment:**
```bash

python -m venv venv

# Windows:
venv\Scripts\activate

# Linux/Mac:
source venv/bin/activate

```


3. **نصب وابستگی‌ها | Install Dependencies:**
```bash
pip install -r requirements.txt
```


4. **اجرای برنامه | Run Application:**
```bash
python main.py
```



> **نکته:** 
> برنامه به صورت پیش‌فرض از دیتابیس **SQLite** استفاده می‌کند و نیازی به نصب سرور دیتابیس جداگانه برای تست نیست.

---

## 📖 راهنمای کاربری | User Manual

برای مشاهده آموزش کامل نحوه کار با نرم‌افزار، تصاویر محیط برنامه و راهنمای گام‌به‌گام، لطفاً به فایل‌های راهنما مراجعه کنید:

For detailed usage instructions, screenshots, and step-by-step guides, please refer to the help files:

* 📘 **[راهنمای فارسی (Persian Manual)](https://github.com/Pezhm4n/hypermarket_management_system/blob/main/fa_help.md)**
* 📘 **[English Manual](https://github.com/Pezhm4n/hypermarket_management_system/blob/main/en_help.md)**

---

## 📄 مجوز | License

This project is licensed under the **MIT License**.

```text
Copyright (c) 2026 Hypermarket Management System Team
```