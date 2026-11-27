# Independent University, Bangladesh
## CSE309 Web Application & Internet

# Final Project Submission Report

**Submitted by:**<br>
Name: Saker Ahmed Shimul<br>
Student ID: 2230957<br>
Section: 06

**Project Title:** SkillSwap<br>
**Vercel URL:** [https://2230957-s6-skillswap.vercel.app/](https://2230957-s6-skillswap.vercel.app/)<br>
**GitHub Repository:** [https://github.com/Saker001/2230957-S6-SkillSwap](https://github.com/Saker001/2230957-S6-SkillSwap)

**Submitted To:**<br>
Sayef Reyadh<br>
Adjunct Lecturer<br>
Department of Computer Science & Engineering<br>
Independent University, Bangladesh

**Semester:** Autumn 2026
**Date of Submission:** 27 November 2026

---

# SkillSwap — Project Details

**API documentation:** [OpenAPI UI](https://2230957-s6-skillswap.vercel.app/api/docs) · [OpenAPI schema](https://2230957-s6-skillswap.vercel.app/api/openapi.json)

## 1. Executive summary

SkillSwap is a peer-learning web application for publishing skills, finding learning opportunities, and requesting sessions. The project combines a React and TypeScript browser interface with a FastAPI REST service and SQLModel persistence. The current implementation includes account signup and login, member profiles, owner- and participant-scoped resource access, skill groups with per-member capabilities, and an administrator workspace for account/content management, activity review, and CSV export.

The local source and test suite demonstrate the implemented behavior described in this report. The public deployment was reachable during the latest endpoint check: the frontend root and API health, documentation, and schema routes returned HTTP 200. This is evidence of route availability only—not a successful sign-in, persistent database, or end-to-end acceptance run. The deployed authenticated flows and demo data have not been verified for this report, so deployment readiness remains conditional.

## 2. Product requirements and delivered scope

### Purpose and users

The product addresses the gap between people who want to teach a skill and people who want to learn it. A member can take either role. The intended workflow is to publish a skill listing, discover a suitable listing, send a session request, and let the listing owner respond.

| User | Current product use |
|---|---|
| Signed-out visitor | Create an account or sign in |
| Member (`user`) | Browse listings, manage their own listings, create requests, and access requests where they are a learner or listing owner |
| Group owner/member | Share group listings; the owner manages membership and grants create, edit, and assign capabilities |
| Administrator (`admin`) | Manage accounts, listings, groups, and categories; inspect security/activity data and export filtered records |

### Scope delivered

The core listing and session-request workflows are implemented with server-side validation and authorization. Accounts use profiles and revocable sessions. The group feature adds membership and independently controlled `can_create`, `can_edit`, and `can_assign` capabilities. The administrator dashboard supports user search and details, role changes, bans and unbans, session revocation, content and category management, activity filtering, failed-login insights, and filtered CSV downloads.

The implemented account roles are **user** and **admin**. There is no separate moderator role or moderator-report workflow; moderator functionality in early planning documents is not part of the delivered role model. Payments, chat, video calls, calendar integrations, and mobile applications are outside the current release.

### Requirements traceability

| Product requirement | Implementation evidence | Verification status |
|---|---|---|
| Find and maintain skill listings | `/api/skills` CRUD and React discovery/teaching views; ownership is derived from the authenticated account | Implemented; local API tests cover CRUD and cross-owner denial |
| Coordinate learning requests | `/api/session-requests` CRUD; learners edit their message and listing owners set status | Implemented; local tests cover participants and status rules |
| Establish secure member accounts | Signup/login/logout, profile and password changes, refresh rotation, session listing/revocation | Implemented; local authentication tests pass |
| Support shared group learning | Group creation, membership, capability assignment, and group listings | Implemented; local tests cover owner-only controls and capabilities |
| Provide administration and accountability | Protected admin endpoints, audit records, security summaries, and CSV exports | Implemented; local tests cover admin access/safeguards, filters, and exports |
| Operate the hosted application | Vercel frontend/backend routing and public endpoint availability | Partially verified; live authenticated workflows, persistence, and sample-data state remain unverified |

## 3. Software requirements and permissions

The SRS calls for validated inputs, authenticated identity, least-privilege access, and useful failure responses. Signup validates and normalizes email, trims display names, and requires a password between 12 and 128 characters. Listing and request fields have bounded lengths; request status is limited to `pending`, `accepted`, or `declined`. Public signup assigns the ordinary `user` role on the server and cannot create an administrator.

| Operation | Signed out | Member | Group member | Admin |
|---|---:|---|---|---|
| Read member skill listings | No | Yes | Yes | Yes |
| Create a skill listing | No | Yes | If group grants `can_create` | Yes |
| Edit/delete an ordinary listing | No | Own listing only | Not applicable | Own listing through member routes; platform-wide management through admin routes |
| Create/read a session request | No | Create; read as learner or listing owner | Same member rules | Same member rules; admin user detail exposes associated records |
| Change a request | No | Learner changes message; listing owner changes status | Same member rules | Same member rules |
| Manage group membership/settings | No | Group owner only | No | Admin group management endpoints |
| Review accounts/content and export data | No | No | No | Yes |

Authorization is enforced by FastAPI dependencies and resource-level checks, not just by hiding interface controls. A resource outside the caller's ownership or participation scope is generally returned as not found, reducing information disclosure. The backend has no separate moderator scope.

## 4. Technical design

### Architecture and data

The browser UI is built with React, TypeScript, and Vite. Its typed API client calls same-origin `/api/...` routes and keeps the short-lived access token in memory. FastAPI validates requests, resolves identity and permissions, applies resource rules, and uses SQLModel/SQLAlchemy for persistence. SQLite is the local default; a PostgreSQL connection is selected through `DATABASE_URL`. Vercel rewrites `/api/*` to the backend service and other paths to the frontend.

Principal records include users and refresh sessions, skill listings and session requests, skill groups and memberships, group-to-listing assignments, categories, and audit events. Nullable ownership fields preserve older records without assigning them to a new account. Those unowned legacy listings are not exposed in member discovery. Database setup creates current tables and applies idempotent migrations for ownership, user-ban fields, and audit client metadata.

```text
backend/
  main.py                 FastAPI app, skills, requests, groups, health route
  auth.py                 User/session models, credentials, auth/profile routes
  authorization.py        Role and group-capability dependencies
  permissions.py          Role-to-permission mapping
  admin.py                Administrator routes, audit views, CSV exports
  audit.py                Audit event storage
  database.py             Database engine and request-scoped sessions
  migrations.py           Compatibility migrations
  models.py               Skill, request, group, and membership models
  seed_demo.py            Guarded demo-data provisioner
  tests/                  API and seed-provisioning tests
frontend/src/
  App.tsx                 Member workflows and navigation
  AdminDashboard.tsx      Administrator interface
  api.ts                  Typed API client and session handling
docs/
  01-prd.md               Product requirements
  02-srs.md               Software requirements and acceptance criteria
  03-tdd.md               Technical design
  FINAL_REPORT.md         Final project submission report
```

### API surface

Representative routes include `POST /api/auth/signup`, `POST /api/auth/login`, `POST /api/auth/refresh`, `POST /api/auth/logout`; `GET/PATCH /api/users/me`; `GET/POST /api/skills` and `PATCH/DELETE /api/skills/{skill_id}`; session-request routes under `/api/session-requests`; group routes under `/api/groups`; and administrator routes under `/api/admin`. FastAPI publishes the schema at `/api/openapi.json` and interactive docs at `/api/docs`. The API’s health check is `/api/health`.

## 5. Security, privacy, and limitations

- **Password storage:** the password is first keyed with an HMAC-SHA256 pepper from the server environment, then hashed with Argon2id. Password hashes are not included in public response schemas.
- **Access credentials:** signed HS256 JWTs expire after 15 minutes and contain `iss`, `sub`, `role`, `sid`, `iat`, `exp`, and `jti` claims. For each protected request, the backend resolves the user and refresh-session record and rejects inactive, banned, revoked, expired, or mismatched sessions.
- **Refresh sessions:** random refresh values are stored as SHA-256 hashes, rotated on refresh, and delivered through an HttpOnly, SameSite=Lax cookie scoped to `/api`; the cookie is Secure on Vercel. The session lifetime is 14 days. Logout, password changes, and session revocation invalidate database sessions.
- **Abuse and administration safeguards:** login failures use a generic credential error and trigger a 15-minute account lock after five failed attempts. Admin routes require `admin:manage`. The service prevents self-role changes and self-bans, blocks banning administrators, and protects the last active administrator from demotion. Banning an account revokes its sessions.
- **Audit and exports:** events record relevant authentication, account, content, and export actions with available client IP and user-agent metadata. Export columns are explicitly selected; password hashes and authentication tokens are not exported. CSV output also guards spreadsheet-formula values.
- **Secret and database configuration:** production requires stable `JWT_SECRET_KEY`, `PASSWORD_PEPPER`, and persistent PostgreSQL `DATABASE_URL` values configured outside source control. The Vercel backend refuses to start without required configuration rather than silently selecting local ephemeral SQLite.

These controls reduce common account and authorization risks, but do not constitute a penetration test or a formal security certification. The application has no multi-factor authentication or separate moderator role. Production data backup, retention, privacy notice, and IP/user-agent retention policy should be confirmed by the deployment owner. Do not put live credentials or connection strings in this report, screenshots, or source control.

## 6. Deployment and current verification

**Deployment links:** [application](https://2230957-s6-skillswap.vercel.app/) · [API docs](https://2230957-s6-skillswap.vercel.app/api/docs) · [OpenAPI JSON](https://2230957-s6-skillswap.vercel.app/api/openapi.json)

The latest public checks on 27 November 2026 returned HTTP 200 for `GET /`, `GET /api/health`, `GET /api/docs`, and `GET /api/openapi.json`. These responses confirm that the routes are reachable; they do not prove that account flows, database writes, cross-account isolation, or administration work in the live environment. Those authenticated acceptance checks and production database persistence remain **not verified**.

Demo account and group state is also **not verified**. The repository provides `backend/seed_demo.py` to prepare two administrator accounts, three member accounts, a mixed-capability group, and a sample listing. It is PostgreSQL-only, defaults to dry-run, requires an explicit confirmation before writes, and refuses conflicting existing accounts or permissions rather than changing them. No account credentials are reproduced here. Only run it from a trusted operator environment after reviewing its dry-run and verifying the target database.

| Deployment check | Current report finding |
|---|---|
| Public application root | HTTP 200 |
| Health, docs, and OpenAPI routes | HTTP 200 each |
| Signup, login, refresh, logout on production | Not verified |
| Authenticated CRUD, permissions, and admin operations on production | Not verified |
| Persistent database connection and data survival | Not verified |
| Demo accounts, group, and sample listing | Not verified |
| Current authenticated screenshots / evidence package | Not included |

## 7. Testing and results

The following checks were run against the current repository:

| Check | Command | Result |
|---|---|---|
| Backend API and seed tests | From `backend/`: `python -m unittest discover -s tests` | **26 tests passed** |
| Frontend type-check and production bundle | From `frontend/`: `npm run build` | **Passed** (`tsc` and Vite production build) |
| Whitespace / patch validation | `git diff --check` | **Passed** |

The backend tests use a temporary SQLite database and cover resource CRUD, ownership and participant checks, group capabilities, auth/token rejection and rotation, lockout, password changes, admin safeguards, audit/export behavior, migration compatibility, persistence across app restart, and safe seed behavior. They are local automated tests, not evidence that the same configuration or data is present on Vercel.

## 8. Submission evidence and project management

No current authenticated screenshots or narrated demo video are included in this Markdown report. The existing `assets/live-deployment-blocked.png` captured an earlier HTTP 500 condition and is stale; it must not be used as evidence of the current deployment or successful authenticated behavior. The earlier root-level PDF was removed from the latest `main` branch and has not been regenerated; submit the Markdown report unless an updated PDF is produced from verified content.

The remaining evidence work belongs to the student/instructor submission process: verify the deployed flows with authorized demo accounts, capture genuine screenshots of user and admin paths (including a denied action), record the required narrated video, and update any PDF only after those checks. Do not fabricate screenshots, account state, or test outcomes.

### AI assistance disclosure

GitHub Copilot was used as an AI-assisted tool for implementation and review support. The student remains responsible for reviewing the source, independently checking the behavior, understanding and being able to explain the design, and following the course’s rules for AI-assisted work. This report does not claim that the project was produced without AI assistance or substitute for the student’s own demonstration.

## 9. Conclusion and next verification steps

SkillSwap has a functioning full-stack implementation in the repository with authentication, ownership-aware learning workflows, group capabilities, and protected administrative features. Automated backend tests and the frontend production build pass. Public endpoint checks are healthy, but production user journeys, persistent storage, sample-data provisioning, and submission evidence are still outstanding. The final deployment claim should be limited to what is verified after those checks.

## 10. References

1. SkillSwap [Product Requirements Document](01-prd.md).
2. SkillSwap [Software Requirements Specification](02-srs.md).
3. SkillSwap [Technical Design Document](03-tdd.md).
4. SkillSwap source repository: [Saker001/2230957-S6-SkillSwap](https://github.com/Saker001/2230957-S6-SkillSwap).
5. Deployed application and API references linked in Section 6.
