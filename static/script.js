(() => {
  // If chatbot HTML is not on this page, do nothing
  const chatWidget = document.getElementById("chat-widget");
  if (!chatWidget) return;

  // 🔗 Backend URL for chatbot_app.py (runs on port 8000)
  const CHATBOT_BASE_URL = "http://127.0.0.1:5000";

  const chatToggle = document.getElementById("chat-toggle");
  const chatPanel = document.getElementById("chat-panel");
  const chatClose = document.getElementById("chat-close");
  const sendBtn = document.getElementById("send-btn");
  const userInput = document.getElementById("user-input");
  const messagesDiv = document.getElementById("messages");
  const micBtn = document.getElementById("mic-btn");
  const recordingIndicator = document.getElementById("recording-indicator");
  const languageSelect = document.getElementById("language-select");

  // New Stop Audio button (ensure this exists in your HTML)
  const stopAudioBtn = document.getElementById("stop-audio-btn");

  let isRecording = false;
  let mediaRecorder;
  let audioChunks = [];
  let currentAudio = null; // 🔊 track currently playing audio

  // --- Chat open/close ---
  chatToggle.addEventListener("click", () => {
    chatWidget.classList.toggle("chat-closed");
    const isClosed = chatWidget.classList.contains("chat-closed");
    chatPanel.setAttribute("aria-hidden", isClosed);
  });

  chatClose.addEventListener("click", () => {
    chatWidget.classList.add("chat-closed");
    chatPanel.setAttribute("aria-hidden", "true");
  });

  // --- Helper: append messages ---
  function appendMessage(who, text) {
    const div = document.createElement("div");
    div.className = who === "user" ? "msg user" : "msg bot";
    div.textContent = text;
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
  }

  // --- Send text message ---
  async function sendTextMessage(text, fromVoice = false) {
    if (!text.trim()) return;
    appendMessage("user", text);
    userInput.value = "";

    appendMessage("bot", "⏳ Thinking...");

    try {
      const res = await fetch(`${CHATBOT_BASE_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_message: text,
          language_code: languageSelect.value,
          from_voice: fromVoice
        }),
      });

      if (!res.ok) {
        messagesDiv.lastChild.remove(); // remove "Thinking..."
        appendMessage("bot", "⚠️ Error contacting chatbot. Please try again.");
        return;
      }

      const data = await res.json();
      // Remove "thinking" placeholder
      messagesDiv.lastChild.remove();
      appendMessage("bot", data.bot_response || "No response received.");

      // --- Audio playback section ---
      if (fromVoice && data.audio_response) {
        setTimeout(() => {
          // Stop any currently playing audio before starting a new one
          if (currentAudio) {
            currentAudio.pause();
            currentAudio.currentTime = 0;
          }
          currentAudio = new Audio("data:audio/mp3;base64," + data.audio_response);
          currentAudio.play();
        }, 500);
      }
    } catch (err) {
      messagesDiv.lastChild.remove(); // remove "Thinking..."
      appendMessage("bot", "⚠️ Error contacting chatbot: " + err.message);
    }
  }

  sendBtn.addEventListener("click", () => sendTextMessage(userInput.value, false));

  userInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendTextMessage(userInput.value, false);
    }
  });

  // --- Stop Audio Button ---
  if (stopAudioBtn) {
    stopAudioBtn.addEventListener("click", () => {
      if (currentAudio) {
        currentAudio.pause();
        currentAudio.currentTime = 0;
        appendMessage("bot", "🔇 Audio stopped.");
      }
    });
  }

  // --- Voice input handling ---
  micBtn.addEventListener("click", async () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  });

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      audioChunks = [];
      isRecording = true;
      recordingIndicator.classList.remove("hidden");

      mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
      mediaRecorder.onstop = handleAudioStop;
      mediaRecorder.start();
    } catch (err) {
      appendMessage("bot", "🎤 Microphone not accessible: " + err.message);
    }
  }

  function stopRecording() {
    if (mediaRecorder && isRecording) {
      mediaRecorder.stop();
      isRecording = false;
      recordingIndicator.classList.add("hidden");
    }
  }

  async function handleAudioStop() {
    const blob = new Blob(audioChunks, { type: "audio/webm" });
    const formData = new FormData();
    formData.append("file", blob, "speech.webm");
    formData.append("language_code", languageSelect.value);

    appendMessage("user", "🎤 Processing your voice...");

    try {
      const res = await fetch(`${CHATBOT_BASE_URL}/speech`, {
        method: "POST",
        body: formData
      });

      if (!res.ok) {
        appendMessage("bot", "⚠️ Error contacting speech service.");
        return;
      }

      const speechData = await res.json();

      if (speechData.transcribed_text?.startsWith("ERROR")) {
        appendMessage("bot", "⚠️ Speech recognition failed.");
        return;
      }

      const userText = speechData.transcribed_text;
      sendTextMessage(userText, true);
    } catch (err) {
      appendMessage("bot", "⚠️ Error contacting speech service: " + err.message);
    }
  }

  // --- Welcome message ---
  appendMessage(
    "bot",
    "🌿 Hi! I’m your AI assistant for pomegranate farming. You can type or talk to me."
  );
})();
