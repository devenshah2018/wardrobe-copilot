import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { api, uploadPhoto } from "./api";
import type { Conversation, Garment } from "./types";

vi.mock("./api", () => ({
  api: {
    items: vi.fn(),
    datasetStatus: vi.fn(),
    datasetItems: vi.fn(),
    status: vi.fn(),
    latestConversation: vi.fn(),
    latestBenchmark: vi.fn(),
    benchmark: vi.fn(),
    startBenchmark: vi.fn(),
    newConversation: vi.fn(),
    updateItem: vi.fn(),
    deleteItem: vi.fn(),
    clearWardrobe: vi.fn(),
    analyzeItem: vi.fn(),
    sendMessage: vi.fn(),
  },
  uploadPhoto: vi.fn(),
}));
const shirt: Garment = {
  id: "shirt",
  name: "Blue Oxford",
  category: "tops",
  subtype: "shirt",
  color: "blue",
  pattern: "solid",
  style: "business casual",
  available: true,
  image_url: "/media/shirt",
  thumbnail_url: "/media/shirt?thumbnail=true",
  analysis_status: "ready",
  analysis_error: null,
  alternatives: [],
  created_at: "",
};
const shoes: Garment = {
  ...shirt,
  id: "shoes",
  name: "Brown loafers",
  category: "footwear",
  subtype: "loafers",
  color: "brown",
};
const conversation: Conversation = {
  id: "conversation",
  constraints: {},
  messages: [],
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.items).mockResolvedValue([shirt, shoes]);
  vi.mocked(api.datasetStatus).mockResolvedValue({
    photo_count: 2,
    indexed_count: 2,
    ready: true,
  });
  vi.mocked(api.datasetItems).mockResolvedValue({
    items: [shirt, shoes],
    total: 2,
  });
  vi.mocked(api.latestBenchmark).mockResolvedValue(null);
  vi.mocked(api.status).mockResolvedValue({
    vision_ready: true,
    ollama_ready: true,
    ollama_model: "gemma3:4b",
    setup_hint: "",
  });
  vi.mocked(api.latestConversation).mockResolvedValue(null);
  vi.mocked(api.newConversation).mockResolvedValue(conversation);
});

describe("wardrobe", () => {
  it("filters categories and searches item names", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "Edit Blue Oxford" });
    await user.click(screen.getByRole("button", { name: "Shoes" }));
    expect(
      screen.queryByRole("button", { name: "Edit Blue Oxford" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Edit Brown loafers" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "All pieces" }));
    await user.type(
      screen.getByRole("textbox", { name: "Search wardrobe" }),
      "Oxford",
    );
    expect(
      screen.queryByRole("button", { name: "Edit Brown loafers" }),
    ).not.toBeInTheDocument();
  });

  it("saves only corrected fields and updates the grid", async () => {
    const user = userEvent.setup();
    vi.mocked(api.updateItem).mockResolvedValue({
      ...shirt,
      name: "Favorite shirt",
    });
    render(<App />);
    await user.click(
      await screen.findByRole("button", { name: "Edit Blue Oxford" }),
    );
    await user.clear(screen.getByLabelText("Item name"));
    await user.type(screen.getByLabelText("Item name"), "Favorite shirt");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByRole("button", { name: "Edit Favorite shirt" });
    expect(api.updateItem).toHaveBeenCalledWith("shirt", {
      name: "Favorite shirt",
    });
  });

  it("continues a batch after failure and supports retry", async () => {
    const user = userEvent.setup();
    vi.mocked(uploadPhoto)
      .mockRejectedValueOnce(new Error("Bad image"))
      .mockResolvedValueOnce({ ...shirt, id: "uploaded" })
      .mockResolvedValueOnce({ ...shoes, id: "retried" });
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Add pieces" }));
    await user.upload(screen.getByLabelText("Choose garment photos"), [
      new File(["one"], "one.jpg", { type: "image/jpeg" }),
      new File(["two"], "two.jpg", { type: "image/jpeg" }),
    ]);
    await screen.findByText("Added to your wardrobe");
    expect(uploadPhoto).toHaveBeenCalledTimes(2);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(uploadPhoto).toHaveBeenCalledTimes(3));
  });

  it("confirms deletion and removes the item", async () => {
    const user = userEvent.setup();
    vi.mocked(api.deleteItem).mockResolvedValue(undefined);
    render(<App />);
    await user.click(
      await screen.findByRole("button", { name: "Edit Blue Oxford" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Remove from wardrobe" }),
    );
    expect(api.deleteItem).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Yes, remove" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Edit Blue Oxford" }),
      ).not.toBeInTheDocument(),
    );
  });
});

describe("stylist", () => {
  it("keeps the draft when Ollama is unavailable", async () => {
    const user = userEvent.setup();
    vi.mocked(api.sendMessage).mockRejectedValue(new Error("Start Ollama"));
    render(<App />);
    await screen.findByRole("button", { name: "Edit Blue Oxford" });
    const input = screen.getByRole("textbox", { name: "Message your stylist" });
    await user.type(input, "Business casual please");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByRole("alert");
    expect(input).toHaveValue("Business casual please");
    expect(api.sendMessage).toHaveBeenCalledWith(
      "conversation",
      "Business casual please",
    );
  });

  it("renders the actual item images and missing components", async () => {
    const user = userEvent.setup();
    vi.mocked(api.sendMessage).mockResolvedValue({
      ...conversation,
      messages: [
        {
          id: "reply",
          role: "assistant",
          text: "Here is a look.",
          created_at: "",
          outfits: [
            {
              title: "Easy Oxford",
              explanation: "A simple combination.",
              item_ids: ["shirt", "shoes"],
              items: [shirt, shoes],
              missing_components: ["bottom"],
            },
          ],
        },
      ],
    });
    render(<App />);
    await screen.findByRole("button", { name: "Edit Blue Oxford" });
    await user.type(
      screen.getByRole("textbox", { name: "Message your stylist" }),
      "Business casual",
    );
    await user.click(screen.getByRole("button", { name: "Send message" }));
    const look = await screen.findByRole("button", {
      name: "View Easy Oxford",
    });
    expect(look.querySelector("img")).toHaveAttribute(
      "src",
      "/media/shirt?thumbnail=true",
    );
    expect(screen.getByText("To complete: bottom")).toBeInTheDocument();
    await user.click(look);
    expect(
      screen.getByRole("dialog", { name: "Easy Oxford" }),
    ).toBeInTheDocument();
  });

  it("does not allow an old look to be refined against the latest outfit list", async () => {
    const user = userEvent.setup();
    const outfit = {
      title: "Old look",
      explanation: "",
      item_ids: ["shirt"],
      items: [shirt],
      missing_components: ["bottom", "footwear"],
    };
    vi.mocked(api.latestConversation).mockResolvedValue({
      ...conversation,
      messages: [
        {
          id: "old",
          role: "assistant",
          text: "Before",
          created_at: "",
          outfits: [outfit],
        },
        {
          id: "new",
          role: "assistant",
          text: "Now",
          created_at: "",
          outfits: [{ ...outfit, title: "New look" }],
        },
      ],
    });
    render(<App />);
    await user.click(
      await screen.findByRole("button", { name: "View Old look" }),
    );
    expect(
      screen.queryByRole("button", { name: "Refine this look" }),
    ).not.toBeInTheDocument();
  });
});

describe("clear wardrobe", () => {
  it("requires confirmation and allows canceling", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      await screen.findByRole("button", { name: "Clear wardrobe" }),
    );
    expect(
      screen.getByRole("dialog", { name: "Clear your wardrobe?" }),
    ).toBeInTheDocument();
    expect(api.clearWardrobe).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(api.clearWardrobe).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "Edit Blue Oxford" }),
    ).toBeInTheDocument();
  });

  it("clears all pieces even when the wardrobe is filtered", async () => {
    const user = userEvent.setup();
    vi.mocked(api.clearWardrobe).mockResolvedValue(undefined);
    render(<App />);
    await screen.findByRole("button", { name: "Edit Blue Oxford" });
    await user.click(screen.getByRole("button", { name: "Shoes" }));
    await user.click(screen.getByRole("button", { name: "Clear wardrobe" }));
    expect(screen.getByText(/all 2 pieces/)).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Yes, clear wardrobe" }),
    );
    expect(
      await screen.findByRole("heading", {
        name: "Start with your favorites.",
      }),
    ).toBeInTheDocument();
    expect(api.clearWardrobe).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByRole("button", { name: "Edit Brown loafers" }),
    ).not.toBeInTheDocument();
  });

  it("keeps the confirmation open for a failed request and retry", async () => {
    const user = userEvent.setup();
    vi.mocked(api.clearWardrobe).mockRejectedValueOnce(
      new Error("Please retry"),
    );
    render(<App />);
    await user.click(
      await screen.findByRole("button", { name: "Clear wardrobe" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Yes, clear wardrobe" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Please retry");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    vi.mocked(api.clearWardrobe).mockResolvedValue(undefined);
    await user.click(
      screen.getByRole("button", { name: "Yes, clear wardrobe" }),
    );
    expect(
      await screen.findByRole("heading", {
        name: "Start with your favorites.",
      }),
    ).toBeInTheDocument();
  });
});

describe("DeepFashion2 evaluation", () => {
  it("keeps the dataset visible when an earlier personal request finishes late", async () => {
    const user = userEvent.setup();
    let finishPersonal!: (items: Garment[]) => void;
    vi.mocked(api.items).mockReturnValue(new Promise((resolve) => { finishPersonal = resolve; }));
    render(<App />);
    await user.click(screen.getByRole("button", { name: "DeepFashion2" }));
    await screen.findByRole("button", { name: "View Blue Oxford" });
    await act(async () => { finishPersonal([]); });
    expect(screen.getByRole("button", { name: "View Blue Oxford" })).toBeInTheDocument();
  });

  it("switches to the read-only dataset and shows benchmark results in the stylist", async () => {
    const user = userEvent.setup();
    vi.mocked(api.startBenchmark).mockResolvedValue({
      id: "benchmark-1",
      created_at: "",
      status: "complete",
      photo_count: 2,
      indexed_count: 2,
      error: null,
      cases: [{
        id: "casual",
        label: "Casual",
        prompt: "Give me three casual outfits.",
        follow_up_to: null,
        seconds: 4.2,
        outfit_count: 1,
        partial_count: 0,
        distinct_count: 1,
        message: "One option.",
        outfits: [{
          title: "Simple look",
          explanation: "A relaxed outfit.",
          item_ids: ["shirt", "shoes"],
          items: [shirt, shoes],
          missing_components: [],
        }],
        error: null,
      }],
    });
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "DeepFashion2" }));
    await screen.findByRole("button", { name: "View Blue Oxford" });
    expect(screen.queryByRole("button", { name: "Clear wardrobe" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Run benchmark" }));
    const results = await screen.findByRole("region", { name: "DeepFashion2 benchmark results" });
    expect(results).toHaveTextContent("Ten outfit requests");
    expect(results).toHaveTextContent(/1\s+rule-valid looks/);
  });
});
