(() => {
  "use strict";

  const form = document.getElementById("chat-form");
  const questionInput = document.getElementById("question");
  const messages = document.getElementById("messages");
  const sendButton = document.getElementById("send-button");
  const requestStatus = document.getElementById("request-status");
  const documentRef = document.getElementById("document-ref");
  const chunkLimit = document.getElementById("chunk-limit");
  const maxParagraphs = document.getElementById("max-paragraphs");
  const maxTokens = document.getElementById("max-tokens");

  const scrollToLatest = () => {
    messages.scrollTop = messages.scrollHeight;
  };

  const addMessage = (role, text, payload = null) => {
    const article = document.createElement("article");
    article.className = `message ${role}`;

    const speaker = document.createElement("div");
    speaker.className = "speaker";
    speaker.textContent = role === "user" ? "Bạn" : "Agent";

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    const paragraph = document.createElement("p");
    paragraph.textContent = text;
    bubble.appendChild(paragraph);

    if (payload && payload.sources && payload.sources.length > 0) {
      const details = document.createElement("details");
      details.className = "source-details";
      const summary = document.createElement("summary");
      summary.textContent = `${payload.sources.length} nguồn đã sử dụng`;
      details.appendChild(summary);

      const list = document.createElement("ol");
      list.className = "source-list";
      payload.sources.forEach((source, index) => {
        const item = document.createElement("li");
        const pages = source.page_start === null
          ? "không có số trang"
          : `trang ${source.page_start}${source.page_end !== source.page_start ? `-${source.page_end}` : ""}`;
        item.textContent = `${source.citation || `[${index + 1}]`} ${source.source} · ${pages} · ${source.chunk_id}`;
        list.appendChild(item);
      });
      details.appendChild(list);
      bubble.appendChild(details);
    }

    if (payload && payload.model_version) {
      const model = document.createElement("div");
      model.className = "model-line";
      model.textContent = `Model: ${payload.model_version}`;
      bubble.appendChild(model);
    }

    article.append(speaker, bubble);
    messages.appendChild(article);
    scrollToLatest();
  };

  const statusMessage = (payload) => {
    if (payload.status === "no_retrieval_context") {
      return "Tôi chưa tìm thấy chunk phù hợp trong phạm vi đã chọn.";
    }
    if (payload.status === "no_relevant_concept_role") {
      return "Đã tìm thấy chunk, nhưng chưa có concept-role đủ phù hợp để trả lời an toàn.";
    }
    return payload.answer || "Không có câu trả lời.";
  };

  const numericValue = (element) => Number.parseInt(element.value, 10);

  const sendQuestion = async (question) => {
    const normalized = question.trim();
    if (!normalized || sendButton.disabled) return;

    addMessage("user", normalized);
    questionInput.value = "";
    sendButton.disabled = true;
    requestStatus.textContent = "Đang tìm chunk và tạo câu trả lời...";

    const selectedDocument = documentRef.value.trim();
    const body = {
      question: normalized,
      chunk_limit: numericValue(chunkLimit),
      max_paragraphs: numericValue(maxParagraphs),
      max_tokens: numericValue(maxTokens),
    };
    if (selectedDocument) {
      body.filters = { document_ref: selectedDocument };
    }

    try {
      const response = await fetch("/agent/chat/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || `HTTP ${response.status}`);
      }
      addMessage("assistant", statusMessage(payload), payload);
      requestStatus.textContent = "Sẵn sàng";
    } catch (error) {
      addMessage("assistant", `Không thể xử lý câu hỏi: ${error.message}`);
      requestStatus.textContent = "Có lỗi, hãy thử lại";
    } finally {
      sendButton.disabled = false;
      questionInput.focus();
    }
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    sendQuestion(questionInput.value);
  });

  questionInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  document.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => {
      questionInput.value = button.dataset.question;
      questionInput.focus();
    });
  });

  document.getElementById("clear-chat").addEventListener("click", () => {
    messages.querySelectorAll(".message:not(.welcome-message)").forEach((message) => message.remove());
    requestStatus.textContent = "Sẵn sàng";
    questionInput.focus();
  });
})();
