import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../src/mira/voice.js", import.meta.url), "utf8");
const identityUrl = "/v1/identity?channel=voice";
const credentialUrl = "/v1/realtime/client-secret";
const callUrl = "https://api.openai.com/v1/realtime/calls";

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

function jsonResponse(body) {
  return { ok: true, json: async () => body };
}

const answerResponse = { ok: true, text: async () => "answer-sdp" };

function browser({
  transport = "openai-realtime-webrtc",
  getMicrophone = (stream) => stream,
  getAnswer = () => answerResponse,
} = {}) {
  const requests = [];
  const peers = [];
  const timers = new Map();
  let microphoneRequests = 0;
  let stoppedTracks = 0;
  const stream = { getTracks: () => [{ stop: () => { stoppedTracks += 1; } }] };
  const elements = Object.fromEntries(
    ["start", "stop", "owner-token", "status", "transcript", "usage", "speaker"].map((id) => [
      id, { addEventListener(event, listener) { this[event] = listener; } },
    ]),
  );

  class Peer {
    constructor() {
      peers.push(this);
      this.sent = [];
    }
    addTrack() {}
    async createOffer() {
      return { type: "offer", sdp: "offer-sdp" };
    }
    async setLocalDescription() {}
    async setRemoteDescription(answer) {
      this.answer = answer;
      this.events.readyState = "open";
      this.events.onopen();
    }
    createDataChannel() {
      this.events = {
        readyState: "connecting",
        send: (event) => { this.sent.push(JSON.parse(event)); },
        close() { this.readyState = "closed"; },
      };
      return this.events;
    }
    close() {
      this.connectionState = "closed";
      this.onconnectionstatechange();
    }
  }

  runInNewContext(source, {
    AbortController,
    document: { getElementById: (id) => elements[id] },
    navigator: { mediaDevices: { getUserMedia: async () => {
      microphoneRequests += 1;
      return getMicrophone(stream);
    } } },
    RTCPeerConnection: Peer,
    fetch: async (url, options) => {
      requests.push({ url, options });
      if (url === identityUrl) return jsonResponse({ voice_transport: transport });
      if (url === credentialUrl) {
        return jsonResponse({ value: "ek_test", model: "test-model", voice: "marin" });
      }
      assert.equal(url, callUrl);
      return getAnswer(options);
    },
    window: {
      setTimeout(callback, milliseconds) {
        timers.set(milliseconds, callback);
        return milliseconds;
      },
      clearTimeout: (id) => timers.delete(id),
    },
  });

  return {
    requests, peers, timers, elements,
    start: () => {
      elements["owner-token"].value = "local-test-owner-token";
      return elements.start.click();
    },
    stop: () => elements.stop.click(),
    get microphoneRequests() { return microphoneRequests; },
    get stoppedTracks() { return stoppedTracks; },
  };
}

test("disabled voice checks local configuration before requesting microphone access", async () => {
  const page = browser({ transport: "disabled" });
  await page.start();
  assert.deepEqual(page.requests.map(({ url }) => url), [identityUrl]);
  assert.equal(page.microphoneRequests, 0);
  assert.match(page.elements.transcript.textContent, /not enabled/);
});

test("ending a session while the permission prompt is open stops a late microphone stream", async () => {
  const requested = deferred();
  const permission = deferred();
  const page = browser({ getMicrophone(stream) {
    requested.resolve(stream);
    return permission.promise;
  } });
  const starting = page.start();
  const stream = await requested.promise;
  page.stop();
  permission.resolve(stream);
  await starting;
  assert.deepEqual(page.requests.map(({ url }) => url), [identityUrl]);
  assert.equal(page.stoppedTracks, 1);
  assert.equal(page.peers.length, 0);
  assert.equal(page.elements.status.textContent, "Session ended by you.");
});

test("ending a connection aborts signaling and ignores a late OpenAI answer", async () => {
  const requested = deferred();
  const reply = deferred();
  const page = browser({ getAnswer(options) {
    requested.resolve(options);
    return reply.promise;
  } });
  const starting = page.start();
  const options = await requested.promise;
  page.stop();
  assert.equal(options.signal.aborted, true);
  assert.equal(page.peers[0].connectionState, "closed");
  assert.equal(page.stoppedTracks, 1);
  reply.resolve(answerResponse);
  await starting;
  assert.equal(page.peers[0].answer, undefined);
  assert.deepEqual(page.peers[0].sent, []);
  assert.equal(page.timers.size, 0);
  assert.equal(page.elements.status.textContent, "Session ended by you.");
});

test("every new voice connection requests Mira's introduction and ends at the page time limit", async () => {
  const page = browser();
  for (let i = 0; i < 2; i += 1) {
    await page.start();
    assert.equal(page.peers[i].answer.sdp, "answer-sdp");
    const [greeting, response] = page.peers[i].sent;
    assert.equal(greeting.type, "conversation.item.create");
    assert.match(greeting.item.content[0].text, /Mira introduction/);
    assert.deepEqual(response, { type: "response.create", response: { output_modalities: ["audio"] } });
    assert.match(page.elements.status.textContent, /Connected to Mira/);
    page.timers.get(600_000)();
    assert.equal(page.peers[i].connectionState, "closed");
  }
  assert.deepEqual(page.requests.map(({ url }) => url), [
    identityUrl, credentialUrl, callUrl, identityUrl, credentialUrl, callUrl,
  ]);
  assert.equal(page.stoppedTracks, 2);
});
