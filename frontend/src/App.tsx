import { type FormEvent, useCallback, useEffect, useState } from "react"
import { api, type SessionRequest, type SkillListing, type User, type UserSession } from "./api"

const emptySkill = {
  teacher_name: "",
  title: "",
  description: "",
  category: "",
}

const emptyRequest = {
  skill_listing_id: "",
  message: "",
  status: "pending" as SessionRequest["status"],
}

const emptyAuthForm = {
  email: "",
  display_name: "",
  password: "",
}

const emptyPasswordForm = {
  current_password: "",
  new_password: "",
}

export default function App() {
  const [authStatus, setAuthStatus] = useState<"restoring" | "guest" | "authenticated">("restoring")
  const [user, setUser] = useState<User | null>(null)
  const [authMode, setAuthMode] = useState<"login" | "signup">("login")
  const [authForm, setAuthForm] = useState(emptyAuthForm)
  const [profileName, setProfileName] = useState("")
  const [passwordForm, setPasswordForm] = useState(emptyPasswordForm)
  const [userSessions, setUserSessions] = useState<UserSession[]>([])
  const [skills, setSkills] = useState<SkillListing[]>([])
  const [sessionRequests, setSessionRequests] = useState<SessionRequest[]>([])
  const [skillForm, setSkillForm] = useState(emptySkill)
  const [requestForm, setRequestForm] = useState(emptyRequest)
  const [editingSkillId, setEditingSkillId] = useState<number | null>(null)
  const [editingRequestId, setEditingRequestId] = useState<number | null>(null)
  const [selectedSkill, setSelectedSkill] = useState<SkillListing | null>(null)
  const [selectedRequest, setSelectedRequest] = useState<SessionRequest | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const editingRequest = sessionRequests.find((request) => request.id === editingRequestId)
  const editingRequestIsOwner =
    editingRequest !== undefined &&
    skills.some(
      (skill) =>
        skill.id === editingRequest.skill_listing_id && skill.owner_id === user?.id,
    )
  const editingRequestIsLearner = editingRequest?.learner_id === user?.id

  useEffect(() => {
    let active = true
    api.restoreSession()
      .then((restoredUser) => {
        if (!active) return
        setUser(restoredUser)
        setProfileName(restoredUser?.display_name ?? "")
        setAuthStatus(restoredUser ? "authenticated" : "guest")
      })
      .catch((err: unknown) => {
        if (!active) return
        setError(err instanceof Error ? err.message : "Could not restore your session.")
        setAuthStatus("guest")
      })
    return () => {
      active = false
    }
  }, [])

  const refreshData = useCallback(async () => {
    const [skillRows, requestRows, sessions] = await Promise.all([
      api.listSkills(),
      api.listSessionRequests(),
      api.listSessions(),
    ])
    setSkills(skillRows)
    setSessionRequests(requestRows)
    setUserSessions(sessions)
  }, [])

  useEffect(() => {
    if (authStatus !== "authenticated") return
    setLoading(true)
    refreshData()
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Could not load SkillSwap data."),
      )
      .finally(() => setLoading(false))
  }, [authStatus, refreshData])

  async function handleAuthSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError("")
    setNotice("")
    try {
      if (authMode === "signup") {
        await api.signUp(authForm)
      }
      const signedInUser = await api.logIn({
        email: authForm.email,
        password: authForm.password,
      })
      setUser(signedInUser)
      setProfileName(signedInUser.display_name)
      setAuthStatus("authenticated")
      setAuthForm(emptyAuthForm)
      setNotice(authMode === "signup" ? "Account created and signed in." : "Signed in successfully.")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in.")
    }
  }

  async function handleSignOut() {
    setError("")
    try {
      await api.logOut()
      setUser(null)
      setUserSessions([])
      setAuthStatus("guest")
      setNotice("You have signed out.")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign out.")
    }
  }

  async function handleProfileSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError("")
    setNotice("")
    try {
      const updatedUser = await api.updateProfile(profileName)
      setUser(updatedUser)
      setProfileName(updatedUser.display_name)
      setNotice("Profile updated.")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update your profile.")
    }
  }

  async function handlePasswordSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError("")
    setNotice("")
    try {
      await api.changePassword(passwordForm.current_password, passwordForm.new_password)
      setPasswordForm(emptyPasswordForm)
      setUser(null)
      setUserSessions([])
      setAuthStatus("guest")
      setNotice("Password changed. Sign in again with your new password.")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change your password.")
    }
  }

  async function handleRevokeSession(sessionId: string) {
    setError("")
    setNotice("")
    try {
      const currentSession = api.isCurrentSession(sessionId)
      await api.revokeSession(sessionId)
      if (currentSession) {
        await api.logOut()
        setUser(null)
        setUserSessions([])
        setAuthStatus("guest")
        setNotice("This session was revoked. Sign in again to continue.")
        return
      }
      setUserSessions((sessions) =>
        sessions.map((session) =>
          session.id === sessionId ? { ...session, revoked_at: new Date().toISOString() } : session,
        ),
      )
      setNotice("Session revoked.")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not revoke that session.")
    }
  }

  async function handleSkillSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError("")
    setNotice("")
    try {
      if (editingSkillId === null) {
        await api.createSkill(skillForm)
        setNotice("Skill listing created.")
      } else {
        await api.updateSkill(editingSkillId, skillForm)
        setNotice("Skill listing updated.")
      }
      setSkillForm(emptySkill)
      setEditingSkillId(null)
      setSelectedSkill(null)
      await refreshData()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the skill listing.")
    }
  }

  async function handleRequestSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError("")
    setNotice("")
    try {
      const data = {
        skill_listing_id: Number(requestForm.skill_listing_id),
        message: requestForm.message,
      }
      if (editingRequestId === null) {
        await api.createSessionRequest(data)
        setNotice("Session request created.")
      } else if (editingRequestIsOwner) {
        await api.updateSessionRequest(editingRequestId, {
          status: requestForm.status,
        })
        setNotice("Session request status updated.")
      } else {
        await api.updateSessionRequest(editingRequestId, {
          message: requestForm.message,
        })
        setNotice("Session request updated.")
      }
      setRequestForm(emptyRequest)
      setEditingRequestId(null)
      setSelectedRequest(null)
      await refreshData()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the session request.")
    }
  }

  async function showSkill(id: number) {
    setError("")
    try {
      setSelectedSkill(await api.getSkill(id))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the skill listing.")
    }
  }

  async function showRequest(id: number) {
    setError("")
    try {
      setSelectedRequest(await api.getSessionRequest(id))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the session request.")
    }
  }

  function editSkill(skill: SkillListing) {
    setEditingSkillId(skill.id)
    setSkillForm({
      teacher_name: skill.teacher_name,
      title: skill.title,
      description: skill.description,
      category: skill.category,
    })
  }

  function editRequest(request: SessionRequest) {
    setEditingRequestId(request.id)
    setRequestForm({
      skill_listing_id: String(request.skill_listing_id),
      message: request.message,
      status: request.status,
    })
  }

  async function removeSkill(id: number) {
    if (!window.confirm("Delete this skill listing and its related session requests?")) return
    setError("")
    setNotice("")
    try {
      await api.deleteSkill(id)
      if (selectedSkill?.id === id) setSelectedSkill(null)
      if (selectedRequest?.skill_listing_id === id) setSelectedRequest(null)
      if (Number(requestForm.skill_listing_id) === id) {
        setEditingRequestId(null)
        setRequestForm(emptyRequest)
      }
      setNotice("Skill listing and related requests deleted.")
      await refreshData()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete the skill listing.")
    }
  }

  async function removeRequest(id: number) {
    if (!window.confirm("Delete this session request?")) return
    setError("")
    setNotice("")
    try {
      await api.deleteSessionRequest(id)
      if (selectedRequest?.id === id) setSelectedRequest(null)
      setNotice("Session request deleted.")
      await refreshData()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete the session request.")
    }
  }

  if (authStatus === "restoring") {
    return (
      <main className="app-shell">
        <p className="muted" role="status">Restoring your SkillSwap session...</p>
      </main>
    )
  }

  if (!user) {
    return (
      <main className="app-shell">
        <header className="hero">
          <p className="eyebrow">Learn from each other</p>
          <h1>SkillSwap</h1>
          <p className="intro">Sign in or create an account to continue.</p>
        </header>
        {error && <p className="alert error" role="alert">{error}</p>}
        {notice && <p className="alert success" role="status">{notice}</p>}
        <section className="panel auth-panel" aria-labelledby="auth-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Your account</p>
              <h2 id="auth-heading">{authMode === "login" ? "Sign in" : "Create account"}</h2>
            </div>
            <button
              className="secondary"
              type="button"
              onClick={() => {
                setAuthMode(authMode === "login" ? "signup" : "login")
                setError("")
              }}
            >
              {authMode === "login" ? "Create account" : "I already have an account"}
            </button>
          </div>
          <form className="form-card" onSubmit={handleAuthSubmit}>
            {authMode === "signup" && (
              <label>
                Display name
                <input
                  required
                  minLength={1}
                  maxLength={80}
                  autoComplete="name"
                  value={authForm.display_name}
                  onChange={(event) =>
                    setAuthForm({ ...authForm, display_name: event.target.value })
                  }
                />
              </label>
            )}
            <label>
              Email
              <input
                required
                type="email"
                autoComplete="email"
                value={authForm.email}
                onChange={(event) => setAuthForm({ ...authForm, email: event.target.value })}
              />
            </label>
            <label>
              Password
              <input
                required
                type="password"
                minLength={authMode === "signup" ? 12 : 1}
                maxLength={128}
                autoComplete={authMode === "login" ? "current-password" : "new-password"}
                value={authForm.password}
                onChange={(event) => setAuthForm({ ...authForm, password: event.target.value })}
              />
              {authMode === "signup" && (
                <span className="muted">Use at least 12 characters.</span>
              )}
            </label>
            <button className="primary" type="submit">
              {authMode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>
        </section>
      </main>
    )
  }

  return (
    <main className="app-shell">
      <header className="hero">
        <p className="eyebrow">Learn from each other</p>
        <h1>SkillSwap</h1>
        <p className="intro">
          Share what you know, discover a skill to learn, and arrange a session.
        </p>
        <div className="account-toolbar">
          <span>Signed in as <strong>{user.display_name}</strong> ({user.role})</span>
          <button className="secondary" type="button" onClick={handleSignOut}>Sign out</button>
        </div>
      </header>

      {error && <p className="alert error" role="alert">{error}</p>}
      {notice && <p className="alert success" role="status">{notice}</p>}
      {loading && <p className="muted" role="status">Loading SkillSwap...</p>}

      <section className="panel" aria-labelledby="skills-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Explore and share</p>
            <h2 id="skills-heading">Skill listings</h2>
          </div>
          <span className="count">{skills.length} listings</span>
        </div>

        <div className="content-grid">
          <form className="form-card" onSubmit={handleSkillSubmit}>
            <h3>{editingSkillId === null ? "Offer a skill" : "Edit your listing"}</h3>
            <label>
              Your name
              <input
                required
                maxLength={80}
                value={skillForm.teacher_name}
                onChange={(event) =>
                  setSkillForm({ ...skillForm, teacher_name: event.target.value })
                }
                placeholder="e.g. Alex"
              />
            </label>
            <label>
              Skill title
              <input
                required
                maxLength={100}
                value={skillForm.title}
                onChange={(event) => setSkillForm({ ...skillForm, title: event.target.value })}
                placeholder="e.g. Beginner guitar"
              />
            </label>
            <label>
              Category
              <input
                required
                maxLength={60}
                value={skillForm.category}
                onChange={(event) =>
                  setSkillForm({ ...skillForm, category: event.target.value })
                }
                placeholder="e.g. Music"
              />
            </label>
            <label>
              What can you teach?
              <textarea
                required
                maxLength={1000}
                rows={4}
                value={skillForm.description}
                onChange={(event) =>
                  setSkillForm({ ...skillForm, description: event.target.value })
                }
                placeholder="Describe what learners can expect."
              />
            </label>
            <div className="form-actions">
              <button className="primary" type="submit">
                {editingSkillId === null ? "Create listing" : "Save changes"}
              </button>
              {editingSkillId !== null && (
                <button
                  type="button"
                  className="secondary"
                  onClick={() => {
                    setEditingSkillId(null)
                    setSkillForm(emptySkill)
                  }}
                >
                  Cancel
                </button>
              )}
            </div>
          </form>

          <div className="listing-column">
            {skills.length === 0 && !loading ? (
              <div className="empty-state">No skills yet. Add the first listing.</div>
            ) : (
              skills.map((skill) => (
                <article className="item-card" key={skill.id}>
                  <div className="item-topline">
                    <span className="tag">{skill.category}</span>
                    <span className="muted">#{skill.id}</span>
                  </div>
                  <h3>{skill.title}</h3>
                  <p className="muted">Taught by {skill.teacher_name}</p>
                  <p className="item-description">{skill.description}</p>
                  <div className="item-actions">
                    <button className="secondary" onClick={() => showSkill(skill.id)}>Details</button>
                    {skill.owner_id === user.id && (
                      <>
                        <button className="secondary" onClick={() => editSkill(skill)}>Edit</button>
                        <button className="danger" onClick={() => removeSkill(skill.id)}>Delete</button>
                      </>
                    )}
                  </div>
                </article>
              ))
            )}
          </div>
        </div>
        {selectedSkill && (
          <div className="detail-card">
            <div className="section-heading">
              <h3>Listing details</h3>
              <button className="secondary" onClick={() => setSelectedSkill(null)}>Close</button>
            </div>
            <p><strong>{selectedSkill.title}</strong> · {selectedSkill.category}</p>
            <p>{selectedSkill.description}</p>
            <p className="muted">Teacher: {selectedSkill.teacher_name} · Listing #{selectedSkill.id}</p>
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="requests-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Arrange a learning session</p>
            <h2 id="requests-heading">Session requests</h2>
          </div>
          <span className="count">{sessionRequests.length} requests</span>
        </div>
        <div className="content-grid">
          <form className="form-card" onSubmit={handleRequestSubmit}>
            <h3>{editingRequestId === null ? "Request a session" : "Manage session request"}</h3>
            {editingRequestId === null && <label>
              Skill
              <select
                required
                value={requestForm.skill_listing_id}
                onChange={(event) =>
                  setRequestForm({ ...requestForm, skill_listing_id: event.target.value })
                }
              >
                <option value="">Choose a listing</option>
                {skills.filter((skill) => skill.owner_id !== user.id).map((skill) => (
                  <option value={skill.id} key={skill.id}>
                    {skill.title} — {skill.teacher_name}
                  </option>
                ))}
              </select>
            </label>}
            {editingRequestId === null && skills.every((skill) => skill.owner_id === user.id) && (
              <p className="muted">No other members' listings are available to request yet.</p>
            )}
            <label>
              What would you like to learn?
              <textarea
                required
                maxLength={1000}
                rows={4}
                value={requestForm.message}
                disabled={editingRequestId !== null && !editingRequestIsLearner}
                onChange={(event) =>
                  setRequestForm({ ...requestForm, message: event.target.value })
                }
                placeholder="Introduce yourself and share your learning goal."
              />
            </label>
            {editingRequestId !== null && editingRequestIsOwner && (
              <label>
                Request status
                <select
                  value={requestForm.status}
                  onChange={(event) =>
                    setRequestForm({
                      ...requestForm,
                      status: event.target.value as SessionRequest["status"],
                    })
                  }
                >
                  <option value="pending">Pending</option>
                  <option value="accepted">Accepted</option>
                  <option value="declined">Declined</option>
                </select>
              </label>
            )}
            <div className="form-actions">
              <button
                className="primary"
                type="submit"
                disabled={
                  editingRequestId === null
                    ? skills.every((skill) => skill.owner_id === user.id)
                    : !editingRequestIsOwner && !editingRequestIsLearner
                }
              >
                {editingRequestId === null
                  ? "Send request"
                  : editingRequestIsOwner
                    ? "Update status"
                    : "Save message"}
              </button>
              {editingRequestId !== null && (
                <button
                  type="button"
                  className="secondary"
                  onClick={() => {
                    setEditingRequestId(null)
                    setRequestForm(emptyRequest)
                  }}
                >
                  Cancel
                </button>
              )}
            </div>
            {editingRequestId === null && skills.length === 0 && (
              <p className="muted">No members' listings are available to request yet.</p>
            )}
          </form>

          <div className="listing-column">
            {sessionRequests.length === 0 && !loading ? (
              <div className="empty-state">No session requests yet.</div>
            ) : (
              sessionRequests.map((request) => (
                <article className="item-card" key={request.id}>
                  <div className="item-topline">
                    <span className={`tag status-${request.status}`}>{request.status}</span>
                    <span className="muted">#{request.id}</span>
                  </div>
                  <h3>{skills.find((skill) => skill.id === request.skill_listing_id)?.title ?? "Skill listing"}</h3>
                  <p className="muted">Requested by {request.learner_name}</p>
                  <p className="item-description">{request.message}</p>
                  <div className="item-actions">
                    <button className="secondary" onClick={() => showRequest(request.id)}>Details</button>
                    {(request.learner_id === user.id ||
                      skills.some(
                        (skill) =>
                          skill.id === request.skill_listing_id && skill.owner_id === user.id,
                      )) && (
                      <>
                        <button className="secondary" onClick={() => editRequest(request)}>
                          {request.learner_id === user.id ? "Edit message" : "Update status"}
                        </button>
                        <button className="danger" onClick={() => removeRequest(request.id)}>
                          Delete
                        </button>
                      </>
                    )}
                  </div>
                </article>
              ))
            )}
          </div>
        </div>
        {selectedRequest && (
          <div className="detail-card">
            <div className="section-heading">
              <h3>Request details</h3>
              <button className="secondary" onClick={() => setSelectedRequest(null)}>Close</button>
            </div>
            <p><strong>Request #{selectedRequest.id}</strong> · {selectedRequest.status}</p>
            <p>Skill listing: {skills.find((skill) => skill.id === selectedRequest.skill_listing_id)?.title ?? `#${selectedRequest.skill_listing_id}`}</p>
            <p>Requested by {selectedRequest.learner_name}</p>
            <p>{selectedRequest.message}</p>
          </div>
        )}
      </section>
      <section className="panel" aria-labelledby="account-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Account settings</p>
            <h2 id="account-heading">Profile and security</h2>
          </div>
        </div>
        <div className="content-grid account-grid">
          <form className="form-card" onSubmit={handleProfileSubmit}>
            <h3>Update profile</h3>
            <label>
              Display name
              <input
                required
                minLength={1}
                maxLength={80}
                value={profileName}
                onChange={(event) => setProfileName(event.target.value)}
              />
            </label>
            <button className="primary" type="submit">Save profile</button>
          </form>
          <form className="form-card" onSubmit={handlePasswordSubmit}>
            <h3>Change password</h3>
            <label>
              Current password
              <input
                required
                type="password"
                autoComplete="current-password"
                value={passwordForm.current_password}
                onChange={(event) =>
                  setPasswordForm({ ...passwordForm, current_password: event.target.value })
                }
              />
            </label>
            <label>
              New password
              <input
                required
                type="password"
                minLength={12}
                maxLength={128}
                autoComplete="new-password"
                value={passwordForm.new_password}
                onChange={(event) =>
                  setPasswordForm({ ...passwordForm, new_password: event.target.value })
                }
              />
            </label>
            <button className="primary" type="submit">Change password</button>
          </form>
        </div>
        <div className="session-list">
          <h3>Your sessions</h3>
          {userSessions.length === 0 ? (
            <p className="muted">No sessions found.</p>
          ) : (
            userSessions.map((session) => (
              <div className="session-row" key={session.id}>
                <div>
                  <strong>
                    {session.user_agent ?? "Unknown device"}
                    {api.isCurrentSession(session.id) ? " · This device" : ""}
                  </strong>
                  <p className="muted">
                    Started {new Date(session.created_at).toLocaleString()}
                    {session.ip_address ? ` · ${session.ip_address}` : ""}
                  </p>
                  {session.revoked_at && <span className="tag status-declined">Revoked</span>}
                </div>
                {!session.revoked_at && (
                  <button
                    className="danger"
                    type="button"
                    onClick={() => handleRevokeSession(session.id)}
                  >
                    Revoke
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      </section>
      <footer>
        Signed in as {user.email}. Listings and session requests are limited to their owners and participants.
      </footer>
    </main>
  )
}
