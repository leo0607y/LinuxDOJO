// /course/ 用データ (public/course-data.json, course-search.json) を tools/build_course_data.py で生成する。
// 単体実行: node scripts/build-course.mjs。lib/course-data.js も、ファイルが無いとき自動で呼ぶ。
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

export function buildCourseData() {
  const root = join(dirname(fileURLToPath(import.meta.url)), '..');
  const script = join(root, '..', '..', 'tools', 'build_course_data.py');
  for (const python of ['python3', 'python']) {
    const result = spawnSync(python, [script, '-o', join(root, 'public', 'course-data.json')], { stdio: 'inherit' });
    if (result.status === 0) return;
  }
  throw new Error('course-data.json を作れませんでした。Python 3.9 以上とリポジトリ全体 (curriculum/, docs/) が必要です。');
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) buildCourseData();
