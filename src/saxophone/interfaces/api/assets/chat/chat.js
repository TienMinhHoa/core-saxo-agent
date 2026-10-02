(() => {
  "use strict";

  const form = document.getElementById("chat-form");
  const questionInput = document.getElementById("question");
  const messages = document.getElementById("messages");
  const sendButton = document.getElementById("send-button");
  const requestStatus = document.getElementById("request-status");
  const requestActivity = document.getElementById("request-activity");
  const requestElapsed = document.getElementById("request-elapsed");
  let activityTimer = null;
  const stopProcessing = () => {
    if (activityTimer !== null) clearInterval(activityTimer);
    activityTimer = null;
    requestActivity.hidden = true;
    form.setAttribute("aria-busy", "false");
  };
  const startProcessing = () => {
    stopProcessing();
    const started = Date.now();
    form.setAttribute("aria-busy", "true");
    requestActivity.hidden = false;
    requestElapsed.textContent = "0s";
    activityTimer = setInterval(() => {
      requestElapsed.textContent = `${Math.floor((Date.now() - started) / 1000)}s`;
    }, 1000);
  };
  const documentRef = document.getElementById("document-ref");
  const chunkLimit = document.getElementById("chunk-limit");
  const maxParagraphs = document.getElementById("max-paragraphs");
  const maxTokens = document.getElementById("max-tokens");
  let activeRunId = null;
  let thinkingTimeline = null;
  let chatHistory = [];
  let chatGeneration = 0;

  const rememberMessage = (role, content) => {
    if (typeof content !== "string" || !content.trim()) return;
    // Keep the newest context within the API's history limits.
    const chars = Array.from(content.trim()).slice(0, 4000);
    chatHistory.push({ role, content: chars.join("") });
    chatHistory = chatHistory.slice(-20);
    while (chatHistory.reduce((total, item) => total + item.content.length, 0) > 20000) {
      chatHistory.shift();
    }
  };

  const rememberResult = (question, payload) => {
    if (["failed", "budget_exhausted"].includes(payload?.status)) return;
    const answer = payload?.answer || payload?.clarification?.question;
    if (typeof answer !== "string" || !answer.trim()) return;
    rememberMessage("user", question);
    rememberMessage("assistant", answer);
  };

  const scrollToLatest = () => {
    messages.scrollTop = messages.scrollHeight;
  };

  const renderSourceGallery = (payload, container) => {
    const images = (payload?.sources || []).flatMap((source, index) =>
      (Array.isArray(source.images) ? source.images : []).map((image) => ({
        ...image,
        citation: source.citation || `[${index + 1}]`,
        source: source.source || "source",
      })),
    );
    if (images.length === 0) return;
    const sourceGallery = document.createElement("section");
    sourceGallery.className = "source-gallery";
    sourceGallery.setAttribute("aria-label", "Hình trong câu trả lời");
    const heading = document.createElement("div");
    heading.className = "source-gallery-head";
    heading.textContent = "Hình trong câu trả lời";
    const sourceGalleryItems = document.createElement("div");
    sourceGalleryItems.className = "source-images";
    images.forEach((image) => {
      const figure = document.createElement("figure");
      figure.className = "source-image";
      const img = document.createElement("img");
      img.src = image.url;
      img.alt = image.alt || image.caption || "Source image";
      img.loading = "lazy";
      img.decoding = "async";
      const caption = document.createElement("figcaption");
      caption.textContent = `${image.citation} ${image.caption || image.source}`;
      figure.append(img, caption);
      sourceGalleryItems.appendChild(figure);
    });
    sourceGallery.append(heading, sourceGalleryItems);
    container.appendChild(sourceGallery);
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

    // Show cited source images directly with the answer instead of hiding them in source details.
    if (role === "assistant") renderSourceGallery(payload, bubble);

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
        const pages = source.page_start == null
          ? "không có số trang"
          : `trang ${source.page_start}${source.page_end !== source.page_start ? `-${source.page_end}` : ""}`;
        const sourceLabel = document.createElement("div");
        sourceLabel.textContent = `${source.citation || `[${index + 1}]`} ${source.source} · ${pages}`;
        item.appendChild(sourceLabel);
        if (typeof source.url === "string" && /^https?:\/\//i.test(source.url)) {
          const link = document.createElement("a");
          link.href = source.url;
          link.textContent = source.url;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          item.appendChild(link);
        }

        if (Array.isArray(source.image_errors) && source.image_errors.length > 0) {
          const error = document.createElement("div");
          error.className = "source-image-error";
          error.textContent = "Không thể tải hình minh họa của nguồn này.";
          item.appendChild(error);
        }
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

    if (
      payload &&
      payload.clarification &&
      Array.isArray(payload.clarification.options)
    ) {
      const options = document.createElement("div");
      options.className = "clarification-options";
      payload.clarification.options.forEach((option) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "clarification-option";
        button.textContent = option;
        button.addEventListener("click", () => {
          questionInput.value = option;
          questionInput.focus();
          if (activeRunId) resumeClarification(option);
        });
        options.appendChild(button);
      });
      bubble.appendChild(options);
    }

    article.append(speaker, bubble);
    messages.appendChild(article);
    scrollToLatest();
  };

  const statusMessage = (payload) => {
    if (payload.status === "needs_clarification") {
      return payload.clarification?.question || "Bạn muốn nói đến ý nào?";
    }
    if (payload.status === "no_retrieval_context") {
      return "Tôi chưa tìm thấy chunk phù hợp trong phạm vi đã chọn.";
    }
    if (payload.status === "no_relevant_concept_role") {
      return "Đã tìm thấy chunk, nhưng chưa có concept-role đủ phù hợp để trả lời an toàn.";
    }
    return payload.answer || "Không có câu trả lời.";
  };

  const renderThinking = (text) => {
    if (!text) return;
    if (!thinkingTimeline) {
      thinkingTimeline = document.createElement("article");
      thinkingTimeline.className = "message assistant thinking-message";
      const speaker = document.createElement("div");
      speaker.className = "speaker";
      speaker.textContent = "Tiến độ agent";
      const panel = document.createElement("div");
      panel.className = "thinking-panel";
      thinkingTimeline.append(speaker, panel);
      messages.appendChild(thinkingTimeline);
    }
    const panel = thinkingTimeline.querySelector(".thinking-panel");
    const entry = document.createElement("div");
    entry.className = "thinking-entry";
    entry.textContent = text;
    panel.appendChild(entry);
    requestStatus.textContent = text;
    scrollToLatest();
  };

  const numericValue = (element) => Number.parseInt(element.value, 10);

  const requestBody = (question) => {
    const selectedDocument = documentRef.value.trim();
    const body = {
      question: question.trim(),
      history: chatHistory.map((item) => ({ ...item })),
      chunk_limit: numericValue(chunkLimit),
      max_paragraphs: numericValue(maxParagraphs),
      max_tokens: numericValue(maxTokens),
    };
    if (selectedDocument) body.filters = { document_ref: selectedDocument };
    return body;
  };

  const readAgentStream = async (response) => {
    const reader = response.body?.getReader();
    if (!reader) throw new Error("SSE stream is unavailable");
    const decoder = new TextDecoder();
    let buffer = "";
    let result = null;
    const consume = (block) => {
      const data = block.split(/\r?\n/)
        .filter((line) => line.startsWith("data: "))
        .map((line) => line.slice(6))
        .join("\n");
      if (!data) return;
      const event = JSON.parse(data);
      if (event.run_id) activeRunId = event.run_id;
      if (event.type === "thinking") {
        renderThinking(event.text);
      } else if (event.type === "stage_started") {
        requestStatus.textContent = `Đang xử lý: ${event.stage}`;
      } else if (event.type === "tool_completed") {
        requestStatus.textContent = `${event.tool || "Tool"} đã tìm thấy ${event.hit_count ?? event.result_count ?? 0} kết quả`;
      } else if (event.type === "answer_delta") {
        requestStatus.textContent = "Đang viết câu trả lời...";
      } else if (event.type === "run_result") {
        result = event.result;
      }
    };
    while (true) {
      const chunk = await reader.read();
      buffer += decoder.decode(chunk.value || new Uint8Array(), { stream: !chunk.done });
      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() || "";
      blocks.forEach(consume);
      if (chunk.done) break;
    }
    if (buffer.trim()) consume(buffer);
    if (!result) throw new Error("Agent stream ended without a result");
    return result;
  };

  const sendLegacy = async (body) => {
    const response = await fetch("/agent/chat/messages", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    return payload;
  };

  async function resumeClarification(option) {
    if (!activeRunId) return;
    const generation = chatGeneration;
    sendButton.disabled = true;
    requestStatus.textContent = "Đang tiếp tục theo lựa chọn...";
    startProcessing();
    try {
      const response = await fetch(`/agent/chat/runs/${encodeURIComponent(activeRunId)}/resume`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ option }),
      });
      const payload = await readAgentStream(response);
      if (generation !== chatGeneration) return;
      addMessage("assistant", statusMessage(payload), payload);
      rememberResult(option, payload);
      requestStatus.textContent = "Sẵn sàng";
    } catch (error) {
      if (generation !== chatGeneration) return;
      addMessage("assistant", `Không thể tiếp tục: ${error.message}`);
      requestStatus.textContent = "Có lỗi, hãy thử lại";
    } finally {
      stopProcessing();
      sendButton.disabled = false;
    }
  }

  const sendQuestion = async (question) => {
    const normalized = question.trim();
    if (!normalized || sendButton.disabled) return;
    const generation = chatGeneration;

    addMessage("user", normalized);
    questionInput.value = "";
    sendButton.disabled = true;
    thinkingTimeline = null;
    requestStatus.textContent = "Đang tìm chunk và tạo câu trả lời...";
    startProcessing();

    const body = requestBody(normalized);

    try {
      const response = await fetch("/agent/chat/stream", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      let payload;
      if (response.status === 503) payload = await sendLegacy(body);
      else {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        payload = await readAgentStream(response);
      }
      if (generation !== chatGeneration) return;
      addMessage("assistant", statusMessage(payload), payload);
      rememberResult(normalized, payload);
      requestStatus.textContent = "Sẵn sàng";
    } catch (error) {
      if (generation !== chatGeneration) return;
      addMessage("assistant", `Không thể xử lý câu hỏi: ${error.message}`);
      requestStatus.textContent = "Có lỗi, hãy thử lại";
    } finally {
      stopProcessing();
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
    chatGeneration += 1;
    stopProcessing();
    chatHistory = [];
    activeRunId = null;
    thinkingTimeline = null;
    messages.querySelectorAll(".message:not(.welcome-message)").forEach((message) => message.remove());
    requestStatus.textContent = "Sẵn sàng";
    questionInput.focus();
  });
})();
