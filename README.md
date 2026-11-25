# SkillSwap

SkillSwap is a peer-to-peer learning platform where members can share skills they teach, find skills they want to learn, and arrange learning sessions.

> **Project status:** Skill and session-request CRUD, account authentication, ownership checks, groups, and the admin dashboard are implemented, including security auditing and filtered CSV exports.

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

- Register, sign in, manage a profile, and change a password.
- Use short-lived access tokens and rotating, revocable refresh sessions.
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
- Account signup, login/logout, profile editing, password changes, and session revocation.
- Argon2 password hashing with a server-side pepper, short-lived JWT access tokens, and rotating httpOnly refresh cookies.
- Protected API routes reject missing, invalid, expired, revoked, or inactive-user sessions.
- Listings are visible to signed-in members, but only their authenticated owner can modify or delete them. Legacy listings remain unowned and are excluded from member views.
- Session requests are visible only to their learner and listing owner. Learners can update their message; listing owners can update status. Participant identity is assigned by the backend.
- Reusable permission dependencies protect resource routes. The ownership migration adds nullable fields for existing SQLite and PostgreSQL databases without assigning legacy records to a member.
- Administrators have a protected dashboard for user and content moderation, managed categories, account and group details, session revocation, searchable activity, failed-login insights, and filtered CSV exports.
- Audit events record authentication outcomes, password changes, moderation, content deletion, session revocation, and exports with client IP and user-agent metadata. Export columns are explicitly selected and exclude password hashes and tokens.
- User signup cannot grant administrator access; provision administrator roles through a trusted database operation.
- SQLModel persistence using SQLite by default, with PostgreSQL support through `DATABASE_URL`.
- A Vite development proxy that forwards `/api` requests to the local backend.
- FastAPI's interactive API documentation at `/api/docs`.
- A Vercel configuration for the frontend and backend services.

Public signup cannot assign roles. Admin endpoints independently enforce the administrator permission and prevent self-role changes, self-bans, banning administrator accounts, and demoting the last active administrator.

## Project documentation

- [Product Requirements Document (PRD)](docs/01-prd.md) — product goals, users, release scope, and success criteria.
- [Software Requirements Specification (SRS)](docs/02-srs.md) — functional, non-functional, and interface requirements.
- [Technical Design Document (TDD)](docs/03-tdd.md) — current architecture and proposed implementation design.

## Technology stack

- **Frontend:** React, TypeScript, Vite
- **Backend:** FastAPI, Python
- **Communication:** REST APIs
- **Authentication:** Argon2 password hashes, JWT access tokens, rotating httpOnly refresh cookies
- **Authorization:** Ownership, group capabilities, and administrator permissions are enforced by the backend
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
| `POST` | `/api/auth/signup` | Create a member account |
| `POST` | `/api/auth/login` | Sign in and issue an access token |
| `POST` | `/api/auth/refresh` | Rotate the refresh session and issue a new access token |
| `POST` | `/api/auth/logout` | Revoke the current refresh session |
| `GET` | `/api/users/me` | Read the signed-in member's profile |
| `PATCH` | `/api/users/me` | Update the signed-in member's profile |
| `POST` | `/api/users/me/password` | Change password and revoke sessions |
| `GET` | `/api/users/me/sessions` | List the signed-in member's sessions |
| `DELETE` | `/api/users/me/sessions/{session_id}` | Revoke one of the member's sessions |

## Administrative API

The admin dashboard is available to signed-in administrator accounts. Its API routes require the backend `admin:manage` permission, regardless of UI visibility.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/admin/overview` | Read platform totals and recent administrative activity |
| `GET` | `/api/admin/users` | Search, filter, and paginate accounts |
| `GET` | `/api/admin/users/{user_id}` | View an account's listings, requests, groups, sessions, and activity |
| `PATCH` | `/api/admin/users/{user_id}/role` | Change a user's role |
| `POST` | `/api/admin/users/{user_id}/ban` | Ban an account with a reason and revoke its sessions |
| `POST` | `/api/admin/users/{user_id}/unban` | Restore a banned account |
| `POST` | `/api/admin/users/bulk-ban` | Ban multiple accounts with a reason |
| `POST` | `/api/admin/users/bulk-unban` | Unban multiple accounts |
| `POST` | `/api/admin/users/{user_id}/revoke-sessions` | Revoke all active sessions for an account |
| `GET` | `/api/admin/listings`, `/api/admin/groups` | Filter and paginate platform content |
| `DELETE` | `/api/admin/listings/{listing_id}`, `/api/admin/groups/{group_id}` | Remove a listing or group |
| `GET`, `POST`, `PATCH`, `DELETE` | `/api/admin/categories` | Manage skill categories |
| `GET` | `/api/admin/activity` | Search and filter audit events by text, action, actor, target, or time |
| `GET` | `/api/admin/security/failed-logins` | Review failed-login counts by client IP and account |
| `GET` | `/api/admin/exports/users.csv`, `/api/admin/exports/records.csv`, `/api/admin/exports/activity.csv` | Download CSV data using the selected filters |

## Authorization scope examples

The backend may use scopes such as:

- `skills:read` — browse skill listings
- `skills:create` — create a listing
- `skills:update:own` — update your own listings
- `requests:create` — create a session request
- `requests:read:participant` — read requests where you are learner or listing owner
- `requests:update:participant` — update your own message or the status of your listing's request
- `requests:delete:participant` — delete a request where you are a participant

These scopes are enforced by reusable FastAPI permission dependencies. Resource ownership and participation are checked in addition to the permission scope. Administrative routes additionally require the `admin:manage` scope.

## Local development

### Requirements

- Python 3.10 or later
- Node.js 22 or later

### Start the backend

From the repository root, create a virtual environment and install the backend dependencies. SQLite is used by default and the database file is created at `backend/skillswap.db`.

Set two independent secrets before starting the API. For local testing, PowerShell can generate them:

```powershell
$env:JWT_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"
$env:PASSWORD_PEPPER = python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`.env.example` lists the required variable names and contains placeholders only; it is not a source of production secrets.

In production, configure stable `JWT_SECRET_KEY` and `PASSWORD_PEPPER` values in Vercel's backend environment settings. Rotating the pepper invalidates existing password hashes; rotating the JWT secret invalidates active access tokens.

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

PostgreSQL support is available for a hosted database. Add `DATABASE_URL`, `JWT_SECRET_KEY`, and `PASSWORD_PEPPER` to the backend service's Vercel environment configuration before deployment; do not commit credentials.

### Backend API tests

From `backend/`, run:

```powershell
python -m unittest discover -s tests
```

## Deployment

The repository includes a `vercel.json` configuration for deploying the frontend and backend as Vercel services. Configure `DATABASE_URL` with a persistent PostgreSQL connection string and set stable `JWT_SECRET_KEY` and `PASSWORD_PEPPER` secrets in Vercel before deploying. The application rejects missing database configuration on Vercel instead of silently using ephemeral storage.

## Configuration and security

Authenticated listing discovery and participant-scoped request data are implemented. Unowned legacy records are preserved but hidden from member views until reviewed. As later Beta features are added:

- Keep secrets out of source control and load them from environment variables (for example, `DATABASE_URL`, `JWT_SECRET_KEY`, and `CORS_ORIGINS`).
- Validate required configuration when the backend starts.
- Continue extending the reusable audit event model for authentication, content, and session activity without weakening backend ownership checks.
- Store passwords using an established password-hashing method.
- Give each role only the permissions it needs.
