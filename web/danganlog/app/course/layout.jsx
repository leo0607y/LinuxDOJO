import Masthead from '../../components/Masthead.jsx';
import styles from './course.module.css';

export default function CourseLayout({ children }) {
  return (
    <div className={styles.shell}>
      <a className={styles.skip} href="#main">本文へ移動</a>
      <Masthead />
      <main id="main" className={styles.main}>{children}</main>
    </div>
  );
}
