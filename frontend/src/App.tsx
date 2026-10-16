import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUp,
  Check,
  CircleHelp,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Shirt,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { api } from "./api";
import {
  BenchmarkPanel,
  Dialog,
  ItemDialog,
  OutfitCard,
  OutfitDialog,
  UploadDialog,
} from "./components";
import { categories, categoryLabels } from "./types";
import type {
  Category,
  BenchmarkRun,
  Conversation,
  DatasetStatus,
  Garment,
  ModelStatus,
  Outfit,
  WardrobeId,
} from "./types";

export default function App() {
  const [items, setItems] = useState<Garment[]>([]);
  const [wardrobe, setWardrobe] = useState<WardrobeId>("personal");
  const [datasetStatus, setDatasetStatus] = useState<DatasetStatus | null>(null);
  const [datasetTotal, setDatasetTotal] = useState(0);
  const [benchmark, setBenchmark] = useState<BenchmarkRun | null>(null);
  const [benchmarkError, setBenchmarkError] = useState("");
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [status, setStatus] = useState<ModelStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [chatError, setChatError] = useState("");
  const [category, setCategory] = useState<Category | "all">("all");
  const [search, setSearch] = useState("");
  const [availableOnly, setAvailableOnly] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [clearError, setClearError] = useState("");
  const [selectedItem, setSelectedItem] = useState<Garment | null>(null);
  const [selectedOutfit, setSelectedOutfit] = useState<{
    outfit: Outfit;
    index: number;
    latest: boolean;
  } | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [mobileView, setMobileView] = useState<"wardrobe" | "stylist">(
    "wardrobe",
  );
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [pendingText, setPendingText] = useState("");
  const messagesEnd = useRef<HTMLDivElement>(null);
  const benchmarkTop = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const requestInFlight = useRef(false);
  const loadRequest = useRef(0);
  const datasetRequest = useRef(0);

  async function load() {
    const requestNumber = ++loadRequest.current;
    const filterNumber = datasetRequest.current;
    setLoading(true);
    setError("");
    try {
      const [collection, latest, readiness, source, latestBenchmark] = await Promise.all([
        wardrobe === "personal"
          ? api.items()
          : api.datasetItems(category, search),
        api.latestConversation(wardrobe),
        api.status(),
        api.datasetStatus(),
        api.latestBenchmark(),
      ]);
      if (requestNumber !== loadRequest.current) return;
      if (wardrobe === "personal" || filterNumber === datasetRequest.current) {
        setItems(Array.isArray(collection) ? collection : collection.items);
        setDatasetTotal(Array.isArray(collection) ? 0 : collection.total);
      }
      setConversation(latest);
      setStatus(readiness);
      setDatasetStatus(source);
      setBenchmark(latestBenchmark);
    } catch (error) {
      if (requestNumber !== loadRequest.current) return;
      setError(
        error instanceof Error
          ? error.message
          : "Could not load your wardrobe.",
      );
    } finally {
      if (requestNumber === loadRequest.current) setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, [wardrobe]);
  useEffect(() => {
    if (wardrobe !== "deepfashion2") return;
    const requestNumber = ++datasetRequest.current;
    const timer = window.setTimeout(() => {
      void api.datasetItems(category, search).then((page) => {
        if (requestNumber !== datasetRequest.current) return;
        setItems(page.items);
        setDatasetTotal(page.total);
      }).catch((problem) => {
        if (requestNumber === datasetRequest.current)
          setError(problem instanceof Error ? problem.message : "Could not load DeepFashion2.");
      });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [wardrobe, category, search]);
  useEffect(() => {
    if (benchmark?.status !== "running") return;
    const timer = window.setInterval(() => {
      void api.benchmark(benchmark.id).then(setBenchmark).catch(() => {
        setBenchmarkError("Could not refresh benchmark progress.");
      });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [benchmark?.id, benchmark?.status]);
  useEffect(() => {
    const messageList = messagesEnd.current?.parentElement;
    if (messageList && (sending || conversation?.messages.length)) {
      messageList.scrollTop = messageList.scrollHeight;
    }
  }, [conversation?.messages.length, sending, mobileView]);
  useEffect(() => {
    if (benchmark && !sending) {
      benchmarkTop.current?.scrollIntoView({ block: "start", behavior: "auto" });
    }
  }, [benchmark?.id, benchmark?.cases.length, benchmark?.status, mobileView]);

  function updateItem(item: Garment) {
    setItems((current) => [
      item,
      ...current.filter((existing) => existing.id !== item.id),
    ]);
    setSelectedItem((current) => (current?.id === item.id ? item : current));
  }
  async function clearWardrobe() {
    if (clearing || wardrobe !== "personal") return;
    setClearing(true);
    setClearError("");
    try {
      await api.clearWardrobe();
      setItems([]);
      setCategory("all");
      setSearch("");
      setAvailableOnly(false);
      setSelectedItem(null);
      setSelectedOutfit(null);
      setClearOpen(false);
    } catch (error) {
      try {
        setItems(await api.items());
      } catch {
        // Keep the current view if the server is unreachable.
      }
      setClearError(
        error instanceof Error
          ? error.message
          : "Could not clear your wardrobe. Please retry.",
      );
    } finally {
      setClearing(false);
    }
  }
  async function send(text = draft) {
    if (!text.trim() || requestInFlight.current) return;
    requestInFlight.current = true;
    setDraft(text);
    setSending(true);
    setPendingText(text);
    setChatError("");
    setMobileView("stylist");
    try {
      const active = conversation ?? (await api.newConversation(wardrobe));
      setConversation(active);
      const updated = await api.sendMessage(active.id, text.trim());
      setConversation(updated);
      setDraft("");
    } catch (error) {
      setChatError(
        error instanceof Error
          ? error.message
          : "The stylist could not finish. Try again.",
      );
    } finally {
      requestInFlight.current = false;
      setSending(false);
      setPendingText("");
      composer.current?.focus();
    }
  }
  async function newConversation() {
    if (sending) return;
    try {
      setConversation(await api.newConversation(wardrobe));
      setChatError("");
      setDraft("");
    } catch (error) {
      setChatError(
        error instanceof Error
          ? error.message
          : "Could not start a conversation.",
      );
    }
  }
  function switchWardrobe(next: WardrobeId) {
    if (next === wardrobe || sending || benchmark?.status === "running") return;
    loadRequest.current += 1;
    datasetRequest.current += 1;
    setWardrobe(next);
    setConversation(null);
    setItems([]);
    setCategory("all");
    setSearch("");
    setAvailableOnly(false);
    setSelectedItem(null);
    setSelectedOutfit(null);
    setChatError("");
  }
  async function loadMore() {
    try {
      const page = await api.datasetItems(category, search, items.length);
      setItems((current) => [...current, ...page.items]);
      setDatasetTotal(page.total);
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "Could not load more photos.");
    }
  }
  async function startBenchmark() {
    setBenchmarkError("");
    setMobileView("stylist");
    try {
      setBenchmark(await api.startBenchmark());
    } catch (problem) {
      setBenchmarkError(problem instanceof Error ? problem.message : "Could not start the benchmark.");
    }
  }
  function currentOutfit(outfit: Outfit): Outfit {
    if (wardrobe === "deepfashion2") return outfit;
    return {
      ...outfit,
      items: outfit.item_ids.map(
        (id) =>
          items.find((item) => item.id === id) ?? {
            id,
            name: "Removed item",
            deleted: true,
            available: false,
            image_url: null,
            thumbnail_url: null,
          },
      ),
    };
  }
  const visibleItems = items.filter(
    (item) =>
      (wardrobe === "deepfashion2" || category === "all" || item.category === category) &&
      (!availableOnly || item.available) &&
      (wardrobe === "deepfashion2" || `${item.name} ${item.color} ${item.subtype} ${item.style}`
        .toLowerCase()
        .includes(search.toLowerCase())),
  );
  const ready = status?.vision_ready && status?.ollama_ready;
  const messages = conversation?.messages ?? [];
  const latestOutfitMessage = [...messages]
    .reverse()
    .find((message) => message.outfits.length);

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="wordmark" href="/" aria-label="Wardrobe home">
          <span className="brand-symbol">
            <Shirt size={22} strokeWidth={1.3} />
          </span>
          wardrobe<span className="wordmark-period">.</span>
        </a>
        <span className="header-note">
          A little less deciding. A little more you.
        </span>
        <div className="header-actions">
          <button
            className="icon-button help-button"
            aria-label="About your wardrobe"
            onClick={() => setHelpOpen(true)}
          >
            <CircleHelp size={18} />
          </button>
        </div>
      </header>
      <nav className="mobile-nav" aria-label="Main views">
        <button
          aria-current={mobileView === "wardrobe" ? "page" : undefined}
          onClick={() => setMobileView("wardrobe")}
        >
          Wardrobe
        </button>
        <button
          aria-current={mobileView === "stylist" ? "page" : undefined}
          onClick={() => setMobileView("stylist")}
        >
          Stylist
        </button>
      </nav>
      <main className="workspace">
        <section
          className={`wardrobe-panel ${mobileView === "wardrobe" ? "mobile-visible" : ""}`}
          aria-label="Your wardrobe"
        >
          <div className="wardrobe-switch" aria-label="Choose wardrobe">
            <button
              aria-pressed={wardrobe === "personal"}
              disabled={sending || benchmark?.status === "running"}
              onClick={() => switchWardrobe("personal")}
            >
              Your wardrobe
            </button>
            <button
              aria-pressed={wardrobe === "deepfashion2"}
              disabled={sending || benchmark?.status === "running"}
              onClick={() => switchWardrobe("deepfashion2")}
            >
              DeepFashion2
            </button>
          </div>
          <div className="collection-heading">
            <div>
              <p className="eyebrow">
                {wardrobe === "personal" ? "Your personal collection" : "Validation image collection"}
              </p>
              <h1>
                {wardrobe === "personal" ? (
                  <>Good pieces.<br /><em>New possibilities.</em></>
                ) : (
                  <>DeepFashion2.<br /><em>A larger wardrobe.</em></>
                )}
              </h1>
              <p className="collection-description">
                {wardrobe === "personal"
                  ? "Everything you own, thoughtfully put together."
                  : "Local validation photos, indexed with FashionCLIP. Read-only."}
              </p>
            </div>
            {wardrobe === "personal" && <div className="collection-actions">
              <button
                className="button primary add-button"
                onClick={() => setUploadOpen(true)}
              >
                <Plus size={16} />
                Add pieces
              </button>
              {items.length > 0 && (
                <button
                  className="text-button"
                  disabled={loading || sending}
                  onClick={() => {
                    setClearError("");
                    setClearOpen(true);
                  }}
                >
                  Clear wardrobe
                </button>
              )}
            </div>}
          </div>
          {wardrobe === "deepfashion2" && (
            <p className="dataset-note">
              {datasetStatus?.indexed_count.toLocaleString() ?? "0"} of {datasetStatus?.photo_count.toLocaleString() ?? "0"} local photos indexed. This collection contains clothing categories but no footwear, so suggestions may be partial.
            </p>
          )}
          <div className="collection-tools">
            <div className="collection-count">
              <span>{wardrobe === "personal" ? "THE WARDROBE" : "DEEPFASHION2"}</span>
              <span className="count">
                {(wardrobe === "personal" ? items.length : datasetTotal).toLocaleString()}
              </span>
            </div>
            <div className="search-tools">
              <label className="search-box">
                <Search size={15} />
                <input
                  aria-label="Search wardrobe"
                  placeholder="Find a piece"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
                {search && (
                  <button
                    className="icon-button"
                    aria-label="Clear search"
                    onClick={() => setSearch("")}
                  >
                    <X size={13} />
                  </button>
                )}
              </label>
              {wardrobe === "personal" && <button
                className={`icon-button availability-filter ${availableOnly ? "active" : ""}`}
                aria-label="Show available pieces only"
                aria-pressed={availableOnly}
                onClick={() => setAvailableOnly(!availableOnly)}
              >
                <SlidersHorizontal size={16} />
              </button>}
            </div>
          </div>
          <nav className="category-tabs" aria-label="Garment categories">
            <button
              aria-pressed={category === "all"}
              onClick={() => setCategory("all")}
            >
              All pieces
            </button>
            {categories.map((value) => (
              <button
                key={value}
                aria-pressed={category === value}
                onClick={() => setCategory(value)}
              >
                {categoryLabels[value]}
              </button>
            ))}
          </nav>
          {error && (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <button className="text-button" onClick={() => void load()}>
                Retry
              </button>
            </div>
          )}
          {loading ? (
            <div className="loading-state" role="status">
              <Loader2 className="spin" size={20} />
              Opening your wardrobe…
            </div>
          ) : items.length === 0 && wardrobe === "deepfashion2" ? (
            <div className="empty-wardrobe">
              <h2>{datasetStatus?.photo_count ? "Index the collection first." : "Add the DeepFashion2 photos first."}</h2>
              <p>{datasetStatus?.photo_count ? "Run the local indexing step in the README, then refresh." : "Place validation JPEGs in data/deepfashion2."}</p>
            </div>
          ) : items.length === 0 ? (
            <div className="empty-wardrobe">
              <div className="empty-still-life" aria-hidden="true">
                <div className="outline-piece piece-one">
                  <Shirt size={76} strokeWidth={0.65} />
                </div>
                <div className="outline-piece piece-two">
                  <Shirt size={64} strokeWidth={0.65} />
                </div>
                <span className="still-life-caption">
                  A collection that’s entirely yours.
                </span>
              </div>
              <h2>Start with your favorites.</h2>
              <p>
                Add a few pieces you love. We’ll find the details
                <br className="desktop-break" /> and help you see them in a new
                light.
              </p>
              <button
                className="button primary"
                onClick={() => setUploadOpen(true)}
              >
                Add your first pieces <ArrowRight size={16} />
              </button>
              <span className="small muted">
                One garment per photo. Always editable.
              </span>
            </div>
          ) : visibleItems.length === 0 ? (
            <div className="no-results">
              <Shirt size={28} strokeWidth={1} />
              <h2>No pieces here yet.</h2>
              <p>Try another category or a different search.</p>
              <button
                className="text-button"
                onClick={() => {
                  setCategory("all");
                  setSearch("");
                  setAvailableOnly(false);
                }}
              >
                Show all pieces <ArrowRight size={14} />
              </button>
            </div>
          ) : (
            <div className="garment-grid">
              {visibleItems.map((item, index) => (
                <button
                  className={`garment-card ${!item.available ? "unavailable" : ""}`}
                  key={item.id}
                  onClick={() => setSelectedItem(item)}
                  aria-label={`${wardrobe === "personal" ? "Edit" : "View"} ${item.name}`}
                >
                  <div className="garment-image">
                    <img
                      src={item.thumbnail_url}
                      alt={item.name}
                      loading="lazy"
                    />
                    <span className="piece-index">
                      {(index + 1).toString().padStart(2, "0")}
                    </span>
                    {!item.available ? (
                      <span className="item-badge">Away for now</span>
                    ) : item.category === "unrecognized" ? (
                      <span className="item-badge">Needs a look</span>
                    ) : null}
                    <span className="edit-hint">
                      View details <ArrowRight size={13} />
                    </span>
                  </div>
                  <div className="garment-caption">
                    <h3>{item.name}</h3>
                    <span>{item.subtype || categoryLabels[item.category]}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
          {wardrobe === "deepfashion2" && items.length < datasetTotal && (
            <button className="button secondary load-more" onClick={() => void loadMore()}>
              Load more photos
            </button>
          )}
          <footer className="collection-footer">
            <span>{wardrobe === "personal" ? "Your clothes. Your combinations." : "DeepFashion2 validation photos."}</span>
            <span>{wardrobe === "personal" ? "Made for everyday dressing." : "For local evaluation."}</span>
          </footer>
        </section>
        <aside
          className={`stylist-panel ${mobileView === "stylist" ? "mobile-visible" : ""}`}
          aria-label="Personal stylist"
        >
          <div className="stylist-heading">
            <div>
              <span className="eyebrow">A fresh perspective</span>
              <h2>Your stylist</h2>
            </div>
            <div className="stylist-actions">
              {wardrobe === "deepfashion2" && (
                <button
                  className="button secondary benchmark-button"
                  disabled={sending || benchmark?.status === "running" || !datasetStatus?.ready}
                  onClick={() => void startBenchmark()}
                >
                  {benchmark?.status === "running" ? "Running…" : "Run benchmark"}
                </button>
              )}
              <button
                className="icon-button"
                aria-label="New conversation"
                title="New conversation"
                disabled={sending || benchmark?.status === "running"}
                onClick={() => void newConversation()}
              >
                <Plus size={20} />
              </button>
            </div>
          </div>
          <div className="conversation" aria-live="polite" aria-busy={sending}>
            {messages.length === 0 && !sending && (
              <div className="stylist-welcome">
                <div className="stylist-monogram" aria-hidden="true">
                  w.
                </div>
                <h3>
                  Let’s put something
                  <br />
                  <em>together.</em>
                </h3>
                <p>
                  An occasion, a mood, a favorite piece.
                  <br />
                  Tell me where you’d like to start.
                </p>
                <div className="prompt-suggestions">
                  {[
                    "A few business-casual options",
                    "Something relaxed for the weekend",
                    "A fresh way to wear my favorites",
                  ].map((prompt) => (
                    <button key={prompt} onClick={() => void send(prompt)}>
                      {prompt}
                      <ArrowUp size={14} />
                    </button>
                  ))}
                </div>
                <div className="stylist-note">
                  <Check size={14} />
                  <span>
                    Outfits from your wardrobe.
                    <br />
                    Nothing you need to buy.
                  </span>
                </div>
              </div>
            )}
            {messages.map((message) => (
              <div key={message.id} className={`message ${message.role}`}>
                <span className="message-label">
                  {message.role === "user" ? "You" : "Your stylist"}
                </span>
                <p>{message.text}</p>
                {message.outfits.map((outfit, index) => (
                  <OutfitCard
                    key={`${message.id}-${index}`}
                    outfit={currentOutfit(outfit)}
                    onOpen={() =>
                      setSelectedOutfit({
                        outfit,
                        index,
                        latest: message.id === latestOutfitMessage?.id,
                      })
                    }
                  />
                ))}
              </div>
            ))}
            {wardrobe === "deepfashion2" && benchmark && (
              <div ref={benchmarkTop}>
                <BenchmarkPanel result={benchmark} onOpen={(outfit) => setSelectedOutfit({ outfit, index: 0, latest: false })} />
              </div>
            )}
            {benchmarkError && <p className="error" role="alert">{benchmarkError}</p>}
            {sending && (
              <>
                <div className="message user pending">
                  <span className="message-label">You</span>
                  <p>{pendingText}</p>
                </div>
                <div className="thinking" role="status">
                  <Loader2 size={15} className="spin" />
                  <span>Considering your pieces…</span>
                </div>
              </>
            )}
            <div ref={messagesEnd} />
          </div>
          <div className="composer-area">
            {chatError && (
              <p className="error" role="alert">
                {chatError}
              </p>
            )}
            <form
              className="composer"
              onSubmit={(event) => {
                event.preventDefault();
                void send();
              }}
            >
              <textarea
                ref={composer}
                rows={2}
                maxLength={2000}
                aria-label="Message your stylist"
                placeholder="What are you dressing for?"
                value={draft}
                disabled={sending}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (
                    event.key === "Enter" &&
                    !event.shiftKey &&
                    !event.nativeEvent.isComposing
                  ) {
                    event.preventDefault();
                    void send();
                  }
                }}
              />
              <button
                className="send-button"
                aria-label="Send message"
                disabled={sending || !draft.trim()}
              >
                {sending ? (
                  <Loader2 size={17} className="spin" />
                ) : (
                  <ArrowUp size={19} />
                )}
              </button>
            </form>
            <p className="composer-note">
              {wardrobe === "personal" ? "Only your wardrobe. Entirely on your device." : "DeepFashion2 photos. Entirely on your device."}
            </p>
          </div>
        </aside>
      </main>
      {clearOpen && (
        <Dialog
          title="Clear your wardrobe?"
          onClose={() => {
            if (!clearing) setClearOpen(false);
          }}
        >
          <p className="dialog-intro muted">
            Are you sure? This permanently removes all {items.length} pieces and
            their photos, including any hidden by filters. This cannot be
            undone. Your conversations will stay, with removed pieces marked
            unavailable.
          </p>
          {clearError && (
            <p className="error-banner" role="alert">
              {clearError}
            </p>
          )}
          <div className="clear-actions">
            <button
              autoFocus
              className="button secondary"
              disabled={clearing}
              onClick={() => setClearOpen(false)}
            >
              Cancel
            </button>
            <button
              className="button primary"
              disabled={clearing}
              onClick={() => void clearWardrobe()}
            >
              {clearing ? "Clearing…" : "Yes, clear wardrobe"}
            </button>
          </div>
        </Dialog>
      )}
      {uploadOpen && (
        <UploadDialog
          onClose={() => setUploadOpen(false)}
          onUploaded={updateItem}
        />
      )}
      {selectedItem && wardrobe === "personal" && (
        <ItemDialog
          key={selectedItem.id}
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
          onUpdated={updateItem}
          onDeleted={(id) =>
            setItems((current) => current.filter((item) => item.id !== id))
          }
        />
      )}
      {selectedItem && wardrobe === "deepfashion2" && (
        <Dialog title={selectedItem.name} onClose={() => setSelectedItem(null)}>
          <div className="dataset-detail">
            <img src={selectedItem.image_url} alt={selectedItem.name} />
            <p>{selectedItem.subtype} · {selectedItem.color} · {selectedItem.style}</p>
            <p className="small muted">DeepFashion2 validation image. Labels are FashionCLIP suggestions.</p>
          </div>
        </Dialog>
      )}
      {selectedOutfit && (
        <OutfitDialog
          outfit={currentOutfit(selectedOutfit.outfit)}
          canRefine={selectedOutfit.latest}
          onClose={() => setSelectedOutfit(null)}
          onRefine={() => {
            setDraft(`For option ${selectedOutfit.index + 1}, `);
            setSelectedOutfit(null);
            setMobileView("stylist");
            composer.current?.focus();
          }}
        />
      )}
      {helpOpen && (
        <Dialog
          title="Your wardrobe, at home."
          onClose={() => setHelpOpen(false)}
        >
          <p className="dialog-intro muted">
            Your photos and conversations stay on this computer. Once the models
            are downloaded, no internet connection is needed.
          </p>
          <div className="setup-status">
            <p>
              <span
                className={`status-dot ${status?.vision_ready ? "ready" : ""}`}
              />
              Clothing recognition{" "}
              <strong>{status?.vision_ready ? "Ready" : "Setup needed"}</strong>
            </p>
            <p>
              <span
                className={`status-dot ${status?.ollama_ready ? "ready" : ""}`}
              />
              Personal stylist{" "}
              <strong>{status?.ollama_ready ? "Ready" : "Start Ollama"}</strong>
            </p>
          </div>
          {!ready && (
            <div className="setup-instructions">
              <p>From the project folder:</p>
              <code>.venv/bin/python scripts/download_models.py</code>
              <code>ollama pull gemma3:4b</code>
              <p>
                Open Ollama or run <code>ollama serve</code>, then check again.
              </p>
              <button
                className="button secondary"
                onClick={() =>
                  void api
                    .status()
                    .then(setStatus)
                    .catch((error) => setError(String(error)))
                }
              >
                <RefreshCw size={14} />
                Check connection
              </button>
            </div>
          )}
          <p className="small muted">
            Photograph one garment at a time. Suggested details are a starting
            point—you can change them whenever you like.
          </p>
        </Dialog>
      )}
    </div>
  );
}
