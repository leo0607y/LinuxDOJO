import Link from 'next/link';
import { loadCourse } from '../../lib/course-data.js';
import CourseSearch from './CourseSearch.jsx';
import Badge from './Badge.jsx';
import styles from './course.module.css';

export const metadata = {
  title: 'Linux常用コース: 32トピック | DANGAN LOG',
  description: 'Linuxを日常的に使うための32トピックを、コマンド、ミッション、実機実習、検証状況つきで一覧します。'
};

export default function CourseIndex() {
  const { topics } = loadCourse();
  const groups = [['core', 'コア'], ['extension', '拡張']];
  return (
    <>
      <h1>Linux常用コース: {topics.length}トピック</h1>
      <p className={styles.lead}>
        日常のファイル操作から開発、小規模サービス運用までの到達目標です。各トピックに、使うコマンド、練習ミッション、
        本物のツールやVMで行う実習、その検証状況を書いています。<Link href="/course/coverage/">資格試験の目標との対応と未達</Link>も公開しています。
      </p>
      <CourseSearch />
      {groups.map(([level, label]) => {
        const items = topics.filter((t) => t.level === level);
        return (
          <section key={level} aria-labelledby={`g-${level}`}>
            <h2 id={`g-${level}`}>{label} ({items.length})</h2>
            <ul className={styles.grid}>
              {items.map((t) => (
                <li key={t.id} className={styles.card}>
                  <h3><Link href={`/course/${t.id}/`}>{t.title}</Link></h3>
                  <ul className={styles.meta}>
                    <li className={styles.tag}>{t.category}</li>
                    <li className={styles.tag}>ミッション {t.missions.length}件</li>
                    <li className={styles.tag}>ネイティブ実習 {t.native.length}件</li>
                    <li className={styles.tag}>VM実習 {t.vm.length}件</li>
                  </ul>
                  <p className={styles.cmds}>{t.commands.slice(0, 8).join(' ')}{t.commands.length > 8 ? ' ...' : ''}</p>
                  {t.native.length + t.vm.length === 0 ? <Badge kind="static">実機実習なし (読解・模擬のみ)</Badge> : null}
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </>
  );
}
