'use client';
import { useEffect } from 'react';
import { applyTheme, readPrefs } from './preferences.js';
import { usePathname } from 'next/navigation';

export default function Masthead() {
  const path = usePathname();
  useEffect(() => { applyTheme(readPrefs().theme); }, []);
  const links = [['/', '学習画面'], ['/course/', '常用コース'], ['/course/real-linux/', '環境の準備'], ['/course/coverage/', '網羅性と未達']];
  return (
    <header className="masthead">
      <div className="masthead-inner">
        <a className="wordmark" href="/" aria-label="DANGAN LOG 学習画面">
          <span className="shell-mark" aria-hidden="true">&gt;_</span>
          <span className="masthead-name">DANGAN LOG</span>
        </a>
        <nav className="masthead-nav" aria-label="サイト内の移動">
          {links.map(([href, title]) => {
            const current = path === href || path + '/' === href;
            return <a key={href} href={href} aria-current={current ? 'page' : undefined}>{title}</a>;
          })}
        </nav>
      </div>
    </header>
  );
}
