// ═══════════════════════════════════════════════════════════
// DermaAI Chatbot Logic
// ═══════════════════════════════════════════════════════════

document.addEventListener("DOMContentLoaded", () => {
  const API_BASE = window.API_BASE || 'https://sujal1207-dermaai54.hf.space';
  const chatToggle = document.getElementById("chat-toggle");
  const chatClose = document.getElementById("chat-close");
  const chatWindow = document.getElementById("chat-window");
  const chatBody = document.getElementById("chat-body");
  const chatInput = document.getElementById("chat-input");
  const chatSend = document.getElementById("chat-send");
  
  let isChatOpen = false;

  // Toggle chat
  chatToggle.addEventListener("click", () => {
    isChatOpen = !isChatOpen;
    chatWindow.classList.toggle("open", isChatOpen);
    if (isChatOpen) {
      chatInput.focus();
    }
  });

  chatClose.addEventListener("click", () => {
    isChatOpen = false;
    chatWindow.classList.remove("open");
  });

  // Append message to UI
  function appendMessage(text, sender, tag = null) {
    const msgDiv = document.createElement("div");
    msgDiv.classList.add("chat-message", sender);
    
    let content = `<div class="msg-bubble">${text}</div>`;
    
    if (tag) {
      content += `<div class="msg-tag">Powered by ${tag}</div>`;
    }

    msgDiv.innerHTML = content;
    chatBody.appendChild(msgDiv);
    
    // Smooth scroll to bottom
    chatBody.scrollTo({
      top: chatBody.scrollHeight,
      behavior: 'smooth'
    });
  }

  // Handle send logic
  async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;

    // Add user message
    appendMessage(text, "user");
    chatInput.value = "";
    
    // Add loading indicator
    const loadingId = "loader-" + Date.now();
    const loadingDiv = document.createElement("div");
    loadingDiv.classList.add("chat-message", "bot");
    loadingDiv.id = loadingId;
    loadingDiv.innerHTML = `<div class="msg-bubble loading"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>`;
    chatBody.appendChild(loadingDiv);
    chatBody.scrollTop = chatBody.scrollHeight;

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text })
      });

      const data = await response.json();
      
      // remove loader
      document.getElementById(loadingId).remove();

      if (response.ok) {
        // Render bot reply with markdown link fix and line breaks
        let reply = data.reply.replace(/\n/g, "<br>");
        appendMessage(reply, "bot", data.provider);
      } else {
        appendMessage("An error occurred: " + (data.error || "Please try again."), "bot", "System");
      }
      
    } catch (error) {
      document.getElementById(loadingId).remove();
      appendMessage("Network error. Cannot reach the server.", "bot", "System");
    }
  }

  chatSend.addEventListener("click", sendMessage);
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendMessage();
  });
});
