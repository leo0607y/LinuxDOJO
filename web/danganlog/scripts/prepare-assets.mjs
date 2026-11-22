// ビルド前に、サイトが配信する生成物を public/ に用意する。
//  - public/pyodide/      : npm の pyodide から実行に必要な5ファイルをコピー (自前配信)
//  - public/python-source.json : tools/build_web.py が教材 Python ソースをまとめる
import { copyFileSync, mkdirSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { buildCourseData } from './build-course.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const source = join(root, 'node_modules', 'pyodide');
const target = join(root, 'public', 'pyodide');
if (!existsSync(source)) { console.error('node_modules/pyodide がありません。npm ci を先に実行してください。'); process.exit(1); }
mkdirSync(target, { recursive: true });
for (const name of ['pyodide.js', 'pyodide.asm.js', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json']) {
  copyFileSync(join(source, name), join(target, name));
}
const builder = join(root, '..', '..', 'tools', 'build_web.py');
for (const python of ['python3', 'python']) {
  const result = spawnSync(python, [builder, '-o', join(root, 'public', 'python-source.json')], { stdio: 'inherit' });
  if (result.status === 0) {
    buildCourseData();
    process.exit(0);
  }
}
console.error('python-source.json を作れませんでした。Python 3.9 以上が必要です。');
process.exit(1);
