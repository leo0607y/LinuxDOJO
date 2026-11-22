// クライアントでも node のテストでも使える検索。外部サービスなし。日本語は部分一致 (空白区切りは AND)。
export function normalize(text) {
  return String(text || '').normalize('NFKC').toLowerCase();
}

export function searchEntries(entries, query) {
  const terms = normalize(query).split(/[\s　]+/).filter(Boolean);
  if (!terms.length) return [];
  const results = [];
  for (const e of entries) {
    const title = normalize(e.title);
    const commands = e.commands.map(normalize);
    const keywords = e.keywords.map(normalize);
    const body = normalize(e.text);
    let score = 0;
    let ok = true;
    for (const term of terms) {
      let s = 0;
      if (commands.includes(term)) s += 8;
      else if (commands.some((c) => c.includes(term))) s += 3;
      if (keywords.includes(term)) s += 6;
      else if (keywords.some((k) => k.includes(term))) s += 3;
      if (title.includes(term)) s += 5;
      if (body.includes(term)) s += 1;
      if (!s) { ok = false; break; }
      score += s;
    }
    if (ok) results.push({ entry: e, score });
  }
  results.sort((a, b) => b.score - a.score || a.entry.id.localeCompare(b.entry.id));
  return results.map((r) => r.entry);
}
