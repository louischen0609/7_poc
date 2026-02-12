const messagesDiv = document.getElementById("messages");
const input = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");

function addMessage(content, role) {
    const div = document.createElement("div");
    div.className = `message ${role}`;
    div.textContent = content;
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    return div;
}

async function sendMessage() {
    const text = input.value.trim();
    if (!text) return;

    addMessage(text, "user");
    input.value = "";
    sendBtn.disabled = true;

    const thinkingDiv = addMessage("思考中...", "assistant thinking");

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text }),
        });
        const data = await res.json();
        thinkingDiv.remove();
        addMessage(data.reply, "assistant");
    } catch (err) {
        thinkingDiv.remove();
        addMessage("系統錯誤，請稍後再試。", "assistant");
    } finally {
        sendBtn.disabled = false;
        input.focus();
    }
}

sendBtn.addEventListener("click", sendMessage);
input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.isComposing) sendMessage();
});

window.addEventListener("DOMContentLoaded", () => {
    addMessage(
        "您好！我是客戶服務助手，可以幫您：\n" +
        "- 查詢產品資訊\n" +
        "- 下單訂購\n" +
        "- 查詢訂單\n" +
        "- 安排配送（專車/郵寄）\n" +
        "- 記錄損耗\n\n" +
        "請問有什麼需要幫忙的嗎？",
        "assistant"
    );
    input.focus();
});
