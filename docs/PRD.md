# Product Requirements Document (PRD)

## 1. Document purpose

This document defines the product scope, users, and release requirements for SkillSwap. It is a planning document: the repository currently contains a React and TypeScript frontend starter and a FastAPI backend starter, not the SkillSwap features described here.

## 2. Product summary

SkillSwap helps people learn from one another by letting members offer skills they can teach, find skills they want to learn, and coordinate peer-to-peer learning sessions.

### Problem

People often have useful skills to share and subjects they want to learn, but lack a simple way to discover a suitable peer and arrange a learning session.

### Product goals

- Make it easy to discover skills offered by other members.
- Let members publish and maintain their own skill listings.
- Provide a simple request-and-response workflow for learning sessions.
- Demonstrate a working full-stack application using React, TypeScript, FastAPI, and REST APIs.
- Add authentication and role-based access control in the Beta release.

## 3. Users and roles

| User | Needs |
| --- | --- |
| Visitor (MVP) | Browse public skill listings and view listing details. |
| Member (MVP/Beta) | Offer skills, find skills to learn, manage their listings, and create or respond to session requests. A member may teach and learn. |
| Moderator (Beta) | Review reports and hide inappropriate listings. |
| Administrator (Beta) | Manage users, categories, and listings across the platform. |

In the MVP, authentication is out of scope. Ownership-sensitive operations may use a clearly identified development owner, but must not be presented as production-secure. Beta adds real accounts and server-enforced permissions.

## 4. Release scope

### MVP — Mid-term demo

The MVP focuses on the core learning exchange and local demonstration:

- Browse and view skill listings.
- Create, update, and delete a member's own listings.
- Send a session request for a listing.
- Let the listing owner accept or decline a request.
- Show request status to the involved participants.
- Run the frontend and backend locally.

### Beta — Final demo

The Beta builds on the MVP with secure accounts and deployment:

- Register, sign in, and sign out.
- Provide a member profile dashboard.
- Enforce member, moderator, and administrator permissions on the backend.
- Restrict operations with authorization scopes.
- Let moderators review reports and hide inappropriate listings.
- Let administrators manage users, categories, and listings.
- Deploy the application.

## 5. Functional requirements

| ID | Release | Requirement |
| --- | --- | --- |
| PRD-F01 | MVP | Visitors can browse available skill listings and view listing details. |
| PRD-F02 | MVP | A member can create a listing describing a skill they can teach. |
| PRD-F03 | MVP | A member can edit or delete only their own listings. |
| PRD-F04 | MVP | A learner can request a session for an available listing. |
| PRD-F05 | MVP | A listing owner can accept or decline an incoming request. |
| PRD-F06 | MVP | Both participants can view the current status of their session requests. |
| PRD-F07 | Beta | A user can register, authenticate, and access their own profile. |
| PRD-F08 | Beta | The backend authorizes operations according to member, moderator, or administrator role and required permission scope. |
| PRD-F09 | Beta | A moderator can review reports and hide inappropriate listings. |
| PRD-F10 | Beta | An administrator can manage users, categories, and listings across the platform. |
| PRD-F11 | Beta | Members can view and update appropriate profile information in a dashboard. |

## 6. Non-functional requirements

| ID | Release | Requirement |
| --- | --- | --- |
| PRD-NF01 | MVP | The application can be started locally with separate frontend and backend development servers. |
| PRD-NF02 | MVP | API requests use JSON and return appropriate HTTP status codes for success and validation errors. |
| PRD-NF03 | MVP | User-provided values are validated by the backend before persistence. |
| PRD-NF04 | Beta | Authorization is enforced by the API and cannot be bypassed by changing frontend state or calling endpoints directly. |
| PRD-NF05 | Beta | Passwords are stored using a recognized password-hashing algorithm; plaintext passwords are never stored. |
| PRD-NF06 | Beta | Secrets and deployment-specific settings are supplied through environment configuration, not committed to source control. |
| PRD-NF07 | Beta | Errors do not expose passwords, tokens, secret configuration, or unnecessary personal data. |

## 7. Success criteria

### MVP demo

- A user can browse listings, create and manage a listing, submit a session request, and see a response and request status.
- The frontend communicates with the FastAPI backend through documented REST endpoints.
- The complete demo can be run locally using the repository instructions.

### Beta demo

- A user can register and sign in, and access a profile dashboard.
- Attempts to perform an unauthorized action are rejected by the backend.
- Moderator and administrator capabilities are limited to their defined responsibilities.
- The deployed application works without exposing credentials or relying on frontend-only authorization.

## 8. Out of scope

To keep the course project achievable, the initial releases do not include payments, video conferencing, a real-time chat system, mobile applications, calendar synchronization, or advanced recommendation algorithms.

## 9. Assumptions and risks

- Members are allowed to both teach and learn.
- Session coordination initially consists of a request and an accept/decline response; scheduling and communication can be handled outside the app.
- The database has not yet been selected. Persistence and deployment requirements should guide that decision before feature implementation.
- The MVP has no production authentication, so ownership enforcement for a classroom demo must not be represented as secure account-based access control.
