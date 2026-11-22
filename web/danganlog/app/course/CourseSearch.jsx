'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { searchEntries } from '../../lib/course-search.js';
import styles from './course.module.css';

export default function CourseSearch() {
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');

  useEffect(() => {
    let alive = true;
    fetch('/course-search.json')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => { if (alive) setEntries(d.entries); })
      .catch(() => { if (alive) setError('検索索引を読み込めませんでした。下の一覧から選べます。'); });
    return () => { alive = false; };
  }, []);

  const results = entries ? searchEntries(entries, query) : [];
  const asked = query.trim().length > 0;
  return (
    <section aria-labelledby="search-title">
      <h2 id="search-title">目的から探す</h2>
      <div className={styles.search} role="search">
        <label htmlFor="course-q">やりたいこと、困っていること、コマンド名 (例: 権限 読めない / 圧縮 / curl)</label>
        <input id="course-q" type="search" value={query} autoComplete="off"
          onChange={(e) => setQuery(e.target.value)} disabled={!entries && !error} />
      </div>
      {error ? <p role="alert">{error}</p> : null}
      <div aria-live="polite" role="status">
        {asked && entries ? <p>{results.length ? `${results.length} 件見つかりました。` : '該当するトピックがありません。別の言い方か、コマンド名で試してください。'}</p> : null}
      </div>
      {results.length ? (
        <ul className={styles.results}>
          {results.map((e) => (
            <li key={e.id}>
              <Link href={`/course/${e.id}/`}>{e.title}</Link>
              <span className={styles.tag}> {e.category}{e.level === 'extension' ? ' / 拡張' : ''}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
