# Technical Design Document (TDD)

## 1. Purpose and status

This document describes the current starter architecture and the proposed technical design for SkillSwap. The repository does not yet implement listing management, session requests, persistence, authentication, or authorization. Proposed components are design intent, not a claim about existing code.

## 2. Constraints and technology

| Area | Technology or status |
| --- | --- |
| Frontend | React, TypeScript, Vite |
| Backend | FastAPI, Python |
| API | JSON over REST |
| Database | Not selected |
| Deployment configuration | Vercel configuration is present; production deployment is planned for Beta |

The course requires React with TypeScript and FastAPI with Python. Implementation should remain small enough to demonstrate and test within the course schedule.

## 3. Architecture

### 3.1 Current starter architecture

The Vite frontend runs independently during development and proxies `/api` calls to the FastAPI server. The backend currently exposes health and hello endpoints and can serve the built frontend when a `frontend/dist` directory exists. `vercel.json` describes frontend and backend services and routes API traffic to the backend.

### 3.2 Target architecture

```text
Browser
  |
  | HTTPS / JSON REST
  v
React + TypeScript client
  |
  | /api requests
  v
FastAPI routers
  |
  +--> Request validation and Pydantic schemas
  +--> Authentication and authorization dependencies (Beta)
  +--> Service/business rules
  |
  v
Persistence layer (MVP)
  |
  v
Relational database (engine to be selected)
```

Routers should handle HTTP concerns, schemas should validate request and response data, and service functions should enforce business rules. Database access should be isolated from route handlers so that ownership, state transitions, and authorization rules can be tested independently.

## 4. Backend design

### 4.1 Proposed module boundaries

As features are implemented, organize the backend around focused modules:

- `main.py`: application construction, router registration, health endpoint.
- `routers/skills.py`: listing endpoints.
- `routers/session_requests.py`: request endpoints and response actions.
- `routers/auth.py` and `routers/users.py`: Beta authentication and profile endpoints.
- `schemas/`: Pydantic input and output models.
- `models/`: persisted entity definitions.
- `services/`: listing, request, and account business rules.
- `core/config.py` and `core/security.py`: Beta configuration, password hashing, and token/authentication helpers.
- `db/`: connection/session lifecycle and migrations, after database selection.

This is a target organization, not the current repository layout. Add modules only as their functionality is implemented.

### 4.2 API behavior

- Use Pydantic request models for create/update payloads and validate all data on the server.
- Return stable response schemas and appropriate HTTP status codes.
- Return `404` when a requested record does not exist; use `403` for an authenticated caller who lacks permission, and `401` when authentication is required but missing or invalid.
- Avoid returning password hashes, internal secrets, or unnecessary user data.
- Document endpoints through FastAPI's generated OpenAPI documentation.

### 4.3 Request state

Session requests begin in `pending` state. The listing owner can transition them to `accepted` or `declined`. The API must reject responses from anyone other than the listing owner and reject invalid or repeated terminal transitions unless a later product decision explicitly allows them.

## 5. Frontend design

The React client should keep route/page responsibilities separate from reusable form and listing components as the interface grows. API calls should be centralized behind small typed functions rather than duplicated through components.

Planned views:

- **MVP:** listing browse, listing detail, listing create/edit form, participant request list, request response controls.
- **Beta:** registration/sign-in, profile dashboard, role-appropriate moderation and administration views.

The client may improve usability by hiding unavailable controls, but must display backend errors and never be relied on for security decisions.

## 6. Data design

The database engine remains undecided. Before implementing persistence, select a relational database and access/migration approach that work locally and with the intended deployment environment. Keep the model portable and avoid coupling business rules to database-specific behavior.

### 6.1 Proposed entities

| Entity | Important relationships and fields |
| --- | --- |
| `User` (Beta) | Owns skill listings; can participate in requests; has unique email, password hash, role, and profile fields. |
| `Category` | Groups skill listings; has a unique name. |
| `SkillListing` | Belongs to an owner and category; has title, description, availability/visibility, timestamps. |
| `SessionRequest` | References a listing, learner, and teacher/listing owner; has message, status, and timestamps. |
| `Report` (Beta) | References a listing and reporter; records reason, review state, and moderator action. |

Use stable identifiers, foreign keys, and database constraints for required values and unique account email. Consider indexes for listing category/availability and session-request participants/status. Determine cascade and archival behavior before migrations.

## 7. Authentication and authorization (Beta)

- Use a maintained password-hashing implementation; never store plaintext passwords.
- Load signing keys and other secrets from environment configuration and validate required production settings at startup.
- Choose and document a token or secure-cookie strategy before implementing authentication.
- Derive identity and role from verified backend credentials, never from client-supplied role fields.
- Enforce permissions through FastAPI dependencies or an equivalent centralized backend mechanism.
- Apply ownership checks in service/API operations for listings and session requests.
- Use least privilege: members manage their own resources, moderators handle reports/listing visibility, and administrators manage platform resources.

Potential scopes include `skills:read`, `skills:create`, `skills:update:own`, `requests:create`, `requests:respond`, `reports:review`, and `users:manage`. Final scope names and the mapping from roles to scopes should be defined with implementation.

## 8. Configuration and deployment

Local development uses the Vite proxy to reach FastAPI. Continue to document backend and frontend setup separately. Keep secrets out of the repository and provide non-secret example configuration only if needed.

For Beta deployment, configure the frontend and backend services using the existing Vercel setup or a reviewed alternative. Provide environment variables through the hosting platform, use HTTPS, and verify that the selected database is reachable and backed up. Deployment is a Beta requirement; the MVP demo must work locally.

## 9. Testing strategy

### MVP

- Backend unit tests for listing validation and session-request state transitions.
- API tests for listing CRUD, request creation/responding, status visibility, and ownership enforcement.
- Frontend build/type-check and focused UI checks for forms, loading, and error states.
- Manual end-to-end local demo using the documented startup steps.

### Beta

- Authentication tests for registration, credential validation, and protected endpoints.
- Authorization tests for member, moderator, and administrator access, including denied actions.
- Tests ensuring users cannot access another user's profile or requests.
- Production configuration/deployment smoke checks; verify secrets are not exposed in client bundles or responses.

Tests should use isolated test data and should not require live production credentials.

## 10. Risks and open decisions

- **Database and migration tooling:** Select before building persistent features; confirm local and hosting compatibility.
- **MVP identity:** Without authentication, the project needs a controlled demo strategy for resource ownership. Do not treat a client-provided owner identifier as secure.
- **Authentication design:** Decide token versus secure cookie handling, expiration, and refresh behavior before Beta implementation.
- **Scope feasibility:** Prioritize a complete listing/request flow over optional messaging, scheduling integrations, or other non-MVP features.
- **Deployment configuration:** Validate the Vercel service configuration against the final backend/frontend build and database choice.
