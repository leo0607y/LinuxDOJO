'use client';

import { useEffect, useState } from 'react';

const previewAd = process.env.NEXT_PUBLIC_ADSENSE_PREVIEW === 'true';
const coffeeUrl = process.env.NEXT_PUBLIC_BMC_URL || '';

export default function SupportRail() {
  const [wide, setWide] = useState(false);

  useEffect(() => {
    const query = window.matchMedia('(min-width: 1280px) and (min-height: 800px)');
    const update = () => setWide(query.matches);
    update();
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);

  const coffee = /^https:\/\/(?:www\.)?buymeacoffee\.com\/[A-Za-z0-9_-]+\/?$/.test(coffeeUrl);
  if (!wide || (!previewAd && !coffee)) return null;

  return (
    <aside className="support-rail" aria-label="広告とサイトの支援">
      {coffee ? <a className="coffee-link" href={coffeeUrl} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M5 9h12v6a4 4 0 0 1-4 4H9a4 4 0 0 1-4-4V9Z" />
          <path d="M17 10h1.5a2.5 2.5 0 0 1 0 5H17M4 21h15M8 5c1-1 1-2 0-3m5 3c1-1 1-2 0-3" />
        </svg>
        <span>作者にCoffeeを送る</span><span aria-hidden="true">↗</span>
      </a> : null}
      {previewAd ? <div className="ad-unit">
        <span className="ad-label">広告</span>
        <div className="ad-placeholder">AdSense枠のプレビュー<br />広告通信は発生しません</div>
      </div> : null}
    </aside>
  );
}
