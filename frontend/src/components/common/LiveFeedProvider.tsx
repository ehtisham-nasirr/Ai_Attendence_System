import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";

import { LiveStatusContext, type LiveStatus } from "@/hooks/useLiveFeed";
import { applyLiveMessage, backoffDelay, parseLiveMessage, throttledInvalidator } from "@/lib/live";

const UNAUTHORISED_CLOSE = 4401;
const HIDDEN_GRACE_MS = 60_000;

function socketUrl(): string {
  const path = import.meta.env.VITE_WS_URL ?? "/ws/live";
  if (/^wss?:\/\//.test(path)) return path;
  const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${window.location.host}${path}`;
}

/**
 * Owns the single `/ws/live` connection (standards/08): reconnects with backoff, pauses while the
 * tab is hidden, and writes every message into the query cache. Pages never open their own socket.
 */
export function LiveFeedProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<LiveStatus>("connecting");

  useEffect(() => {
    const invalidate = throttledInvalidator(queryClient);
    let socket: WebSocket | null = null;
    let attempt = 0;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let hiddenTimer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;

    const connect = () => {
      if (stopped || socket) return;
      setStatus("connecting");
      const ws = new WebSocket(socketUrl());
      socket = ws;
      ws.onopen = () => {
        attempt = 0;
        setStatus("open");
        // Anything missed while disconnected is refetched from the REST API.
        void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      };
      ws.onmessage = (event: MessageEvent) => {
        const message = parseLiveMessage(event.data);
        if (message) applyLiveMessage(queryClient, message, invalidate);
      };
      ws.onclose = (event: CloseEvent) => {
        socket = null;
        if (stopped) return;
        if (event.code === UNAUTHORISED_CLOSE) {
          setStatus("closed");
          return; // session ended; the next API call shows the sign-in page
        }
        if (document.visibilityState === "hidden") {
          setStatus("paused");
          return;
        }
        setStatus("closed");
        retryTimer = setTimeout(connect, backoffDelay(attempt++));
      };
    };

    const onVisibility = () => {
      if (document.visibilityState === "hidden") {
        hiddenTimer = setTimeout(() => {
          setStatus("paused");
          socket?.close(1000, "tab hidden");
        }, HIDDEN_GRACE_MS);
      } else {
        clearTimeout(hiddenTimer);
        clearTimeout(retryTimer);
        attempt = 0;
        connect();
      }
    };

    connect();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stopped = true;
      clearTimeout(retryTimer);
      clearTimeout(hiddenTimer);
      invalidate.cancel();
      document.removeEventListener("visibilitychange", onVisibility);
      socket?.close(1000, "unmount");
    };
  }, [queryClient]);

  return <LiveStatusContext.Provider value={status}>{children}</LiveStatusContext.Provider>;
}
