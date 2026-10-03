/**
 * URLs of authenticated image endpoints, for <img src>. Browsers send the session cookie with these
 * same-origin GETs. This is the only place image URLs are built (the generated functions return blobs).
 */
const origin = import.meta.env.VITE_API_ORIGIN ?? "";
const base = `${origin}/api/v1`;

export const mediaUrl = {
  eventSnapshot: (eventId: number) => `${base}/events/${eventId}/snapshot`,
  unknownSnapshot: (unknownId: number) => `${base}/unknown-faces/${unknownId}/snapshot`,
  face: (employeeId: number, faceId: number, thumbnail = true) =>
    `${base}/employees/${employeeId}/faces/${faceId}/image${thumbnail ? "?thumbnail=true" : ""}`,
  employeePhoto: (employeeId: number) => `${base}/employees/${employeeId}/photo`,
};
