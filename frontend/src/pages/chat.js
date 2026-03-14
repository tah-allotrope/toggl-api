import { callApi } from "../api";

const QUICK_QUERIES = [
  "What did I work on today?",
  "Top projects this year",
  "How much did I track this week?",
  "Compare 2023 and 2024"
];

export async function renderChat(container, ctx) {
  container.innerHTML = `
    <h2>Chat</h2>
    <p class="muted">Ask questions about your tracked time history.</p>

    <div class="panel">
      <div class="row" id="quick-queries"></div>
    </div>

    <div class="chat-box" id="chat-box"></div>

    <div class="panel row">
      <div style="flex:1; min-width: 220px;">
        <label for="chat-input">Message</label>
        <input id="chat-input" type="text" placeholder="Ask about projects, tags, dates, or totals..." />
      </div>
      <div style="align-self:end;">
        <button id="chat-send" class="button">Send</button>
      </div>
    </div>
  `;

  const chatBox = container.querySelector("#chat-box");
  const input = container.querySelector("#chat-input");
  const sendButton = container.querySelector("#chat-send");
  const quick = container.querySelector("#quick-queries");

  const messages = [];

  function renderMessages() {
    chatBox.innerHTML = messages
      .map(
        (message) => `
          <div class="chat-msg ${message.role}">
            <strong>${message.role === "user" ? "You" : "Assistant"}</strong>
            <div>${message.content}</div>
          </div>
        `
      )
      .join("");
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  async function ask(question) {
    if (!question.trim()) {
      return;
    }

    messages.push({ role: "user", content: question });
    renderMessages();

    sendButton.disabled = true;
    sendButton.textContent = "Thinking...";

    try {
      const result = await callApi(ctx.auth, "/chat", { question });
      const answer = result?.answer || "No answer returned.";
      messages.push({ role: "assistant", content: answer });
    } catch (err) {
      messages.push({ role: "assistant", content: `Error: ${err.message || String(err)}` });
    } finally {
      sendButton.disabled = false;
      sendButton.textContent = "Send";
      renderMessages();
    }
  }

  quick.innerHTML = QUICK_QUERIES.map((text, index) => `<button class="button" id="quick-${index}" style="width:auto;">${text}</button>`).join("");
  QUICK_QUERIES.forEach((text, index) => {
    quick.querySelector(`#quick-${index}`).addEventListener("click", () => ask(text));
  });

  sendButton.addEventListener("click", () => {
    const question = input.value;
    input.value = "";
    ask(question);
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      const question = input.value;
      input.value = "";
      ask(question);
    }
  });

  messages.push({ role: "assistant", content: "Ask me about years, projects, tags, clients, tasks, and trends." });
  renderMessages();
}
