import Link from 'next/link';
import styles from './course.module.css';

export default function CourseLayout({ children }) {
  return (
    <div className={styles.shell}>
      <a className={styles.skip} href="#main">本文へ移動</a>
      <header className={styles.header}>
        <nav className={styles.nav} aria-label="コース内の移動">
          <strong>Linux常用コース</strong>
          <Link href="/course/">トピック一覧</Link>
          <Link href="/course/coverage/">網羅性と未達</Link>
          <Link href="/">学習画面へ</Link>
        </nav>
      </header>
      <main id="main" className={styles.main}>{children}</main>
    </div>
  );
}
