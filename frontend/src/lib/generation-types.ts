// Verified against backend/app/schemas/generation.py::GenerationType and
// backend/app/core/constants.py::GenerationType. Keep this list in sync
// with the backend enum — it is the single place the frontend names each
// generation type and points at its Create workflow.
export const GENERATION_TYPES = [
  "text_to_image",
  "image_to_image",
  "text_to_video",
  "image_to_video",
  "avatar",
  "video_translation",
  "audio_replace",
] as const;

export type GenerationTypeId = (typeof GENERATION_TYPES)[number];

export const TYPE_LABELS: Record<string, string> = {
  text_to_image: "Text to Image",
  image_to_image: "Image to Image",
  text_to_video: "Text to Video",
  image_to_video: "Image to Video",
  avatar: "Avatar",
  video_translation: "Video Translation",
  audio_replace: "Audio Replace",
  movie_shot: "Movie Shot",
};

export const TYPE_CREATE_ROUTES: Record<string, string> = {
  text_to_image: "/create/text-to-image",
  image_to_image: "/create/image-to-image",
  text_to_video: "/create/text-to-video",
  image_to_video: "/create/image-to-video",
  avatar: "/create/avatar",
  video_translation: "/create/translate",
  audio_replace: "/create/audio-replace",
};

export function isVideoType(type: string) {
  return ["text_to_video", "image_to_video", "avatar", "video_translation", "audio_replace", "movie_shot"].includes(
    type,
  );
}

export function isImageType(type: string) {
  return ["text_to_image", "image_to_image"].includes(type);
}
