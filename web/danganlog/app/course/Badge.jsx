import styles from './course.module.css';

const CLASS = { verified: styles.ok, unit: styles.warn, new: styles.warn, real: styles.ok, static: styles.ng };

// 検証状況は色だけでなく文言で示す。
export default function Badge({ kind, children }) {
  return <span className={`${styles.badge} ${CLASS[kind] || styles.warn}`}>{children}</span>;
}
