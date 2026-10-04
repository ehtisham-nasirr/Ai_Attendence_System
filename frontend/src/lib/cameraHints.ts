/** What the owner can do about the most common RTSP failures (the raw error is still shown). */
export function connectionHint(error: string): string | null {
  const text = error.toLowerCase();
  if (text.includes("401") || text.includes("unauthorized")) {
    return "The camera rejected the username or password. Check them in VLC first. In the URL, write special characters in the password as @ → %40, # → %23, : → %3A. Many cameras lock the account for a while after several wrong attempts.";
  }
  if (text.includes("403") || text.includes("forbidden")) {
    return "The camera refused this account. Cameras such as Dahua lock the account for a while (often 30 minutes) after several wrong passwords; FaceTrack keeps retrying a saved wrong link, so save the correct link, or turn the camera off here, then wait or restart the camera. Also check that the user may view live video.";
  }
  if (text.includes("404") || text.includes("not found")) {
    return "The camera answered but the stream path is wrong. Dahua: /cam/realmonitor?channel=1&subtype=0; Hikvision: /Streaming/Channels/101.";
  }
  if (text.includes("timed out") || text.includes("timeout") || text.includes("no route") || text.includes("refused")) {
    return "The engine cannot reach the camera. Check the IP address, the RTSP port (usually 554) and that this computer is on the camera network.";
  }
  return null;
}
