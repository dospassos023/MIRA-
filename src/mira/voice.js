"use strict";

const startButton = document.getElementById("start");
const stopButton = document.getElementById("stop");
const tokenInput = document.getElementById("owner-token");
const statusLine = document.getElementById("status");
const transcriptBox = document.getElementById("transcript");
const usageLine = document.getElementById("usage");
const speaker = document.getElementById("speaker");

let peer = null;
let microphone = null;
let channel = null;
let sessionTimer = null;
let totalTokens = 0;
let sessionController = null;

function setStatus(message) {
  statusLine.textContent = message;
}

function stopSession(message = "Disconnected") {
  sessionController?.abort();
  sessionController = null;
  window.clearTimeout(sessionTimer);
  sessionTimer = null;
  if (channel && channel.readyState !== "closed") channel.close();
  if (peer) peer.close();
  if (microphone) microphone.getTracks().forEach((track) => track.stop());
  peer = null;
  microphone = null;
  channel = null;
  speaker.srcObject = null;
  startButton.disabled = false;
  stopButton.disabled = true;
  setStatus(message);
}

function requireVoiceResponse(response) {
  if (response.ok) return;
  if (response.status === 401 || response.status === 403) {
    throw new Error("The MIRA owner token was not accepted.");
  }
  if (response.status === 503) {
    throw new Error("Dedicated voice is not enabled on this MIRA server yet.");
  }
  throw new Error("MIRA could not prepare the voice session.");
}

async function startSession() {
  if (sessionController) return;
  sessionController = new AbortController();
  const { signal } = sessionController;
  startButton.disabled = true;
  stopButton.disabled = false;
  transcriptBox.textContent = "";
  totalTokens = 0;
  usageLine.textContent = "Session token usage: 0";
  setStatus("Checking voice availability…");

  const ownerToken = tokenInput.value.trim();
  tokenInput.value = "";
  try {
    if (!ownerToken) throw new Error("Enter your MIRA owner token first.");
    const identityResponse = await fetch("/v1/identity?channel=voice", {
      headers: { Authorization: `Bearer ${ownerToken}` },
      cache: "no-store",
      signal,
    });
    signal.throwIfAborted();
    requireVoiceResponse(identityResponse);
    const identity = await identityResponse.json();
    signal.throwIfAborted();
    if (identity.voice_transport !== "openai-realtime-webrtc") {
      throw new Error("Dedicated voice is not enabled on this MIRA server yet.");
    }

    setStatus("Waiting for microphone permission…");
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    if (signal.aborted) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    microphone = stream;
    const connection = new RTCPeerConnection();
    peer = connection;
    connection.ontrack = (event) => {
      if (signal.aborted) return;
      speaker.srcObject = event.streams[0];
      speaker.play().catch(() => {
        if (!signal.aborted) setStatus("Connected. Press Play to hear Mira.");
      });
    };
    connection.onconnectionstatechange = () => {
      if (!signal.aborted && ["failed", "closed", "disconnected"].includes(connection.connectionState)) {
        stopSession("Voice connection ended.");
      }
    };
    stream.getTracks().forEach((track) => connection.addTrack(track, stream));
    const events = connection.createDataChannel("mira-events");
    channel = events;

    const offer = await connection.createOffer();
    signal.throwIfAborted();
    await connection.setLocalDescription(offer);
    signal.throwIfAborted();
    setStatus("Preparing a short-lived voice connection…");
    const secretResponse = await fetch("/v1/realtime/client-secret", {
      method: "POST",
      headers: { Authorization: `Bearer ${ownerToken}` },
      cache: "no-store",
      signal,
    });
    signal.throwIfAborted();
    requireVoiceResponse(secretResponse);
    const { value: ephemeralKey, model, voice } = await secretResponse.json();
    signal.throwIfAborted();
    if (typeof ephemeralKey !== "string" || !ephemeralKey.startsWith("ek_")) {
      throw new Error("MIRA received an invalid temporary voice credential.");
    }

    events.onopen = () => {
      if (signal.aborted) return;
      setStatus(`Connected to Mira · ${model} · ${voice}`);
      events.send(JSON.stringify({
        type: "conversation.item.create",
        item: { type: "message", role: "user", content: [{
          type: "input_text",
          text: "Welcome me now with the brief truthful Mira introduction from your system instructions.",
        }] },
      }));
      events.send(JSON.stringify({
        type: "response.create",
        response: { output_modalities: ["audio"] },
      }));
    };
    events.onmessage = (event) => {
      if (signal.aborted) return;
      let message;
      try { message = JSON.parse(event.data); } catch { return; }
      if (message.type === "response.output_audio_transcript.delta" && typeof message.delta === "string") {
        transcriptBox.textContent += message.delta;
      } else if (message.type === "response.output_audio_transcript.done" && typeof message.transcript === "string") {
        transcriptBox.textContent = message.transcript;
      } else if (message.type === "response.done" && message.response && message.response.usage) {
        const count = message.response.usage.total_tokens;
        if (Number.isSafeInteger(count) && count >= 0) {
          totalTokens += count;
          usageLine.textContent = `Session token usage: ${totalTokens} · Check the OpenAI dashboard for billed amount`;
        }
      } else if (message.type === "error") {
        setStatus("Mira voice reported a connection error. End the session and try again.");
      }
    };

    const callResponse = await fetch("https://api.openai.com/v1/realtime/calls", {
      method: "POST",
      headers: { Authorization: `Bearer ${ephemeralKey}`, "Content-Type": "application/sdp" },
      body: offer.sdp,
      cache: "no-store",
      signal,
    });
    signal.throwIfAborted();
    if (!callResponse.ok) throw new Error("OpenAI could not start the voice session.");
    const answer = await callResponse.text();
    signal.throwIfAborted();
    setStatus("Connecting to Mira…");
    await connection.setRemoteDescription({ type: "answer", sdp: answer });
    signal.throwIfAborted();
    sessionTimer = window.setTimeout(() => stopSession("Session ended after 10 minutes."), 10 * 60 * 1000);
  } catch (error) {
    if (signal.aborted) return;
    stopSession("Disconnected");
    transcriptBox.textContent = error instanceof Error ? error.message : "Mira could not start the voice session.";
  }
}

startButton.addEventListener("click", startSession);
stopButton.addEventListener("click", () => stopSession("Session ended by you."));
