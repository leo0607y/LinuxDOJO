import { loadCourse } from '../../../lib/course-data.js';
import Inline from '../Inline.jsx';
import styles from '../course.module.css';

export const metadata = {
  title: '網羅性と未達 | Linux常用コース',
  description: 'LPIC・LFCS・RHCSAの公開試験範囲に対し、実操作で検証済みの目標、一部のみ、未対応の件数を示します。'
};

export default function CoveragePage() {
  const { coverage, statusLegend } = loadCourse();
  const { exams, total, note } = coverage;
  const pct = (n, d) => (d ? Math.round((n / d) * 100) : 0);
  return (
    <>
      <h1>網羅性と未達</h1>
      <p className={styles.lead}>
        公開されている試験範囲の各行について、このコースが実操作で検証しているかを厳しめに判定した結果です。資格対策教材ではなく、修了の証明でもありません。
        合計 {total.rows} 行のうち、実操作で検証済みは {total.covered} 行 ({pct(total.covered, total.rows)}%)、実装済み・実VM未検証は {total.unverified} 行、一部のみは {total.partial} 行、未対応は {total.missing} 行です。
      </p>
      <div className={styles.tablewrap}>
        <table className={styles.table}>
          <caption className={styles.crumbs}>試験別の判定件数 (出典: docs/objectives_matrix.md)</caption>
          <thead><tr><th scope="col">試験</th><th scope="col" className={styles.num}>行数</th><th scope="col" className={styles.num}>COVERED-REAL (検証済み)</th><th scope="col" className={styles.num}>IMPLEMENTED-UNVERIFIED (実装済み・未検証)</th><th scope="col" className={styles.num}>PARTIAL (一部のみ)</th><th scope="col" className={styles.num}>MISSING (未対応)</th></tr></thead>
          <tbody>
            {exams.map((e) => (
              <tr key={e.exam}><th scope="row">{e.exam}</th><td className={styles.num}>{e.rows}</td><td className={styles.num}>{e.covered}</td><td className={styles.num}>{e.unverified}</td><td className={styles.num}>{e.partial}</td><td className={styles.num}>{e.missing}</td></tr>
            ))}
            <tr><th scope="row">合計 (試験間の重複を含む)</th><td className={styles.num}>{total.rows}</td><td className={styles.num}>{total.covered}</td><td className={styles.num}>{total.unverified}</td><td className={styles.num}>{total.partial}</td><td className={styles.num}>{total.missing}</td></tr>
          </tbody>
        </table>
      </div>
      <p><Inline text={note} /></p>
      <h2>読み方と限界</h2>
      <ul className={styles.list}>
        <li>COVERED は、ネイティブ実習、実VMで検証済みのVM実習、または作業フォルダで実ツールを動かして成果物を検査するミッションが、その目標の操作を実際に行わせる場合だけです。</li>
        <li>IMPLEMENTED-UNVERIFIED は、実状態を判定する実習が実装済みで、実VMでの検証がまだ済んでいないものです。</li>
        <li>PARTIAL は、出力や設定例を読むだけの課題、目標の一部だけを行う場合を含みます。</li>
        <li>RHEL系固有の目標は、実習がなければ MISSING です。RHCSA の一覧は取得元の数が不整合で、信頼度が最も低い点に注意してください。</li>
        <li>試験間で重複する行が多いため、合計を独立した目標数として扱わないでください。</li>
      </ul>
      <h2>実習の検証状況の区分</h2>
      <ul className={styles.list}>
        {statusLegend.native.concat(statusLegend.vm).map((s) => <li key={s}>{s}</li>)}
      </ul>
      <p className={styles.footer}>VM実習は、この開発環境ではすべてを実VMで実行できていません。表示の区分を実行済みの証明として読まないでください。</p>
    </>
  );
}
