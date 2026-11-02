# SkillSwap

SkillSwap is a peer-to-peer learning platform where members can share skills they teach, find skills they want to learn, and arrange learning sessions.

> **Project status:** MVP CRUD for skill listings and session requests is implemented. Authentication, RBAC, and Beta features remain planned.

## Project goals

- Build a full-stack web application with React, TypeScript, and FastAPI.
- Provide REST APIs for skill listings, session requests, and member profiles.
- Enforce authentication, role-based access control (RBAC), and permission scopes on the backend.
- Keep the initial release small enough to complete and demonstrate.

## Planned features

### MVP — Mid-term demo

- Browse available skill listings.
- Create, view, edit, and delete skill listings.
- Create, view, edit, and delete session requests.
- View request status.
- Run the frontend and backend locally.

### Beta — Final demo

- Register and sign in.
- Give members, moderators, and administrators distinct permissions.
- Restrict actions using authorization scopes.
- Provide a member profile dashboard.
- Deploy the application.

## User roles

| Role | Main permissions |
| --- | --- |
| **Member** | Browse listings, manage their own listings, and create or respond to session requests. Members can both teach and learn. (Beta permissions) |
| **Moderator** | Review reports and hide inappropriate listings. |
| **Administrator** | Manage users, categories, and listings across the platform. |

Authorization must be enforced by the backend. For example, members may manage only their own listings, while administrators may manage listings across the platform.

## Current implementation

The MVP currently includes:

- Skill listing CRUD in the React frontend and FastAPI REST API.
- Session request CRUD in the React frontend and FastAPI REST API.
- SQLModel persistence using SQLite by default, with PostgreSQL support through `DATABASE_URL`.
- A Vite development proxy that forwards `/api` requests to the local backend.
- FastAPI's interactive API documentation at `/api/docs`.
- A Vercel configuration for the frontend and backend services.

Authentication, authorization, member profiles, moderation, and administration are planned for Beta. The MVP has no sign-in, so listing and request data is shared and the frontend does not enforce ownership.

## Project documentation

- [Product Requirements Document (PRD)](docs/01-prd.md) — product goals, users, release scope, and success criteria.
- [Software Requirements Specification (SRS)](docs/02-srs.md) — functional, non-functional, and interface requirements.
- [Technical Design Document (TDD)](docs/03-tdd.md) — current architecture and proposed implementation design.

## Technology stack

- **Frontend:** React, TypeScript, Vite
- **Backend:** FastAPI, Python
- **Communication:** REST APIs
- **Authentication and authorization:** Planned
- **Database:** SQLite locally; PostgreSQL when configured through `DATABASE_URL`

## MVP API

These routes are implemented by the current MVP.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/skills` | Browse skill listings |
| `POST` | `/api/skills` | Create a skill listing |
| `GET` | `/api/skills/{skill_id}` | View a listing |
| `PATCH` | `/api/skills/{skill_id}` | Update a listing |
| `DELETE` | `/api/skills/{skill_id}` | Delete a listing |
| `POST` | `/api/session-requests` | Request a learning session |
| `GET` | `/api/session-requests` | List session requests |
| `GET` | `/api/session-requests/{request_id}` | View one session request |
| `PATCH` | `/api/session-requests/{request_id}` | Update a request or its status |
| `DELETE` | `/api/session-requests/{request_id}` | Delete a session request |

## Authorization scope examples

The backend may use scopes such as:

- `skills:read` — browse skill listings
- `skills:create` — create a listing
- `skills:update:own` — update your own listings
- `requests:create` — create a session request
- `requests:respond` — respond to a request
- `reports:review` — review reported content
- `users:manage` — administer user accounts

These are examples; final scope names should match the authorization implementation.

## Local development

### Requirements

- Python 3.10 or later
- Node.js 22 or later

### Start the backend

From the repository root, create a virtual environment and install the backend dependencies. SQLite is used by default and the database file is created at `backend/skillswap.db`.

**Windows PowerShell:**

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
fastapi dev main.py
```

**macOS or Linux:**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
fastapi dev main.py
```

The API runs at `http://localhost:8000`; interactive documentation is at `http://localhost:8000/api/docs`.

To use PostgreSQL locally, set `DATABASE_URL` before starting FastAPI. Use the connection string from your database provider and keep it out of source control.

```powershell
$env:DATABASE_URL = "postgresql://USER:PASSWORD@HOST:PORT/DATABASE"
```

### Start the frontend

In a second terminal, from the repository root:

```bash
cd frontend
npm install
npm run dev
```

Open the local address printed by Vite (typically `http://localhost:5173`). The Vite development server forwards `/api` requests to the backend on port `8000`.

PostgreSQL support is available for a hosted database. Add `DATABASE_URL` to the backend service's production environment configuration before deployment; do not commit credentials.

### Backend API tests

From `backend/`, run:

```powershell
python -m unittest discover -s tests
```

## Deployment

The repository includes a `vercel.json` configuration for deploying the frontend and backend as Vercel services. Configure `DATABASE_URL` in the backend service with a PostgreSQL connection string before deploying; Vercel's local filesystem is not persistent storage. Keep the connection string in Vercel environment settings, never in source control.

## Configuration and security

The MVP does not yet implement authentication or authorization. Its listing and request data is shared; do not use it to store private or sensitive information. As Beta security features are added:

- Keep secrets out of source control and load them from environment variables (for example, `DATABASE_URL`, `JWT_SECRET_KEY`, and `CORS_ORIGINS`).
- Validate required configuration when the backend starts.
- Enforce permissions and listing ownership in the backend, not only in the frontend.
- Store passwords using an established password-hashing method.
- Give each role only the permissions it needs.
