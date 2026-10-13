# Software Requirements Specification (SRS)

## 1. Introduction

### 1.1 Purpose

This specification defines the externally observable requirements for SkillSwap and separates the mid-term MVP from the final-demo Beta. It is intended for implementation, testing, and course-project review.

### 1.2 Product scope

SkillSwap is a web application for publishing skills, discovering learning opportunities, and arranging peer-to-peer session requests. The planned stack is a React and TypeScript frontend, a FastAPI and Python REST backend, and a database that has not yet been selected.

### 1.3 Current implementation status

The repository currently has a React frontend that calls `GET /api/hello`, a FastAPI backend providing `GET /api/health` and `GET /api/hello`, a Vite API proxy, and Vercel service configuration. The requirements below are planned. Listings, requests, persistence, user accounts, roles, and authorization are not implemented.

## 2. System context

The system consists of:

- **Web client:** React with TypeScript; presents listing, request, and profile screens.
- **REST API:** FastAPI; validates input, applies business rules, enforces permissions, and accesses persistent data.
- **Database:** Not selected; stores users, categories, listings, requests, and reports as features are implemented.

The browser must treat the API as authoritative for validation, request status, and authorization decisions.

## 3. User classes

| User class | Description | Release |
| --- | --- | --- |
| Visitor | Unauthenticated user who can browse public listing information. | MVP |
| Member | User who can teach and learn, maintain their own listings, and participate in relevant session requests. | MVP/Beta |
| Moderator | User trusted to review reports and hide inappropriate listings. | Beta |
| Administrator | User who manages platform users, categories, and listings. | Beta |

## 4. Functional requirements

### 4.1 Skill listings

| ID | Release | Requirement |
| --- | --- | --- |
| SRS-F01 | MVP | The API shall return a collection of available skill listings. |
| SRS-F02 | MVP | A visitor shall be able to retrieve an individual listing by its identifier. |
| SRS-F03 | MVP | A member shall be able to create a listing with the required skill information. |
| SRS-F04 | MVP | A member shall be able to update or delete only a listing they own. |
| SRS-F05 | MVP | The API shall validate required fields and reject invalid listing data with a client-error response. |
| SRS-F06 | Beta | A moderator shall be able to hide a listing after reviewing a report. |
| SRS-F07 | Beta | An administrator shall be able to manage listings regardless of owner. |

### 4.2 Session requests

| ID | Release | Requirement |
| --- | --- | --- |
| SRS-F08 | MVP | A member shall be able to create a request for an available listing. |
| SRS-F09 | MVP | The listing owner shall be able to accept or decline a request addressed to them. |
| SRS-F10 | MVP | A participant shall be able to list only session requests in which they are involved. |
| SRS-F11 | MVP | A request shall have a defined status, initially `pending`, and transition to `accepted` or `declined` after the owner's response. |
| SRS-F12 | Beta | The backend shall verify participant identity and request ownership for each request operation. |

### 4.3 Accounts, roles, and profiles

| ID | Release | Requirement |
| --- | --- | --- |
| SRS-F13 | Beta | A visitor shall be able to register with valid account details. |
| SRS-F14 | Beta | A registered user shall be able to authenticate and sign out. |
| SRS-F15 | Beta | An authenticated member shall be able to retrieve and update permitted fields in their own profile. |
| SRS-F16 | Beta | The backend shall assign or verify a user's role and required permission scope before protected operations. |
| SRS-F17 | Beta | A moderator shall be able to review reports and hide inappropriate listings. |
| SRS-F18 | Beta | An administrator shall be able to manage users and categories. |

## 5. External interface requirements

### 5.1 User interface

- The frontend shall provide a listing browse/detail experience and forms for applicable listing and session-request operations. (MVP)
- The frontend shall display validation errors and request status returned by the API. (MVP)
- The frontend shall provide account and profile views after authentication is implemented. (Beta)
- The frontend may hide controls the current user cannot use, but this is usability behavior and not a substitute for backend authorization. (Beta)

### 5.2 API interface

The planned API uses JSON over HTTP. Route names may evolve with implementation.

| Method | Path | Purpose | Release |
| --- | --- | --- | --- |
| `GET` | `/api/skills` | Browse available listings | MVP |
| `POST` | `/api/skills` | Create a listing | MVP |
| `GET` | `/api/skills/{skill_id}` | Retrieve a listing | MVP |
| `PATCH` | `/api/skills/{skill_id}` | Update an owned listing | MVP |
| `DELETE` | `/api/skills/{skill_id}` | Delete an owned listing | MVP |
| `POST` | `/api/session-requests` | Create a session request | MVP |
| `GET` | `/api/session-requests` | List requests available to the caller | MVP |
| `PATCH` | `/api/session-requests/{request_id}` | Respond to or update a request | MVP |
| `POST` | `/api/auth/register` | Register an account | Beta |
| `POST` | `/api/auth/token` | Authenticate and obtain credentials | Beta |
| `GET` | `/api/users/me` | Retrieve the signed-in user's profile | Beta |

The API shall use standard HTTP status codes: `2xx` for successful operations, `4xx` for invalid input or unauthorized/forbidden/not-found resources, and `5xx` for unexpected server failures. Error responses shall not include secrets or stack traces.

### 5.3 Database interface

The database engine and persistence library are design decisions still to be made. Once selected, the API shall persist data across application restarts and enforce referential integrity for related records. (MVP)

## 6. Data requirements

The initial logical entities are:

- **SkillListing:** identifier, owner, title, description, category, availability/status, created timestamp, updated timestamp.
- **SessionRequest:** identifier, listing, learner, teacher/listing owner, message or learning goal, status, created timestamp, updated timestamp.
- **User (Beta):** identifier, email, password hash, display name, role, profile fields, created timestamp.
- **Category:** identifier, name, description.
- **Report (Beta):** identifier, reporter, listing, reason, status, created timestamp, review metadata.

The final field definitions, deletion behavior, and indexes must be established alongside the database selection and migrations.

## 7. Non-functional requirements

| ID | Release | Requirement |
| --- | --- | --- |
| SRS-NF01 | MVP | Backend input validation shall be performed independently of browser-side validation. |
| SRS-NF02 | MVP | The local development setup shall run the API and frontend with documented commands. |
| SRS-NF03 | MVP | The API shall return deterministic JSON response shapes for documented operations. |
| SRS-NF04 | Beta | Protected actions shall be authorized on every backend request; frontend checks alone shall never grant access. |
| SRS-NF05 | Beta | Passwords shall be stored only as salted password hashes produced by a maintained hashing library. |
| SRS-NF06 | Beta | Authentication secrets and deployment configuration shall come from environment variables or a managed secret store. |
| SRS-NF07 | Beta | The application shall validate authentication and authorization failures without disclosing whether sensitive credentials are correct. |
| SRS-NF08 | Beta | Production deployment shall use HTTPS and secure cookie/token handling appropriate to the selected authentication design. |
| SRS-NF09 | Beta | Tests shall cover API validation, listing ownership, request participation, and role/scope authorization. |

## 8. Business rules

1. A member may teach and learn; role does not limit them to one side of an exchange.
2. A session request must reference an existing, available listing.
3. The listing owner cannot respond to a request as the learner.
4. Only the listing owner may accept or decline that listing's session request.
5. Members may edit or delete only their own listings; Beta administrators may manage platform listings.
6. A listing hidden by a moderator is not available for new session requests.
7. The backend is the source of truth for identity, ownership, status transitions, and permission checks.

## 9. Acceptance and verification

- **MVP acceptance:** Exercise listing browse/detail/create/update/delete and session-request create/respond/status flows against a locally running API; verify invalid data and ownership violations are rejected.
- **Beta acceptance:** Exercise registration/sign-in, profile access, and role-specific endpoints; verify member, moderator, and administrator permissions with automated API tests, including denied requests.
- **Documentation acceptance:** Keep route, field, and release descriptions aligned with the implemented API as the project evolves.
