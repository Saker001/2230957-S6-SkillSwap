export type SkillListing = {
  id: number
  teacher_name: string
  title: string
  description: string
  category: string
  created_at: string
}

export type SessionRequest = {
  id: number
  skill_listing_id: number
  learner_name: string
  message: string
  status: "pending" | "accepted" | "declined"
  created_at: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (init?.body) headers.set("Content-Type", "application/json")
  const response = await fetch(path, {
    ...init,
    headers,
  })

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
    throw new Error(detail)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  listSkills: () => request<SkillListing[]>("/api/skills"),
  getSkill: (id: number) => request<SkillListing>(`/api/skills/${id}`),
  createSkill: (data: Omit<SkillListing, "id" | "created_at">) =>
    request<SkillListing>("/api/skills", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateSkill: (id: number, data: Partial<Omit<SkillListing, "id" | "created_at">>) =>
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
    learner_name: string
    message: string
  }) =>
    request<SessionRequest>("/api/session-requests", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateSessionRequest: (
    id: number,
    data: Partial<
      Pick<SessionRequest, "skill_listing_id" | "learner_name" | "message" | "status">
    >,
  ) =>
    request<SessionRequest>(`/api/session-requests/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteSessionRequest: (id: number) =>
    request<void>(`/api/session-requests/${id}`, { method: "DELETE" }),
}
