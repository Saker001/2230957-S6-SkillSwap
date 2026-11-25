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

  if (!response.ok) {
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
    throw new ApiError(detail, response.status)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
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
}
