/**
 * Live hints for webcam enrollment (§13 screen 5 "quality feedback"). These are guidance only: the
 * engine's /embed validation (FR-9) decides whether a photo is accepted.
 */

export interface QualityHint {
  brightness: number; // 0..255 mean luma inside the guide oval
  sharpness: number; // variance of a Laplacian over the oval
  ok: boolean;
  message: string;
}

const DARK = 60;
const BRIGHT = 200;
const BLURRY = 60;

/** Mean luma and Laplacian variance over the central ellipse of an RGBA image. */
export function measureQuality(pixels: Uint8ClampedArray, width: number, height: number): QualityHint {
  const luma = new Float32Array(width * height);
  for (let i = 0, p = 0; i < luma.length; i += 1, p += 4) {
    luma[i] = 0.299 * pixels[p] + 0.587 * pixels[p + 1] + 0.114 * pixels[p + 2];
  }
  const cx = width / 2;
  const cy = height / 2;
  const rx = width * 0.3;
  const ry = height * 0.42;
  let sum = 0;
  let count = 0;
  let lapSum = 0;
  let lapSq = 0;
  let lapCount = 0;
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const dx = (x - cx) / rx;
      const dy = (y - cy) / ry;
      if (dx * dx + dy * dy > 1) continue;
      const i = y * width + x;
      sum += luma[i];
      count += 1;
      const lap = luma[i - 1] + luma[i + 1] + luma[i - width] + luma[i + width] - 4 * luma[i];
      lapSum += lap;
      lapSq += lap * lap;
      lapCount += 1;
    }
  }
  const brightness = count ? sum / count : 0;
  const mean = lapCount ? lapSum / lapCount : 0;
  const sharpness = lapCount ? lapSq / lapCount - mean * mean : 0;
  if (brightness < DARK) return { brightness, sharpness, ok: false, message: "Too dark: add light in front of the face" };
  if (brightness > BRIGHT) return { brightness, sharpness, ok: false, message: "Too bright: avoid strong light behind or above" };
  if (sharpness < BLURRY) return { brightness, sharpness, ok: false, message: "Blurry: hold still and keep the face in focus" };
  return { brightness, sharpness, ok: true, message: "Good: keep the face inside the oval and capture" };
}
