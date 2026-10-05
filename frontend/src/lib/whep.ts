/**
 * Minimal WHEP client for MediaMTX WebRTC playback (standards/08 "Live Video"). The browser only ever
 * talks to MediaMTX through the URL and short-lived token from GET /cameras/{id}/live — never to the
 * camera or its RTSP credentials.
 */

const ICE_GATHER_TIMEOUT_MS = 2_000;

function waitForIce(pc: RTCPeerConnection): Promise<void> {
  if (pc.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolve) => {
    const done = () => {
      pc.removeEventListener("icegatheringstatechange", check);
      resolve();
    };
    const check = () => pc.iceGatheringState === "complete" && done();
    pc.addEventListener("icegatheringstatechange", check);
    setTimeout(done, ICE_GATHER_TIMEOUT_MS);
  });
}

export interface WhepSession {
  stop: () => void;
}

export async function startWhep(
  url: string,
  token: string,
  onStream: (stream: MediaStream) => void,
  onFailed: () => void,
): Promise<WhepSession> {
  const pc = new RTCPeerConnection();
  pc.addTransceiver("video", { direction: "recvonly" });
  pc.ontrack = (event) => onStream(event.streams[0] ?? new MediaStream([event.track]));
  pc.onconnectionstatechange = () => {
    if (pc.connectionState === "failed") onFailed();
  };
  await pc.setLocalDescription(await pc.createOffer());
  await waitForIce(pc);
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/sdp", Authorization: `Bearer ${token}` },
    body: pc.localDescription?.sdp ?? "",
  });
  if (!response.ok) {
    pc.close();
    if (response.status === 401) throw new Error("Live view not authorised");
    const detail = await response.text().catch(() => "");
    if (/codecs? not supported/i.test(detail)) {
      throw new Error("The browser cannot play this stream's codec (often H.265). Set the camera stream to H.264.");
    }
    throw new Error(`Live view unavailable (${response.status})`);
  }
  await pc.setRemoteDescription({ type: "answer", sdp: await response.text() });
  const location = response.headers.get("Location");
  return {
    stop: () => {
      pc.close();
      if (location) {
        void fetch(new URL(location, new URL(url, window.location.href)), {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        }).catch(() => undefined);
      }
    },
  };
}
