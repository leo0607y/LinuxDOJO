// `code` だけを <code> にする。HTML 文字列は使わず、すべて React のテキストとして出す。
export default function Inline({ text }) {
  const clean = String(text).replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1');
  return clean.split('`').map((part, i) => (i % 2 ? <code key={i}>{part}</code> : part));
}
