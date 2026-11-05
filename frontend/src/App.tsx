import { type FormEvent, useCallback, useEffect, useState } from "react"
import { api, type SessionRequest, type SkillListing } from "./api"

const emptySkill = {
  teacher_name: "",
  title: "",
  description: "",
  category: "",
}

const emptyRequest = {
  skill_listing_id: "",
  learner_name: "",
  message: "",
  status: "pending" as SessionRequest["status"],
}

export default function App() {
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

  const refreshData = useCallback(async () => {
    const [skillRows, requestRows] = await Promise.all([
      api.listSkills(),
      api.listSessionRequests(),
    ])
    setSkills(skillRows)
    setSessionRequests(requestRows)
  }, [])

  useEffect(() => {
    refreshData()
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Could not load SkillSwap data."),
      )
      .finally(() => setLoading(false))
  }, [refreshData])

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
        learner_name: requestForm.learner_name,
        message: requestForm.message,
      }
      if (editingRequestId === null) {
        await api.createSessionRequest(data)
        setNotice("Session request created.")
      } else {
        await api.updateSessionRequest(editingRequestId, {
          ...data,
          status: requestForm.status,
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
      learner_name: request.learner_name,
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

  return (
    <main className="app-shell">
      <header className="hero">
        <p className="eyebrow">Learn from each other</p>
        <h1>SkillSwap</h1>
        <p className="intro">
          Share what you know, discover a skill to learn, and arrange a session.
        </p>
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
                    <button className="secondary" onClick={() => editSkill(skill)}>Edit</button>
                    <button className="danger" onClick={() => removeSkill(skill.id)}>Delete</button>
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
            <h3>{editingRequestId === null ? "Request a session" : "Edit session request"}</h3>
            <label>
              Skill
              <select
                required
                value={requestForm.skill_listing_id}
                onChange={(event) =>
                  setRequestForm({ ...requestForm, skill_listing_id: event.target.value })
                }
              >
                <option value="">Choose a listing</option>
                {skills.map((skill) => (
                  <option value={skill.id} key={skill.id}>
                    {skill.title} — {skill.teacher_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Your name
              <input
                required
                maxLength={80}
                value={requestForm.learner_name}
                onChange={(event) =>
                  setRequestForm({ ...requestForm, learner_name: event.target.value })
                }
                placeholder="e.g. Jamie"
              />
            </label>
            <label>
              What would you like to learn?
              <textarea
                required
                maxLength={1000}
                rows={4}
                value={requestForm.message}
                onChange={(event) =>
                  setRequestForm({ ...requestForm, message: event.target.value })
                }
                placeholder="Introduce yourself and share your learning goal."
              />
            </label>
            {editingRequestId !== null && (
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
              <button className="primary" type="submit" disabled={skills.length === 0}>
                {editingRequestId === null ? "Send request" : "Save changes"}
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
            {skills.length === 0 && <p className="muted">Create a skill listing before requesting a session.</p>}
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
                    <button className="secondary" onClick={() => editRequest(request)}>Edit</button>
                    <button className="danger" onClick={() => removeRequest(request.id)}>Delete</button>
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
      <footer>
        Shared data, no sign-in. Authentication and ownership controls are planned for Beta.
      </footer>
    </main>
  )
}
