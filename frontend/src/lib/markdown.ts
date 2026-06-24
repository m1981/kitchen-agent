import { marked, Renderer } from "marked";
import { markedHighlight } from "marked-highlight";
import hljs from "highlight.js";

const renderer = new Renderer();

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function isSafeUrl(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return false;

  const protocolMatch = trimmed.match(/^([a-z][a-z0-9+.-]*):/i);
  if (!protocolMatch) return true;

  return ["http:", "https:", "mailto:", "tel:"].includes(protocolMatch[0].toLowerCase());
}

function optionalTitleAttr(title: string | null | undefined): string {
  return title ? ` title="${escapeHtml(title)}"` : "";
}

renderer.html = ({ text }) => escapeHtml(text);

renderer.link = function ({ href, title, tokens }) {
  const text = this.parser.parseInline(tokens);
  if (!isSafeUrl(href)) return text;

  return `<a href="${escapeHtml(href)}"${optionalTitleAttr(title)} rel="noreferrer">${text}</a>`;
};

renderer.image = ({ href, title, text }) => {
  if (!isSafeUrl(href)) return escapeHtml(text);

  return `<img src="${escapeHtml(href)}" alt="${escapeHtml(text)}"${optionalTitleAttr(title)} />`;
};

marked.use(
  markedHighlight({
    emptyLangClass: "hljs",
    langPrefix: "hljs language-",
    highlight(code, lang) {
      const language = lang && hljs.getLanguage(lang) ? lang : "plaintext";
      return hljs.highlight(code, { language }).value;
    },
  }),
);

marked.use({
  gfm: true,
  breaks: true,
  renderer,
});

export function parseMarkdown(src: string): string {
  return marked.parse(src) as string;
}
