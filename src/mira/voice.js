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
let closing = false;

function setStatus(message) {
  statusLine.textContent = message;
}

function stopSession(message = "Disconnected") {
  if (closing) return;
  closing = true;
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
  closing = false;
}

function showError(message) {
  transcriptBox.textContent = message;
}

async function startSession() {
  startButton.disabled = true;
  stopButton.disabled = false;
  transcriptBox.textContent = "";
  totalTokens = 0;
  usageLine.textContent = "Session token usage: 0";
  setStatus("Preparing a short-lived voice connection…");

  let ownerToken = tokenInput.value.trim();
  tokenInput.value = "";
  let ephemeralKey = "";
  try {
    if (!ownerToken) throw new Error("Enter your MIRA owner token first.");
    const secretResponse = await fetch("/v1/realtime/client-secret", {
      method: "POST",
      headers: { Authorization: `Bearer ${ownerToken}` },
      cache: "no-store",
    });
    ownerToken = "";
    if (!secretResponse.ok) {
      const detail = secretResponse.status === 503
        ? "Dedicated voice is not enabled on this MIRA server yet."
        : secretResponse.status === 401 || secretResponse.status === 403
          ? "The MIRA owner token was not accepted."
          : "MIRA could not prepare the voice session.";
      throw new Error(detail);
    }
    const secret = await secretResponse.json();
    ephemeralKey = secret.value;
    if (typeof ephemeralKey !== "string" || !ephemeralKey.startsWith("ek_")) {
      throw new Error("MIRA received an invalid temporary voice credential.");
    }

    microphone = await navigator.mediaDevices.getUserMedia({ audio: true });
    peer = new RTCPeerConnection();
    peer.ontrack = (event) => {
      speaker.srcObject = event.streams[0];
      speaker.play().catch(() => setStatus("Connected. Press Play to hear Mira."));
    };
    peer.onconnectionstatechange = () => {
      if (peer && ["failed", "closed", "disconnected"].includes(peer.connectionState)) {
        stopSession("Voice connection ended.");
      }
    };
    microphone.getTracks().forEach((track) => peer.addTrack(track, microphone));
    channel = peer.createDataChannel("mira-events");
    channel.onopen = () => {
      setStatus(`Connected to Mira · ${secret.model} · ${secret.voice}`);
      channel.send(JSON.stringify({
        type: "conversation.item.create",
        item: { type: "message", role: "user", content: [{
          type: "input_text",
          text: "Welcome me now with the brief truthful Mira introduction from your system instructions.",
        }] },
      }));
      channel.send(JSON.stringify({
        type: "response.create",
        response: { output_modalities: ["audio"], max_output_tokens: 96 },
      }));
    };
    channel.onmessage = (event) => {
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

    const offer = await peer.createOffer();
    await peer.setLocalDescription(offer);
    const callResponse = await fetch("https://api.openai.com/v1/realtime/calls", {
      method: "POST",
      headers: { Authorization: `Bearer ${ephemeralKey}`, "Content-Type": "application/sdp" },
      body: offer.sdp,
      cache: "no-store",
    });
    ephemeralKey = "";
    if (!callResponse.ok) throw new Error("OpenAI could not start the voice session.");
    await peer.setRemoteDescription({ type: "answer", sdp: await callResponse.text() });
    sessionTimer = window.setTimeout(() => stopSession("Session ended after 10 minutes."), 10 * 60 * 1000);
    setStatus("Connecting to Mira…");
  } catch (error) {
    ownerToken = "";
    ephemeralKey = "";
    stopSession("Disconnected");
    showError(error instanceof Error ? error.message : "Mira could not start the voice session.");
  }
}

startButton.addEventListener("click", startSession);
stopButton.addEventListener("click", () => stopSession("Session ended by you."));
