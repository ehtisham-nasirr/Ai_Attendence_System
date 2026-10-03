import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LiveFeedProvider } from "@/components/common/LiveFeedProvider";
import { LIVE_KEYS, type RecognitionCreatedData } from "@/lib/live";

class MockSocket {
  static instances: MockSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  url: string;
  closed = false;
  constructor(url: string) {
    this.url = url;
    MockSocket.instances.push(this);
  }
  close() {
    this.closed = true;
  }
  open() {
    this.onopen?.();
  }
  send(message: unknown) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
  drop(code = 1006) {
    this.onclose?.({ code });
  }
}

function mount(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <LiveFeedProvider>
        <span>child</span>
      </LiveFeedProvider>
    </QueryClientProvider>,
  );
}

describe("LiveFeedProvider (one shared /ws/live socket)", () => {
  beforeEach(() => {
    MockSocket.instances = [];
    vi.stubGlobal("WebSocket", MockSocket);
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("writes messages into the query cache", () => {
    const client = new QueryClient();
    mount(client);
    const socket = MockSocket.instances[0];
    expect(socket.url).toMatch(/^ws:\/\/.+\/ws\/live$/);
    act(() => {
      socket.open();
      socket.send({
        type: "RecognitionCreated",
        sent_at: "",
        data: { event_id: 5, camera_id: 1, status: "recognized", employee_name: "Sara", bbox: null, confidence: 0.7, captured_at: "" },
      });
    });
    expect(client.getQueryData<RecognitionCreatedData[]>(LIVE_KEYS.recentEvents)?.[0].event_id).toBe(5);
  });

  it("reconnects with backoff after a drop", () => {
    mount(new QueryClient());
    act(() => MockSocket.instances[0].drop());
    expect(MockSocket.instances).toHaveLength(1);
    act(() => vi.advanceTimersByTime(1_300));
    expect(MockSocket.instances).toHaveLength(2);
    act(() => MockSocket.instances[1].drop());
    act(() => vi.advanceTimersByTime(1_300));
    expect(MockSocket.instances).toHaveLength(2); // second attempt waits ~2 s
    act(() => vi.advanceTimersByTime(1_200));
    expect(MockSocket.instances).toHaveLength(3);
  });

  it("does not reconnect when the session was rejected (4401)", () => {
    mount(new QueryClient());
    act(() => MockSocket.instances[0].drop(4401));
    act(() => vi.advanceTimersByTime(60_000));
    expect(MockSocket.instances).toHaveLength(1);
  });

  it("closes the socket on unmount", () => {
    const view = mount(new QueryClient());
    view.unmount();
    expect(MockSocket.instances[0].closed).toBe(true);
  });
});
