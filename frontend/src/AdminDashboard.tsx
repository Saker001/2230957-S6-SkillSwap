import { type FormEvent, useEffect, useState } from "react"
import {
  api,
  type AdminAuditEvent,
  type AdminOverview,
  type AdminPage,
  type AdminUser,
  type AdminUserDetail,
  type SkillCategory,
  type SkillGroup,
  type SkillListing,
} from "./api"

type Section = "overview" | "users" | "listings" | "groups" | "categories"

const pageSize = 25

function formatDate(value: string) {
  return new Date(value).toLocaleString()
}

function ActivityList({ events }: { events: AdminAuditEvent[] }) {
  if (events.length === 0) return <p className="muted">No administrative activity yet.</p>
  return (
    <div className="admin-activity">
      {events.map((event) => (
        <article className="session-row" key={event.id}>
          <div>
            <strong>{event.action.replaceAll(".", " ")}</strong>
            <p className="muted">
              {event.target_type} {event.target_id} · Admin {event.actor_id ?? "removed"}
            </p>
            {typeof event.details.reason === "string" && (
              <p className="muted">Reason: {event.details.reason}</p>
            )}
          </div>
          <time className="muted" dateTime={event.created_at}>{formatDate(event.created_at)}</time>
        </article>
      ))}
    </div>
  )
}

export default function AdminDashboard({ onExit }: { onExit: () => void }) {
  const [section, setSection] = useState<Section>("overview")
  const [overview, setOverview] = useState<AdminOverview | null>(null)
  const [users, setUsers] = useState<AdminPage<AdminUser> | null>(null)
  const [listings, setListings] = useState<AdminPage<SkillListing> | null>(null)
  const [groups, setGroups] = useState<AdminPage<SkillGroup> | null>(null)
  const [categories, setCategories] = useState<SkillCategory[]>([])
  const [detail, setDetail] = useState<AdminUserDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [queryInput, setQueryInput] = useState("")
  const [query, setQuery] = useState("")
  const [roleFilter, setRoleFilter] = useState("")
  const [banFilter, setBanFilter] = useState("")
  const [categoryFilter, setCategoryFilter] = useState("")
  const [categoryName, setCategoryName] = useState("")
  const [editingCategory, setEditingCategory] = useState<number | null>(null)
  const [editingCategoryName, setEditingCategoryName] = useState("")
  const [offset, setOffset] = useState(0)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    let active = true
    api.adminOverview()
      .then((result) => { if (active) setOverview(result) })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Could not load the dashboard.")
      })
    return () => { active = false }
  }, [revision])

  useEffect(() => {
    if (section !== "users" && section !== "listings" && section !== "groups") return
    let active = true
    setLoading(true)
    const request =
      section === "users"
        ? api.adminUsers({
            q: query,
            role: roleFilter || undefined,
            banned: banFilter === "" ? null : banFilter === "banned",
            limit: pageSize,
            offset,
          })
        : section === "listings"
          ? api.adminListings({ q: query, category: categoryFilter || undefined, limit: pageSize, offset })
          : api.adminGroups({ q: query, limit: pageSize, offset })
    request
      .then((result) => {
        if (!active) return
        if (section === "users") setUsers(result as AdminPage<AdminUser>)
        else if (section === "listings") setListings(result as AdminPage<SkillListing>)
        else setGroups(result as AdminPage<SkillGroup>)
        setSelectedIds([])
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Could not load records.")
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [section, query, roleFilter, banFilter, categoryFilter, offset, revision])

  useEffect(() => {
    let active = true
    if (section === "categories") setLoading(true)
    api.adminCategories()
      .then((result) => { if (active) setCategories(result) })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Could not load categories.")
      })
      .finally(() => { if (active && section === "categories") setLoading(false) })
    return () => { active = false }
  }, [section, revision])

  function applySearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setOffset(0)
    setQuery(queryInput.trim())
  }

  function toggleSelected(id: number) {
    setSelectedIds((ids) => ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id])
  }

  function showError(reason: unknown) {
    setError(reason instanceof Error ? reason.message : "The administrative action failed.")
  }

  async function loadUser(id: number) {
    setDetailLoading(true)
    setError("")
    try {
      setDetail(await api.adminUserDetail(id))
    } catch (reason) {
      showError(reason)
    } finally {
      setDetailLoading(false)
    }
  }

  async function handleBan(user: AdminUser) {
    const reason = window.prompt(`Why are you banning ${user.display_name}?`)
    if (reason === null) return
    setError("")
    try {
      await api.adminBanUser(user.id, reason)
      setNotice(`${user.display_name} was banned.`)
      setRevision((value) => value + 1)
      if (detail?.user.id === user.id) await loadUser(user.id)
    } catch (reason) { showError(reason) }
  }

  async function handleUnban(user: AdminUser) {
    setError("")
    try {
      await api.adminUnbanUser(user.id)
      setNotice(`${user.display_name} was unbanned.`)
      setRevision((value) => value + 1)
      if (detail?.user.id === user.id) await loadUser(user.id)
    } catch (reason) { showError(reason) }
  }

  async function handleRoleChange(user: AdminUser, role: AdminUser["role"]) {
    if (role === user.role) return
    setError("")
    try {
      await api.adminUpdateRole(user.id, role)
      setNotice(`${user.display_name}'s role was updated.`)
      setRevision((value) => value + 1)
      if (detail?.user.id === user.id) await loadUser(user.id)
    } catch (reason) { showError(reason) }
  }

  async function handleBulkUsers(unban: boolean) {
    if (selectedIds.length === 0) return
    const reason = unban ? "" : window.prompt("Enter the reason for this bulk ban.")
    if (reason === null) return
    setError("")
    try {
      const result = unban
        ? await api.adminBulkUnban(selectedIds)
        : await api.adminBulkBan(selectedIds, reason)
      setNotice(`${result.affected} account${result.affected === 1 ? "" : "s"} updated.`)
      setSelectedIds([])
      setRevision((value) => value + 1)
    } catch (reason) { showError(reason) }
  }

  async function handleRevokeSessions(id: number) {
    setError("")
    try {
      const result = await api.adminRevokeSessions(id)
      setNotice(`${result.affected} session${result.affected === 1 ? "" : "s"} revoked.`)
      setRevision((value) => value + 1)
      await loadUser(id)
    } catch (reason) { showError(reason) }
  }

  async function handleRevokeSession(userId: number, sessionId: string) {
    setError("")
    try {
      await api.adminRevokeSession(userId, sessionId)
      setNotice("Session revoked.")
      await loadUser(userId)
    } catch (reason) { showError(reason) }
  }

  async function handleBulkDelete(kind: "listings" | "groups") {
    if (!selectedIds.length || !window.confirm(`Permanently delete ${selectedIds.length} selected ${kind}?`)) return
    setError("")
    try {
      const result = kind === "listings"
        ? await api.adminBulkDeleteListings(selectedIds)
        : await api.adminBulkDeleteGroups(selectedIds)
      setNotice(`${result.affected} ${kind} deleted.`)
      setSelectedIds([])
      setRevision((value) => value + 1)
    } catch (reason) { showError(reason) }
  }

  async function handleDeleteOne(kind: "listings" | "groups", id: number) {
    if (!window.confirm(`Permanently delete this ${kind === "listings" ? "listing" : "group"}?`)) return
    setError("")
    try {
      if (kind === "listings") await api.adminDeleteListing(id)
      else await api.adminDeleteGroup(id)
      setNotice(`${kind === "listings" ? "Listing" : "Group"} deleted.`)
      setRevision((value) => value + 1)
    } catch (reason) { showError(reason) }
  }

  async function handleCreateCategory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError("")
    try {
      await api.adminCreateCategory(categoryName)
      setCategoryName("")
      setNotice("Category created.")
      setRevision((value) => value + 1)
    } catch (reason) { showError(reason) }
  }

  async function handleRenameCategory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (editingCategory === null) return
    setError("")
    try {
      await api.adminRenameCategory(editingCategory, editingCategoryName)
      setEditingCategory(null)
      setEditingCategoryName("")
      setNotice("Category renamed.")
      setRevision((value) => value + 1)
    } catch (reason) { showError(reason) }
  }

  async function handleDeleteCategory(category: SkillCategory) {
    if (!window.confirm(`Delete category "${category.name}"?`)) return
    setError("")
    try {
      await api.adminDeleteCategory(category.id)
      setNotice("Category deleted.")
      setRevision((value) => value + 1)
    } catch (reason) { showError(reason) }
  }

  const page = section === "users" ? users : section === "listings" ? listings : groups
  const nav: { id: Section; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "users", label: "Users" },
    { id: "listings", label: "Listings" },
    { id: "groups", label: "Groups" },
    { id: "categories", label: "Categories" },
  ]

  return (
    <section className="panel admin-panel" aria-labelledby="admin-heading">
      <header className="admin-heading">
        <div>
          <p className="eyebrow">Platform controls</p>
          <h2 id="admin-heading">Admin dashboard</h2>
        </div>
        <button className="secondary" type="button" onClick={onExit}>Back to SkillSwap</button>
      </header>
      <nav className="admin-nav" aria-label="Administration">
        {nav.map((item) => (
          <button
            className={section === item.id ? "primary" : "secondary"}
            key={item.id}
            type="button"
            aria-current={section === item.id ? "page" : undefined}
            onClick={() => {
              setSection(item.id)
              setOffset(0)
              setError("")
              setNotice("")
            }}
          >
            {item.label}
          </button>
        ))}
      </nav>
      {error && <p className="alert error" role="alert">{error}</p>}
      {notice && <p className="alert success" role="status">{notice}</p>}
      {loading && <p className="muted" role="status">Loading admin data...</p>}

      {section === "overview" && (
        <>
          {overview ? (
            <div className="admin-stats">
              {[
                ["Users", overview.users],
                ["Banned users", overview.banned_users],
                ["Skill records", overview.records],
                ["Groups", overview.groups],
              ].map(([label, count]) => (
                <article className="admin-stat" key={label}>
                  <span className="muted">{label}</span>
                  <strong>{count}</strong>
                </article>
              ))}
            </div>
          ) : !loading && <div className="empty-state">Dashboard totals are unavailable.</div>}
          <div className="admin-subsection">
            <h3>Recent administrative activity</h3>
            <ActivityList events={overview?.recent_activity ?? []} />
          </div>
        </>
      )}

      {(section === "users" || section === "listings" || section === "groups") && (
        <>
          <form className="admin-filters" onSubmit={applySearch}>
            <label>
              Search
              <input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} />
            </label>
            {section === "users" && (
              <>
                <label>
                  Role
                  <select value={roleFilter} onChange={(event) => { setRoleFilter(event.target.value); setOffset(0) }}>
                    <option value="">All roles</option>
                    <option value="user">User</option>
                    <option value="admin">Admin</option>
                  </select>
                </label>
                <label>
                  Status
                  <select value={banFilter} onChange={(event) => { setBanFilter(event.target.value); setOffset(0) }}>
                    <option value="">All accounts</option>
                    <option value="active">Not banned</option>
                    <option value="banned">Banned</option>
                  </select>
                </label>
              </>
            )}
            {section === "listings" && (
              <label>
                Category
                <input
                  value={categoryFilter}
                  onChange={(event) => { setCategoryFilter(event.target.value); setOffset(0) }}
                  placeholder="Filter by category"
                />
              </label>
            )}
            <button className="primary" type="submit">Search</button>
          </form>

          {section === "users" && (
            <>
              {selectedIds.length > 0 && (
                <div className="admin-bulk-actions">
                  <span>{selectedIds.length} selected</span>
                  <button className="danger" type="button" onClick={() => handleBulkUsers(false)}>Bulk ban</button>
                  <button className="secondary" type="button" onClick={() => handleBulkUsers(true)}>Bulk unban</button>
                </div>
              )}
              {users?.items.map((user) => (
                <article className="admin-record" key={user.id}>
                  <input aria-label={`Select ${user.email}`} type="checkbox" checked={selectedIds.includes(user.id)} onChange={() => toggleSelected(user.id)} />
                  <div className="admin-record-main">
                    <strong>{user.display_name}</strong>
                    <span className="muted">{user.email} · Joined {formatDate(user.created_at)}</span>
                    {user.is_banned && <span className="tag status-declined">Banned: {user.ban_reason}</span>}
                  </div>
                  <select aria-label={`Role for ${user.email}`} value={user.role} onChange={(event) => handleRoleChange(user, event.target.value as AdminUser["role"])}>
                    <option value="user">User</option>
                    <option value="admin">Admin</option>
                  </select>
                  <div className="item-actions">
                    <button className="secondary" type="button" onClick={() => loadUser(user.id)}>Details</button>
                    {user.is_banned
                      ? <button className="secondary" type="button" onClick={() => handleUnban(user)}>Unban</button>
                      : <button className="danger" type="button" onClick={() => handleBan(user)}>Ban</button>}
                  </div>
                </article>
              ))}
              {users && users.items.length === 0 && !loading && <div className="empty-state">No users match these filters.</div>}
            </>
          )}

          {section === "listings" && (
            <>
              {selectedIds.length > 0 && (
                <div className="admin-bulk-actions">
                  <span>{selectedIds.length} selected</span>
                  <button className="danger" type="button" onClick={() => handleBulkDelete("listings")}>Delete selected</button>
                </div>
              )}
              {listings?.items.map((listing) => (
                <article className="admin-record" key={listing.id}>
                  <input aria-label={`Select listing ${listing.id}`} type="checkbox" checked={selectedIds.includes(listing.id)} onChange={() => toggleSelected(listing.id)} />
                  <div className="admin-record-main">
                    <strong>{listing.title}</strong>
                    <span className="muted">{listing.teacher_name} · {listing.category} · Owner {listing.owner_id ?? "unknown"}</span>
                  </div>
                  <button className="danger" type="button" onClick={() => handleDeleteOne("listings", listing.id)}>Delete</button>
                </article>
              ))}
              {listings && listings.items.length === 0 && !loading && <div className="empty-state">No listings match these filters.</div>}
            </>
          )}

          {section === "groups" && (
            <>
              {selectedIds.length > 0 && (
                <div className="admin-bulk-actions">
                  <span>{selectedIds.length} selected</span>
                  <button className="danger" type="button" onClick={() => handleBulkDelete("groups")}>Delete selected</button>
                </div>
              )}
              {groups?.items.map((group) => (
                <article className="admin-record" key={group.id}>
                  <input aria-label={`Select group ${group.name}`} type="checkbox" checked={selectedIds.includes(group.id)} onChange={() => toggleSelected(group.id)} />
                  <div className="admin-record-main">
                    <strong>{group.name}</strong>
                    <span className="muted">Owner {group.owner_id} · Created {formatDate(group.created_at)}</span>
                  </div>
                  <button className="danger" type="button" onClick={() => handleDeleteOne("groups", group.id)}>Delete</button>
                </article>
              ))}
              {groups && groups.items.length === 0 && !loading && <div className="empty-state">No groups match this search.</div>}
            </>
          )}

          {page && (
            <div className="admin-pagination">
              <span className="muted">{page.total} total · Showing {Math.min(offset + 1, page.total)}–{Math.min(offset + page.items.length, page.total)}</span>
              <div className="item-actions">
                <button className="secondary" type="button" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(offset - pageSize, 0))}>Previous</button>
                <button className="secondary" type="button" disabled={offset + pageSize >= page.total || loading} onClick={() => setOffset(offset + pageSize)}>Next</button>
              </div>
            </div>
          )}
        </>
      )}

      {section === "categories" && (
        <div className="admin-subsection">
          <form className="admin-category-form" onSubmit={handleCreateCategory}>
            <label>
              New category
              <input required maxLength={60} value={categoryName} onChange={(event) => setCategoryName(event.target.value)} />
            </label>
            <button className="primary" type="submit">Add category</button>
          </form>
          {categories.map((category) => (
            <article className="admin-record" key={category.id}>
              {editingCategory === category.id ? (
                <form className="admin-inline-form" onSubmit={handleRenameCategory}>
                  <input required maxLength={60} value={editingCategoryName} onChange={(event) => setEditingCategoryName(event.target.value)} />
                  <button className="primary" type="submit">Save</button>
                  <button className="secondary" type="button" onClick={() => setEditingCategory(null)}>Cancel</button>
                </form>
              ) : (
                <>
                  <div className="admin-record-main"><strong>{category.name}</strong></div>
                  <button className="secondary" type="button" onClick={() => { setEditingCategory(category.id); setEditingCategoryName(category.name) }}>Rename</button>
                  <button className="danger" type="button" onClick={() => handleDeleteCategory(category)}>Delete</button>
                </>
              )}
            </article>
          ))}
          {categories.length === 0 && !loading && <div className="empty-state">No managed categories yet.</div>}
        </div>
      )}

      {section === "users" && detail && (
        <section className="admin-user-detail" aria-labelledby="user-detail-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Account detail</p>
              <h3 id="user-detail-heading">{detail.user.display_name}</h3>
              <p className="muted">{detail.user.email} · {detail.user.role}</p>
            </div>
            <div className="item-actions">
              <button className="secondary" type="button" disabled={detailLoading} onClick={() => handleRevokeSessions(detail.user.id)}>Revoke all sessions</button>
              <button className="secondary" type="button" onClick={() => setDetail(null)}>Close</button>
            </div>
          </div>
          {detail.user.is_banned && <p className="alert error">Banned {detail.user.banned_at ? formatDate(detail.user.banned_at) : ""}: {detail.user.ban_reason}</p>}
          <div className="content-grid">
            <div className="admin-detail-block">
              <h4>Skill records ({detail.records.length})</h4>
              {detail.records.map((record) => <p key={record.id}>{record.title} · {record.category}</p>)}
              {detail.records.length === 0 && <p className="muted">No skill records.</p>}
              <h4>Session requests ({detail.session_requests.length})</h4>
              {detail.session_requests.map((request) => <p key={request.id}>Request #{request.id} · {request.status}</p>)}
              {detail.session_requests.length === 0 && <p className="muted">No session requests.</p>}
              <h4>Groups ({detail.groups.length})</h4>
              {detail.groups.map((group) => <p key={group.id}>{group.name}</p>)}
              {detail.groups.length === 0 && <p className="muted">No groups.</p>}
            </div>
            <div className="admin-detail-block">
              <h4>Sessions ({detail.sessions.length})</h4>
              {detail.sessions.map((session) => (
                <div className="admin-session" key={session.id}>
                  <span className="muted">{formatDate(session.created_at)} · {session.user_agent ?? "Unknown device"} · {session.revoked_at ? "Revoked" : "Active"}</span>
                  {!session.revoked_at && <button className="danger" type="button" onClick={() => handleRevokeSession(detail.user.id, session.id)}>Revoke</button>}
                </div>
              ))}
              {detail.sessions.length === 0 && <p className="muted">No sessions.</p>}
            </div>
          </div>
          <div className="admin-subsection">
            <h4>Recent administrative activity</h4>
            <ActivityList events={detail.recent_activity} />
          </div>
        </section>
      )}
    </section>
  )
}
