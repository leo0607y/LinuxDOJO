// サーバー側 (ビルド時) だけで使う。public/course-data.json を読み、無ければ Python で生成する。
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { buildCourseData } from '../scripts/build-course.mjs';

const FILE = join(process.cwd(), 'public', 'course-data.json');
let cache;

export function loadCourse() {
  if (!cache) {
    if (!existsSync(FILE)) buildCourseData();
    cache = JSON.parse(readFileSync(FILE, 'utf8'));
  }
  return cache;
}

export function topicIds() {
  return loadCourse().topics.map((t) => t.id);
}

export function getTopic(id) {
  return loadCourse().topics.find((t) => t.id === id) || null;
}
