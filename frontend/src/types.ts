export const categories = [
  "tops",
  "bottoms",
  "one-piece",
  "outerwear",
  "footwear",
  "accessories",
  "unrecognized",
] as const;
export type Category = (typeof categories)[number];
export type WardrobeId = "personal" | "deepfashion2";
export const categoryLabels: Record<Category, string> = {
  tops: "Tops",
  bottoms: "Bottoms",
  "one-piece": "One-pieces",
  outerwear: "Layers",
  footwear: "Shoes",
  accessories: "Accessories",
  unrecognized: "To review",
};
export interface Garment {
  id: string;
  name: string;
  category: Category;
  subtype: string;
  color: string;
  pattern: string;
  style: string;
  available: boolean;
  image_url: string;
  thumbnail_url: string;
  analysis_status: "pending" | "ready" | "review" | "failed";
  analysis_error: string | null;
  alternatives: string[];
  created_at: string;
}
export interface RemovedGarment {
  id: string;
  name: string;
  available: false;
  deleted: true;
  image_url: null;
  thumbnail_url: null;
}
export interface Outfit {
  title: string;
  explanation: string;
  item_ids: string[];
  items: (Garment | RemovedGarment)[];
  missing_components: string[];
}
export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  outfits: Outfit[];
  created_at: string;
}
export interface Conversation {
  id: string;
  wardrobe?: WardrobeId;
  messages: Message[];
  constraints: Record<string, unknown>;
}
export interface ItemPage {
  items: Garment[];
  total: number;
}
export interface DatasetStatus {
  photo_count: number;
  indexed_count: number;
  ready: boolean;
}
export interface BenchmarkCase {
  id: string;
  label: string;
  prompt: string;
  follow_up_to: string | null;
  seconds: number;
  outfit_count: number;
  partial_count: number;
  distinct_count: number;
  message: string;
  outfits: Outfit[];
  error: string | null;
}
export interface BenchmarkRun {
  id: string;
  created_at: string;
  status: "running" | "complete" | "failed";
  photo_count: number;
  indexed_count: number;
  cases: BenchmarkCase[];
  error: string | null;
}
export interface ModelStatus {
  vision_ready: boolean;
  ollama_ready: boolean;
  ollama_model: string;
  setup_hint: string;
}
export type GarmentChanges = Pick<
  Garment,
  "name" | "category" | "subtype" | "color" | "pattern" | "style" | "available"
>;
