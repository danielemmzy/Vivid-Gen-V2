"use client";

import {
  AudioLines,
  Check,
  ChevronDown,
  Clapperboard,
  Copy,
  Film,
  Layers3,
  Maximize2,
  Mic2,
  Minus,
  MousePointer2,
  Music2,
  Pause,
  Play,
  Plus,
  Redo2,
  Scissors,
  Settings2,
  Sparkles,
  Type,
  Undo2,
  Volume2,
  VolumeX,
  WandSparkles,
  Trash2,
  Upload,
  Video,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import type { Shot } from "~/actions/projects";
import {
  getProjectAssetUploadUrl,
  listProjectAssets,
  registerProjectAsset,
  renderEditorTimeline,
  saveEditorTimeline,
  type EditorAsset,
  type EditorTimeline,
} from "~/actions/projects";
import { cn } from "~/lib/utils";

type Clip = {
  id: string;
  shotId: string;
  title: string;
  prompt: string;
  duration: number;
  trimStart: number;
  trimEnd: number;
  transition: "none" | "fade" | "dissolve" | "wipe";
  volume: number;
  muted: boolean;
};
type TextLayer = {
  id: string;
  text: string;
  start: number;
  duration: number;
  style: "title" | "caption" | "label";
  clipId?: string | null;
  clipOffset?: number;
};
type AudioLayer = {
  id: string;
  name: string;
  assetId: string | null;
  start: number;
  duration: number;
  volume: number;
  kind: "music" | "voice" | "sfx";
  loop?: boolean;
};
type StudioState = {
  version: 1;
  clips: Clip[];
  textLayers: TextLayer[];
  audioLayers: AudioLayer[];
  aspectRatio: string;
  zoom: number;
  selectedId: string | null;
};
const defaults = (shots: Shot[], aspectRatio: string): StudioState => ({
  version: 1,
  clips: [...shots]
    .sort((a, b) => a.order_index - b.order_index)
    .map((shot, i) => ({
      id: `clip-${shot.id}`,
      shotId: shot.id,
      title: `Scene ${i + 1}`,
      prompt: shot.prompt,
      duration: Math.max(1, Number(shot.duration_seconds ?? 5)),
      trimStart: 0,
      trimEnd: Math.min(
        Math.max(
          0,
          Number(shot.duration_seconds ?? 5) -
            Number(
              shot.timeline_duration_seconds ?? shot.duration_seconds ?? 5,
            ),
        ),
        Math.max(0, Number(shot.duration_seconds ?? 5) - 0.5),
      ),
      transition: "none",
      volume: 100,
      muted: false,
    })),
  textLayers: [],
  audioLayers: [],
  aspectRatio,
  zoom: 1,
  selectedId: shots[0] ? `clip-${shots[0].id}` : null,
});
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const visibleDuration = (clip: Clip) =>
  Math.max(0.05, clip.duration - clip.trimStart - clip.trimEnd);
const incomingOverlap = (clip: Clip, previous: Clip | undefined) =>
  clip.transition !== "none" && previous
    ? Math.min(
        0.5,
        Math.max(0, visibleDuration(clip) - 0.05),
        Math.max(0, visibleDuration(previous) - 0.05),
      )
    : 0;
const timelineDuration = (clips: Clip[]) =>
  clips.reduce(
    (sum, clip, index) =>
      sum + visibleDuration(clip) - incomingOverlap(clip, clips[index - 1]),
    0,
  );
const clipStartInTimeline = (clips: Clip[], id: string) => {
  const index = clips.findIndex((clip) => clip.id === id);
  if (index <= 0) return 0;
  return clips
    .slice(0, index)
    .reduce(
      (sum, clip, i) =>
        sum + visibleDuration(clip) - incomingOverlap(clips[i + 1]!, clip),
      0,
    );
};
const normalizeLayerTiming = (draft: StudioState) => {
  const duration = timelineDuration(draft.clips);
  for (const layer of draft.textLayers) {
    const anchoredClip = layer.clipId
      ? draft.clips.find((clip) => clip.id === layer.clipId)
      : undefined;
    if (anchoredClip && layer.clipId) {
      const offset = Math.max(
        0,
        Math.min(
          Number(layer.clipOffset ?? 0),
          visibleDuration(anchoredClip) - 0.05,
        ),
      );
      layer.clipOffset = offset;
      layer.start = clipStartInTimeline(draft.clips, anchoredClip.id) + offset;
      layer.duration = Math.max(
        0.1,
        Math.min(layer.duration, visibleDuration(anchoredClip) - offset),
      );
    }
    layer.duration = Math.max(
      0.1,
      Math.min(layer.duration, Math.max(0.1, duration)),
    );
    layer.start = Math.max(
      0,
      Math.min(layer.start, Math.max(0, duration - layer.duration)),
    );
  }
  for (const layer of draft.audioLayers) {
    layer.duration = Math.max(
      0.1,
      Math.min(layer.duration, Math.max(0.1, duration)),
    );
    layer.start = Math.max(
      0,
      Math.min(layer.start, Math.max(0, duration - 0.05)),
    );
  }
};
const fmt = (seconds: number) =>
  `${Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0")}:${Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0")}`;

const toolItems = [
  { id: "media", label: "Media", icon: Upload },
  { id: "scenes", label: "Scenes", icon: Film },
  { id: "text", label: "Text", icon: Type },
  { id: "audio", label: "Audio", icon: Music2 },
  { id: "captions", label: "Captions", icon: AudioLines },
  { id: "brand", label: "Brand kit", icon: Layers3 },
  { id: "ai", label: "AI tools", icon: Sparkles },
] as const;
type ToolId = (typeof toolItems)[number]["id"];

export function StudioEditor({
  projectId,
  projectTitle,
  shots,
  outputUrl,
  aspectRatio,
  initialTimeline,
}: {
  projectId: string;
  projectTitle: string;
  shots: Shot[];
  outputUrl: string | null;
  aspectRatio: string;
  initialTimeline?: EditorTimeline | null;
}) {
  const [state, setState] = useState<StudioState>(() => ({
    ...defaults(shots, aspectRatio),
    ...((initialTimeline as Partial<StudioState> | null) ?? {}),
  }));
  const [history, setHistory] = useState<StudioState[]>([]);
  const [future, setFuture] = useState<StudioState[]>([]);
  const [tool, setTool] = useState<ToolId>("scenes");
  const [playing, setPlaying] = useState(false);
  const [playhead, setPlayhead] = useState(0);
  const [saveStatus, setSaveStatus] = useState<"saved" | "saving" | "error">(
    "saved",
  );
  const [newText, setNewText] = useState("Your title here");
  const [captionText, setCaptionText] = useState("Add a caption");
  const [showExport, setShowExport] = useState(false);
  const [renderingEdited, setRenderingEdited] = useState(false);
  const [draggingClipId, setDraggingClipId] = useState<string | null>(null);
  const [assets, setAssets] = useState<EditorAsset[]>([]);
  const [loadingAssets, setLoadingAssets] = useState(false);
  const [uploadingAsset, setUploadingAsset] = useState(false);
  const [assetRefreshKey, setAssetRefreshKey] = useState(0);
  const videoRef = useRef<HTMLVideoElement>(null);
  const stateRef = useRef(state);
  stateRef.current = state;
  useEffect(() => {
    setState((current) => {
      const knownShotIds = new Set(current.clips.map((clip) => clip.shotId));
      const additions = [...shots]
        .sort((a, b) => a.order_index - b.order_index)
        .filter((shot) => !knownShotIds.has(shot.id));
      if (!additions.length) return current;
      const nextClips = additions.map((shot) => ({
        id: `clip-${shot.id}`,
        shotId: shot.id,
        title: `Scene ${current.clips.length + 1}`,
        prompt: shot.prompt,
        duration: Math.max(1, Number(shot.duration_seconds ?? 5)),
        trimStart: 0,
        trimEnd: Math.min(
          Math.max(
            0,
            Number(shot.duration_seconds ?? 5) -
              Number(
                shot.timeline_duration_seconds ?? shot.duration_seconds ?? 5,
              ),
          ),
          Math.max(0, Number(shot.duration_seconds ?? 5) - 0.5),
        ),
        transition: "none" as const,
        volume: 100,
        muted: false,
      }));
      return {
        ...current,
        clips: [...current.clips, ...nextClips],
        selectedId: current.selectedId ?? nextClips[0]?.id ?? null,
      };
    });
  }, [shots]);
  const totalDuration = useMemo(
    () => timelineDuration(state.clips),
    [state.clips],
  );
  const selectedClip =
    state.clips.find((clip) => clip.id === state.selectedId) ?? null;
  const selectedText =
    state.textLayers.find((layer) => layer.id === state.selectedId) ?? null;
  const selectedAudio =
    state.audioLayers.find((layer) => layer.id === state.selectedId) ?? null;

  const commit = useCallback((mutator: (draft: StudioState) => void) => {
    setHistory((items) => [...items.slice(-39), clone(stateRef.current)]);
    setFuture([]);
    setState((current) => {
      const next = clone(current);
      mutator(next);
      normalizeLayerTiming(next);
      return next;
    });
  }, []);
  const updateClip = (id: string, patch: Partial<Clip>) =>
    commit((draft) => {
      const target = draft.clips.find((clip) => clip.id === id);
      draft.clips = draft.clips.map((clip) =>
        clip.id === id ||
        (patch.prompt !== undefined && target && clip.shotId === target.shotId)
          ? { ...clip, ...patch }
          : clip,
      );
    });
  const undo = () => {
    const previous = history.at(-1);
    if (!previous) return;
    setFuture((items) => [clone(state), ...items]);
    setState(previous);
    setHistory((items) => items.slice(0, -1));
  };
  const redo = () => {
    const next = future[0];
    if (!next) return;
    setHistory((items) => [...items, clone(state)]);
    setState(next);
    setFuture((items) => items.slice(1));
  };
  const moveClip = (id: string, direction: -1 | 1) =>
    commit((draft) => {
      const index = draft.clips.findIndex((clip) => clip.id === id);
      const next = index + direction;
      if (index < 0 || next < 0 || next >= draft.clips.length) return;
      [draft.clips[index], draft.clips[next]] = [
        draft.clips[next]!,
        draft.clips[index]!,
      ];
    });
  const splitSelected = () => {
    if (!selectedClip) return;
    const visibleDuration =
      selectedClip.duration - selectedClip.trimStart - selectedClip.trimEnd;
    const leftDuration = Math.max(
      0.5,
      Math.min(visibleDuration - 0.5, playhead - clipStart(selectedClip.id)),
    );
    if (leftDuration <= 0.5 || leftDuration >= visibleDuration - 0.5) {
      toast.error("Move the playhead inside the selected clip to split it.");
      return;
    }
    commit((draft) => {
      const index = draft.clips.findIndex(
        (clip) => clip.id === selectedClip.id,
      );
      const source = draft.clips[index];
      if (!source) return;
      const right = {
        ...source,
        id: `${source.id}-split-${Date.now()}`,
        title: `${source.title} (split)`,
        trimStart: source.trimStart + leftDuration,
        transition: "none" as const,
      };
      draft.clips[index] = {
        ...source,
        title: `${source.title} (part 1)`,
        trimEnd: source.duration - source.trimStart - leftDuration,
      };
      for (const layer of draft.textLayers) {
        if (layer.clipId !== source.id) continue;
        const offset = Number(layer.clipOffset ?? 0);
        if (offset >= leftDuration) {
          layer.clipId = right.id;
          layer.clipOffset = offset - leftDuration;
        } else if (offset + layer.duration > leftDuration) {
          layer.duration = Math.max(0.1, leftDuration - offset);
        }
      }
      draft.clips.splice(index + 1, 0, right);
      draft.selectedId = right.id;
    });
    toast.success("Clip split on the timeline.");
  };
  const clipStart = (id: string) => {
    const index = Math.max(
      0,
      state.clips.findIndex((clip) => clip.id === id),
    );
    return state.clips
      .slice(0, index)
      .reduce(
        (sum, clip, i) =>
          sum +
          visibleDuration(clip) -
          (i + 1 < state.clips.length
            ? incomingOverlap(state.clips[i + 1]!, clip)
            : 0),
        0,
      );
  };
  const addTextLayer = (style: TextLayer["style"]) => {
    const activeClip =
      [...state.clips]
        .reverse()
        .find((clip) => clipStart(clip.id) <= playhead) ?? state.clips[0];
    const activeClipStart = activeClip ? clipStart(activeClip.id) : 0;
    const clipOffset = activeClip
      ? Math.max(
          0,
          Math.min(
            visibleDuration(activeClip) - 0.1,
            playhead - activeClipStart,
          ),
        )
      : 0;
    const layer: TextLayer = {
      id: `text-${Date.now()}`,
      text: style === "title" ? newText : captionText,
      start: playhead,
      duration: Math.min(5, Math.max(1, totalDuration - playhead || 5)),
      style,
      clipId: activeClip?.id ?? null,
      clipOffset,
    };
    commit((draft) => {
      draft.textLayers.push(layer);
      draft.selectedId = layer.id;
    });
    setTool("text");
    toast.success(
      style === "caption"
        ? "Caption added to timeline."
        : "Text overlay added.",
    );
  };
  const addAudioLayer = (kind: AudioLayer["kind"]) => {
    const layer: AudioLayer = {
      id: `${kind}-${Date.now()}`,
      name:
        kind === "music"
          ? "Music bed"
          : kind === "voice"
            ? "Voiceover"
            : "Sound effect",
      assetId: null,
      start: playhead,
      duration: Math.max(1, Math.min(30, totalDuration - playhead || 10)),
      volume: 80,
      kind,
      loop: kind === "music",
    };
    commit((draft) => {
      draft.audioLayers.push(layer);
      draft.selectedId = layer.id;
    });
    setTool("audio");
    toast.info("Select or upload an audio asset for this track before export.");
  };
  const deleteSelected = () => {
    if (!state.selectedId) return;
    commit((draft) => {
      const deletedClipId = draft.clips.some(
        (clip) => clip.id === draft.selectedId,
      )
        ? draft.selectedId
        : null;
      draft.clips = draft.clips.filter((clip) => clip.id !== draft.selectedId);
      draft.textLayers = draft.textLayers.filter(
        (layer) =>
          layer.id !== draft.selectedId &&
          (!deletedClipId || layer.clipId !== deletedClipId),
      );
      draft.audioLayers = draft.audioLayers.filter(
        (layer) => layer.id !== draft.selectedId,
      );
      draft.selectedId =
        draft.clips[0]?.id ??
        draft.textLayers[0]?.id ??
        draft.audioLayers[0]?.id ??
        null;
    });
  };
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        if (event.shiftKey) redo();
        else undo();
      } else if (
        (event.ctrlKey || event.metaKey) &&
        event.key.toLowerCase() === "y"
      ) {
        event.preventDefault();
        redo();
      } else if (
        event.code === "Space" &&
        !(event.target instanceof HTMLInputElement) &&
        !(event.target instanceof HTMLTextAreaElement)
      ) {
        event.preventDefault();
        setPlaying((value) => !value);
      } else if (
        (event.key === "Delete" || event.key === "Backspace") &&
        !(event.target instanceof HTMLInputElement) &&
        !(event.target instanceof HTMLTextAreaElement)
      )
        deleteSelected();
      else if (
        event.key.toLowerCase() === "s" &&
        !(event.target instanceof HTMLInputElement) &&
        !(event.target instanceof HTMLTextAreaElement)
      )
        splitSelected();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  useEffect(() => {
    const timer = window.setTimeout(() => {
      void (async () => {
        setSaveStatus("saving");
        try {
          await saveEditorTimeline(
            projectId,
            stateRef.current as EditorTimeline,
          );
          setSaveStatus("saved");
        } catch {
          setSaveStatus("error");
        }
      })();
    }, 650);
    return () => window.clearTimeout(timer);
  }, [projectId, state]);
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (playing && outputUrl) void video.play().catch(() => setPlaying(false));
    else video.pause();
  }, [playing, outputUrl]);
  useEffect(() => {
    let active = true;
    setLoadingAssets(true);
    void listProjectAssets(projectId)
      .then((result) => {
        if (active) setAssets(result.assets);
      })
      .catch(() => {
        if (active) toast.error("Could not load this project's media assets.");
      })
      .finally(() => {
        if (active) setLoadingAssets(false);
      });
    return () => {
      active = false;
    };
  }, [projectId, assetRefreshKey]);

  const uploadAudioAsset = async (file: File) => {
    if (!file.type.startsWith("audio/")) {
      toast.error("Choose an audio file (MP3, WAV, M4A, AAC or OGG).");
      return;
    }
    setUploadingAsset(true);
    try {
      const { url, key } = await getProjectAssetUploadUrl(file.name, file.type);
      const response = await fetch(url, {
        method: "PUT",
        headers: { "Content-Type": file.type },
        body: file,
      });
      if (!response.ok) throw new Error("The audio upload failed.");
      await registerProjectAsset(projectId, {
        key,
        file_name: file.name,
        mime_type: file.type,
      });
      setAssetRefreshKey((v) => v + 1);
      toast.success("Audio asset uploaded and added to this project.");
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Could not upload audio asset.",
      );
    } finally {
      setUploadingAsset(false);
    }
  };

  const selectedClipIndex = selectedClip
    ? state.clips.findIndex((clip) => clip.id === selectedClip.id)
    : -1;
  const onRenderEdited = async () => {
    setRenderingEdited(true);
    try {
      setSaveStatus("saving");
      await saveEditorTimeline(projectId, stateRef.current as EditorTimeline);
      setSaveStatus("saved");
      await renderEditorTimeline(projectId);
      toast.success(
        "Edited render queued. The preview will update when rendering finishes.",
      );
      setShowExport(false);
    } catch (error) {
      setSaveStatus("error");
      toast.error(
        error instanceof Error
          ? error.message
          : "Could not queue the edited render.",
      );
    } finally {
      setRenderingEdited(false);
    }
  };

  return (
    <section className="overflow-hidden rounded-2xl border border-[#282a34] bg-[#111218] text-[#f5f5f7] shadow-2xl shadow-black/10">
      <header className="flex min-h-14 flex-wrap items-center justify-between gap-3 border-b border-white/10 bg-[#17181f] px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500">
            <Clapperboard className="size-5" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">{projectTitle}</div>
            <div className="flex items-center gap-1.5 text-[11px] text-white/45">
              <span
                className={cn(
                  "size-1.5 rounded-full",
                  saveStatus === "saved"
                    ? "bg-emerald-400"
                    : saveStatus === "saving"
                      ? "bg-amber-400"
                      : "bg-red-400",
                )}
              />
              {saveStatus === "saved"
                ? "All changes saved"
                : saveStatus === "saving"
                  ? "Saving edits…"
                  : "Save failed — retrying on next edit"}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            title="Undo (Ctrl+Z)"
            onClick={undo}
            disabled={!history.length}
            className="rounded-lg p-2 text-white/65 hover:bg-white/10 disabled:opacity-25"
          >
            <Undo2 size={17} />
          </button>
          <button
            title="Redo (Ctrl+Y)"
            onClick={redo}
            disabled={!future.length}
            className="rounded-lg p-2 text-white/65 hover:bg-white/10 disabled:opacity-25"
          >
            <Redo2 size={17} />
          </button>
          <span className="mx-1 hidden h-6 w-px bg-white/10 sm:block" />
          <span className="hidden text-xs text-white/50 sm:inline">
            {state.aspectRatio}
          </span>
          <button
            onClick={() => setShowExport(true)}
            className="ml-1 flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-xs font-semibold text-[#14141a] transition hover:bg-violet-100"
          >
            <Video size={15} /> Export <ChevronDown size={13} />
          </button>
        </div>
      </header>
      <div className="grid min-h-[600px] grid-cols-[64px_minmax(180px,230px)_minmax(0,1fr)] lg:grid-cols-[72px_240px_minmax(0,1fr)_250px]">
        <nav className="border-r border-white/10 bg-[#15161c] p-1.5 sm:p-2">
          <div className="space-y-1">
            {toolItems.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setTool(id)}
                title={label}
                className={cn(
                  "flex w-full flex-col items-center justify-center gap-1 rounded-xl px-1 py-3 text-[10px] transition",
                  tool === id
                    ? "bg-violet-500/20 text-violet-200 ring-1 ring-violet-400/30"
                    : "text-white/50 hover:bg-white/5 hover:text-white/90",
                )}
              >
                <Icon size={19} strokeWidth={1.8} />
                <span className="hidden sm:block">{label}</span>
              </button>
            ))}
          </div>
        </nav>
        <aside className="min-w-0 border-r border-white/10 bg-[#191a21] p-3 sm:p-4">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold">
              {toolItems.find((item) => item.id === tool)?.label}
            </h3>
            <button
              onClick={() => setTool("scenes")}
              className="rounded p-1 text-white/40 hover:bg-white/10"
            >
              <X size={14} />
            </button>
          </div>
          {tool === "scenes" && (
            <div className="space-y-2">
              {state.clips.map((clip, index) => (
                <button
                  key={clip.id}
                  onClick={() => {
                    setState((current) => ({
                      ...current,
                      selectedId: clip.id,
                    }));
                    setPlayhead(clipStart(clip.id));
                  }}
                  className={cn(
                    "w-full rounded-xl border p-2 text-left transition",
                    state.selectedId === clip.id
                      ? "border-violet-400/70 bg-violet-500/10"
                      : "border-white/8 bg-white/[0.025] hover:border-white/20",
                  )}
                >
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-[10px] font-semibold tracking-wide text-white/45 uppercase">
                      Scene {index + 1}
                    </span>
                    <span className="text-[10px] text-white/40">
                      {fmt(clip.duration)}
                    </span>
                  </div>
                  <div className="mb-2 grid aspect-video place-items-center overflow-hidden rounded-lg bg-gradient-to-br from-[#302d4c] via-[#262b3c] to-[#171920]">
                    {assets.find(
                      (asset) =>
                        asset.type === "video" &&
                        asset.source_generation_id ===
                          shots.find((shot) => shot.id === clip.shotId)
                            ?.generation_id,
                    )?.url ? (
                      <video
                        src={
                          assets.find(
                            (asset) =>
                              asset.type === "video" &&
                              asset.source_generation_id ===
                                shots.find((shot) => shot.id === clip.shotId)
                                  ?.generation_id,
                          )?.url
                        }
                        preload="metadata"
                        muted
                        playsInline
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <Film size={22} className="text-white/30" />
                    )}
                  </div>
                  <div className="line-clamp-2 text-xs font-medium">
                    {clip.title}
                  </div>
                  <div className="mt-1 line-clamp-2 text-[10px] leading-relaxed text-white/40">
                    {clip.prompt}
                  </div>
                </button>
              ))}
              {!state.clips.length && (
                <p className="text-xs leading-5 text-white/45">
                  No scenes yet. Add a shot to your project to start editing.
                </p>
              )}
            </div>
          )}
          {tool === "media" && (
            <div className="space-y-3">
              <div className="rounded-xl border border-dashed border-white/20 p-5 text-center">
                <Upload size={22} className="mx-auto mb-2 text-violet-300" />
                <p className="text-xs font-medium">Bring in your media</p>
                <p className="mt-1 text-[10px] leading-4 text-white/45">
                  Upload is not connected to a project asset endpoint in this
                  editor yet.
                </p>
              </div>
              <div className="rounded-xl bg-white/[0.04] p-3 text-xs text-white/60">
                Generated scenes appear in the Scenes panel. Upload integration
                can be wired to the existing asset service next.
              </div>
            </div>
          )}
          {tool === "text" && (
            <div className="space-y-3">
              <label className="block text-[11px] text-white/55">
                Title text
                <input
                  value={newText}
                  onChange={(e) => setNewText(e.target.value)}
                  className="mt-1.5 w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white outline-none focus:border-violet-400"
                />
              </label>
              <button
                onClick={() => addTextLayer("title")}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-violet-500 px-3 py-2.5 text-xs font-semibold hover:bg-violet-400"
              >
                <Plus size={14} /> Add title overlay
              </button>
              <label className="block text-[11px] text-white/55">
                Caption text
                <input
                  value={captionText}
                  onChange={(e) => setCaptionText(e.target.value)}
                  className="mt-1.5 w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white outline-none focus:border-violet-400"
                />
              </label>
              <button
                onClick={() => addTextLayer("caption")}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-white/15 px-3 py-2.5 text-xs hover:bg-white/5"
              >
                <Type size={14} /> Add caption
              </button>
              <p className="text-[10px] leading-4 text-white/40">
                Text and caption layers are composited into the final FFmpeg
                render and their timing is kept inside the edited timeline.
              </p>
            </div>
          )}
          {tool === "audio" && (
            <div className="space-y-2">
              {(
                [
                  { kind: "music", label: "Music bed", icon: Music2 },
                  { kind: "voice", label: "Voiceover", icon: Mic2 },
                  { kind: "sfx", label: "Sound effects", icon: AudioLines },
                ] as const
              ).map(({ kind, label, icon: Icon }) => (
                <button
                  key={kind}
                  onClick={() => addAudioLayer(kind)}
                  className="flex w-full items-center gap-3 rounded-xl border border-white/10 bg-white/[0.025] p-3 text-left hover:border-violet-400/50"
                >
                  <span className="grid size-9 place-items-center rounded-lg bg-violet-500/15 text-violet-200">
                    <Icon size={17} />
                  </span>
                  <span>
                    <span className="block text-xs font-medium">
                      Add {label.toLowerCase()}
                    </span>
                    <span className="mt-0.5 block text-[10px] text-white/40">
                      Create track placeholder
                    </span>
                  </span>
                  <Plus size={14} className="ml-auto text-white/40" />
                </button>
              ))}
              <p className="pt-2 text-[10px] leading-4 text-white/40">
                Track placement, mute, and volume are editable. Audio file
                selection and final mix integration are still required for
                export.
              </p>
            </div>
          )}
          {tool === "captions" && (
            <div className="space-y-3">
              <p className="text-xs leading-5 text-white/55">
                Add caption layers and position them on the timeline. Automatic
                speech-to-text caption generation is not invoked from this panel
                yet.
              </p>
              <button
                onClick={() => addTextLayer("caption")}
                className="w-full rounded-lg bg-violet-500 px-3 py-2.5 text-xs font-semibold hover:bg-violet-400"
              >
                <Plus size={14} className="mr-1 inline" /> Add caption layer
              </button>
            </div>
          )}
          {tool === "brand" && (
            <div className="space-y-3">
              <div className="rounded-xl border border-white/10 p-3">
                <div className="mb-2 text-xs font-medium">Project style</div>
                <div className="flex gap-2">
                  <span className="size-7 rounded-lg bg-violet-500" />
                  <span className="size-7 rounded-lg bg-fuchsia-400" />
                  <span className="size-7 rounded-lg bg-white" />
                  <span className="size-7 rounded-lg bg-[#15161c] ring-1 ring-white/20" />
                </div>
                <p className="mt-2 text-[10px] text-white/45">
                  Palette preview only
                </p>
              </div>
              <button
                onClick={() => addTextLayer("label")}
                className="w-full rounded-lg border border-white/15 px-3 py-2.5 text-xs hover:bg-white/5"
              >
                <Plus size={14} className="mr-1 inline" /> Add brand label
              </button>
              <p className="text-[10px] leading-4 text-white/40">
                Logo upload and brand kit application are not connected yet.
              </p>
            </div>
          )}
          {tool === "ai" && (
            <div className="space-y-2">
              <button
                onClick={() =>
                  toast.info(
                    "AI editing actions need to be connected to the existing production plan before they can safely change generated media.",
                  )
                }
                className="flex w-full items-center gap-2 rounded-xl border border-violet-400/30 bg-violet-500/10 p-3 text-xs"
              >
                <WandSparkles size={17} className="text-violet-200" /> Refine
                selected scene
              </button>
              <button
                onClick={() =>
                  toast.info(
                    "AI tools will preserve the current generation pipeline; this action is not wired yet.",
                  )
                }
                className="flex w-full items-center gap-2 rounded-xl border border-white/10 p-3 text-xs"
              >
                <Sparkles size={17} /> Generate b-roll
              </button>
              <p className="text-[10px] leading-4 text-white/40">
                These are intentionally not fake generation buttons; AI actions
                must use the existing credit-aware production pipeline.
              </p>
            </div>
          )}
        </aside>
        <main className="col-span-1 flex min-w-0 flex-col bg-[#101116] lg:col-span-1">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/8 px-3 py-2.5">
            <div className="flex items-center gap-2 text-[11px] text-white/55">
              <MousePointer2 size={14} />
              <span>Preview</span>
              <span className="text-white/20">/</span>
              <span>{state.aspectRatio}</span>
            </div>
            <div className="flex items-center gap-1">
              <select
                value={state.aspectRatio}
                onChange={(e) =>
                  commit((draft) => {
                    draft.aspectRatio = e.target.value;
                  })
                }
                className="rounded-md border border-white/10 bg-[#1b1c24] px-2 py-1.5 text-[10px] text-white/70 outline-none"
              >
                <option>16:9</option>
                <option>9:16</option>
                <option>1:1</option>
                <option>4:5</option>
              </select>
              <button
                onClick={() => setTool("scenes")}
                title="Fit preview"
                className="rounded-md p-1.5 text-white/50 hover:bg-white/10"
              >
                <Maximize2 size={14} />
              </button>
            </div>
          </div>
          <div className="flex min-h-[270px] flex-1 items-center justify-center p-4 sm:min-h-[360px] sm:p-7">
            <div
              className={cn(
                "relative flex max-h-[440px] w-full max-w-[680px] items-center justify-center overflow-hidden rounded-lg border border-white/10 bg-[#090a0e] shadow-2xl",
                state.aspectRatio === "9:16"
                  ? "aspect-[9/16] max-w-[260px]"
                  : state.aspectRatio === "1:1"
                    ? "aspect-square max-w-[440px]"
                    : state.aspectRatio === "4:5"
                      ? "aspect-[4/5] max-w-[360px]"
                      : "aspect-video",
              )}
            >
              {outputUrl ? (
                <video
                  ref={videoRef}
                  src={outputUrl}
                  controls={false}
                  onTimeUpdate={(e) => setPlayhead(e.currentTarget.currentTime)}
                  onEnded={() => setPlaying(false)}
                  className="h-full w-full object-contain"
                />
              ) : (
                <div className="absolute inset-0 flex flex-col items-center justify-center bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-[#30274d] via-[#171925] to-[#08090d] px-6 text-center">
                  <div className="mb-4 grid size-14 place-items-center rounded-2xl border border-white/15 bg-white/5">
                    <Film size={26} className="text-violet-200" />
                  </div>
                  <p className="text-sm font-medium">Your video preview</p>
                  <p className="mt-2 max-w-xs text-xs leading-5 text-white/45">
                    When your project render is ready, it will appear here.
                    Select a scene to edit its timing and generation notes.
                  </p>
                </div>
              )}
              {selectedText && (
                <div
                  className={cn(
                    "pointer-events-none absolute inset-x-4 text-center font-bold drop-shadow-[0_2px_6px_rgba(0,0,0,0.9)]",
                    selectedText.style === "title"
                      ? "top-[28%] text-2xl sm:text-4xl"
                      : selectedText.style === "caption"
                        ? "bottom-[12%] text-sm sm:text-lg"
                        : "top-[10%] text-sm",
                  )}
                >
                  <span className="bg-black/30 px-2 py-1">
                    {selectedText.text}
                  </span>
                </div>
              )}
              {selectedClip && !outputUrl && (
                <div className="absolute right-3 bottom-3 left-3 rounded-lg border border-white/10 bg-black/45 p-2 text-left backdrop-blur">
                  <div className="text-[10px] font-semibold text-white/80">
                    {selectedClip.title}
                  </div>
                  <div className="mt-1 line-clamp-2 text-[10px] text-white/55">
                    {selectedClip.prompt}
                  </div>
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center justify-center gap-3 border-t border-white/8 px-3 py-3">
            <button
              onClick={() => {
                setPlayhead(0);
                if (videoRef.current) videoRef.current.currentTime = 0;
              }}
              className="rounded-lg p-2 text-white/55 hover:bg-white/10"
            >
              <Minus size={15} />
            </button>
            <button
              onClick={() => setPlaying((value) => !value)}
              className="grid size-10 place-items-center rounded-full bg-white text-[#15151b] transition hover:scale-105"
            >
              {playing ? (
                <Pause size={17} fill="currentColor" />
              ) : (
                <Play size={17} fill="currentColor" className="ml-0.5" />
              )}
            </button>
            <button
              onClick={() => setPlaying(false)}
              className="rounded-lg p-2 text-white/55 hover:bg-white/10"
            >
              <Volume2 size={15} />
            </button>
            <span className="font-mono text-[11px] text-white/55">
              {fmt(playhead)} <span className="text-white/25">/</span>{" "}
              {fmt(totalDuration)}
            </span>
            <div className="h-1 w-20 rounded-full bg-white/10 sm:w-28">
              <div
                className="h-full rounded-full bg-violet-400"
                style={{
                  width: `${totalDuration ? Math.min(100, (playhead / totalDuration) * 100) : 0}%`,
                }}
              />
            </div>
          </div>
        </main>
        <aside className="col-span-3 border-t border-white/10 bg-[#191a21] p-4 lg:col-span-1 lg:border-t-0 lg:border-l">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold">Inspector</h3>
            <Settings2 size={16} className="text-white/40" />
          </div>
          {selectedClip && (
            <div className="space-y-4">
              <div>
                <div className="mb-1.5 text-[10px] font-semibold tracking-wider text-white/40 uppercase">
                  Selected clip
                </div>
                <input
                  value={selectedClip.title}
                  onChange={(e) =>
                    updateClip(selectedClip.id, { title: e.target.value })
                  }
                  className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs outline-none focus:border-violet-400"
                />
              </div>
              <div>
                <div className="mb-1.5 text-[10px] font-semibold tracking-wider text-white/40 uppercase">
                  Generation prompt
                </div>
                <textarea
                  value={selectedClip.prompt}
                  onChange={(e) =>
                    updateClip(selectedClip.id, { prompt: e.target.value })
                  }
                  rows={4}
                  className="w-full resize-y rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs leading-5 outline-none focus:border-violet-400"
                />
                <p className="mt-1 text-[10px] leading-4 text-white/35">
                  Editing this prompt saves the edit but does not silently
                  regenerate or spend credits.
                </p>
              </div>
              <div>
                <div className="mb-2 flex items-center justify-between text-xs">
                  <span className="text-white/65">Clip duration</span>
                  <span className="font-mono">
                    {Math.max(
                      0.25,
                      selectedClip.duration -
                        selectedClip.trimStart -
                        selectedClip.trimEnd,
                    ).toFixed(1)}
                    s
                  </span>
                </div>
                <input
                  aria-label="Clip duration"
                  type="range"
                  min="0.5"
                  max={Math.max(
                    1,
                    selectedClip.duration - selectedClip.trimStart,
                  )}
                  step="0.5"
                  value={Math.max(
                    0.5,
                    selectedClip.duration -
                      selectedClip.trimStart -
                      selectedClip.trimEnd,
                  )}
                  onChange={(e) =>
                    updateClip(selectedClip.id, {
                      trimEnd: Math.max(
                        0,
                        selectedClip.duration -
                          selectedClip.trimStart -
                          Number(e.target.value),
                      ),
                    })
                  }
                  className="w-full accent-violet-400"
                />
                <div className="mt-1 flex justify-between text-[10px] text-white/30">
                  <span>0.5 sec</span>
                  <span>Timeline duration</span>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <label className="text-[10px] text-white/50">
                  Trim in (s)
                  <input
                    type="number"
                    min="0"
                    max={Math.max(0, selectedClip.duration - 0.5)}
                    step="0.1"
                    value={selectedClip.trimStart}
                    onChange={(e) =>
                      updateClip(selectedClip.id, {
                        trimStart: Math.min(
                          Number(e.target.value),
                          selectedClip.duration - selectedClip.trimEnd - 0.5,
                        ),
                      })
                    }
                    className="mt-1 w-full rounded-lg border border-white/10 bg-black/20 px-2 py-2 text-xs text-white"
                  />
                </label>
                <label className="text-[10px] text-white/50">
                  Trim out (s)
                  <input
                    type="number"
                    min="0"
                    max={Math.max(0, selectedClip.duration - 0.5)}
                    step="0.1"
                    value={selectedClip.trimEnd}
                    onChange={(e) =>
                      updateClip(selectedClip.id, {
                        trimEnd: Math.min(
                          Number(e.target.value),
                          selectedClip.duration - selectedClip.trimStart - 0.5,
                        ),
                      })
                    }
                    className="mt-1 w-full rounded-lg border border-white/10 bg-black/20 px-2 py-2 text-xs text-white"
                  />
                </label>
              </div>
              <div>
                <label className="mb-1.5 block text-xs text-white/65">
                  Transition to next clip
                </label>
                <select
                  value={selectedClip.transition}
                  onChange={(e) =>
                    updateClip(selectedClip.id, {
                      transition: e.target.value as Clip["transition"],
                    })
                  }
                  className="w-full rounded-lg border border-white/10 bg-[#101116] px-3 py-2 text-xs text-white outline-none"
                >
                  <option value="none">Cut</option>
                  <option value="fade">Fade</option>
                  <option value="dissolve">Dissolve</option>
                  <option value="wipe">Wipe</option>
                </select>
              </div>
              <div>
                <div className="mb-2 flex items-center justify-between text-xs">
                  <span className="text-white/65">Clip audio</span>
                  <button
                    onClick={() =>
                      updateClip(selectedClip.id, {
                        muted: !selectedClip.muted,
                      })
                    }
                    className="rounded-md p-1 hover:bg-white/10"
                  >
                    {selectedClip.muted ? (
                      <VolumeX size={14} />
                    ) : (
                      <Volume2 size={14} />
                    )}
                  </button>
                </div>
                <input
                  aria-label="Clip audio volume"
                  type="range"
                  min="0"
                  max="100"
                  value={selectedClip.muted ? 0 : selectedClip.volume}
                  onChange={(e) =>
                    updateClip(selectedClip.id, {
                      volume: Number(e.target.value),
                      muted: Number(e.target.value) === 0,
                    })
                  }
                  className="w-full accent-violet-400"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => moveClip(selectedClip.id, -1)}
                  disabled={selectedClipIndex <= 0}
                  className="rounded-lg border border-white/10 px-2 py-2 text-[11px] hover:bg-white/5 disabled:opacity-30"
                >
                  Move left
                </button>
                <button
                  onClick={() => moveClip(selectedClip.id, 1)}
                  disabled={
                    selectedClipIndex < 0 ||
                    selectedClipIndex >= state.clips.length - 1
                  }
                  className="rounded-lg border border-white/10 px-2 py-2 text-[11px] hover:bg-white/5 disabled:opacity-30"
                >
                  Move right
                </button>
              </div>
            </div>
          )}
          {selectedText && (
            <div className="space-y-4">
              <label className="block text-xs text-white/65">
                Text content
                <textarea
                  value={selectedText.text}
                  onChange={(e) =>
                    commit((draft) => {
                      const layer = draft.textLayers.find(
                        (item) => item.id === selectedText.id,
                      );
                      if (layer) layer.text = e.target.value;
                    })
                  }
                  rows={3}
                  className="mt-1.5 w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white outline-none focus:border-violet-400"
                />
              </label>
              <label className="block text-xs text-white/65">
                Start time
                <input
                  type="number"
                  min="0"
                  step="0.5"
                  value={selectedText.start}
                  onChange={(e) =>
                    commit((draft) => {
                      const layer = draft.textLayers.find(
                        (item) => item.id === selectedText.id,
                      );
                      if (layer) {
                        layer.start = Number(e.target.value);
                        layer.clipId = null;
                        layer.clipOffset = undefined;
                      }
                    })
                  }
                  className="mt-1.5 w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white"
                />
              </label>
              <label className="block text-xs text-white/65">
                Duration
                <input
                  type="number"
                  min="0.5"
                  step="0.5"
                  value={selectedText.duration}
                  onChange={(e) =>
                    commit((draft) => {
                      const layer = draft.textLayers.find(
                        (item) => item.id === selectedText.id,
                      );
                      if (layer) layer.duration = Number(e.target.value);
                    })
                  }
                  className="mt-1.5 w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white"
                />
              </label>
            </div>
          )}
          {selectedAudio && (
            <div className="space-y-4">
              <div className="rounded-xl bg-white/[0.04] p-3">
                <div className="mb-1 flex items-center gap-2 text-xs font-medium">
                  <Music2 size={15} />
                  {selectedAudio.name}
                </div>
                <label className="block text-[10px] text-white/60">
                  Audio asset
                  <select
                    value={selectedAudio.assetId ?? ""}
                    onChange={(e) => {
                      const asset = assets.find(
                        (item) => item.id === e.target.value,
                      );
                      commit((draft) => {
                        const layer = draft.audioLayers.find(
                          (item) => item.id === selectedAudio.id,
                        );
                        if (layer) {
                          layer.assetId = asset?.id ?? null;
                          if (asset?.duration_seconds)
                            layer.duration = Math.min(
                              asset.duration_seconds,
                              Math.max(0.1, totalDuration - layer.start),
                            );
                          if (asset?.file_name) layer.name = asset.file_name;
                        }
                      });
                    }}
                    className="mt-1.5 w-full rounded-lg border border-white/10 bg-[#101116] px-2 py-2 text-xs text-white"
                  >
                    <option value="">Choose an uploaded audio asset…</option>
                    {assets
                      .filter((asset) =>
                        ["audio", "music", "voiceover", "ambience"].includes(
                          asset.type,
                        ),
                      )
                      .map((asset) => (
                        <option key={asset.id} value={asset.id}>
                          {asset.file_name}
                          {asset.duration_seconds
                            ? ` (${asset.duration_seconds.toFixed(1)}s)`
                            : ""}
                        </option>
                      ))}
                  </select>
                </label>
                <label className="mt-3 block text-[10px] text-white/60">
                  Upload audio file
                  <input
                    type="file"
                    accept=".mp3,.wav,.m4a,.aac,.ogg,audio/mpeg,audio/wav,audio/x-wav,audio/mp4,audio/x-m4a,audio/ogg,audio/aac"
                    disabled={uploadingAsset}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) void uploadAudioAsset(file);
                      e.currentTarget.value = "";
                    }}
                    className="mt-1.5 block w-full text-[10px] text-white/65 file:mr-2 file:rounded-md file:border-0 file:bg-violet-500 file:px-2 file:py-1.5 file:text-[10px] file:font-semibold file:text-white"
                  />
                  {uploadingAsset
                    ? "Uploading…"
                    : loadingAssets
                      ? "Loading assets…"
                      : "Only project-owned audio assets can be rendered."}
                </label>
              </div>
              <label className="block text-xs text-white/65">
                Start time (s)
                <input
                  type="number"
                  min="0"
                  step="0.5"
                  value={selectedAudio.start}
                  onChange={(e) =>
                    commit((draft) => {
                      const layer = draft.audioLayers.find(
                        (item) => item.id === selectedAudio.id,
                      );
                      if (layer) layer.start = Number(e.target.value);
                    })
                  }
                  className="mt-1.5 w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white"
                />
              </label>
              <label className="block text-xs text-white/65">
                Duration (s)
                <input
                  type="number"
                  min="0.5"
                  step="0.5"
                  value={selectedAudio.duration}
                  onChange={(e) =>
                    commit((draft) => {
                      const layer = draft.audioLayers.find(
                        (item) => item.id === selectedAudio.id,
                      );
                      if (layer) layer.duration = Number(e.target.value);
                    })
                  }
                  className="mt-1.5 w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white"
                />
              </label>
              <label className="block text-xs text-white/65">
                Volume: {selectedAudio.volume}%
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={selectedAudio.volume}
                  onChange={(e) =>
                    commit((draft) => {
                      const layer = draft.audioLayers.find(
                        (item) => item.id === selectedAudio.id,
                      );
                      if (layer) layer.volume = Number(e.target.value);
                    })
                  }
                  className="mt-2 w-full accent-violet-400"
                />
              </label>
            </div>
          )}
          {!selectedClip && !selectedText && !selectedAudio && (
            <div className="rounded-xl border border-dashed border-white/15 p-5 text-center">
              <Settings2 size={22} className="mx-auto mb-2 text-white/30" />
              <p className="text-xs text-white/55">Select a clip or layer</p>
              <p className="mt-1 text-[10px] leading-4 text-white/30">
                Timing, transitions, prompt, text, and audio settings appear
                here.
              </p>
            </div>
          )}
          <div className="mt-5 border-t border-white/8 pt-4">
            <button
              onClick={deleteSelected}
              disabled={!state.selectedId}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-red-400/20 px-3 py-2.5 text-xs text-red-200/80 hover:bg-red-500/10 disabled:opacity-30"
            >
              <Trash2 size={14} /> Delete selected layer
            </button>
          </div>
        </aside>
      </div>
      <div className="border-t border-white/10 bg-[#14151b]">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/8 px-3 py-2.5 sm:px-4">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold">Timeline</span>
            <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-white/40">
              {state.clips.length} clips · {fmt(totalDuration)}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-1">
            <button
              onClick={splitSelected}
              title="Split at playhead (S)"
              className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[10px] text-white/60 hover:bg-white/10"
            >
              <Scissors size={13} /> Split
            </button>
            <button
              onClick={() =>
                selectedClip &&
                commit((draft) => {
                  const clip = draft.clips.find(
                    (item) => item.id === selectedClip.id,
                  );
                  if (clip)
                    draft.clips.splice(
                      draft.clips.findIndex((item) => item.id === clip.id) + 1,
                      0,
                      {
                        ...clip,
                        id: `clip-${Date.now()}`,
                        title: `${clip.title} copy`,
                      },
                    );
                })
              }
              disabled={!selectedClip}
              className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[10px] text-white/60 hover:bg-white/10 disabled:opacity-30"
            >
              <Copy size={13} /> Duplicate
            </button>
            <button
              onClick={() =>
                commit((draft) => {
                  draft.zoom = Math.min(2.5, draft.zoom + 0.25);
                })
              }
              title="Zoom timeline"
              className="rounded-md p-1.5 text-white/60 hover:bg-white/10"
            >
              <Plus size={13} />
            </button>
            <button
              onClick={() =>
                commit((draft) => {
                  draft.zoom = Math.max(0.5, draft.zoom - 0.25);
                })
              }
              title="Zoom out timeline"
              className="rounded-md p-1.5 text-white/60 hover:bg-white/10"
            >
              <Minus size={13} />
            </button>
          </div>
        </div>
        <div className="overflow-x-auto p-3 sm:p-4">
          <div
            className="min-w-[560px]"
            style={{
              minWidth: `${Math.max(560, (totalDuration || 10) * 34 * state.zoom)}px`,
            }}
          >
            <div className="mb-2 flex h-5 items-center font-mono text-[9px] text-white/35">
              {Array.from(
                { length: Math.max(6, Math.ceil(totalDuration / 5) + 1) },
                (_, i) => (
                  <span
                    key={i}
                    className="flex-1 border-l border-white/10 pl-1"
                  >
                    {fmt(i * 5)}
                  </span>
                ),
              )}
            </div>
            <div className="relative space-y-2">
              <div className="flex min-h-[62px] items-stretch gap-1 rounded-lg bg-black/20 p-1">
                {state.clips.map((clip, index) => (
                  <button
                    key={clip.id}
                    draggable
                    onDragStart={() => setDraggingClipId(clip.id)}
                    onDragOver={(event) => event.preventDefault()}
                    onDragEnd={() => setDraggingClipId(null)}
                    onDrop={(event) => {
                      event.preventDefault();
                      const from = state.clips.findIndex(
                        (item) => item.id === draggingClipId,
                      );
                      const to = state.clips.findIndex(
                        (item) => item.id === clip.id,
                      );
                      if (from >= 0 && to >= 0 && from !== to)
                        commit((draft) => {
                          const [moved] = draft.clips.splice(from, 1);
                          if (moved) draft.clips.splice(to, 0, moved);
                        });
                      setDraggingClipId(null);
                    }}
                    onClick={() => {
                      setState((current) => ({
                        ...current,
                        selectedId: clip.id,
                      }));
                      setPlayhead(clipStart(clip.id));
                      if (videoRef.current)
                        videoRef.current.currentTime = clipStart(clip.id);
                    }}
                    onDoubleClick={() => {
                      const title = window.prompt("Rename clip", clip.title);
                      if (title?.trim())
                        updateClip(clip.id, { title: title.trim() });
                    }}
                    style={{
                      flex: `${Math.max(0.5, clip.duration - clip.trimStart - clip.trimEnd)} 1 0%`,
                      minWidth: 68,
                    }}
                    className={cn(
                      "relative overflow-hidden rounded-md border p-2 text-left transition",
                      draggingClipId === clip.id ? "opacity-40" : "",
                      state.selectedId === clip.id
                        ? "border-violet-300 bg-gradient-to-br from-violet-500/35 to-fuchsia-500/15 ring-1 ring-violet-400/35"
                        : "border-white/10 bg-gradient-to-br from-[#34334b] to-[#202431] hover:border-white/25",
                    )}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <span className="truncate text-[10px] font-semibold">
                        {clip.title}
                      </span>
                      <span className="shrink-0 text-[9px] text-white/45">
                        {Math.max(
                          0.25,
                          clip.duration - clip.trimStart - clip.trimEnd,
                        ).toFixed(1)}
                        s
                      </span>
                    </div>
                    <div className="mt-2 flex items-center gap-1">
                      <span className="h-1 flex-1 rounded-full bg-white/20">
                        <span
                          className="block h-full rounded-full bg-violet-300"
                          style={{
                            width: `${Math.max(15, ((clip.duration - clip.trimStart - clip.trimEnd) / Math.max(clip.duration, 0.1)) * 100)}%`,
                          }}
                        />
                      </span>
                      {clip.transition !== "none" && (
                        <span
                          title={clip.transition}
                          className="rounded bg-fuchsia-300/20 px-1 text-[8px] text-fuchsia-100"
                        >
                          {clip.transition}
                        </span>
                      )}
                    </div>
                    <span className="absolute right-1 bottom-1 text-[8px] text-white/30">
                      {index + 1}
                    </span>
                  </button>
                ))}
              </div>
              {state.textLayers.length > 0 && (
                <div className="flex min-h-8 items-center gap-1 rounded-lg bg-black/20 p-1">
                  <span className="w-14 shrink-0 pl-1 text-[9px] text-white/35">
                    TEXT
                  </span>
                  {state.textLayers.map((layer) => (
                    <button
                      key={layer.id}
                      onClick={() =>
                        setState((current) => ({
                          ...current,
                          selectedId: layer.id,
                        }))
                      }
                      style={{
                        marginLeft: `${layer.start * 5 * state.zoom}px`,
                        minWidth: `${Math.max(60, layer.duration * 12 * state.zoom)}px`,
                      }}
                      className={cn(
                        "rounded-md border px-2 py-1 text-left text-[9px]",
                        state.selectedId === layer.id
                          ? "border-amber-200/60 bg-amber-300/20 text-amber-100"
                          : "border-amber-200/20 bg-amber-300/10 text-amber-100/70",
                      )}
                    >
                      {layer.text}
                    </button>
                  ))}
                </div>
              )}
              {state.audioLayers.length > 0 && (
                <div className="flex min-h-9 items-center gap-1 rounded-lg bg-black/20 p-1">
                  <span className="w-14 shrink-0 pl-1 text-[9px] text-white/35">
                    AUDIO
                  </span>
                  {state.audioLayers.map((layer) => (
                    <button
                      key={layer.id}
                      onClick={() =>
                        setState((current) => ({
                          ...current,
                          selectedId: layer.id,
                        }))
                      }
                      style={{
                        marginLeft: `${layer.start * 5 * state.zoom}px`,
                        minWidth: `${Math.max(60, layer.duration * 12 * state.zoom)}px`,
                      }}
                      className={cn(
                        "flex items-center gap-1 rounded-md border px-2 py-1 text-left text-[9px]",
                        state.selectedId === layer.id
                          ? "border-emerald-200/60 bg-emerald-400/20 text-emerald-100"
                          : "border-emerald-200/20 bg-emerald-400/10 text-emerald-100/70",
                      )}
                    >
                      <AudioLines size={11} />
                      {layer.name}
                    </button>
                  ))}
                </div>
              )}
              <button
                aria-label="Set timeline playhead"
                onClick={(e) => {
                  const rect = e.currentTarget.getBoundingClientRect();
                  const time = Math.max(
                    0,
                    Math.min(
                      totalDuration,
                      ((e.clientX - rect.left) / rect.width) * totalDuration,
                    ),
                  );
                  setPlayhead(time);
                  if (videoRef.current) videoRef.current.currentTime = time;
                }}
                className="relative mt-1 h-4 w-full cursor-crosshair rounded-sm bg-white/[0.025]"
              >
                <span
                  className="absolute top-0 bottom-0 w-px bg-rose-400"
                  style={{
                    left: `${totalDuration ? (playhead / totalDuration) * 100 : 0}%`,
                  }}
                />
                <span
                  className="absolute top-0 size-2 -translate-x-1/2 rounded-full bg-rose-400"
                  style={{
                    left: `${totalDuration ? (playhead / totalDuration) * 100 : 0}%`,
                  }}
                />
              </button>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/8 px-3 py-2.5 text-[10px] text-white/40 sm:px-4">
          <span>
            Drag clips to reorder · Space play/pause · S split · Ctrl/Cmd+Z undo
            · Delete remove
          </span>
          <span className="flex items-center gap-1">
            <Check
              size={12}
              className={
                saveStatus === "saved" ? "text-emerald-300" : "text-white/30"
              }
            />
            {saveStatus === "saved"
              ? "Saved to project"
              : saveStatus === "saving"
                ? "Saving…"
                : "Save error"}
          </span>
        </div>
      </div>
      {showExport && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-white/15 bg-[#1a1b23] p-5 text-white shadow-2xl">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-base font-semibold">Export project</h3>
              <button
                onClick={() => setShowExport(false)}
                className="rounded p-1 text-white/50 hover:bg-white/10"
              >
                <X size={17} />
              </button>
            </div>
            <p className="text-xs leading-5 text-white/60">
              Render the saved clip order, trims, composited transitions, real
              selected audio assets, and timed text overlays into a new master.
              This does not regenerate shots or reserve generation credits.
              Captions are timeline overlays in editor mode; generated captions
              from the original scene order are omitted to avoid silently
              mis-timing them after reorder/split.
            </p>
            {outputUrl && (
              <a
                href={outputUrl}
                target="_blank"
                rel="noreferrer"
                className="mt-3 flex items-center justify-center gap-2 rounded-lg border border-white/15 px-4 py-2.5 text-xs text-white/80 hover:bg-white/5"
              >
                <Video size={14} /> Open current rendered video
              </a>
            )}
            <button
              onClick={() => void onRenderEdited()}
              disabled={renderingEdited || saveStatus === "saving"}
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-white px-4 py-2.5 text-xs font-semibold text-black hover:bg-violet-100 disabled:opacity-50"
            >
              {renderingEdited ? (
                <>
                  <span className="size-3 animate-spin rounded-full border-2 border-black/30 border-t-black" />{" "}
                  Queueing render…
                </>
              ) : (
                <>
                  <Video size={14} /> Render edited video
                </>
              )}
            </button>
            <button
              onClick={() => setShowExport(false)}
              className="mt-3 w-full rounded-lg border border-white/15 px-4 py-2.5 text-xs hover:bg-white/5"
            >
              Back to editor
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
