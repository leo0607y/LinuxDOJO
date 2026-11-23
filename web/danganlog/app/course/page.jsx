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
      <div className={styles.intro}>
        <div>
          <h1>Linux常用コース</h1>
          <p className={styles.lead}>
            日常のファイル操作から小規模サービスの運用まで、{topics.length}のトピックを収録。
            各トピックでコマンド、練習ミッション、実機実習と検証状況を確認できます。
          </p>
          <p className={styles.links}>
            <Link href="/course/real-linux/">模擬ターミナルから実際のLinux環境へ進む</Link>
            <Link href="/course/coverage/">資格試験の目標との対応と未達</Link>
          </p>
        </div>
        <CourseSearch />
      </div>
      {groups.map(([level, label]) => {
        const items = topics.filter((t) => t.level === level);
        return (
          <section key={level} className={styles.group} aria-labelledby={`g-${level}`}>
            <h2 id={`g-${level}`}>{label}<small>{items.length} トピック</small></h2>
            <div className={styles.columns} aria-hidden="true">
              <span>分野</span><span>トピック・コマンド</span>
              <div className={styles.counts}><span>ミッション</span><span>ネイティブ実習</span><span>VM実習</span></div>
            </div>
            <ul className={styles.directory}>
              {items.map((t) => (
                <li key={t.id} className={styles.row}>
                  <span className={styles.category}>{t.category}</span>
                  <div>
                    <h3><Link href={`/course/${t.id}/`}>{t.title}</Link></h3>
                    <p className={styles.cmds}>{t.commands.slice(0, 8).join(' ')}{t.commands.length > 8 ? ' …' : ''}</p>
                    {t.native.length + t.vm.length === 0 ? <Badge kind="static">実機実習なし (読解・模擬のみ)</Badge> : null}
                  </div>
                  <dl className={styles.counts}>
                    <div><dt>ミッション</dt><dd>{t.missions.length}</dd></div>
                    <div><dt>ネイティブ実習</dt><dd>{t.native.length}</dd></div>
                    <div><dt>VM実習</dt><dd>{t.vm.length}</dd></div>
                  </dl>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </>
  );
}
