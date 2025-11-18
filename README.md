# Report Mauto CDSBO API

API service for managing and retrieving M-Auto CDSBO report data.

## Overview

This service provides a RESTful API for retrieving M-Auto CDSBO report data based on various filters such as application date, NIK, branch code, and account number.

## Tech Stack

- **Python**: 3.13+
- **FastAPI**: Web framework for building APIs
- **SQLAlchemy**: SQL toolkit and ORM
- **Pydantic**: Data validation and settings management
- **PostgreSQL**: Database (via psycopg2)
- **Uvicorn**: ASGI server

## Project Structure

```
report-mauto-cdsbo/
├── app/
│   ├── api/            # API routes and endpoints
│   ├── core/           # Core functionality (config, deps, etc.)
│   ├── db/             # Database models and connections
│   ├── models/         # Data models
│   ├── schemas/        # Pydantic schemas for validation
│   └── service/        # Business logic services
├── docs/               # Documentation
├── logs/               # Application logs
├── .env                # Environment variables (not in version control)
├── .env.sample         # Sample environment variables
├── main.py             # Application entry point
├── pyproject.toml      # Project dependencies and metadata
└── README.md           # This file
```

## Installation

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv .venv
   ```
3. Activate the virtual environment:
   - Windows: `.venv\Scripts\activate`
   - Linux/Mac: `source .venv/bin/activate`
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Copy `.env.sample` to `.env` and update the values

## Configuration

Configure the application by setting the following environment variables in the `.env` file:

```
DATABASE_URL=postgresql://user:password@localhost/dbname
LOG_LEVEL=INFO
```

## Usage

### Running the API

```bash
python main.py
```

Or with uvicorn directly:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### API Endpoints

#### Get Report Mauto CDSBO

```
POST /v1/report-mauto
```

Request Body:
- `apply_date`: Date in ddmmyyyy format (required)
- `nik`: NIK filter (optional)
- `cc_reff`: CC Reff filter (optional)
- `branch_code`: Branch code filter (optional)
- `account_number`: Account number filter (optional)

Note : `nik` or `cc_reff` must be provided

Example:
```json
{
    "apply_date": "01082025",
    "nik": "1234567890"
}
```

## Documentation
API documentation is available at `/docs` or `/redoc` when the server is running.
