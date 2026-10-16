import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  ArrowUpRight,
  Check,
  Loader2,
  Plus,
  RefreshCw,
  Shirt,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { api, uploadPhoto } from "./api";
import { categories, categoryLabels } from "./types";
import type { BenchmarkRun, Garment, GarmentChanges, Outfit } from "./types";

export function Dialog({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    return () => {
      element.close();
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      className={wide ? "dialog wide-dialog" : "dialog"}
      aria-label={title}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="dialog-inner">
        <div className="dialog-heading">
          <h2>{title}</h2>
          <button
            className="icon-button"
            aria-label="Close dialog"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}

interface UploadEntry {
  id: number;
  file: File;
  progress: number;
  state: "waiting" | "uploading" | "analyzing" | "done" | "failed";
  error?: string;
}
export function UploadDialog({
  onClose,
  onUploaded,
}: {
  onClose: () => void;
  onUploaded: (item: Garment) => void;
}) {
  const [entries, setEntries] = useState<UploadEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const nextId = useRef(0);
  const processing = useRef(false);
  const input = useRef<HTMLInputElement>(null);
  const update = (id: number, changes: Partial<UploadEntry>) =>
    setEntries((current) =>
      current.map((entry) =>
        entry.id === id ? { ...entry, ...changes } : entry,
      ),
    );
  async function process(batch: UploadEntry[]) {
    if (processing.current) return;
    processing.current = true;
    setBusy(true);
    for (const entry of batch) {
      if (
        !/\.(jpe?g|png|webp)$/i.test(entry.file.name) ||
        entry.file.size > 10 * 1024 * 1024
      ) {
        update(entry.id, {
          state: "failed",
          error: "Choose a JPEG, PNG, or WebP up to 10 MB.",
        });
        continue;
      }
      update(entry.id, { state: "uploading", error: undefined, progress: 0 });
      try {
        const item = await uploadPhoto(entry.file, (progress) =>
          update(entry.id, {
            progress,
            state: progress === 100 ? "analyzing" : "uploading",
          }),
        );
        onUploaded(item);
        update(entry.id, {
          state: "done",
          progress: 100,
          error:
            item.analysis_status === "failed"
              ? "Saved. Open this item to set its tags or retry analysis."
              : undefined,
        });
      } catch (error) {
        update(entry.id, {
          state: "failed",
          error: error instanceof Error ? error.message : "Upload failed.",
        });
      }
    }
    processing.current = false;
    setBusy(false);
  }
  function addFiles(files: FileList | File[]) {
    if (processing.current) return;
    const additions = Array.from(files).map((file) => ({
      id: nextId.current++,
      file,
      progress: 0,
      state: "waiting" as const,
    }));
    setEntries((current) => [...current, ...additions]);
    void process(additions);
  }
  return (
    <Dialog
      title="Add to your wardrobe"
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <p className="muted dialog-intro">
        One piece per photo. A little natural light goes a long way.
      </p>
      <input
        ref={input}
        className="visually-hidden"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        multiple
        aria-label="Choose garment photos"
        onChange={(event) => {
          if (event.target.files) addFiles(event.target.files);
          event.target.value = "";
        }}
        disabled={busy}
      />
      <button
        className={`drop-zone ${dragging ? "dragging" : ""}`}
        disabled={busy}
        onClick={() => input.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          addFiles(event.dataTransfer.files);
        }}
      >
        <Upload size={27} strokeWidth={1.3} />
        <span>Drop your photos here</span>
        <span className="muted small">
          or click to browse · JPG, PNG, WebP · 10 MB each
        </span>
      </button>
      <div className="upload-list" aria-live="polite">
        {entries.map((entry) => (
          <div className="upload-entry" key={entry.id}>
            {entry.state === "done" ? (
              <Check size={17} />
            ) : entry.state === "failed" ? (
              <X size={17} />
            ) : (
              <Loader2 size={17} className="spin" />
            )}
            <div>
              <strong>{entry.file.name}</strong>
              <span>
                {entry.error ||
                  {
                    waiting: "Waiting",
                    uploading: `Uploading ${entry.progress}%`,
                    analyzing: "Finding the details…",
                    done: "Added to your wardrobe",
                    failed: "Upload failed",
                  }[entry.state]}
              </span>
            </div>
            {entry.state === "failed" && (
              <button
                className="text-button"
                disabled={busy}
                onClick={() => void process([entry])}
              >
                Retry
              </button>
            )}
          </div>
        ))}
      </div>
      <div className="dialog-footer">
        <span className="muted small">
          {busy
            ? "Keep this window open while your pieces are added."
            : "You can always edit the suggested details."}
        </span>
        <button className="button primary" disabled={busy} onClick={onClose}>
          {busy ? "Adding pieces…" : "Done"}
        </button>
      </div>
    </Dialog>
  );
}

export function ItemDialog({
  item,
  onClose,
  onUpdated,
  onDeleted,
}: {
  item: Garment;
  onClose: () => void;
  onUpdated: (item: Garment) => void;
  onDeleted: (id: string) => void;
}) {
  const [form, setForm] = useState<GarmentChanges>({
    name: item.name,
    category: item.category,
    subtype: item.subtype,
    color: item.color,
    pattern: item.pattern,
    style: item.style,
    available: item.available,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  async function save() {
    setBusy(true);
    setError("");
    try {
      const changes = Object.fromEntries(
        Object.entries(form).filter(
          ([key, value]) => value !== item[key as keyof GarmentChanges],
        ),
      );
      onUpdated(await api.updateItem(item.id, changes));
      onClose();
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Could not save changes.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    setBusy(true);
    setError("");
    try {
      await api.deleteItem(item.id);
      onDeleted(item.id);
      onClose();
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Could not remove item.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function analyze() {
    setBusy(true);
    setError("");
    try {
      const updated = await api.analyzeItem(item.id);
      onUpdated(updated);
      setForm({
        name: updated.name,
        category: updated.category,
        subtype: updated.subtype,
        color: updated.color,
        pattern: updated.pattern,
        style: updated.style,
        available: updated.available,
      });
      if (updated.analysis_error) setError(updated.analysis_error);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Analysis failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      title="The details"
      wide
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <div className="item-editor">
        <div className="editor-image">
          <img src={item.image_url} alt={item.name} />
        </div>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <p className="eyebrow">Make it yours</p>
          <label>
            Item name
            <input
              value={form.name}
              maxLength={120}
              required
              onChange={(event) =>
                setForm({ ...form, name: event.target.value })
              }
            />
          </label>
          <div className="field-pair">
            <label>
              Category
              <select
                value={form.category}
                onChange={(event) =>
                  setForm({
                    ...form,
                    category: event.target.value as Garment["category"],
                  })
                }
              >
                {categories.map((category) => (
                  <option key={category} value={category}>
                    {categoryLabels[category]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Type
              <input
                value={form.subtype}
                maxLength={80}
                onChange={(event) =>
                  setForm({ ...form, subtype: event.target.value })
                }
              />
            </label>
          </div>
          <div className="field-pair">
            <label>
              Color
              <input
                value={form.color}
                maxLength={80}
                onChange={(event) =>
                  setForm({ ...form, color: event.target.value })
                }
              />
            </label>
            <label>
              Pattern
              <input
                value={form.pattern}
                maxLength={80}
                onChange={(event) =>
                  setForm({ ...form, pattern: event.target.value })
                }
              />
            </label>
          </div>
          <label>
            Style
            <input
              value={form.style}
              maxLength={80}
              placeholder="For example, business casual"
              onChange={(event) =>
                setForm({ ...form, style: event.target.value })
              }
            />
          </label>
          <label className="check-label">
            <input
              type="checkbox"
              checked={form.available}
              onChange={(event) =>
                setForm({ ...form, available: event.target.checked })
              }
            />
            Available for outfits
          </label>
          {item.analysis_status !== "ready" && (
            <p className="small muted">
              These details need a look. Edit them here, or retry the photo
              analysis.
            </p>
          )}
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <div className="editor-actions">
            <button
              type="button"
              className="text-button"
              disabled={busy}
              onClick={() => void analyze()}
            >
              <RefreshCw size={14} />
              Analyze again
            </button>
            <button
              className="button primary"
              disabled={busy || !form.name.trim()}
            >
              {busy ? "Working…" : "Save changes"}
            </button>
          </div>
        </form>
      </div>
      <div className="delete-row">
        {confirmDelete ? (
          <>
            <span className="small">Remove this piece and its photo?</span>
            <button
              className="text-button"
              disabled={busy}
              onClick={() => setConfirmDelete(false)}
            >
              Keep it
            </button>
            <button
              className="text-button danger"
              disabled={busy}
              onClick={() => void remove()}
            >
              Yes, remove
            </button>
          </>
        ) : (
          <button
            className="text-button muted"
            disabled={busy}
            onClick={() => setConfirmDelete(true)}
          >
            <Trash2 size={14} />
            Remove from wardrobe
          </button>
        )}
      </div>
    </Dialog>
  );
}

export function OutfitCard({
  outfit,
  onOpen,
}: {
  outfit: Outfit;
  onOpen: () => void;
}) {
  return (
    <button
      className="outfit-card"
      onClick={onOpen}
      aria-label={`View ${outfit.title}`}
    >
      <div className="outfit-images">
        {outfit.items.map((item) => (
          <div key={item.id}>
            {item.thumbnail_url ? (
              <img src={item.thumbnail_url} alt={item.name} loading="lazy" />
            ) : (
              <span className="removed-piece">
                <Shirt size={22} />
                Removed
              </span>
            )}
          </div>
        ))}
      </div>
      <div className="outfit-heading">
        <h3>{outfit.title}</h3>
        <ArrowUpRight size={16} />
      </div>
      <p>{outfit.explanation}</p>
      {outfit.missing_components.length > 0 && (
        <span className="partial-label">
          To complete: {outfit.missing_components.join(", ")}
        </span>
      )}
    </button>
  );
}

export function BenchmarkPanel({
  result,
  onOpen,
}: {
  result: BenchmarkRun;
  onOpen: (outfit: Outfit) => void;
}) {
  const outfitCount = result.cases.reduce((total, item) => total + item.outfit_count, 0);
  const partialCount = result.cases.reduce((total, item) => total + item.partial_count, 0);
  const successfulCases = result.cases.filter((item) => item.outfit_count > 0 && !item.error).length;
  return (
    <section className="benchmark-panel" aria-label="DeepFashion2 benchmark results">
      <span className="message-label">Evaluation · DeepFashion2</span>
      <div className="benchmark-heading">
        <h3>Ten outfit requests</h3>
        <span>{result.status === "running" ? `${result.cases.length}/10 running` : result.status}</span>
      </div>
      <p className="benchmark-description">
        {result.indexed_count.toLocaleString()} local validation photos. Each prompt uses this wardrobe only; follow-ups reuse the named earlier result. Style quality is not automatically scored.
      </p>
      <div className="benchmark-summary">
        <span><strong>{successfulCases}/{result.cases.length}</strong> prompts with outfits</span>
        <span><strong>{outfitCount}</strong> rule-valid looks</span>
        <span><strong>{partialCount}</strong> partial looks</span>
      </div>
      {result.error && <p className="error" role="alert">{result.error}</p>}
      <div className="benchmark-cases">
        {result.cases.map((item, index) => (
          <details key={item.id} className="benchmark-case">
            <summary>
              <span className="benchmark-number">{String(index + 1).padStart(2, "0")}</span>
              <span className="benchmark-case-title">{item.label}</span>
              <span className="benchmark-case-meta">{item.outfit_count} looks · {item.seconds.toFixed(1)}s</span>
            </summary>
            <div className="benchmark-case-body">
              <p className="benchmark-prompt">“{item.prompt}”</p>
              {item.follow_up_to && <p className="small muted">Follow-up to {item.follow_up_to}.</p>}
              {item.error && <p className="error">{item.error}</p>}
              {item.message && <p className="small muted">{item.message}</p>}
              <p className="small muted">
                {item.distinct_count} distinct combinations · {item.partial_count} missing footwear or other pieces
              </p>
              {item.outfits.map((outfit, position) => (
                <OutfitCard key={`${item.id}-${position}`} outfit={outfit} onOpen={() => onOpen(outfit)} />
              ))}
            </div>
          </details>
        ))}
        {result.status === "running" && <p className="benchmark-working"><Loader2 className="spin" size={15} /> Evaluating the next request…</p>}
      </div>
    </section>
  );
}

export function OutfitDialog({
  outfit,
  onClose,
  onRefine,
  canRefine,
}: {
  outfit: Outfit;
  onClose: () => void;
  onRefine: () => void;
  canRefine: boolean;
}) {
  return (
    <Dialog title={outfit.title} wide onClose={onClose}>
      <p className="muted dialog-intro">{outfit.explanation}</p>
      <div className="look-grid">
        {outfit.items.map((item) => (
          <div key={item.id}>
            <div className="look-image">
              {item.image_url ? (
                <img src={item.image_url} alt={item.name} />
              ) : (
                <Shirt size={38} />
              )}
            </div>
            <h3>{item.name}</h3>
            {!item.available && (
              <span className="small muted">Currently unavailable</span>
            )}
          </div>
        ))}
      </div>
      <div className="dialog-footer">
        <span className="small muted">
          {outfit.missing_components.length
            ? `Still needs: ${outfit.missing_components.join(", ")}`
            : "Every piece, already yours."}
        </span>
        {canRefine ? (
          <button className="button primary" onClick={onRefine}>
            Refine this look <Plus size={15} />
          </button>
        ) : (
          <span className="small muted">
            A look from an earlier conversation turn.
          </span>
        )}
      </div>
    </Dialog>
  );
}
