# 🏠 VOT House Finding

A Django-based house finding platform by **VOT Mwanza Limited**. Browse properties, book rooms, manage payments, and handle tenant roles seamlessly.

## 🚀 Features
- Role-based access (Tenant, Landlord, Admin)
- Property listings with rent (TZS), distance from city center, amenities & availability
- Booking flow & payment tracking
- Responsive UI with Bootstrap 5 & Crispy Forms
- Postgres (Neon) backend

## 📋 Prerequisites
- Python 3.10+
- A Postgres database (e.g. a free [Neon](https://neon.tech) project)
- Git

## 🛠️ Local Setup

python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
nano .env  # Fill in your DATABASE_URL & SECRET_KEY

See `.env.example` for the required variables. **Never commit `.env`** — it's git-ignored on purpose because it holds real database credentials.
