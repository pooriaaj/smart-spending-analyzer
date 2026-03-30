# Smart Spending Analyzer

A full-stack financial analytics platform that helps users understand their spending behavior, detect patterns, and receive intelligent financial insights.

Live App:  
https://smart-spending-analyzer.vercel.app  

Backend API:  
https://smart-spending-analyzer.onrender.com  

---

## Overview

Smart Spending Analyzer is designed to go beyond basic expense tracking.

It provides:
- structured transaction management
- automated CSV import with validation
- spending analytics and trend detection
- intelligent categorization
- a financial assistant that answers user questions and suggests actions

The long-term vision is to evolve this into a fully automated financial intelligence system with AI-driven insights.

---

## Tech Stack

Frontend:
- React (Vite)
- Recharts (data visualization)
- CSS (custom UI system)

Backend:
- FastAPI
- SQLAlchemy
- PostgreSQL

Authentication:
- JWT (token-based authentication)

Deployment:
- Frontend: Vercel
- Backend: Render

---

## Features

### Authentication & Security
- User registration and login
- JWT-based authentication
- Protected API routes

### Transaction Management
- Add, edit, delete transactions
- Filter by:
  - type (income/expense)
  - category
  - month
- Export transactions to CSV

### CSV Import System
- Upload bank-style CSV files
- Supports multiple encodings:
  - utf-8
  - utf-8-sig
  - cp1252
  - latin-1
- Automatic:
  - header detection
  - delimiter detection
- Duplicate detection (no double imports)
- Import result feedback:
  - imported rows
  - duplicates skipped
  - invalid rows skipped

### Smart Categorization
- Detects uncategorized transactions
- Suggests categories using rule-based logic
- Bulk apply suggestions
- Confidence scoring and explanation

### Analytics Dashboard
- Total income, expenses, balance
- Monthly summary (bar chart)
- Category breakdown (pie chart)
- Top expense category
- Recent transactions

### Advanced Insights
- Spending insights (observations + recommendations)
- Overspending alerts
- Category trend analysis (month-over-month)

### Financial Assistant
- Chat-based assistant
- Supports:
  - balance queries
  - spending trends
  - category analysis
  - savings advice
- Context-aware conversation (short memory)
- Suggested follow-ups
- Suggested actions:
  - open analytics sections
  - filter transactions dynamically

---

## Architecture

Frontend communicates with backend via REST API.

Key backend layers:
- Routes (API endpoints)
- Services (logic like categorization)
- Models (SQLAlchemy)
- Schemas (Pydantic validation)

Data flow:
User → React UI → API → Database → Analytics → UI/Assistant

---

## Example Use Cases

- Import a bank CSV → instantly analyze spending
- Detect overspending in the current month
- Identify top expense category
- Ask:
  - "Did my spending increase?"
  - "How can I save money?"
- Navigate directly to relevant filtered data from assistant

---

## Engineering Highlights

- Robust CSV ingestion pipeline
- Duplicate-safe import system
- Query-based filtering across analytics endpoints
- Reusable analytics engine (used by both dashboard and assistant)
- Context-aware assistant design (history + snapshot-based logic)
- Clean separation between UI, API, and data layers

---

## Future Improvements

- AI-based transaction categorization (ML / NLP)
- Bank API integrations (Plaid or similar)
- Real-time transaction sync
- Personalized budgeting system
- Predictive spending analysis
- Mobile-friendly UI

---

## Author

Mohammadreza Alijani  
Toronto, Canada  

GitHub: https://github.com/pooriaaj  

---

## License

This project is for educational and portfolio purposes.