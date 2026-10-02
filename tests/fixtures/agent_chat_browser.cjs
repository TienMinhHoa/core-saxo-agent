"use strict";

const fs = require("node:fs");
const vm = require("node:vm");

const scenario = JSON.parse(fs.readFileSync(0, "utf8"));
const elements = new Map();

class Element {
  constructor(tag = "div") {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.listeners = new Map();
    this.dataset = {};
    this.className = "";
    this.value = "";
    this.disabled = false;
    this.hidden = false;
    this.attributes = {};
    this.parentNode = null;
    this._text = "";
    this.classList = {
      add: (...names) => { this.className += " " + names.join(" "); },
      remove: (...names) => {
        this.className = this.className.split(" ").filter((name) => !names.includes(name)).join(" ");
      },
      contains: (name) => this.className.split(" ").includes(name),
      toggle: (name, enabled) => {
        if (enabled) this.classList.add(name);
        else this.classList.remove(name);
      },
    };
  }

  get textContent() { return this._text + this.children.map((child) => child.textContent).join(" "); }
  set textContent(value) { this._text = String(value); this.children = []; }
  set innerHTML(value) {
    if (value) throw new Error("Browser tests prohibit rendering untrusted HTML");
    this.children = [];
    this._text = "";
  }
  append(...children) {
    children.forEach((child) => {
      if (typeof child === "string") {
        const text = new Element("text");
        text.textContent = child;
        child = text;
      }
      child.parentNode = this;
      this.children.push(child);
    });
  }
  appendChild(child) { this.append(child); return child; }
  replaceChildren(...children) { this.children = []; this._text = ""; this.append(...children); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name]; }
  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }
  async dispatch(type) {
    for (const listener of this.listeners.get(type) || []) {
      await listener({ preventDefault() {}, target: this, currentTarget: this });
    }
  }
  focus() {}
  scrollIntoView() {}
  requestSubmit() { return this.dispatch("submit"); }
  remove() {
    if (this.parentNode) {
      this.parentNode.children = this.parentNode.children.filter((child) => child !== this);
    }
  }
  querySelectorAll(selector) {
    const matches = [];
    const visit = (node) => {
      node.children.forEach((child) => {
        if (selector === ".message:not(.welcome-message)" && child.classList.contains("message") && !child.classList.contains("welcome-message")) {
          matches.push(child);
        } else if (selector.startsWith(".") && child.className.split(" ").includes(selector.slice(1))) {
          matches.push(child);
        } else if (selector.toUpperCase() === child.tagName) {
          matches.push(child);
        }
        visit(child);
      });
    };
    visit(this);
    return matches;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

const element = (id) => {
  if (!elements.has(id)) elements.set(id, new Element());
  return elements.get(id);
};
const document = {
  getElementById: element,
  createElement: (tag) => new Element(tag),
  createTextNode: (text) => { const node = new Element("text"); node.textContent = text; return node; },
  querySelector: (selector) => selector.startsWith("#") ? element(selector.slice(1)) : null,
  querySelectorAll: (selector) => {
    if (selector === "[data-question]") return [];
    return Array.from(elements.values()).flatMap((node) => node.querySelectorAll(selector));
  },
};

element("question").value = scenario.initialQuestion || "Which triad?";
element("document-ref").value = "music-book";
element("chunk-limit").value = "7";
element("max-paragraphs").value = "12";
element("max-tokens").value = "2400";

const calls = [];
const activeTimers = new Set();
let streamTurn = 0;
const fetch = async (url, options = {}) => {
  calls.push({
    url, body: options.body ? JSON.parse(options.body) : null,
    processing: element("chat-form").getAttribute("aria-busy"),
    activityVisible: !element("request-activity").hidden,
    activeTimerCount: activeTimers.size,
  });
  if (url.endsWith("/resume")) return streamingResponse(scenario.resumeFrames);
  if (url === "/agent/chat/stream") {
    const turn = streamTurn++;
    const status = scenario.streamStatuses?.[turn] || scenario.streamStatus;
    if (status && status !== 200) {
      return new Response(JSON.stringify({ detail: "stream unavailable" }), {
        status, headers: { "Content-Type": "application/json" },
      });
    }
    return streamingResponse(scenario.framesByTurn?.[turn] || scenario.frames);
  }
  if (url === "/agent/chat/messages") {
    return new Response(JSON.stringify(scenario.jsonResult), {
      status: 200, headers: { "Content-Type": "application/json" },
    });
  }
  throw new Error("Unexpected fetch: " + url);
};

function streamingResponse(frames) {
  if (!frames) throw new Error("Missing scripted stream");
  const separator = scenario.crlf ? "\r\n" : "\n";
  const body = frames.map((frame, index) => [
    `id: ${index + 1}`, `event: ${frame.type}`, `data: ${JSON.stringify(frame)}`, "", "",
  ].join(separator)).join("");
  const bytes = new TextEncoder().encode(body);
  const stream = new ReadableStream({
    start(controller) {
      const width = scenario.chunkSize || 17;
      for (let offset = 0; offset < bytes.length; offset += width) {
        controller.enqueue(bytes.slice(offset, offset + width));
      }
      controller.close();
    },
  });
  return new Response(stream, {
    headers: { "Content-Type": "text/event-stream", "X-Agent-Run-ID": "run-browser" },
  });
}

const context = vm.createContext({
  document, fetch, TextDecoder, TextEncoder, AbortController, URL,
  console, setTimeout, clearTimeout, requestAnimationFrame: (callback) => callback(),
  setInterval: (callback, milliseconds) => {
    const timer = setInterval(callback, milliseconds);
    activeTimers.add(timer);
    return timer;
  },
  clearInterval: (timer) => { activeTimers.delete(timer); clearInterval(timer); },
});
context.window = context;
vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), context);

const settle = async () => {
  for (let index = 0; index < 5; index++) await new Promise((resolve) => setTimeout(resolve, 0));
};

(async () => {
  await element("chat-form").dispatch("submit");
  await settle();
  if (scenario.chooseOption) {
    const buttons = element("messages").querySelectorAll("button");
    const choice = buttons.find((button) => button.textContent === scenario.chooseOption);
    if (!choice) throw new Error("Clarification option is missing");
    await choice.dispatch("click");
    await settle();
  }
  for (const question of scenario.followUps || []) {
    if (scenario.clearBeforeFollowUp) await element("clear-chat").dispatch("click");
    element("question").value = question;
    await element("chat-form").dispatch("submit");
    await settle();
  }
  process.stdout.write(JSON.stringify({
    calls,
    text: Array.from(elements.values()).map((node) => node.textContent).join(" "),
    buttonDisabled: element("send-button").disabled,
    question: element("question").value,
    imageCount: element("messages").querySelectorAll("img").length,
    processing: element("chat-form").getAttribute("aria-busy"),
    activityHidden: element("request-activity").hidden,
    activeTimerCount: activeTimers.size,
    links: element("messages").querySelectorAll("a").map((link) => ({
      text: link.textContent, href: link.href || link.getAttribute("href"),
    })),
  }));
})().catch((error) => { console.error(error); process.exitCode = 1; });
