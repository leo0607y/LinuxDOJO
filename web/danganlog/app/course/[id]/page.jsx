import Link from 'next/link';
import { notFound } from 'next/navigation';
import { getTopic, topicIds } from '../../../lib/course-data.js';
import Inline from '../Inline.jsx';
import Badge from '../Badge.jsx';
import styles from '../course.module.css';

export const dynamicParams = false;
export function generateStaticParams() {
  return topicIds().map((id) => ({ id }));
}

export async function generateMetadata({ params }) {
  const { id } = await params;
  const t = getTopic(id);
  if (!t) return {};
  return { title: `${t.title} | Linux常用コース`, description: t.goal.replace(/^到達確認[:：]/, '').slice(0, 120) };
}

function Block({ b }) {
  if (b.t === 'pre') return <pre className={styles.pre}><code>{b.x}</code></pre>;
  if (b.t === 'ul') return <ul className={styles.list}>{b.x.map((x, i) => <li key={i}><Inline text={x} /></li>)}</ul>;
  return <p><Inline text={b.x} /></p>;
}

export default async function TopicPage({ params }) {
  const { id } = await params;
  const t = getTopic(id);
  if (!t) notFound();
  return (
    <article>
      <p className={styles.crumbs}><Link href="/course/">トピック一覧</Link> / {t.category}{t.level === 'extension' ? ' (拡張)' : ''}</p>
      <h1>{t.title}</h1>
      <p className={styles.goal}><Inline text={t.goal} /></p>

      <h2>使うコマンド</h2>
      <p className={styles.cmds}>{t.commands.join(' ')}</p>

      <h2>実習と検証状況</h2>
      <h3>ネイティブ実習 (本物のツール)</h3>
      {t.native.length ? (
        <ul className={styles.list}>
          {t.native.map((l) => (
            <li key={l.id}><code>python3 -m engine.toolbox start {l.id}</code> {l.title}<br /><Badge kind={l.kind}>{l.status}</Badge></li>
          ))}
        </ul>
      ) : <p>このトピック専用のネイティブ実習はありません。</p>}
      <h3>VM実習 (使い捨てVMが必要)</h3>
      {t.vm.length ? (
        <ul className={styles.list}>
          {t.vm.map((v) => (
            <li key={v.id}><code>sudo dojo-vm-lab {v.id} setup</code> {v.title}<br /><Badge kind={v.kind}>{v.status}</Badge></li>
          ))}
        </ul>
      ) : <p>このトピックに対応づけたVM実習はありません。</p>}
      <p className={styles.lead}>ブラウザー版は模擬ターミナルです。上の実習は教材をダウンロードして自分の環境で行います。</p>

      <h2>練習ミッション ({t.missions.length}件)</h2>
      <ul className={styles.meta}>{t.missions.map((m) => <li key={m} className={styles.tag}>{m}</li>)}</ul>

      <h2>{t.heading}</h2>
      {t.blocks.map((b, i) => <Block key={i} b={b} />)}
      <p className={styles.footer}>出典: docs/LINUX_DAILY_USE.md#{t.anchor}</p>
    </article>
  );
}
