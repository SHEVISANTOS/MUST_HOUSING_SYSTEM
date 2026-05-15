# 🏠 MUST Housing Management System

A Django-based housing platform for **Mbeya University of Science and Technology (MUST)** students and staff. Browse properties, book rooms, manage payments, and handle tenant roles seamlessly.

## 🚀 Features
- Role-based access (Tenant, Landlord, Admin)
- Property listings with rent (TZS), distance from campus, amenities & availability
- Booking flow & payment tracking
- Responsive UI with Bootstrap 5 & Crispy Forms
- MySQL backend

## 📋 Prerequisites
- Python 3.10+
- MySQL Server
- Git

## 🛠️ Local Setup

python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

pip install -r requirements.txt
# Ubuntu/Debian: sudo apt install python3-dev default-libmysqlclient-dev build-essential
# macOS: brew install mysql-client pkg-config

cp .env.example .env
nano .env  # Fill in your MySQL credentials & SECRET_KEY

# General Settings
DJANGO_SECRET_KEY=django-insecure-must-housing-temp-key-change-later
DJANGO_DEBUG=True

# Database Credentials (Matches what we created in MariaDB)
DB_NAME=must_housing_db
DB_USER=must_django
DB_PASSWORD=MustHousing@2026!Secure
DB_HOST=localhost
DB_PORT=3306
