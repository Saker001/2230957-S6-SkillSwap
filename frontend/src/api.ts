export type SkillListing = {
  id: number
  owner_id: number | null
  teacher_name: string
  title: string
  description: string
  category: string
  created_at: string
}

export type SessionRequest = {
  id: number
  skill_listing_id: number
  learner_id: number | null
  learner_name: string
  message: string
  status: "pending" | "accepted" | "declined"
  created_at: string
}

export type User = {
  id: number
  email: string
  display_name: string
  role: "user" | "admin"
  created_at: string
}

export type UserSession = {
  id: string
  created_at: string
  expires_at: string
  revoked_at: string | null
  user_agent: string | null
  ip_address: string | null
}

export type SkillGroup = {
  id: number
  owner_id: number
  name: string
  created_at: string
}

export type GroupMember = {
  user_id: number
  display_name: string
  is_owner: boolean
  can_create: boolean
  can_edit: boolean
  can_assign: boolean
}

export type AdminUser = User & {
  is_active: boolean
  is_banned: boolean
  ban_reason: string | null
  banned_at: string | null
}

export type AdminAuditEvent = {
  id: number
  actor_id: number | null
  action: string
  target_type: string
  target_id: string
  details: Record<string, unknown>
  ip_address: string | null
  user_agent: string | null
  created_at: string
}

export type FailedLoginInsight = {
  value: string
  count: number
  last_seen: string
}

export type FailedLoginSummary = {
  by_ip: FailedLoginInsight[]
  by_account: FailedLoginInsight[]
}

export type AdminPage<T> = {
  items: T[]
  total: number
  limit: number
  offset: number
}

export type AdminOverview = {
  users: number
  banned_users: number
  records: number
  groups: number
  recent_activity: AdminAuditEvent[]
}

export type AdminUserDetail = {
  user: AdminUser
  records: SkillListing[]
  session_requests: SessionRequest[]
  groups: SkillGroup[]
  sessions: UserSession[]
  recent_activity: AdminAuditEvent[]
}

export type SkillCategory = {
  id: number
  name: string
  created_at: string
}

type AuthResponse = {
  access_token: string
  token_type: "bearer"
  expires_in: number
  session_id: string
  user: User
}

class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
    this.name = "ApiError"
  }
}

let accessToken: string | null = null
let currentSessionId: string | null = null
let refreshInFlight: Promise<User | null> | null = null

async function responseError(response: Response): Promise<ApiError> {
  let detail = `Request failed (${response.status})`
  if (response.headers.get("content-type")?.includes("application/json")) {
    const body: unknown = await response.json()
    if (typeof body === "object" && body !== null && "detail" in body) {
      if (typeof body.detail === "string") {
        detail = body.detail
      } else if (Array.isArray(body.detail)) {
        detail = body.detail
          .map((item) =>
            typeof item === "object" &&
            item !== null &&
            "msg" in item &&
            typeof item.msg === "string"
              ? item.msg
              : "",
          )
          .filter(Boolean)
          .join("; ") || detail
      }
    }
  }
  return new ApiError(detail, response.status)
}

async function request<T>(
  path: string,
  init?: RequestInit,
  retryAfterRefresh = true,
): Promise<T> {
  const headers = new Headers(init?.headers)
  if (init?.body) headers.set("Content-Type", "application/json")
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`)
  const response = await fetch(path, {
    ...init,
    headers,
    credentials: "include",
  })

  const isAuthRoute = path.startsWith("/api/auth/")
  if (response.status === 401 && retryAfterRefresh && accessToken && !isAuthRoute) {
    refreshInFlight ??= refreshSession().finally(() => {
      refreshInFlight = null
    })
    const user = await refreshInFlight
    if (user) return request<T>(path, init, false)
    accessToken = null
  }

  if (!response.ok) throw await responseError(response)

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function downloadCsv(path: string, retryAfterRefresh = true): Promise<void> {
  const headers = new Headers()
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`)
  const response = await fetch(path, { headers, credentials: "include" })
  if (response.status === 401 && retryAfterRefresh && accessToken) {
    const user = await refreshSession()
    if (user) return downloadCsv(path, false)
    accessToken = null
  }
  if (!response.ok) throw await responseError(response)

  const filename =
    response.headers.get("content-disposition")?.match(/filename="?([^";]+)"?/i)?.[1] ??
    "skillswap-export.csv"
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function exportQuery(
  params: Record<string, string | boolean | number | null | undefined>,
): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value))
  }
  const search = query.toString()
  return search ? `?${search}` : ""
}

async function refreshSession(): Promise<User | null> {
  try {
    const session = await request<AuthResponse>("/api/auth/refresh", { method: "POST" }, false)
    accessToken = session.access_token
    currentSessionId = session.session_id
    return session.user
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      accessToken = null
      currentSessionId = null
      return null
    }
    throw error
  }
}

export const api = {
  restoreSession: () => refreshSession(),
  signUp: (data: { email: string; display_name: string; password: string }) =>
    request<User>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  logIn: async (data: { email: string; password: string }) => {
    const session = await request<AuthResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(data),
    })
    accessToken = session.access_token
    currentSessionId = session.session_id
    return session.user
  },
  logOut: async () => {
    try {
      await request<void>("/api/auth/logout", { method: "POST" }, false)
    } finally {
      accessToken = null
      currentSessionId = null
    }
  },
  updateProfile: (display_name: string) =>
    request<User>("/api/users/me", {
      method: "PATCH",
      body: JSON.stringify({ display_name }),
    }),
  changePassword: async (current_password: string, new_password: string) => {
    await request<void>("/api/users/me/password", {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    })
    accessToken = null
    currentSessionId = null
  },
  listSessions: () => request<UserSession[]>("/api/users/me/sessions"),
  isCurrentSession: (id: string) => currentSessionId === id,
  revokeSession: async (id: string) => {
    await request<void>(`/api/users/me/sessions/${id}`, { method: "DELETE" })
    if (currentSessionId === id) {
      accessToken = null
      currentSessionId = null
    }
  },
  listSkills: () => request<SkillListing[]>("/api/skills"),
  getSkill: (id: number) => request<SkillListing>(`/api/skills/${id}`),
  createSkill: (data: Omit<SkillListing, "id" | "created_at" | "owner_id">) =>
    request<SkillListing>("/api/skills", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateSkill: (
    id: number,
    data: Partial<Omit<SkillListing, "id" | "created_at" | "owner_id">>,
  ) =>
    request<SkillListing>(`/api/skills/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteSkill: (id: number) =>
    request<void>(`/api/skills/${id}`, { method: "DELETE" }),
  listGroups: () => request<SkillGroup[]>("/api/groups"),
  createGroup: (data: { name: string }) =>
    request<SkillGroup>("/api/groups", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateGroup: (id: number, name: string) =>
    request<SkillGroup>(`/api/groups/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),
  deleteGroup: (id: number) =>
    request<void>(`/api/groups/${id}`, { method: "DELETE" }),
  listGroupMembers: (groupId: number) =>
    request<GroupMember[]>(`/api/groups/${groupId}/members`),
  addGroupMember: (
    groupId: number,
    data: { email: string; can_create: boolean; can_edit: boolean; can_assign: boolean },
  ) =>
    request<GroupMember>(`/api/groups/${groupId}/members`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateGroupMember: (
    groupId: number,
    userId: number,
    data: Partial<Pick<GroupMember, "can_create" | "can_edit" | "can_assign">>,
  ) =>
    request<GroupMember>(`/api/groups/${groupId}/members/${userId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  removeGroupMember: (groupId: number, userId: number) =>
    request<void>(`/api/groups/${groupId}/members/${userId}`, { method: "DELETE" }),
  listGroupSkills: (groupId: number) =>
    request<SkillListing[]>(`/api/groups/${groupId}/skills`),
  createGroupSkill: (
    groupId: number,
    data: Omit<SkillListing, "id" | "created_at" | "owner_id">,
  ) =>
    request<SkillListing>(`/api/groups/${groupId}/skills`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  assignGroupSkill: (groupId: number, skillId: number) =>
    request<SkillListing>(`/api/groups/${groupId}/skills/${skillId}/assignment`, {
      method: "POST",
    }),
  updateGroupSkill: (
    groupId: number,
    skillId: number,
    data: Partial<Omit<SkillListing, "id" | "created_at" | "owner_id">>,
  ) =>
    request<SkillListing>(`/api/groups/${groupId}/skills/${skillId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  unassignGroupSkill: (groupId: number, skillId: number) =>
    request<void>(`/api/groups/${groupId}/skills/${skillId}`, { method: "DELETE" }),
  listSessionRequests: () => request<SessionRequest[]>("/api/session-requests"),
  getSessionRequest: (id: number) =>
    request<SessionRequest>(`/api/session-requests/${id}`),
  createSessionRequest: (data: {
    skill_listing_id: number
    message: string
  }) =>
    request<SessionRequest>("/api/session-requests", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateSessionRequest: (
    id: number,
    data: Partial<
      Pick<SessionRequest, "message" | "status">
    >,
  ) =>
    request<SessionRequest>(`/api/session-requests/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteSessionRequest: (id: number) =>
    request<void>(`/api/session-requests/${id}`, { method: "DELETE" }),
  adminOverview: () => request<AdminOverview>("/api/admin/overview"),
  adminActivity: (params: {
    q?: string
    action?: string
    actor_id?: number
    target_type?: string
    since?: string
    until?: string
    limit?: number
    offset?: number
  }) => request<AdminAuditEvent[]>(`/api/admin/activity${exportQuery(params)}`),
  adminFailedLogins: (params: { q?: string; since?: string; limit?: number }) =>
    request<FailedLoginSummary>(`/api/admin/security/failed-logins${exportQuery(params)}`),
  adminExportUsers: (params: { q?: string; role?: string; banned?: boolean | null }) =>
    downloadCsv(`/api/admin/exports/users.csv${exportQuery(params)}`),
  adminExportRecords: (params: { q?: string; category?: string }) =>
    downloadCsv(`/api/admin/exports/records.csv${exportQuery(params)}`),
  adminExportActivity: (params: {
    q?: string
    action?: string
    actor_id?: number
    target_type?: string
    since?: string
    until?: string
  }) => downloadCsv(`/api/admin/exports/activity.csv${exportQuery(params)}`),
  adminUsers: (params: {
    q?: string
    role?: string
    banned?: boolean | null
    limit?: number
    offset?: number
  }) => {
    const query = new URLSearchParams()
    if (params.q) query.set("q", params.q)
    if (params.role) query.set("role", params.role)
    if (params.banned !== null && params.banned !== undefined) {
      query.set("banned", String(params.banned))
    }
    query.set("limit", String(params.limit ?? 25))
    query.set("offset", String(params.offset ?? 0))
    return request<AdminPage<AdminUser>>(`/api/admin/users?${query}`)
  },
  adminUserDetail: (id: number) =>
    request<AdminUserDetail>(`/api/admin/users/${id}`),
  adminUpdateRole: (id: number, role: User["role"]) =>
    request<AdminUser>(`/api/admin/users/${id}/role`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    }),
  adminBanUser: (id: number, reason: string) =>
    request<AdminUser>(`/api/admin/users/${id}/ban`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  adminUnbanUser: (id: number) =>
    request<AdminUser>(`/api/admin/users/${id}/unban`, { method: "POST" }),
  adminBulkBan: (user_ids: number[], reason: string) =>
    request<{ affected: number }>("/api/admin/users/bulk-ban", {
      method: "POST",
      body: JSON.stringify({ user_ids, reason }),
    }),
  adminBulkUnban: (ids: number[]) =>
    request<{ affected: number }>("/api/admin/users/bulk-unban", {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),
  adminRevokeSessions: (id: number) =>
    request<{ affected: number }>(`/api/admin/users/${id}/revoke-sessions`, {
      method: "POST",
    }),
  adminRevokeSession: (userId: number, sessionId: string) =>
    request<void>(`/api/admin/users/${userId}/sessions/${sessionId}/revoke`, {
      method: "POST",
    }),
  adminListings: (params: { q?: string; category?: string; limit?: number; offset?: number }) => {
    const query = new URLSearchParams()
    if (params.q) query.set("q", params.q)
    if (params.category) query.set("category", params.category)
    query.set("limit", String(params.limit ?? 25))
    query.set("offset", String(params.offset ?? 0))
    return request<AdminPage<SkillListing>>(`/api/admin/listings?${query}`)
  },
  adminDeleteListing: (id: number) =>
    request<void>(`/api/admin/listings/${id}`, { method: "DELETE" }),
  adminBulkDeleteListings: (ids: number[]) =>
    request<{ affected: number }>("/api/admin/listings/bulk-delete", {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),
  adminGroups: (params: { q?: string; limit?: number; offset?: number }) => {
    const query = new URLSearchParams()
    if (params.q) query.set("q", params.q)
    query.set("limit", String(params.limit ?? 25))
    query.set("offset", String(params.offset ?? 0))
    return request<AdminPage<SkillGroup>>(`/api/admin/groups?${query}`)
  },
  adminDeleteGroup: (id: number) =>
    request<void>(`/api/admin/groups/${id}`, { method: "DELETE" }),
  adminBulkDeleteGroups: (ids: number[]) =>
    request<{ affected: number }>("/api/admin/groups/bulk-delete", {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),
  adminCategories: () => request<SkillCategory[]>("/api/admin/categories"),
  adminCreateCategory: (name: string) =>
    request<SkillCategory>("/api/admin/categories", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  adminRenameCategory: (id: number, name: string) =>
    request<SkillCategory>(`/api/admin/categories/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),
  adminDeleteCategory: (id: number) =>
    request<void>(`/api/admin/categories/${id}`, { method: "DELETE" }),
}
