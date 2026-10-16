import type {
  Conversation,
  Garment,
  GarmentChanges,
  ModelStatus,
  ItemPage,
  DatasetStatus,
  BenchmarkRun,
  WardrobeId,
} from "./types";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options);
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      typeof error?.detail === "string"
        ? error.detail
        : `Request failed (${response.status}). Please try again.`,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

const json = (body: unknown): RequestInit => ({
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
export const api = {
  items: () => request<Garment[]>("/api/items"),
  datasetStatus: () => request<DatasetStatus>("/api/deepfashion2/status"),
  datasetItems: (category: string, search: string, offset = 0) => {
    const query = new URLSearchParams({ offset: String(offset), limit: "48" });
    if (category !== "all") query.set("category", category);
    if (search.trim()) query.set("search", search.trim());
    return request<ItemPage>(`/api/deepfashion2/items?${query}`);
  },
  status: () => request<ModelStatus>("/api/status"),
  latestConversation: (wardrobe: WardrobeId = "personal") =>
    request<Conversation | null>(`/api/conversations/latest?wardrobe=${wardrobe}`),
  newConversation: (wardrobe: WardrobeId = "personal") =>
    request<Conversation>(`/api/conversations?wardrobe=${wardrobe}`, { method: "POST" }),
  latestBenchmark: () => request<BenchmarkRun | null>("/api/benchmarks/latest"),
  benchmark: (id: string) => request<BenchmarkRun>(`/api/benchmarks/${id}`),
  startBenchmark: () => request<BenchmarkRun>("/api/benchmarks", { method: "POST" }),
  updateItem: (id: string, changes: Partial<GarmentChanges>) =>
    request<Garment>(`/api/items/${id}`, { method: "PATCH", ...json(changes) }),
  clearWardrobe: () => request<void>("/api/items", { method: "DELETE" }),
  deleteItem: (id: string) =>
    request<void>(`/api/items/${id}`, { method: "DELETE" }),
  analyzeItem: (id: string) =>
    request<Garment>(`/api/items/${id}/analyze`, { method: "POST" }),
  sendMessage: (id: string, text: string) =>
    request<Conversation>(`/api/conversations/${id}/messages`, {
      method: "POST",
      ...json({ text }),
    }),
};

export function uploadPhoto(
  file: File,
  onProgress: (progress: number) => void,
): Promise<Garment> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/items");
    xhr.timeout = 180_000;
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable)
        onProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onerror = () =>
      reject(
        new Error("Upload interrupted. Check that the backend is running."),
      );
    xhr.ontimeout = () =>
      reject(
        new Error(
          "Upload timed out. Refresh your wardrobe before retrying; the photo may have been saved.",
        ),
      );
    xhr.onload = () => {
      try {
        const result = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) resolve(result);
        else
          reject(
            new Error(
              typeof result.detail === "string"
                ? result.detail
                : "This photo could not be uploaded.",
            ),
          );
      } catch {
        reject(new Error("The server returned an unreadable upload response."));
      }
    };
    const data = new FormData();
    data.append("file", file);
    xhr.send(data);
  });
}
