# SkillSwap

SkillSwap is a peer-to-peer learning platform where members can share skills they teach, find skills they want to learn, and arrange learning sessions.

> **Project status:** In development. The repository currently contains a React and FastAPI starter application; the SkillSwap features below are planned and are not yet implemented.

## Project goals

- Build a full-stack web application with React, TypeScript, and FastAPI.
- Provide REST APIs for skill listings, session requests, and member profiles.
- Enforce authentication, role-based access control (RBAC), and permission scopes on the backend.
- Keep the initial release small enough to complete and demonstrate.

## Planned features

### MVP — Mid-term demo

- Browse available skill listings.
- Create, view, edit, and delete your own listings.
- Send and respond to session requests.
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
| **Member** | Browse listings, manage their own listings, and create or respond to session requests. Members can both teach and learn. |
| **Moderator** | Review reports and hide inappropriate listings. |
| **Administrator** | Manage users, categories, and listings across the platform. |

Authorization must be enforced by the backend. For example, members may manage only their own listings, while administrators may manage listings across the platform.

## Current implementation

The starter application currently includes:

- A FastAPI backend with `GET /api/health` and `GET /api/hello`.
- A React and TypeScript frontend with a form that calls `/api/hello`.
- A Vite development proxy that forwards `/api` requests to the local backend.
- FastAPI's interactive API documentation at `/docs`.
- A Vercel configuration for the frontend and backend services.

Skill listings, session requests, user accounts, authentication, authorization, persistence, and the planned roles are not implemented yet. The database technology has not been selected.

## Project documentation

- [Product Requirements Document (PRD)](docs/01-prd.md) — product goals, users, release scope, and success criteria.
- [Software Requirements Specification (SRS)](docs/02-srs.md) — functional, non-functional, and interface requirements.
- [Technical Design Document (TDD)](docs/03-tdd.md) — current architecture and proposed implementation design.

## Technology stack

- **Frontend:** React, TypeScript, Vite
- **Backend:** FastAPI, Python
- **Communication:** REST APIs
- **Authentication and authorization:** Planned
- **Database:** To be selected

## Planned API

These routes describe the intended API and may change during implementation.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/skills` | Browse skill listings |
| `POST` | `/api/skills` | Create a skill listing |
| `GET` | `/api/skills/{skill_id}` | View a listing |
| `PATCH` | `/api/skills/{skill_id}` | Update an owned listing |
| `DELETE` | `/api/skills/{skill_id}` | Delete an owned listing |
| `POST` | `/api/session-requests` | Request a learning session |
| `GET` | `/api/session-requests` | View requests available to the signed-in member |
| `PATCH` | `/api/session-requests/{request_id}` | Respond to or update a request |
| `GET` | `/api/users/me` | View the signed-in member's profile |

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

From the repository root, create a virtual environment and install the backend dependencies.

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

The API runs at `http://localhost:8000`; interactive documentation is at `http://localhost:8000/docs`.

### Start the frontend

In a second terminal, from the repository root:

```bash
cd frontend
npm install
npm run dev
```

Open the local address printed by Vite (typically `http://localhost:5173`). The Vite development server forwards `/api` requests to the backend on port `8000`.

## Deployment

The repository includes a `vercel.json` configuration for deploying the frontend and backend as Vercel services. To deploy, import the repository in Vercel and follow the project's deployment setup. Configure deployment settings and environment variables in the Vercel project before enabling production use.

## Configuration and security

The application does not yet implement authentication, authorization, or database configuration. As those features are added:

- Keep secrets out of source control and load them from environment variables (for example, `DATABASE_URL`, `JWT_SECRET_KEY`, and `CORS_ORIGINS`).
- Validate required configuration when the backend starts.
- Enforce permissions and listing ownership in the backend, not only in the frontend.
- Store passwords using an established password-hashing method.
- Give each role only the permissions it needs.
